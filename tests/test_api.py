"""The public surface, end to end over a synthetic lake."""

from __future__ import annotations

import pyarrow as pa
import pytest

from pegasus_data.api import Catalog as PublicCatalog
from pegasus_data.api import LabelUnavailable, describe, load
from pegasus_data.catalog.store import Catalog
from pegasus_data.config import Settings
from pegasus_data.inventory.families import family_id_for, schema_signature
from pegasus_data.normalize.engine import MissingColumnError
from pegasus_data.persist.duck import DuckLake
from pegasus_data.persist.lake import Lake
from pegasus_data.semantics.dictionary import (
    CodelistBinding,
    DictionaryEntry,
    persist_bindings,
    persist_entries,
)


@pytest.fixture
def built_lake(settings: Settings, catalog: Catalog) -> tuple[Settings, Catalog, str]:
    """A miniature SIH-RD with two schema generations and a decoded SEXO."""
    fields_old = ["MUNIC_RES", "SEXO", "DIAG_SECUN", "VAL_TOT"]
    fields_new = ["MUNIC_RES", "SEXO", "DIAGSEC1", "VAL_TOT"]
    sig_old, sig_new = schema_signature(fields_old), schema_signature(fields_new)
    fam_old = family_id_for("SIHSUS", "RD", sig_old)
    fam_new = family_id_for("SIHSUS", "RD", sig_new)

    catalog.executemany(
        """INSERT INTO families (family_id, system, series, schema_signature, field_count,
           time_min, time_max, geo_coverage, file_count) VALUES (?,?,?,?,?,?,?,?,?)""",
        [
            (fam_old, "SIHSUS", "RD", sig_old, 4, 2008, 2014, '["AL"]', 2),
            (fam_new, "SIHSUS", "RD", sig_new, 4, 2015, 2024, '["AL"]', 2),
        ],
    )
    catalog.executemany(
        "INSERT INTO schema_presence (schema_signature, field_name, field_order) VALUES (?,?,?)",
        [(sig_old, f, i) for i, f in enumerate(fields_old)]
        + [(sig_new, f, i) for i, f in enumerate(fields_new)],
    )
    catalog.executemany(
        """INSERT INTO variable_profiles (family_id, field_name, schema_signature, semantic_type,
           semantic_confidence, semantic_evidence, distinct_count, physical_type, width)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        [
            (fam_new, "SEXO", sig_new, "categorical_undecoded", 0.5, '{"rule":"categorical"}', 2, "C", 1),
            (fam_new, "MUNIC_RES", sig_new, "municipality_code_6", 0.8, '{"rule":"municipality"}', 3, "C", 6),
            (fam_new, "VAL_TOT", sig_new, "money", 0.9, '{"rule":"money"}', 4, "N", 10),
        ],
    )
    catalog.executemany(
        """INSERT INTO value_frequencies (family_id, field_name, schema_signature, value, count, percent, rank)
           VALUES (?,?,?,?,?,?,?)""",
        [
            (fam_new, "SEXO", sig_new, "1", 60, 0.6, 1),
            (fam_new, "SEXO", sig_new, "2", 40, 0.4, 2),
        ],
    )
    persist_entries(
        catalog,
        [
            DictionaryEntry(
                system="SIHSUS", value_raw="1", value_label="Masculino", source="cnv",
                source_ref="TAB_SIH.zip!SEXO.CNV:3", confidence=0.95, value_group="SEXO",
            ),
            DictionaryEntry(
                system="SIHSUS", value_raw="2", value_label="Feminino", source="cnv",
                source_ref="TAB_SIH.zip!SEXO.CNV:4", confidence=0.95, value_group="SEXO",
            ),
            DictionaryEntry(
                system="SIHSUS", value_raw="270430", value_label="Maceió", source="cnv",
                source_ref="TAB_SIH.zip!MUNIC.CNV:9", confidence=0.95, value_group="MUNIC",
            ),
            DictionaryEntry(
                system="SIHSUS", value_raw="271070", value_label="Rio Largo", source="cnv",
                source_ref="TAB_SIH.zip!MUNIC.CNV:10", confidence=0.95, value_group="MUNIC",
            ),
        ],
    )
    persist_bindings(
        catalog, [CodelistBinding("SIHSUS", "SEXO", "SEXO", "def", "TAB_SIH.zip!RD.DEF:12", 0.9)]
    )
    catalog.executemany(
        """INSERT INTO def_variables (def_path, system, usage, display_name, field_name, line_no)
           VALUES (?,?,?,?,?,?)""",
        [("d", "SIHSUS", "L", "Sexo", "SEXO", 12), ("d", "SIHSUS", "I", "Valor Total", "VAL_TOT", 7)],
    )

    from pegasus_data.semantics.ledger import build_ledger, persist_ledger

    persist_ledger(catalog, build_ledger(catalog))

    # The view layer joins labels from lake/reference/ at read time, so the
    # reference tables have to exist for a label to be producible at all.
    from pegasus_data.persist.reference import register_reference_tables, write_reference_tables

    register_reference_tables(catalog, write_reference_tables(catalog, settings.lake_dir))

    # code_system is what decides replace-vs-accompany (§5.2), and it lives in
    # the curated dictionary rather than in a heuristic.
    catalog.executemany(
        """INSERT INTO variable_docs (system, field_name, code_system, codelist, source,
           asserted_by) VALUES (?,?,?,?,?,?)""",
        [
            ("SIHSUS", "SEXO", "internal", "SEXO", "manual", "test"),
            ("SIHSUS", "MUNIC_RES", "external", "MUNIC", "manual", "test"),
            ("SIHSUS", "VAL_TOT", "none", None, "manual", "test"),
        ],
    )

    lake = Lake(settings.lake_dir, catalog)
    table = pa.table(
        {
            "MUNIC_RES": pa.array(["270430", "270430", "271070"]),
            "SEXO": pa.array(["1", "2", "1"]),
            "SEXO_label": pa.array(["Masculino", "Feminino", "Masculino"]),
            "DIAGSEC1": pa.array(["W199", None, "V878"]),
            "VAL_TOT": pa.array([1234.5, 99.0, 7000.0]),
        }
    )
    lake.write_batches(
        table.to_batches(), system="SIHSUS", family_id=fam_new,
        schema_signature=sig_new, uf="AL", year=2020,
    )
    return settings, catalog, fam_new


class TestCatalogSurface:
    def test_systems_and_families(self, built_lake):
        settings, catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            families = public.families(system="SIHSUS")
            assert len(families) == 2
            coverage = public.coverage("SIHSUS", "RD")
            assert len(coverage["schema_generations"]) == 2
            assert coverage["ufs"] == ["AL"]
        finally:
            public.close()


class TestDescribe:
    def test_returns_labels_coverage_and_provenance(self, built_lake):
        settings, catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            d = describe("SIHSUS", "RD", field="SEXO", catalog=public)
        finally:
            public.close()
        assert d.official_name == "Sexo"
        assert d.dictionary_coverage == pytest.approx(1.0)
        assert {t["label"] for t in d.top_values} == {"Masculino", "Feminino"}
        assert "dictionary" in d.provenance
        assert d.codelists == ["SEXO"]

    def test_states_which_generations_carry_the_column(self, built_lake):
        settings, catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            d = describe("SIHSUS", "RD", field="DIAGSEC1", catalog=public)
        finally:
            public.close()
        has = [g for g in d.generations if g["has_field"]]
        assert len(has) == 1, "DIAGSEC1 exists only in the newer generation"

    def test_declared_measure_is_additive(self, built_lake):
        settings, catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            d = describe("SIHSUS", "RD", field="VAL_TOT", catalog=public)
        finally:
            public.close()
        assert d.aggregation == "additive"

    def test_a_field_in_no_generation_raises(self, built_lake):
        settings, catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            with pytest.raises((MissingColumnError, KeyError)):
                describe("SIHSUS", "RD", field="NOT_A_COLUMN", catalog=public)
        finally:
            public.close()


class TestLoad:
    def test_an_internal_code_is_replaced_by_its_label(self, built_lake):
        """§5.2: nobody wants SEXO=1 in a finished output."""
        settings, catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            table = load("SIHSUS", "RD", uf="AL", years=[2020],
                         columns=["SEXO"], catalog=public)
        finally:
            public.close()
        assert table.num_rows == 3
        assert table.column("SEXO").to_pylist() == ["Masculino", "Feminino", "Masculino"]
        assert "SEXO_label" not in table.schema.names, "internal codes are replaced, not accompanied"

    def test_an_external_code_keeps_its_code_beside_the_label(self, built_lake):
        """§5.2: an external code is a join key and must survive."""
        settings, catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            table = load("SIHSUS", "RD", uf="AL", years=[2020],
                         columns=["MUNIC_RES"], catalog=public)
        finally:
            public.close()
        assert "MUNIC_RES" in table.schema.names
        assert "MUNIC_RES_label" in table.schema.names

    def test_labels_are_joined_not_projected(self, built_lake):
        """§5.5, the real bug: the label must not depend on being in the Parquet.

        The fixture writes a stored SEXO_label column. This asserts the value
        comes from the reference-table join by removing the binding's reach: the
        codes profile renders nothing, so a projected column would still show up.
        """
        settings, catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            table = load("SIHSUS", "RD", uf="AL", years=[2020],
                         columns=["SEXO"], profile="codes", catalog=public)
        finally:
            public.close()
        assert table.column("SEXO").to_pylist() == ["1", "2", "1"]
        assert "SEXO_label" not in table.schema.names

    def test_an_unproducible_label_is_named_not_silently_dropped(self, built_lake):
        settings, catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            with pytest.raises(LabelUnavailable, match="VAL_TOT"):
                load("SIHSUS", "RD", uf="AL", years=[2020], columns=["VAL_TOT"],
                     render={"VAL_TOT": "label"}, strict_labels=True, catalog=public)
        finally:
            public.close()

    def test_partition_pruning_by_year(self, built_lake):
        settings, catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            with pytest.raises(FileNotFoundError):
                load("SIHSUS", "RD", uf="AL", years=[1999], catalog=public)
        finally:
            public.close()

    def test_requesting_a_column_no_generation_has_raises(self, built_lake):
        settings, catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            with pytest.raises(MissingColumnError) as excinfo:
                load("SIHSUS", "RD", columns=["DIAG_SECUN"], catalog=public)
        finally:
            public.close()
        assert "DIAG_SECUN" in str(excinfo.value)


class TestDuckLake:
    def test_views_are_registered_and_queryable(self, built_lake):
        settings, catalog, family_id = built_lake
        with DuckLake(settings.lake_dir, catalog) as duck:
            views = duck.register_all()
            assert "sihsus_rd" in views
            result = duck.query('SELECT COUNT(*) AS n FROM "sihsus_rd"')
            assert result.column("n").to_pylist() == [3]
            columns = [d["column"] for d in duck.describe_dataset("sihsus_rd")]
            assert "SEXO_label" in columns
            assert "uf" in columns and "year" in columns  # hive partitions surface


class TestPopulation:
    def test_a_series_refuses_a_stratification_it_cannot_support(self, built_lake):
        from pegasus_data.api import load_population
        from pegasus_data.sources.ibge import UnsupportedStratification

        settings, catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            with pytest.raises(UnsupportedStratification) as excinfo:
                load_population(series="POPTCU", by=["municipality", "year", "age"], catalog=public)
        finally:
            public.close()
        assert "POPSVS" in str(excinfo.value), "the error points at the series that can"
