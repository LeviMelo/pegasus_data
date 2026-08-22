"""The label layer, small enough to ship — which is what makes labels work.

`fetch(labels=True)` needs a code-to-label table for every column it renders.
Those are built by `semantics` into a 14 GB catalog no user has any reason to
build, so on a fresh install `fetch` returned data and translated NOTHING.

The pack is that layer distilled: code RANGES instead of every code in them, one
copy of what every system agrees on, and entity directories held out. What is
NOT held out is ICD-10 — a size cap would have dropped it, which is how you
learn that size is the wrong criterion and the role is the right one.
"""

from __future__ import annotations

import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.labelpack import (
    _role_of,
    _split_packed,
    _successor,
    build_binding_pack,
    build_label_pack,
    codelist_roles,
    read_packed,
    seed_bindings,
)


class TestRoleDecidesWhatShips:
    """Sorting by size keeps 450 municipal rollups and throws away CID10."""

    def test_an_establishment_directory_is_a_registry(self) -> None:
        roles = codelist_roles()
        assert _role_of("CADGERBR", roles) == "registry"
        assert _role_of("TCNESAC", roles) == "registry"
        assert _role_of("UNIDTOTAL", roles) == "registry"

    def test_a_published_standard_is_not(self) -> None:
        """CID10 is 83,579 runs. Any size cap loses it; the role keeps it."""
        roles = codelist_roles()
        assert _role_of("CID10", roles) == "classification"
        assert _role_of("CBO", roles) == "classification"

    def test_geography_is_kept(self) -> None:
        roles = codelist_roles()
        assert _role_of("MUNICBR", roles) == "geography"
        assert _role_of("BR_MUNICIP", roles) == "geography"

    def test_an_ordinary_enumeration_has_no_special_role(self) -> None:
        assert _role_of("SEXO", codelist_roles()) is None


class TestTwoFactsInOneString:
    """CADGERBR labels pack a tax number in front of an establishment name."""

    def test_the_name_and_the_cnpj_are_separated(self) -> None:
        label, cnpj = _split_packed("CNPJ 12.345.678/0001-90-PREFEITURA DE X")
        assert label == "PREFEITURA DE X"
        assert cnpj == "12.345.678/0001-90"

    def test_an_all_zero_cnpj_is_a_null_not_an_identity(self) -> None:
        label, cnpj = _split_packed("CNPJ 00.000.000/0000-00-PREFEITURA DE X")
        assert label == "PREFEITURA DE X"
        assert cnpj is None

    def test_an_ordinary_label_is_left_alone(self) -> None:
        assert _split_packed("Masculino") == ("Masculino", None)


class TestRunsAreMergedOnlyWhereTheyAreRuns:
    def test_numeric_codes_have_a_successor(self) -> None:
        assert _successor("000123") == "000124"

    def test_a_lettered_code_has_none(self) -> None:
        """A00 and A01 look consecutive; the alphabet is not the code space."""
        assert _successor("A00") is None

    def test_width_is_preserved(self) -> None:
        assert _successor("0001") == "0002"


def _seed(catalog: Catalog) -> None:
    rows = [
        ("SIHSUS", "SEXO", "1", "Masculino"),
        ("SIHSUS", "SEXO", "3", "Feminino"),
        ("SINASC", "SEXO", "1", "Masculino"),          # same reading, other system
        ("SIHSUS", "MUNICBR", "000001", "Brasilia"),
        ("SIHSUS", "MUNICBR", "000002", "Brasilia"),   # a run
        ("SIHSUS", "MUNICBR", "000003", "Brasilia"),
        ("SIHSUS", "CADGERBR", "2001578", "CNPJ 12.345.678/0001-90-HOSPITAL X"),
        ("SIHSUS", "NOISE", "7", "7"),                 # label repeats the code
    ]
    for system, group, code, label in rows:
        catalog.execute(
            "INSERT INTO dictionary (system, value_group, field_name, value_raw,"
            " value_label, source, source_ref, confidence)"
            " VALUES (?,?,?,?,?,'cnv','t.cnv',0.9)",
            (system, group, group, code, label),
        )
        catalog.execute(
            "INSERT OR IGNORE INTO field_codelists (system, family_id, field_name,"
            " codelist, source, source_ref, confidence)"
            " VALUES (?,'',?,?,'def','t.def',0.9)",
            (system, group, group),
        )


@pytest.fixture
def built(settings, tmp_path):
    store = Catalog(settings.catalog_path)
    try:
        _seed(store)
        report = build_label_pack(store, tmp_path / "labels.parquet")
    finally:
        store.close()
    return report, tmp_path / "labels.parquet"


class TestTheBuiltPack:
    @staticmethod
    def _rows(path):
        import pyarrow.parquet as pq

        return pq.read_table(path).to_pylist()

    def test_a_range_becomes_one_run(self, built) -> None:
        runs = [r for r in self._rows(built[1]) if r["codelist"] == "MUNICBR"]
        assert len(runs) == 1
        assert (runs[0]["code_lo"], runs[0]["code_hi"]) == ("000001", "000003")

    def test_what_every_system_agrees_on_is_stored_once(self, built) -> None:
        masc = [
            r for r in self._rows(built[1])
            if r["codelist"] == "SEXO" and r["label"] == "Masculino"
        ]
        assert len(masc) == 1
        assert masc[0]["system"] is None, "null system means: every system agrees"

    def test_a_reading_only_one_system_holds_keeps_its_system(self, built) -> None:
        fem = [r for r in self._rows(built[1]) if r["label"] == "Feminino"]
        assert fem and fem[0]["system"] == "SIHSUS"

    def test_a_registry_is_held_back(self, built) -> None:
        report, path = built
        assert "CADGERBR" in report.held_back
        assert not [r for r in self._rows(path) if r["codelist"] == "CADGERBR"]

    def test_but_its_crosswalk_is_not(self, built) -> None:
        """The CNES-to-CNPJ mapping is a join key, not a label."""
        report, path = built
        assert report.crosswalk_rows == 1
        cross = self._rows(path.with_name("labels_crosswalk.parquet"))
        assert cross[0]["code"] == "2001578"
        assert cross[0]["cnpj"] == "12.345.678/0001-90"

    def test_a_label_that_repeats_its_code_is_dropped(self, built) -> None:
        assert built[0].dropped_useless >= 1


class TestBindingsTravelWithTheLabels:
    def test_they_are_seeded_into_an_empty_catalog(self, settings) -> None:
        """Knowing I219 is a heart attack is no help if nothing says
        DIAG_PRINC is coded in CID10."""
        store = Catalog(settings.catalog_path)
        try:
            assert store.count("field_codelists") == 0
            added = seed_bindings(store)
            assert added > 0
            assert store.count("field_codelists") == added
        finally:
            store.close()

    def test_a_local_build_is_never_overwritten(self, settings) -> None:
        """The guarantee is that the local ROW survives, which is not the same
        as the whole seed being skipped.

        This used to assert `seed_bindings(store) == 0` — the old
        all-or-nothing behaviour — and that assertion was the bug wearing the
        test's name. Curation writes ~900 bindings of its own, so any catalog
        curated before it was seeded looked "non-empty" and could never receive
        the other ~8,500. Same data, two catalogs, CNES-ST labelled 83 columns
        on one and 26 on the other.
        """
        store = Catalog(settings.catalog_path)
        try:
            store.execute(
                "INSERT INTO field_codelists (system, family_id, field_name, codelist,"
                " source, source_ref, confidence)"
                " VALUES ('SIHSUS','','SEXO','MINE','manual','me',1.0)"
            )
            seed_bindings(store)
            mine = store.query(
                "SELECT source, source_ref, confidence FROM field_codelists"
                " WHERE system='SIHSUS' AND family_id='' AND field_name='SEXO'"
                "   AND codelist='MINE'"
            )
            assert len(mine) == 1, "the local binding was replaced or removed"
            assert mine[0]["source"] == "manual"
            assert mine[0]["source_ref"] == "me"
            assert float(mine[0]["confidence"]) == 1.0
        finally:
            store.close()

    def test_the_rest_of_the_pack_still_arrives(self, settings) -> None:
        """One local row must not cost the catalog every packaged one."""
        store = Catalog(settings.catalog_path)
        try:
            store.execute(
                "INSERT INTO field_codelists (system, family_id, field_name, codelist,"
                " source, source_ref, confidence)"
                " VALUES ('SIHSUS','','SEXO','MINE','manual','me',1.0)"
            )
            added = seed_bindings(store)
            assert added > 1000, (
                f"only {added} bindings were merged into a catalog holding one "
                "local row; the pack is being skipped again"
            )
        finally:
            store.close()

    def test_seeding_twice_adds_nothing_the_second_time(self, settings) -> None:
        """Merging must be idempotent, and must SAY it added nothing rather
        than reporting the size of what it offered."""
        store = Catalog(settings.catalog_path)
        try:
            first = seed_bindings(store)
            assert first > 0
            total = store.count("field_codelists")
            assert seed_bindings(store) == 0
            assert store.count("field_codelists") == total
        finally:
            store.close()

    def test_a_partially_seeded_catalog_is_topped_up(self, settings) -> None:
        """The real-world shape of the defect: a catalog that holds SOME of the
        pack, from an interrupted or older run, has to be able to recover."""
        store = Catalog(settings.catalog_path)
        try:
            full = seed_bindings(store)
            rows = store.query(
                "SELECT system, family_id, field_name, codelist FROM field_codelists LIMIT 400"
            )
            keep = {
                (r["system"], r["family_id"], r["field_name"], r["codelist"]) for r in rows
            }
            store.execute("DELETE FROM field_codelists")
            store.executemany(
                "INSERT INTO field_codelists (system, family_id, field_name, codelist,"
                " source, source_ref, confidence) VALUES (?,?,?,?,'def','partial',0.9)",
                sorted(keep),
            )
            assert store.count("field_codelists") == len(keep)

            seed_bindings(store)
            assert store.count("field_codelists") == full, (
                "a partially seeded catalog stayed partial — it can never "
                "recover the labels it is missing"
            )
        finally:
            store.close()

    def test_the_pack_round_trips(self, settings, tmp_path) -> None:
        store = Catalog(settings.catalog_path)
        try:
            store.execute(
                "INSERT INTO field_codelists (system, family_id, field_name, codelist,"
                " source, source_ref, confidence)"
                " VALUES ('SIHSUS','','SEXO','SEXO','def','t.def',0.9)"
            )
            assert build_binding_pack(store, tmp_path / "b.parquet") == 1
        finally:
            store.close()


class TestReadingTheShippedPack:
    def test_icd10_is_there_and_decodes(self) -> None:
        """The table a size cap would have thrown away."""
        table = read_packed("CID10", system="SIHSUS", code_width=4)
        found = dict(
            zip(table.column("code").to_pylist(), table.column("label").to_pylist(), strict=True)
        )
        assert "I219" in found
        assert "infarto" in found["I219"].lower()

    def test_an_unknown_table_is_a_miss_not_a_crash(self) -> None:
        with pytest.raises(FileNotFoundError):
            read_packed("NO_SUCH_TABLE_ANYWHERE")

    def test_a_held_back_registry_is_absent(self) -> None:
        with pytest.raises(FileNotFoundError):
            read_packed("CADGERBR")


class TestLabelsAreNotEscaped:
    r"""An escape leaked into the text somewhere above the `dictionary` table.

    The shipped pack carried `N\ão`, `Domic\ílio`, `Ces\áreo`, `Suic\ídio` and
    125 more, and `Não` is the commonest label in the whole pack — so one
    state-year of SINASC came back with 70,586 cells carrying a stray backslash.
    The sources are clean UTF-8; this was added on the way in.
    """

    def test_an_escaped_accent_is_dropped(self) -> None:
        from pegasus_data.labelpack import _unescape_accents

        assert _unescape_accents(r"N\ão") == "Não"
        assert _unescape_accents(r"Domic\ílio") == "Domicílio"
        assert _unescape_accents(r"AIKAN\Ã-KWAS\Á") == "AIKANÃ-KWASÁ"

    def test_a_separator_before_ascii_is_kept(self) -> None:
        """The establishment directories use a backslash to join two names, and
        216 labels in the pack depend on it surviving."""
        from pegasus_data.labelpack import _unescape_accents

        assert (
            _unescape_accents(r"ILHA DE SANTANA \ ZONA RURAL I")
            == r"ILHA DE SANTANA \ ZONA RURAL I"
        )
        assert _unescape_accents(r"NORBERTO\FRANCINO ANDRADE") == r"NORBERTO\FRANCINO ANDRADE"

    def test_clean_text_is_untouched(self) -> None:
        from pegasus_data.labelpack import _unescape_accents

        for text in ("Hospital", "Indígena", "Espontâneo", "", "Cesáreo"):
            assert _unescape_accents(text) == text

    def test_the_shipped_pack_carries_none(self) -> None:
        """The guard that matters: whatever the builder does, what SHIPS is clean."""
        from importlib.resources import files
        from pathlib import Path

        import pyarrow.parquet as pq

        from pegasus_data.labelpack import _ESCAPED_ACCENT

        path = Path(str(files("pegasus_data.resources") / "labels.parquet"))
        labels = pq.read_table(path, columns=["label"]).column("label").to_pylist()
        bad = [x for x in labels if x and _ESCAPED_ACCENT.search(x)]
        assert not bad, f"{len(bad)} shipped labels carry an escaped accent, e.g. {bad[:3]}"
