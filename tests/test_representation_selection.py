from __future__ import annotations

import json

from pegasus_data.catalog.store import utcnow
from pegasus_data.representations import choose_representations


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


def test_open_conflict_prevents_silent_collapse(catalog) -> None:
    logical = "SIH|RD|AL|2401"
    catalog.execute(
        "INSERT INTO representation_conflicts "
        "(logical_id, representations, evidence, status, noted_at) VALUES (?,?,?,?,?)",
        (logical, json.dumps(["x.dbc", "x.csv"]), "row counts differ", "open", utcnow()),
    )
    choice = choose_representations(
        catalog,
        [_row("x.dbc", logical, "dbc"), _row("x.csv", logical, "csv")],
    )
    assert len(choice.selected) == 2
    assert choice.conflicts == (logical,)


def test_same_format_tie_prefers_the_smaller_physical_payload(catalog) -> None:
    first = _row("large.csv", "SIM|DO|BR|2020", "csv")
    second = _row("small.csv", "SIM|DO|BR|2020", "csv")
    first["size"] = 1_000
    second["size"] = 100
    choice = choose_representations(catalog, [first, second])
    assert [row["path"] for row in choice.selected] == ["small.csv"]
