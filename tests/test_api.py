"""The public surface, end to end over a synthetic lake."""

from __future__ import annotations

import pytest

from pegasus_data.api import Catalog as PublicCatalog
from pegasus_data.api import LabelUnavailable, describe, load
from pegasus_data.normalize.engine import MissingColumnError
from pegasus_data.persist.duck import DuckLake


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

    def test_null_fill_keeps_the_generations_that_lack_the_column(self, built_lake):
        """The opt-in half of the one policy fetch() and load() now share.

        The default raises so a longitudinal request cannot silently begin
        wherever the column was added. Opting in keeps every row, and the
        nullness is reported as STRUCTURAL — the field does not exist in that
        generation, it was not left blank.
        """
        settings, catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            with pytest.raises(MissingColumnError):
                load("SIHSUS", "RD", columns=["DIAG_SECUN"], catalog=public)
            table, rep = load(
                "SIHSUS",
                "RD",
                columns=["DIAG_SECUN"],
                on_missing_column="null_fill",
                catalog=public,
                report=True,
            )
        finally:
            public.close()
        assert table.num_rows > 0, "the rows the default refused to guess about"
        assert any("STRUCTURALLY" in w for w in rep.warnings), (
            "null-filled structural absence must be disclosed, not just permitted"
        )


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
