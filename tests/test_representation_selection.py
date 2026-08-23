from __future__ import annotations

import json

import pytest

from pegasus_data.catalog.store import utcnow
from pegasus_data.representations import RepresentationConflictError, choose_representations


def _row(path: str, logical: str, fmt: str, member: str = "") -> dict[str, object]:
    return {
        "path": path,
        "logical_id": logical,
        "container_format": fmt,
        "member": member,
        "size": 100,
    }


def test_one_logical_publication_contributes_one_preferred_format(catalog) -> None:
    choice = choose_representations(
        catalog,
        [_row("x.dbc", "SIH|RD|AL|2401", "dbc"), _row("x.parquet", "SIH|RD|AL|2401", "parquet")],
    )
    assert [row["path"] for row in choice.selected] == ["x.parquet"]
    assert choice.dropped == ("x.dbc",)


def test_identical_schemas_do_not_merge_distinct_publications(catalog) -> None:
    choice = choose_representations(
        catalog,
        [_row("jan.dbc", "SIH|RD|AL|2401", "dbc"), _row("feb.dbc", "SIH|RD|AL|2402", "dbc")],
    )
    assert len(choice.selected) == 2


def test_archive_members_remain_distinct(catalog) -> None:
    rows = [_row("kit.exe", "SIA|KIT|BR|0201", "lha_sfx", member) for member in ("AB.dbf", "AD.dbf")]
    assert len(choose_representations(catalog, rows).selected) == 2


def test_open_conflict_refuses_analytical_execution(catalog) -> None:
    logical = "SIH|RD|AL|2401"
    catalog.execute(
        "INSERT INTO representation_conflicts "
        "(logical_id, representations, evidence, status, noted_at) VALUES (?,?,?,?,?)",
        (logical, json.dumps(["x.dbc", "x.csv"]), "row counts differ", "open", utcnow()),
    )
    with pytest.raises(RepresentationConflictError, match="duplicate observations"):
        choose_representations(
            catalog,
            [_row("x.dbc", logical, "dbc"), _row("x.csv", logical, "csv")],
        )
    choice = choose_representations(
        catalog,
        [_row("x.dbc", logical, "dbc"), _row("x.csv", logical, "csv")],
        on_conflict="all",
    )
    assert len(choice.selected) == 2
    assert choice.conflicts == (logical,)


def test_open_conflict_also_refuses_a_singleton_candidate(catalog) -> None:
    logical = "SIH|RD|AL|2401"
    catalog.execute(
        "INSERT INTO representation_conflicts "
        "(logical_id, representations, evidence, status, noted_at) VALUES (?,?,?,?,?)",
        (logical, json.dumps(["x.dbc", "x.csv"]), "schema differs", "open", utcnow()),
    )
    with pytest.raises(RepresentationConflictError, match="runtime execution refused"):
        choose_representations(catalog, [_row("x.dbc", logical, "dbc")])


def test_cross_family_schema_contradiction_is_detected_globally(catalog) -> None:
    first = _row("x.dbc", "SIH|RD|AL|2401", "dbc")
    second = _row("x.parquet", "SIH|RD|AL|2401", "parquet")
    first["family_id"], first["schema_signature"] = "F1", "schema-a"
    second["family_id"], second["schema_signature"] = "F2", "schema-b"
    with pytest.raises(RepresentationConflictError, match="runtime execution refused"):
        choose_representations(catalog, [first, second])


def test_same_format_collision_opens_conflict_and_refuses(catalog) -> None:
    first = _row("large.csv", "SIM|DO|BR|2020", "csv")
    second = _row("small.csv", "SIM|DO|BR|2020", "csv")
    first["size"] = 1_000
    second["size"] = 100
    with pytest.raises(RepresentationConflictError):
        choose_representations(catalog, [first, second])
    assert catalog.count("representation_conflicts", "status='open'") == 1


def test_cheap_row_count_contradiction_refuses_alternate_formats(catalog) -> None:
    first = _row("x.dbc", "SIH|RD|AL|2401", "dbc")
    second = _row("x.parquet", "SIH|RD|AL|2401", "parquet")
    first["row_count"] = 100
    second["row_count"] = 99
    with pytest.raises(RepresentationConflictError):
        choose_representations(catalog, [first, second])
