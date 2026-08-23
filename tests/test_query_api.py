from __future__ import annotations

import json
import warnings

import pyarrow as pa
import pytest

import pegasus_data as pg


def _catalogue_publications(settings, publications, *, covered=()) -> None:
    from pegasus_data.catalog.store import Catalog
    from pegasus_data.inventory.families import family_id_for, schema_signature

    fields = ["ANO_CMPT", "MES_CMPT", "MUNIC_RES", "MUNIC_MOV", "VALUE"]
    signature = schema_signature(fields)
    family = family_id_for("SIHSUS", "RD", signature)
    store = Catalog(settings.catalog_path)
    try:
        store.execute(
            "INSERT INTO families (family_id, system, series, schema_signature, field_count) "
            "VALUES (?, 'SIHSUS', 'RD', ?, ?)",
            (family, signature, len(fields)),
        )
        store.executemany(
            "INSERT INTO schema_presence (schema_signature, field_name, field_order) VALUES (?,?,?)",
            [(signature, field, index) for index, field in enumerate(fields)],
        )
        for path, year, yyyymm in publications:
            filename = path.rsplit("/", 1)[-1]
            logical = f"SIHSUS|RD|AL|{yyyymm % 1000000:04d}"
            store.execute(
                "INSERT INTO files (path, logical_id, directory, filename, size, first_seen, last_seen) "
                "VALUES (?,?,?,?,100,'x','x')",
                (path, logical, "/p", filename),
            )
            store.execute(
                "INSERT INTO file_facts (path, system, series_prefix, geo_code, year, "
                "normalized_date, role, logical_id, container_format) "
                "VALUES (?,'SIHSUS','RD','AL',?,?,'data',?,'dbc')",
                (path, year, yyyymm, logical),
            )
            store.execute(
                "INSERT INTO family_files (family_id, path, member) VALUES (?,?,'')",
                (family, path),
            )
        for year, paths in covered:
            store.execute(
                "INSERT INTO lake_partitions (family_id, schema_signature, uf, year, "
                "relative_path, source_paths) VALUES (?,?,?,?,?,?)",
                (family, signature, "AL", year, f"year={year}/part.parquet", json.dumps(paths)),
            )
    finally:
        store.close()


def test_plan_explains_one_period_api_and_hidden_policy(seeded, settings) -> None:
    query_plan = pg.plan(
        "SIH-RD", period=("2023-01", "2024-01"), geography="AL",
        select=["DIAG_PRINC"], settings=settings,
    )
    explanation = query_plan.explain()
    assert query_plan.retrieval.publication_resolution == "month"
    assert query_plan.retrieval.source_strategy == "fetch"
    assert "Requested period: 2023-01..2024-01" in explanation
    assert "Schema policy: union" in explanation


def test_primary_query_keeps_raw_codes_and_adds_labels(built_lake) -> None:
    settings, _catalog, _family = built_lake
    table, report = pg.query(
        "SIH-RD", period=2020, geography="AL", select=["SEXO"],
        settings=settings, return_report=True,
    )
    assert table["SEXO"].to_pylist() == ["1", "2", "1"]
    assert table["SEXO_label"].to_pylist() == ["Masculino", "Feminino", "Masculino"]
    assert report.source_strategy == "lake"


def test_primary_query_reports_structural_absence_in_report_and_arrow_metadata(built_lake) -> None:
    settings, _catalog, _family = built_lake
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        table, report = pg.query(
            "SIH-RD", period=(2008, 2020), select=["DIAG_SECUN", "DIAGSEC1"],
            settings=settings, return_report=True,
        )
    assert report.structural_absence
    assert json.loads(table.schema.metadata[b"pegasus.structural_absence"])
    assert table["DIAG_SECUN"].null_count == table.num_rows


def test_compiled_publication_resolution_survives_inventory_free_lake(built_lake) -> None:
    settings, _catalog, _family = built_lake
    query_plan = pg.plan("SIH-RD", period=("2020-03", "2020-06"), settings=settings)
    assert query_plan.retrieval.publication_resolution == "month"
    assert not query_plan.retrieval.adaptations


def test_period_parser_refuses_reverse_interval() -> None:
    with pytest.raises(ValueError, match="after"):
        pg.plan("SIH-RD", period=("2024-06", "2024-03"))


def test_annual_publication_can_recover_exact_month_from_rows(settings) -> None:
    from pegasus_data._query import _filter_period, _with_row_competence
    from pegasus_data.catalog.store import Catalog
    from pegasus_data.inventory.families import family_id_for, schema_signature

    fields = ["DTOBITO", "VALUE"]
    signature = schema_signature(fields)
    family = family_id_for("SIM", "DO", signature)
    store = Catalog(settings.catalog_path)
    try:
        store.execute(
            "INSERT INTO families (family_id, system, series, schema_signature, field_count) "
            "VALUES (?, 'SIM', 'DO', ?, 2)",
            (family, signature),
        )
        store.executemany(
            "INSERT INTO schema_presence (schema_signature, field_name, field_order) "
            "VALUES (?, ?, ?)",
            [(signature, field, index) for index, field in enumerate(fields)],
        )
        store.execute(
            "INSERT INTO files (path, directory, filename, first_seen, last_seen) "
            "VALUES ('/annual/DO2020.dbc', '/annual', 'DO2020.dbc', 'x', 'x')"
        )
        store.execute(
            "INSERT INTO file_facts (path, system, series_prefix, geo_code, year, "
            "normalized_date, role) VALUES ('/annual/DO2020.dbc', 'SIM', 'DO', 'BR', "
            "2020, 202000, 'data')"
        )
        store.execute(
            "INSERT INTO family_files (family_id, path, member) "
            "VALUES (?, '/annual/DO2020.dbc', '')",
            (family,),
        )
    finally:
        store.close()

    query_plan = pg.plan("SIM-DO", period=("2020-03", "2020-04"), settings=settings)
    assert query_plan.retrieval.publication_resolution == "year"
    assert query_plan.retrieval.row_time_field == "DTOBITO"
    assert query_plan.retrieval.adaptations[0].effective == "2020-03..2020-04"
    assert query_plan.retrieval.adaptations[0].kind == "publication_enclosure_exact_filter"

    table = pa.table({"DTOBITO": ["01022020", "01032020", "2020-04-01", None], "VALUE": [1, 2, 3, 4]})
    filtered = _filter_period(
        _with_row_competence(table, "DTOBITO"), query_plan.spec.period, adapted=False
    )
    assert filtered["VALUE"].to_pylist() == [2, 3]


def test_optional_registry_requirement_is_planned_and_refused_before_retrieval(settings) -> None:
    query_plan = pg.plan(
        "SIH-RD",
        period=2024,
        enrich=["CNES.establishment_name"],
        settings=settings,
    )
    assert query_plan.semantics.required_resources == ("cnes_names",)
    assert "Resource: cnes_names (missing" in query_plan.explain()
    with pytest.raises(FileNotFoundError, match="cnes_names"):
        pg.query(
            "SIH-RD",
            period=2024,
            enrich=["CNES.establishment_name"],
            settings=settings,
        )


def test_municipality_is_a_row_filter_even_when_a_uf_is_also_requested(built_lake) -> None:
    settings, _catalog, _family = built_lake
    table = pg.query(
        "SIH-RD",
        period=2020,
        geography={"uf": "AL", "municipality": "270430"},
        select=["MUNIC_RES", "SEXO"],
        labels=False,
        settings=settings,
    )
    assert table.num_rows == 2
    assert set(table["MUNIC_RES"].to_pylist()) == {"270430"}


def test_partial_year_lake_coverage_routes_whole_year_to_fetch(settings) -> None:
    publications = [("/p/RDAL2301.dbc", 2023, 202301), ("/p/RDAL2302.dbc", 2023, 202302)]
    _catalogue_publications(settings, publications, covered=[(2023, [publications[0][0]])])
    query_plan = pg.plan("SIH-RD", period=2023, geography="AL", settings=settings)
    assert query_plan.retrieval.source_strategy == "fetch"
    assert query_plan.retrieval.lake_years == ()
    assert query_plan.retrieval.fetch_years == (2023,)


def test_complete_and_missing_years_form_a_hybrid_without_overlap(settings) -> None:
    publications = [("/p/RDAL2301.dbc", 2023, 202301), ("/p/RDAL2401.dbc", 2024, 202401)]
    _catalogue_publications(settings, publications, covered=[(2023, [publications[0][0]])])
    query_plan = pg.plan("SIH-RD", period=(2023, 2024), geography="AL", settings=settings)
    assert query_plan.retrieval.source_strategy == "hybrid"
    assert query_plan.retrieval.lake_years == (2023,)
    assert query_plan.retrieval.fetch_years == (2024,)


def test_declared_geography_axis_selects_facility_not_residence(settings) -> None:
    _catalogue_publications(settings, [("/p/RDAL2301.dbc", 2023, 202301)])
    query_plan = pg.plan(
        "SIH-RD", period=2023, geography={"municipality": "270430"},
        geography_by="facility", settings=settings,
    )
    assert query_plan.retrieval.row_geography_field == "MUNIC_MOV"
    assert query_plan.retrieval.geography_axis == "facility"


def test_unresolved_row_time_policy_is_counted_and_never_silent() -> None:
    from pegasus_data._query import QueryReport, _filter_period, _period

    report = QueryReport()
    table = pa.table({"_competencia": [202301, None, 202302], "value": [1, 2, 3]})
    result = _filter_period(table, _period("2023-01"), False, report=report)
    assert result["value"].to_pylist() == [1]
    assert report.rows_time_unresolved == report.rows_time_excluded == 1
    with pytest.raises(ValueError, match="no parseable"):
        _filter_period(table, _period("2023-01"), False, unresolved_time="error")


def test_fresh_install_plans_from_compiled_tree_schema_and_capabilities(tmp_path) -> None:
    from pegasus_data.config import Settings

    query_plan = pg.plan(
        "SIM-DO", period=("2020-03", "2020-04"), settings=Settings(root=tmp_path)
    )
    assert query_plan.retrieval.publication_resolution == "year"
    assert query_plan.retrieval.row_time_field == "DTOBITO"
    assert query_plan.retrieval.year_resolutions == ((2020, "year"),)
    assert query_plan.retrieval.source_strategy == "fetch"
