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


class TestSchemaGenerations:
    """Families collapsed into generations, with the delta between them.

    Two failures the raw family list produces, both fixed here.

    *Duplicate generations.* One schema signature is reached through several
    spellings of the series, so listing families showed SIH.RD's 113-column
    generation twice — reading as though the schema changed and changed back.

    *Silence about what changed.* "113 columns, 2014-2025" tells an analyst
    nothing. "+6, -1 against the previous generation" is what decides whether
    years either side of the boundary can be pooled.
    """

    def _seed(self, catalog: Catalog) -> None:
        for sig, fields in (
            ("a" * 64, ["ID", "SEXO"]),
            ("b" * 64, ["ID", "SEXO", "IDADE"]),
        ):
            for order, name in enumerate(fields):
                catalog.execute(
                    "INSERT INTO schema_presence (schema_signature, field_name, field_order) "
                    "VALUES (?,?,?)",
                    (sig, name, order),
                )

    def test_groups_by_signature_not_family(self, catalog: Catalog) -> None:
        from pegasus_data._info import _generations

        self._seed(catalog)
        families = [
            {"schema_signature": "a" * 64, "field_count": 2, "files": 3,
             "time_min": 2001, "time_max": 2002, "schema_source": "profile"},
            {"schema_signature": "a" * 64, "field_count": 2, "files": 4,
             "time_min": 2003, "time_max": 2004, "schema_source": "profile"},
        ]
        gens = _generations(catalog, families)
        assert len(gens) == 1, "one signature is one generation"
        assert gens[0]["files"] == 7, "file counts merge"
        assert gens[0]["span"] == "2001–2004", "the span covers both families"
        assert gens[0]["families"] == 2

    def test_reports_added_and_dropped(self, catalog: Catalog) -> None:
        from pegasus_data._info import _generations

        self._seed(catalog)
        families = [
            {"schema_signature": "a" * 64, "field_count": 2, "files": 1,
             "time_min": 2001, "time_max": 2001, "schema_source": "profile"},
            {"schema_signature": "b" * 64, "field_count": 3, "files": 1,
             "time_min": 2002, "time_max": 2002, "schema_source": "profile"},
        ]
        gens = _generations(catalog, families)
        assert [g["span"] for g in gens] == ["2001", "2002"], "oldest first"
        assert gens[0]["is_first"] and gens[0]["added"] == []
        assert gens[1]["added"] == ["IDADE"]
        assert gens[1]["dropped"] == []

    def test_empty_is_empty(self, catalog: Catalog) -> None:
        from pegasus_data._info import _generations

        assert _generations(catalog, []) == []


class TestSuggestions:
    """A name that does not resolve should point at the one that does.

    With 131 datasets, "try info() for the list" is not help. A typo or a
    half-remembered word is the overwhelmingly common case, and the declaration
    already holds everything needed to answer it.
    """

    def test_typo_finds_the_intended_dataset(self, onto: Ontology) -> None:
        assert "SIH.RD" in onto.suggest("SIH-RDD")
        assert "SIH.SP" in onto.suggest("SIH.SPP")
        assert "SIA.AQ" in onto.suggest("SIA.AQQ")

    def test_a_word_finds_the_dataset_it_names(self, onto: Ontology) -> None:
        """People search by what the data IS, not by its code."""
        assert "SIA.AQ" in onto.suggest("quimio")
        assert "SISCAN.MM" in onto.suggest("mamografia")
        assert "SINAN.DENG" in onto.suggest("dengue")
        assert "SINAN.VIOL" in onto.suggest("violencia")

    def test_the_right_system_ranks_first(self, onto: Ontology) -> None:
        """Getting the system right and the dataset wrong is the usual mistake."""
        assert onto.suggest("SIH-RDD")[0].startswith("SIH.")

    def test_nonsense_suggests_nothing(self, onto: Ontology) -> None:
        """Inventing a suggestion for genuine nonsense is worse than silence."""
        assert onto.suggest("nonsense-xyz") == []


class TestPublicNamesAreCallable:
    """``from pegasus_data import explore`` must give the FUNCTION.

    ``explore.py`` exporting ``explore`` collided as attributes of the package:
    importing the submodule bound it over the function, so a from-import handed
    back a module and calling it raised ``'module' object is not callable``.
    The implementation modules are private now, and this holds that line.
    """

    def test_from_import_gives_functions(self) -> None:
        from pegasus_data import explore, fetch, info, translate

        for obj in (explore, translate, info, fetch):
            assert callable(obj), f"{obj!r} is not callable"

    def test_attribute_access_gives_functions(self) -> None:
        import pegasus_data

        for name in ("explore", "translate", "info", "fetch"):
            assert callable(getattr(pegasus_data, name))

    def test_the_module_is_still_reachable(self) -> None:
        """Renaming must not make the implementation unreachable for testing."""
        import pegasus_data._explore as module

        assert hasattr(module, "tree_snapshot")
