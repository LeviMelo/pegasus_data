"""Translation without DATASUS.

The semantic layer is derived from files on an FTP server nobody here controls.
What these tests protect is that the derivation is *portable*: that a catalog
with no crawl behind it and no network in front of it can still say `SEXO=3` is
Feminino, and that in making the bundle small we did not make it wrong.

The two failure modes worth naming, because both are silent:

- **Positional drift.** Copying tables by position means the day the catalog
  gains a column, labels land in the wrong slots and every count still looks
  right. Columns are matched by name, and these tests hold that.
- **De-duplication that loses a meaning.** Collapsing vintages is only safe when
  the rows collapsed said the same thing. A code that was *relabelled* must keep
  both readings, or the bundle quietly picks one wording and drops the other.
"""

from __future__ import annotations

import json
import zipfile

import pytest

from pegasus_data.bundle import (
    BundleError,
    pack,
    read_manifest,
    unpack,
)
from pegasus_data.catalog.store import Catalog


def add_code(
    catalog: Catalog,
    *,
    system: str = "SIHSUS",
    group: str = "SEXO",
    field: str = "SEXO",
    code: str = "3",
    label: str = "Feminino",
    valid_from: str = "2019-01",
    valid_to: str = "2019-12",
    source: str = "cnv",
) -> None:
    catalog.execute(
        "INSERT OR REPLACE INTO dictionary "
        "(system, value_group, field_name, value_raw, value_label, source, source_ref, "
        " confidence, valid_from, valid_to) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (system, group, field, code, label, source, f"{group}.CNV", 0.9, valid_from, valid_to),
    )


def bind(
    catalog: Catalog, *, system: str = "SIHSUS", field: str = "SEXO", codelist: str = "SEXO"
) -> None:
    catalog.execute(
        "INSERT OR REPLACE INTO field_codelists "
        "(system, family_id, field_name, codelist, source, source_ref, confidence) "
        "VALUES (?,?,?,?,?,?,?)",
        (system, "", field, codelist, "def", f"{codelist}.DEF", 0.9),
    )


@pytest.fixture
def packed(catalog: Catalog, tmp_path):
    add_code(catalog)
    bind(catalog)
    return pack(catalog, tmp_path / "b.pgsb")


class TestWhatGetsPacked:
    def test_a_bound_codelist_is_carried(self, catalog: Catalog, tmp_path):
        add_code(catalog)
        bind(catalog)
        assert pack(catalog, tmp_path / "b.pgsb").tables["dictionary"] == 1

    def test_an_unbound_codelist_is_left_behind(self, catalog: Catalog, tmp_path):
        """Four in five codelists are TabNet axes no field decodes against."""
        add_code(catalog, group="FXETARIA", field="")
        assert pack(catalog, tmp_path / "b.pgsb").tables["dictionary"] == 0

    def test_all_codelists_can_be_packed_on_request(self, catalog: Catalog, tmp_path):
        add_code(catalog, group="FXETARIA", field="")
        report = pack(catalog, tmp_path / "b.pgsb", bound_only=False)
        assert report.tables["dictionary"] == 1

    def test_a_system_filter_drops_other_systems(self, catalog: Catalog, tmp_path):
        add_code(catalog, system="SIHSUS")
        add_code(catalog, system="SIM")
        bind(catalog, system="SIHSUS")
        bind(catalog, system="SIM")
        report = pack(catalog, tmp_path / "b.pgsb", systems=["SIHSUS"])
        assert report.tables["dictionary"] == 1
        assert report.tables["field_codelists"] == 1

    def test_no_file_inventory_travels_with_a_bundle(self, catalog: Catalog, packed, tmp_path):
        """A bundle explains data; it is not a copy of the lake or the crawl."""
        with zipfile.ZipFile(packed.path) as archive:
            (tmp_path / "inner.sqlite").write_bytes(archive.read("semantics.sqlite"))
        import sqlite3

        conn = sqlite3.connect(tmp_path / "inner.sqlite")
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        conn.close()
        assert "files" not in tables and "variable_profiles" not in tables


class TestDeduplicationKeepsMeaning:
    def test_the_same_label_across_vintages_collapses_to_one_row(
        self, catalog: Catalog, tmp_path
    ):
        for year in range(2015, 2021):
            add_code(catalog, valid_from=f"{year}-01", valid_to=f"{year}-12")
        bind(catalog)
        report = pack(catalog, tmp_path / "b.pgsb")
        assert report.manifest.dictionary_original == 6
        assert report.tables["dictionary"] == 1

    def test_the_collapsed_row_spans_every_vintage_it_covered(
        self, catalog: Catalog, tmp_path, fresh_catalog
    ):
        for year in range(2015, 2021):
            add_code(catalog, valid_from=f"{year}-01", valid_to=f"{year}-12")
        bind(catalog)
        unpack(fresh_catalog, pack(catalog, tmp_path / "b.pgsb").path)
        row = fresh_catalog.query("SELECT valid_from, valid_to FROM dictionary")[0]
        assert (row["valid_from"], row["valid_to"]) == ("2015-01", "2020-12")

    def test_a_relabelled_code_keeps_both_readings(self, catalog: Catalog, tmp_path, fresh_catalog):
        """The whole point of vintages: the wording changed, so both must survive."""
        add_code(catalog, code="1", label="Masculino", valid_from="2010-01", valid_to="2011-12")
        add_code(catalog, code="1", label="Homem", valid_from="2012-01", valid_to="2013-12")
        bind(catalog)
        unpack(fresh_catalog, pack(catalog, tmp_path / "b.pgsb").path)
        labels = {
            r["value_label"]: (r["valid_from"], r["valid_to"])
            for r in fresh_catalog.query("SELECT * FROM dictionary WHERE value_raw='1'")
        }
        assert labels == {
            "Masculino": ("2010-01", "2011-12"),
            "Homem": ("2012-01", "2013-12"),
        }

    def test_the_same_code_in_two_systems_stays_two_rows(
        self, catalog: Catalog, tmp_path, fresh_catalog
    ):
        """System-scoping is what stopped 13 systems' SEXO.CNV being merged."""
        add_code(catalog, system="SIHSUS", label="Feminino")
        add_code(catalog, system="SIM", label="Fem")
        bind(catalog, system="SIHSUS")
        bind(catalog, system="SIM")
        unpack(fresh_catalog, pack(catalog, tmp_path / "b.pgsb").path)
        assert fresh_catalog.count("dictionary") == 2


class TestTheSizeCap:
    def test_an_oversized_codelist_is_left_out(self, catalog: Catalog, tmp_path):
        for n in range(20):
            add_code(catalog, group="MUNICBR", field="MUNIC_RES", code=str(n), label=f"City {n}")
        add_code(catalog)
        bind(catalog)
        bind(catalog, field="MUNIC_RES", codelist="MUNICBR")
        report = pack(catalog, tmp_path / "b.pgsb", max_codelist_rows=5)
        assert report.tables["dictionary"] == 1

    def test_what_was_left_out_is_named_not_merely_counted(self, catalog: Catalog, tmp_path):
        """An unlabelled municipality must read as 'not packed', not 'unknown'."""
        for n in range(20):
            add_code(catalog, group="MUNICBR", field="MUNIC_RES", code=str(n), label=f"City {n}")
        bind(catalog, field="MUNIC_RES", codelist="MUNICBR")
        report = pack(catalog, tmp_path / "b.pgsb", max_codelist_rows=5)
        assert report.manifest.codelists_omitted == ["SIHSUS.MUNICBR"]

    def test_no_cap_omits_nothing(self, packed):
        assert packed.manifest.codelists_omitted == []


class TestRoundTrip:
    def test_an_empty_catalog_can_translate_after_unpacking(
        self, catalog: Catalog, tmp_path, fresh_catalog
    ):
        add_code(catalog)
        bind(catalog)
        assert fresh_catalog.count("dictionary") == 0
        unpack(fresh_catalog, pack(catalog, tmp_path / "b.pgsb").path)
        row = fresh_catalog.query(
            "SELECT value_label FROM dictionary WHERE system='SIHSUS' AND value_raw='3'"
        )[0]
        assert row["value_label"] == "Feminino"

    def test_the_binding_travels_too_so_the_field_still_finds_its_codelist(
        self, catalog: Catalog, tmp_path, fresh_catalog
    ):
        add_code(catalog)
        bind(catalog)
        unpack(fresh_catalog, pack(catalog, tmp_path / "b.pgsb").path)
        assert fresh_catalog.count("field_codelists") == 1

    def test_curated_meaning_travels(self, catalog: Catalog, tmp_path, fresh_catalog):
        catalog.execute(
            "INSERT INTO variable_docs (system, field_name, official_name, code_system, source) "
            "VALUES ('SIHSUS','IDADE','Idade','none','manual')"
        )
        unpack(fresh_catalog, pack(catalog, tmp_path / "b.pgsb").path)
        assert fresh_catalog.count("variable_docs") == 1

    def test_unpacking_twice_changes_nothing(self, catalog: Catalog, tmp_path, fresh_catalog):
        add_code(catalog)
        bind(catalog)
        bundle = pack(catalog, tmp_path / "b.pgsb").path
        unpack(fresh_catalog, bundle)
        unpack(fresh_catalog, bundle)
        assert fresh_catalog.count("dictionary") == 1

    def test_by_default_a_bundle_does_not_overwrite_first_hand_evidence(
        self, catalog: Catalog, tmp_path, fresh_catalog
    ):
        """A local crawl read the file; a bundle read someone's reading of it."""
        add_code(catalog, label="Feminino")
        bind(catalog)
        add_code(fresh_catalog, label="LOCAL READING")
        unpack(fresh_catalog, pack(catalog, tmp_path / "b.pgsb").path)
        row = fresh_catalog.query("SELECT value_label FROM dictionary")[0]
        assert row["value_label"] == "LOCAL READING"

    def test_replace_lets_the_bundle_be_the_source_of_truth(
        self, catalog: Catalog, tmp_path, fresh_catalog
    ):
        add_code(catalog, label="Feminino")
        bind(catalog)
        add_code(fresh_catalog, label="STALE")
        unpack(fresh_catalog, pack(catalog, tmp_path / "b.pgsb").path, replace=True)
        rows = fresh_catalog.query("SELECT value_label FROM dictionary")
        assert [r["value_label"] for r in rows] == ["Feminino"]

    def test_the_unpack_is_recorded_in_the_event_log(
        self, catalog: Catalog, tmp_path, fresh_catalog
    ):
        add_code(catalog)
        bind(catalog)
        unpack(fresh_catalog, pack(catalog, tmp_path / "b.pgsb").path)
        assert fresh_catalog.count("events", "stage = 'bundle'") == 1


class TestColumnsAreMatchedByName:
    def test_a_column_the_local_schema_lacks_is_dropped_not_shifted(
        self, catalog: Catalog, tmp_path, fresh_catalog
    ):
        """The silent-corruption case: positional copying puts labels in the
        wrong slots and every row count still looks correct."""
        add_code(catalog)
        bind(catalog)
        bundle = pack(catalog, tmp_path / "b.pgsb").path
        _inject_extra_column(bundle, tmp_path)

        result = unpack(fresh_catalog, bundle)
        assert result["unknown_columns"]["dictionary"] == ["invented_column"]
        row = fresh_catalog.query("SELECT * FROM dictionary")[0]
        assert row["value_label"] == "Feminino", "not shifted into the neighbouring column"


def _inject_extra_column(bundle_path, tmp_path):
    """Rewrite a bundle so its dictionary carries a column no catalog declares."""
    import shutil
    import sqlite3

    inner = tmp_path / "rewrite.sqlite"
    with zipfile.ZipFile(bundle_path) as archive:
        manifest = archive.read("manifest.json")
        inner.write_bytes(archive.read("semantics.sqlite"))
    conn = sqlite3.connect(inner)
    conn.execute("ALTER TABLE dictionary ADD COLUMN invented_column TEXT DEFAULT 'x'")
    conn.commit()
    conn.close()
    shutil.copy(inner, tmp_path / "payload.sqlite")
    with zipfile.ZipFile(bundle_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", manifest)
        archive.write(tmp_path / "payload.sqlite", "semantics.sqlite")


class TestTheManifest:
    def test_it_states_what_deduplication_bought(self, catalog: Catalog, tmp_path):
        for year in range(2015, 2021):
            add_code(catalog, valid_from=f"{year}-01", valid_to=f"{year}-12")
        bind(catalog)
        manifest = read_manifest(pack(catalog, tmp_path / "b.pgsb").path)
        assert (manifest.dictionary_original, manifest.dictionary_deduplicated) == (6, 1)

    def test_it_names_the_systems_it_covers(self, catalog: Catalog, tmp_path):
        add_code(catalog)
        bind(catalog)
        manifest = read_manifest(pack(catalog, tmp_path / "b.pgsb", systems=["sihsus"]).path)
        assert manifest.systems == ["SIHSUS"]

    def test_a_future_format_is_refused_rather_than_misread(self, packed, tmp_path):
        target = tmp_path / "future.pgsb"
        with zipfile.ZipFile(packed.path) as source:
            payload = source.read("semantics.sqlite")
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("manifest.json", json.dumps({"format": 99}))
            archive.writestr("semantics.sqlite", payload)
        with pytest.raises(BundleError, match="newer than this build"):
            read_manifest(target)

    def test_something_that_is_not_a_bundle_says_so(self, tmp_path):
        stray = tmp_path / "notes.txt"
        stray.write_text("not a bundle")
        with pytest.raises(BundleError):
            read_manifest(stray)

    def test_a_zip_without_a_manifest_says_so(self, tmp_path):
        target = tmp_path / "empty.pgsb"
        with zipfile.ZipFile(target, "w") as archive:
            archive.writestr("readme.txt", "hello")
        with pytest.raises(BundleError, match="not a pegasus_data bundle"):
            read_manifest(target)


class TestItLeavesNothingBehind:
    def test_the_staging_database_is_removed(self, catalog: Catalog, tmp_path):
        add_code(catalog)
        bind(catalog)
        pack(catalog, tmp_path / "b.pgsb")
        assert not list(tmp_path.glob("*.staging.sqlite"))

    def test_unpacking_removes_its_scratch_copy(self, catalog: Catalog, tmp_path, fresh_catalog):
        add_code(catalog)
        bind(catalog)
        unpack(fresh_catalog, pack(catalog, tmp_path / "b.pgsb").path)
        assert not list(tmp_path.glob("*.unpacked.sqlite"))
