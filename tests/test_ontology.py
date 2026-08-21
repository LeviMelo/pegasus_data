"""The ontology, and the binding that attaches observations to it.

The property under test throughout is the separation the module exists to keep:
**what a dataset IS comes from the declaration; how it has been seen comes from
the crawl.** SIH.RD is AIH Reduzida whether or not any file was ever downloaded,
and it stays AIH Reduzida if DATASUS renames the directory tomorrow.

The binding half has to survive a ``series`` column that was derived from
filenames and is therefore polluted: of 1,505 observed ``(system, series)``
pairs in the real catalog, only 181 are clean codes. The rest are archive
members that leaked in, whole filenames, placeholder filenames, and per-year
dataset names. Every case below is one of those, taken from the tree rather
than invented.
"""

from __future__ import annotations

import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.ontology import Ontology, canonical_series
from pegasus_data.retrieve import _families


@pytest.fixture(scope="module")
def onto() -> Ontology:
    return Ontology.load()


class TestCanonicalSeries:
    """Collapsing a filename-derived series onto its code.

    This function knows nothing about the ontology — it only undoes filename
    parsing. It returns the rule that fired so a binding can be audited instead
    of trusted.
    """

    @pytest.mark.parametrize(
        "observed, code, rule",
        [
            ("RD", "RD", "clean"),
            # An archive member leaked into the series name.
            ("RD:RDAC1701", "RD", "colon-member"),
            ("AC:COAC0201:COAC0201", "AC", "colon-member"),
            # A whole filename: PA + SP + 2509 + part A.
            ("PASP2509A", "PA", "filename"),
            ("BIMG2305_1", "BI", "filename"),
            # A placeholder filename DATASUS left in the tree.
            ("EFUFAAMM", "EF", "template"),
            # A per-year dataset name.
            ("SISCAN_CITO_COLO_2013", "SISCAN_CITO_COLO", "year-suffix"),
        ],
    )
    def test_collapses_to_code(self, observed: str, code: str, rule: str) -> None:
        assert canonical_series(observed) == (code, rule)

    def test_leaves_a_real_code_alone(self) -> None:
        """A two-letter code that happens to look filename-ish must survive."""
        assert canonical_series("DO") == ("DO", "clean")
        assert canonical_series("DENG") == ("DENG", "clean")

    def test_rejects_a_non_uf_segment(self) -> None:
        """The filename rule only fires when the middle two letters are a real UF.

        Without this it would happily shred codes that merely resemble filenames.
        """
        code, rule = canonical_series("ABZZ1234")
        assert rule == "clean" and code == "ABZZ1234"


class TestDeclaration:
    """Identity comes from the file, not from the catalog."""

    def test_declares_systems_and_datasets(self, onto: Ontology) -> None:
        assert "SIH" in onto.systems
        assert onto.systems["SIH"].official_name.startswith("Sistema de Informações Hospitalares")
        assert onto.datasets["SIH.RD"].official_name == "AIH Reduzida"

    def test_institutional_name_is_not_the_crawled_name(self, onto: Ontology) -> None:
        """The tree says SIHSUS; the institution says SIH. Both must resolve."""
        assert onto.systems["SIH"].crawled_as == ("SIHSUS",)
        assert onto.resolve("SIH")[1].code == "SIH"
        assert onto.resolve("SIHSUS")[1].code == "SIH"

    def test_sinan_agravos_are_datasets(self, onto: Ontology) -> None:
        """Each agravo is its own dataset, not a slice of one SINAN dataset."""
        assert onto.resolve("SINAN.DENG")[1].code == "SINAN.DENG"
        assert onto.resolve("SINAN.LEPT")[1].system == "SINAN"

    def test_datasets_of_a_system(self, onto: Ontology) -> None:
        codes = {d.code for d in onto.datasets_of("SIH")}
        assert {"SIH.RD", "SIH.RJ", "SIH.SP", "SIH.ER"} <= codes


class TestResolution:
    @pytest.mark.parametrize(
        "target, expected",
        [
            ("SIH.RD", "SIH.RD"),
            ("SIHSUS.RD", "SIH.RD"),
            ("SIH/RD", "SIH.RD"),
            ("sih.rd", "SIH.RD"),
            ("RD", "SIH.RD"),          # unambiguous bare code
            ("SIA.AQ", "SIA.AQ"),
        ],
    )
    def test_resolves_spellings(self, onto: Ontology, target: str, expected: str) -> None:
        found = onto.resolve(target)
        assert found is not None and found[1].code == expected

    def test_unknown_resolves_to_none(self, onto: Ontology) -> None:
        assert onto.resolve("not-a-dataset") is None
        assert onto.resolve("") is None


class TestBinding:
    """Attaching an observed pair to a declared node."""

    def test_declared_alias_wins_over_pattern(self, onto: Ontology) -> None:
        """The same dataset published in two trees binds to one node.

        SIA's APAC datasets appear under SIASUS/ and again under Dados_Abertos/
        as APAC_AB. One dataset, two locations — the case that proves the
        ontology is not just a mirror of the directory layout.
        """
        a = onto.bind("SIASUS", "AB")
        b = onto.bind("DADOS_ABERTOS", "APAC_AB")
        assert a.dataset == b.dataset == "SIA.AB"
        assert a.rule == "declared"

    def test_binds_a_polluted_series(self, onto: Ontology) -> None:
        bound = onto.bind("SIASUS", "PASP2509A")
        assert bound.dataset == "SIA.PA"
        assert bound.rule == "filename"
        assert bound.canonical == "PA"

    def test_unbindable_says_so(self, onto: Ontology) -> None:
        """An unrecognised series must not be silently attached to something."""
        bound = onto.bind("SIASUS", "ZZZZ")
        assert not bound.bound and bound.dataset is None

    def test_ambiguous_bare_code_is_refused(self) -> None:
        """A code claimed by two systems binds to neither.

        A wrong bind is worse than an unbound one: it would file rows under a
        dataset they do not belong to, and nothing downstream would notice.
        """
        from pegasus_data.ontology import DatasetNode

        onto = Ontology(
            systems={},
            datasets={
                "A.XX": DatasetNode(code="A.XX", system="A", observed_as=("XX",)),
                "B.XX": DatasetNode(code="B.XX", system="B", observed_as=("XX",)),
            },
        )
        assert onto.bind("UNKNOWN", "XX").dataset is None


class TestFamilyResolution:
    """The bug this layer was built to fix.

    ``_families`` used to match ``series`` exactly. Because ``series`` is derived
    from filenames, that found 9 of SIA-PA's 736 families and **none** of
    SIA-AC's 7 — ``fetch("SIA-AC")`` returned nothing at all while reporting
    success. Silent under-return is the exact failure the fetch path documents
    itself as preventing.
    """

    def test_collects_every_spelling_of_one_dataset(self, catalog: Catalog) -> None:
        sig = "0" * 64
        catalog.execute(
            "INSERT INTO families (family_id, system, series, schema_signature, field_count) "
            "VALUES (?,?,?,?,?)",
            ("f1", "SIASUS", "PA", sig, 10),
        )
        catalog.execute(
            "INSERT INTO families (family_id, system, series, schema_signature, field_count) "
            "VALUES (?,?,?,?,?)",
            ("f2", "SIASUS", "PASP2509A", sig, 10),
        )
        catalog.execute(
            "INSERT INTO families (family_id, system, series, schema_signature, field_count) "
            "VALUES (?,?,?,?,?)",
            ("f3", "SIASUS", "AQ", sig, 10),
        )

        found = {f["family_id"] for f in _families(catalog, "SIASUS", "PA")}
        assert found == {"f1", "f2"}, "the filename-spelled family must come along"

    def test_a_bare_system_takes_everything(self, catalog: Catalog) -> None:
        sig = "0" * 64
        for fid, series in (("g1", "RD"), ("g2", "RJ")):
            catalog.execute(
                "INSERT INTO families (family_id, system, series, schema_signature, field_count) "
                "VALUES (?,?,?,?,?)",
                (fid, "SIHSUS", series, sig, 10),
            )
        assert len(_families(catalog, "SIHSUS", None)) == 2
