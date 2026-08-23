from __future__ import annotations

import json
import warnings

import pyarrow as pa
import pytest

import pegasus_data as pg


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


def test_subannual_request_against_annual_publication_adapts_with_warning(built_lake) -> None:
    settings, _catalog, _family = built_lake
    query_plan = pg.plan("SIH-RD", period=("2020-03", "2020-06"), settings=settings)
    assert query_plan.retrieval.adaptations
    assert query_plan.retrieval.adaptations[0].effective == "2020"


def test_period_parser_refuses_reverse_interval() -> None:
    with pytest.raises(ValueError, match="after"):
        pg.plan("SIH-RD", period=("2024-06", "2024-03"))


def test_annual_publication_can_recover_exact_month_from_rows(settings) -> None:
    from pegasus_data._query import _filter_period, _with_row_competence
    from pegasus_data.catalog.store import Catalog
    from pegasus_data.inventory.families import family_id_for, schema_signature

    fields = ["COMPETEN", "VALUE"]
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
    assert query_plan.retrieval.row_time_field == "COMPETEN"
    assert query_plan.retrieval.adaptations[0].effective == "2020-03..2020-04"
    assert query_plan.retrieval.adaptations[0].kind == "publication_enclosure_exact_filter"

    table = pa.table({"COMPETEN": ["202002", "202003", "2020-04", None], "VALUE": [1, 2, 3, 4]})
    filtered = _filter_period(
        _with_row_competence(table, "COMPETEN"), query_plan.spec.period, adapted=False
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
