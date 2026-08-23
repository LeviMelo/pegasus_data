from __future__ import annotations

import pyarrow as pa

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
