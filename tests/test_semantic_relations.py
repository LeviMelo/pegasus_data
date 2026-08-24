from __future__ import annotations

import pyarrow as pa
import pytest

import pegasus_data as pg
from pegasus_data.persist.reference import register_reference_tables, write_reference_tables
from pegasus_data.semantics.dictionary import (
    CodelistBinding,
    DictionaryEntry,
    persist_bindings,
    persist_entries,
)
from pegasus_data.semantics.relations import (
    RelationType,
    SemanticRelation,
    adjudicate,
    adjudication_evidence,
    ensure_adjudication_item,
    load_relations,
    relations_for,
    seed_relations,
)


def test_all_required_relation_types_are_modelled() -> None:
    assert {relation.relation_type for relation in load_relations()} >= {
        RelationType.LABEL_OF,
        RelationType.ROLLUP_TO,
        RelationType.ATTRIBUTE_OF,
        RelationType.CROSSWALK_TO,
    }


def test_relations_compile_into_catalog(catalog) -> None:
    assert seed_relations(catalog) >= 4
    assert catalog.count("semantic_relations", "relation_type = 'label_of'") >= 1
    assert catalog.count("semantic_relations", "relation_type = 'crosswalk_to'") >= 1


def test_runtime_ambiguity_is_deduplicated_into_work_item(catalog) -> None:
    kwargs = {
        "kind": "semantic_relation",
        "system": "SINASC",
        "family_id": "F1",
        "field": "CODMUNRES",
        "candidates": ["MUNICBR", "CIRAC"],
        "reason": "ambiguous",
    }
    first = ensure_adjudication_item(catalog, **kwargs)
    second = ensure_adjudication_item(catalog, **kwargs)
    assert first == second
    assert catalog.count("adjudication_items") == 1
    assert adjudication_evidence(catalog, first)["candidates_json"] == ["MUNICBR", "CIRAC"]


def test_applied_adjudication_changes_the_actual_rendered_value(settings, catalog) -> None:
    from pegasus_data.view import render_table

    codelists = [f"CANDIDATE_{index:02d}" for index in range(12)] + ["RIGHT_MUNIC"]
    persist_entries(
        catalog,
        [
            DictionaryEntry(
                system="SIHSUS",
                value_raw="120040",
                value_label=("Rio Branco" if name == "RIGHT_MUNIC" else f"Wrong {name}"),
                value_group=name,
                source="cnv",
                source_ref=f"test!{name}",
                confidence=0.9,
            )
            for name in codelists
        ],
    )
    persist_bindings(
        catalog,
        [CodelistBinding("SIHSUS", "CODMUNRES", name, "def", "test.def", 0.9) for name in codelists],
    )
    catalog.execute(
        "INSERT INTO variable_docs (system, field_name, code_system, source, asserted_by) "
        "VALUES ('SIHSUS', 'CODMUNRES', 'external', 'manual', 'test')"
    )
    register_reference_tables(catalog, write_reference_tables(catalog, settings.lake_dir))
    table = pa.table({"CODMUNRES": ["120040"]})

    refused, report = render_table(
        table, store=catalog, lake_root=settings.lake_dir, system="SIHSUS", profile="audit"
    )
    assert "CODMUNRES_label" not in refused.column_names
    assert "CODMUNRES" in report.unlabelled
    key = str(catalog.query("SELECT key FROM adjudication_items")[0]["key"])

    adjudicate(
        catalog,
        key,
        SemanticRelation(
            system="SIHSUS",
            dataset="",
            field_name="CODMUNRES",
            relation_type=RelationType.LABEL_OF,
            target_type="municipality",
            target_name="",
            artifact="RIGHT_MUNIC",
            evidence="reviewed test evidence",
        ),
        by="test-reviewer",
    )
    rendered, _ = render_table(
        table, store=catalog, lake_root=settings.lake_dir, system="SIHSUS", profile="audit"
    )
    assert rendered["CODMUNRES_label"].to_pylist() == ["Rio Branco"]
    assert adjudication_evidence(catalog, key)["status"] == "adjudicated"


def test_dimension_uses_each_rows_semantic_vintage(settings, monkeypatch) -> None:
    import pegasus_data.labelpack as labelpack
    from pegasus_data._query import QueryReport, _apply_dimensions

    calls = []

    def fake_read(codelist, *, system=None, year=None, competencia=None, **_kwargs):
        calls.append((codelist, year, competencia))
        label = "Old region" if competencia == 202001 else "New region"
        return pa.table({"code": ["270430"], "label": [label]})

    monkeypatch.setattr(labelpack, "read_packed", fake_read)
    query_plan = pg.plan(
        "SIH-RD", period=(2020, 2021), dimensions=["MUNIC_RES.health_region"],
        settings=settings,
    )
    table = pa.table(
        {"MUNIC_RES": ["270430", "270430"], "_competencia": [202001, 202101]}
    )
    result = _apply_dimensions(table, query_plan, QueryReport(), settings)
    assert result["MUNIC_RES_health_region"].to_pylist() == ["Old region", "New region"]
    assert {item[2] for item in calls} == {202001, 202101}


def test_adjudicated_dimension_is_effective_immediately(settings, catalog, monkeypatch) -> None:
    import pegasus_data.labelpack as labelpack
    from pegasus_data._query import QueryReport, _apply_dimensions

    key = ensure_adjudication_item(
        catalog, kind="semantic_relation", system="SIHSUS", dataset="SIHSUS.RD",
        field="MUNIC_RES", candidates=["CUSTOM_REGION"], reason="test ambiguity",
    )
    adjudicate(
        catalog,
        key,
        SemanticRelation(
            system="SIHSUS", dataset="SIHSUS.RD", field_name="MUNIC_RES",
            relation_type=RelationType.ROLLUP_TO, target_type="region",
            target_name="custom_region", artifact="CUSTOM_REGION",
            evidence="reviewed test evidence",
        ),
        by="test-reviewer",
    )
    monkeypatch.setattr(
        labelpack,
        "read_packed",
        lambda *_args, **_kwargs: pa.table({"code": ["270430"], "label": ["Reviewed"]}),
    )
    monkeypatch.setattr(labelpack, "packed_mapping_covers_interval", lambda *_a, **_k: True)
    query_plan = pg.plan(
        "SIH-RD", period=2020, dimensions=["MUNIC_RES.custom_region"], settings=settings
    )
    result = _apply_dimensions(
        pa.table({"MUNIC_RES": ["270430"], "_competencia": [202001]}),
        query_plan, QueryReport(), settings,
    )
    assert result["MUNIC_RES_custom_region"].to_pylist() == ["Reviewed"]


def test_relation_validity_selects_historical_artifact(monkeypatch) -> None:
    import pegasus_data.semantics.relations as relation_module

    relations = (
        SemanticRelation(
            "SIHSUS", "SIH.RD", "DIAG_PRINC", RelationType.ROLLUP_TO,
            "chapter", "chapter", "CID_OLD", valid_to="201012",
        ),
        SemanticRelation(
            "SIHSUS", "SIH.RD", "DIAG_PRINC", RelationType.ROLLUP_TO,
            "chapter", "chapter", "CID_NEW", valid_from="201101",
        ),
    )
    monkeypatch.setattr(relation_module, "load_relations", lambda *_args: relations)
    assert relations_for(
        "SIHSUS", "SIH.RD", "DIAG_PRINC",
        relation_type=RelationType.ROLLUP_TO, vintage=201006,
    )[0].artifact == "CID_OLD"
    assert relations_for(
        "SIHSUS", "SIH.RD", "DIAG_PRINC",
        relation_type=RelationType.ROLLUP_TO, vintage=201106,
    )[0].artifact == "CID_NEW"


def test_adjudicated_temporal_history_survives_catalog_reopen(tmp_path) -> None:
    from pegasus_data.catalog.store import Catalog

    path = tmp_path / "temporal.sqlite"
    store = Catalog(path)
    old = SemanticRelation(
        "SIHSUS", "SIH.RD", "DIAG_PRINC", RelationType.ROLLUP_TO,
        "chapter", "chapter", "CID_OLD", valid_to="201012",
    )
    new = SemanticRelation(
        "SIHSUS", "SIH.RD", "DIAG_PRINC", RelationType.ROLLUP_TO,
        "chapter", "chapter", "CID_NEW", valid_from="201101",
    )
    adjudicate(store, "old", old, by="test")
    adjudicate(store, "new", new, by="test")
    assert store.count("semantic_relations") == 2
    store.close()

    reopened = Catalog(path)
    try:
        assert relations_for(
            "SIHSUS", "SIH.RD", "DIAG_PRINC",
            relation_type=RelationType.ROLLUP_TO, catalog=reopened, vintage=201006,
        )[0].artifact == "CID_OLD"
        assert relations_for(
            "SIHSUS", "SIH.RD", "DIAG_PRINC",
            relation_type=RelationType.ROLLUP_TO, catalog=reopened, vintage=201106,
        )[0].artifact == "CID_NEW"
    finally:
        reopened.close()


def test_curated_temporal_history_seeds_as_two_assertions(catalog, tmp_path) -> None:
    (tmp_path / "joins.yml").write_text(
        """
relations:
  - system: SIHSUS
    dataset: SIH.RD
    field: DIAG_PRINC
    relation: rollup_to
    target_type: chapter
    target_name: chapter
    artifact: CID_OLD
    valid_to: '201012'
  - system: SIHSUS
    dataset: SIH.RD
    field: DIAG_PRINC
    relation: rollup_to
    target_type: chapter
    target_name: chapter
    artifact: CID_NEW
    valid_from: '201101'
""".lstrip(),
        encoding="utf-8",
    )
    assert seed_relations(catalog, tmp_path) == 2
    rows = catalog.query(
        "SELECT artifact, valid_from, valid_to FROM semantic_relations "
        "WHERE field_name='DIAG_PRINC' ORDER BY valid_from"
    )
    assert [(row["artifact"], row["valid_from"], row["valid_to"]) for row in rows] == [
        ("CID_OLD", None, "201012"),
        ("CID_NEW", "201101", None),
    ]


def test_overlapping_local_temporal_assertions_are_rejected(catalog) -> None:
    first = SemanticRelation(
        "SIHSUS", "SIH.RD", "FIELD", RelationType.ROLLUP_TO,
        "region", "region", "A", valid_from="202001", valid_to="202012",
    )
    second = SemanticRelation(
        "SIHSUS", "SIH.RD", "FIELD", RelationType.ROLLUP_TO,
        "region", "region", "B", valid_from="202006", valid_to="202105",
    )
    adjudicate(catalog, "first", first, by="test")
    with pytest.raises(ValueError, match="overlapping temporal relation"):
        adjudicate(catalog, "second", second, by="test")


def test_longitudinal_dimension_uses_relation_artifact_per_source_vintage(
    settings, monkeypatch
) -> None:
    import pegasus_data.labelpack as labelpack
    import pegasus_data.semantics.relations as relation_module
    from pegasus_data._query import QueryReport, _apply_dimensions

    relations = (
        SemanticRelation(
            "SIHSUS", "SIH.RD", "DIAG_PRINC", RelationType.ROLLUP_TO,
            "chapter", "chapter", "CID_OLD", valid_to="201012",
        ),
        SemanticRelation(
            "SIHSUS", "SIH.RD", "DIAG_PRINC", RelationType.ROLLUP_TO,
            "chapter", "chapter", "CID_NEW", valid_from="201101",
        ),
    )
    monkeypatch.setattr(relation_module, "load_relations", lambda *_args: relations)
    monkeypatch.setattr(
        labelpack,
        "read_packed",
        lambda artifact, **_kwargs: pa.table(
            {"code": ["A00"], "label": ["old" if artifact == "CID_OLD" else "new"]}
        ),
    )
    monkeypatch.setattr(labelpack, "packed_mapping_covers_interval", lambda *_a, **_k: True)
    query_plan = pg.plan(
        "SIH-RD", period=(2010, 2011), dimensions=["DIAG_PRINC.chapter"],
        settings=settings,
    )
    result = _apply_dimensions(
        pa.table({"DIAG_PRINC": ["A00", "A00"], "_competencia": [201006, 201106]}),
        query_plan, QueryReport(), settings,
    )
    assert result["DIAG_PRINC_chapter"].to_pylist() == ["old", "new"]


def test_dataset_specific_relation_dominates_wildcard(monkeypatch) -> None:
    import pegasus_data.semantics.relations as relation_module

    relations = (
        SemanticRelation(
            "*", "*", "FIELD", RelationType.ROLLUP_TO,
            "region", "region", "GENERIC",
        ),
        SemanticRelation(
            "SIHSUS", "SIH.RD", "FIELD", RelationType.ROLLUP_TO,
            "region", "region", "SPECIFIC",
        ),
    )
    monkeypatch.setattr(relation_module, "load_relations", lambda *_args: relations)
    effective = relations_for(
        "SIHSUS", "SIH.RD", "FIELD", relation_type=RelationType.ROLLUP_TO
    )
    assert [item.artifact for item in effective] == ["SPECIFIC"]


def test_local_reviewed_relation_dominates_shipped_relation(catalog, monkeypatch) -> None:
    import pegasus_data.semantics.relations as relation_module

    shipped = SemanticRelation(
        "SIHSUS", "SIH.RD", "FIELD", RelationType.ROLLUP_TO,
        "region", "region", "SHIPPED",
    )
    monkeypatch.setattr(relation_module, "load_relations", lambda *_args: (shipped,))
    adjudicate(
        catalog,
        "local",
        SemanticRelation(
            "SIHSUS", "SIH.RD", "FIELD", RelationType.ROLLUP_TO,
            "region", "region", "LOCAL",
        ),
        by="test",
    )
    effective = relations_for(
        "SIHSUS", "SIH.RD", "FIELD",
        relation_type=RelationType.ROLLUP_TO, catalog=catalog,
    )
    assert [item.artifact for item in effective] == ["LOCAL"]


def test_unknown_required_dimension_vintage_is_null(settings, monkeypatch) -> None:
    import pegasus_data.labelpack as labelpack
    from pegasus_data._query import QueryReport, _apply_dimensions

    monkeypatch.setattr(labelpack, "packed_mapping_is_time_invariant", lambda *_a, **_k: False)
    monkeypatch.setattr(
        labelpack,
        "read_packed",
        lambda *_a, **_k: pytest.fail("unknown vintage must not read a current mapping"),
    )
    query_plan = pg.plan(
        "SIH-RD", period=2020, dimensions=["MUNIC_RES.health_region"],
        settings=settings,
    )
    report = QueryReport()
    result = _apply_dimensions(
        pa.table({"MUNIC_RES": ["270430"], "_competencia": [None]}),
        query_plan, report, settings,
    )
    assert result["MUNIC_RES_health_region"].to_pylist() == [None]
    assert report.dimensions[0]["unresolved_vintage_rows"] == 1


def test_annual_dimension_uses_mapping_only_when_safe_for_the_whole_year(
    settings, monkeypatch
) -> None:
    import pegasus_data.labelpack as labelpack
    from pegasus_data._query import QueryReport, _apply_dimensions

    calls: list[int] = []

    def stable_mapping(_artifact, *, competencia=None, **_kwargs):
        calls.append(int(competencia))
        return pa.table({"code": ["270430"], "label": ["Stable region"]})

    monkeypatch.setattr(labelpack, "read_packed", stable_mapping)
    query_plan = pg.plan(
        "SIH-RD", period=2020, dimensions=["MUNIC_RES.health_region"],
        settings=settings,
    )
    result = _apply_dimensions(
        pa.table({"MUNIC_RES": ["270430"], "year": [2020], "_competencia": [None]}),
        query_plan, QueryReport(), settings,
    )
    assert result["MUNIC_RES_health_region"].to_pylist() == ["Stable region"]
    assert calls == list(range(202001, 202013))


def test_annual_dimension_is_null_when_relation_changes_midyear(
    settings, monkeypatch
) -> None:
    import pegasus_data.labelpack as labelpack
    import pegasus_data.semantics.relations as relation_module
    from pegasus_data._query import QueryReport, _apply_dimensions

    relations = (
        SemanticRelation(
            "SIHSUS", "SIH.RD", "FIELD", RelationType.ROLLUP_TO,
            "region", "region", "OLD", valid_to="202006",
        ),
        SemanticRelation(
            "SIHSUS", "SIH.RD", "FIELD", RelationType.ROLLUP_TO,
            "region", "region", "NEW", valid_from="202007",
        ),
    )
    monkeypatch.setattr(relation_module, "load_relations", lambda *_args: relations)
    monkeypatch.setattr(
        labelpack,
        "read_packed",
        lambda *_a, **_k: pytest.fail("a changing annual relation must not be read"),
    )
    query_plan = pg.plan(
        "SIH-RD", period=2020, dimensions=["FIELD.region"], settings=settings
    )
    report = QueryReport()
    result = _apply_dimensions(
        pa.table({"FIELD": ["x"], "year": [2020], "_competencia": [None]}),
        query_plan, report, settings,
    )
    assert result["FIELD_region"].to_pylist() == [None]
    assert report.dimensions[0]["unresolved_vintage_rows"] == 1
