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
            container = "parquet" if filename.endswith(".parquet") else "dbc"
            logical = f"SIHSUS|RD|AL|{yyyymm % 1000000:04d}"
            store.execute(
                "INSERT INTO files (path, logical_id, directory, filename, size, first_seen, last_seen) "
                "VALUES (?,?,?,?,100,'x','x')",
                (path, logical, "/p", filename),
            )
            store.execute(
                "INSERT INTO file_facts (path, system, series_prefix, geo_code, year, "
                "normalized_date, role, logical_id, container_format) "
                "VALUES (?,'SIHSUS','RD','AL',?,?,'data',?,?)",
                (path, year, yyyymm, logical, container),
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


def test_plan_never_opens_fact_data(built_lake, monkeypatch) -> None:
    from pegasus_data.persist.lake import Lake

    settings, _catalog, _family = built_lake
    monkeypatch.setattr(
        Lake,
        "read",
        lambda *_args, **_kwargs: pytest.fail("plan() opened fact data"),
    )
    query_plan = pg.plan(
        "SIH-RD", period=2020, geography="AL", select=["MUNIC_RES"],
        settings=settings,
    )
    assert query_plan.retrieval.source_strategy == "lake"


def test_period_parser_refuses_reverse_interval() -> None:
    with pytest.raises(ValueError, match="after"):
        pg.plan("SIH-RD", period=("2024-06", "2024-03"))


def test_annual_publication_adapts_without_filtering_event_dates(settings) -> None:
    from pegasus_data._query import _filter_source_period
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
    assert query_plan.retrieval.adaptations[0].effective == "2020"
    assert query_plan.retrieval.adaptations[0].kind == "time_resolution"

    table = pa.table(
        {
            "DTOBITO": ["01022020", "01032020", "2020-04-01", None],
            "_competencia": [None, None, None, None],
            "VALUE": [1, 2, 3, 4],
        }
    )
    returned = _filter_source_period(
        table, query_plan.spec.period, retain_annual_enclosures=True
    )
    assert returned["VALUE"].to_pylist() == [1, 2, 3, 4]


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


def test_municipality_is_not_fabricated_from_a_fact_column(built_lake) -> None:
    settings, _catalog, _family = built_lake
    with pytest.raises(ValueError, match="source publications only"):
        pg.plan(
            "SIH-RD",
            period=2020,
            geography={"uf": "AL", "municipality": "270430"},
            settings=settings,
        )


def test_source_geography_never_becomes_a_record_predicate(built_lake) -> None:
    import pyarrow.parquet as pq

    settings, _catalog, _family = built_lake
    part = next((settings.lake_dir / "SIHSUS").rglob("*.parquet"))
    source = pq.ParquetFile(part).read()
    heterogeneous = source.set_column(
        source.column_names.index("MUNIC_RES"),
        "MUNIC_RES",
        pa.array(["270430", "261160", "355030"]),
    )
    pq.write_table(heterogeneous, part)
    result = pg.query(
        "SIH-RD", period=2020, geography="AL", select=["MUNIC_RES"],
        labels=False, settings=settings,
    )
    assert result["MUNIC_RES"].to_pylist() == ["270430", "261160", "355030"]


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


def test_equivalent_representation_keeps_local_completeness(settings) -> None:
    publications = [
        ("/p/RDAL2301.dbc", 2023, 202301),
        ("/p/RDAL2301.parquet", 2023, 202301),
    ]
    _catalogue_publications(settings, publications, covered=[(2023, [publications[0][0]])])
    query_plan = pg.plan("SIH-RD", period=2023, geography="AL", settings=settings)
    assert query_plan.retrieval.source_strategy == "lake"
    assert query_plan.retrieval.lake_years == (2023,)


def test_archive_member_is_part_of_local_completeness(settings) -> None:
    from pegasus_data.catalog.store import Catalog
    from pegasus_data.inventory.families import family_id_for, schema_signature

    signature = schema_signature(["VALUE"])
    family = family_id_for("SIHSUS", "RD", signature)
    logical = "SIHSUS|RD|AL|2301"
    path = "/p/KIT.exe"
    store = Catalog(settings.catalog_path)
    try:
        store.execute(
            "INSERT INTO families (family_id, system, series, schema_signature, field_count) "
            "VALUES (?, 'SIHSUS', 'RD', ?, 1)",
            (family, signature),
        )
        store.execute(
            "INSERT INTO schema_presence (schema_signature, field_name, field_order) "
            "VALUES (?, 'VALUE', 0)",
            (signature,),
        )
        store.execute(
            "INSERT INTO files (path, logical_id, directory, filename, size, first_seen, last_seen) "
            "VALUES (?,?,?,?,100,'x','x')",
            (path, logical, "/p", "KIT.exe"),
        )
        store.execute(
            "INSERT INTO file_facts (path, system, series_prefix, geo_code, year, "
            "normalized_date, role, logical_id, container_format) "
            "VALUES (?,'SIHSUS','RD','AL',2023,202301,'data',?,'lha_sfx')",
            (path, logical),
        )
        store.executemany(
            "INSERT INTO family_files (family_id, path, member) VALUES (?,?,?)",
            [(family, path, "A.dbf"), (family, path, "B.dbf")],
        )
        store.execute(
            "INSERT INTO lake_partitions (family_id, schema_signature, uf, year, "
            "relative_path, source_paths) VALUES (?,?,?,?,?,?)",
            (family, signature, "AL", 2023, "part.parquet", json.dumps([f"{path}!A.dbf"])),
        )
    finally:
        store.close()
    query_plan = pg.plan("SIH-RD", period=2023, geography="AL", settings=settings)
    assert query_plan.retrieval.source_strategy == "fetch"


def test_legacy_analytical_axes_are_not_in_the_public_contract(settings) -> None:
    _catalogue_publications(settings, [("/p/RDAL2301.dbc", 2023, 202301)])
    with pytest.raises(TypeError, match="geography_by"):
        pg.plan("SIH-RD", period=2023, geography_by="facility", settings=settings)
    with pytest.raises(TypeError, match="time_by"):
        pg.plan("SIH-RD", period=2023, time_by="admission", settings=settings)
    with pytest.raises(TypeError, match="unresolved_time"):
        pg.query("SIH-RD", period=2023, unresolved_time="retain", settings=settings)


def test_fresh_install_plans_from_compiled_tree_schema_and_capabilities(tmp_path) -> None:
    from pegasus_data.config import Settings

    query_plan = pg.plan(
        "SIM-DO", period=("2020-03", "2020-04"), settings=Settings(root=tmp_path)
    )
    assert query_plan.retrieval.publication_resolution == "year"
    assert query_plan.retrieval.year_resolutions == ((2020, "year"),)
    assert query_plan.retrieval.source_strategy == "fetch"


def test_unbounded_source_acquisition_requires_explicit_opt_in(tmp_path) -> None:
    from pegasus_data.config import Settings

    with pytest.raises(ValueError, match="period is unbounded"):
        pg.query("SIH-RD", settings=Settings(root=tmp_path))


def test_cnes_registry_enrichment_does_not_inherit_fact_geography(
    settings, monkeypatch
) -> None:
    import pyarrow.parquet as pq

    import pegasus_data.api as api
    from pegasus_data._query_engine.semantics import _enrich_cnes_attribute
    from pegasus_data.catalog.store import Catalog
    from pegasus_data.crosswalk import EnrichmentRequest

    Catalog(settings.catalog_path).close()
    registry_root = settings.lake_dir / "CNES"
    registry_root.mkdir(parents=True)
    pq.write_table(pa.table({"sentinel": [1]}), registry_root / "part.parquet")
    captured = {}

    class _Scanner:
        def to_table(self):
            return pa.table(
                {"CNES": ["2001578"], "NAT_JUR": ["1000"], "COMPETEN": ["202401"]}
            )

    def fake_scan(*_args, **kwargs):
        captured.update(kwargs)
        return _Scanner()

    monkeypatch.setattr(api, "scan", fake_scan)
    query_plan = pg.plan(
        "SIH-RD", period=2024, geography="AL", labels=False,
        enrich=["CNES.legal_nature"], settings=settings,
    )
    enriched, _report = _enrich_cnes_attribute(
        pa.table({"CNES": ["2001578"], "_competencia": [202401]}),
        EnrichmentRequest("CNES.LEGAL_NATURE"), query_plan, settings,
    )
    assert captured["uf"] is None
    assert enriched["CNES_legal_nature"].to_pylist() == ["1000"]
