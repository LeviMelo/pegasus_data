"""Choose one physical representation for each logical publication."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .catalog.store import Catalog
from .inventory.families import DECODE_COST_RANK


@dataclass(frozen=True, slots=True)
class RepresentationSelection:
    selected: tuple[dict[str, Any], ...]
    dropped: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


def choose_representations(
    catalog: Catalog, rows: Sequence[Mapping[str, Any]]
) -> RepresentationSelection:
    """Collapse publisher-declared format alternatives, never datasets/members.

    The grouping key is the catalog's logical publication identity plus archive
    member. A multi-member archive therefore contributes every selected member,
    while loose ``.dbc``/``.csv``/Parquet alternatives for one publication
    contribute once. An open conflict keeps every candidate visible.
    """
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for raw in rows:
        row = dict(raw)
        logical = str(row.get("logical_id") or row.get("path") or "")
        member = str(row.get("member") or "")
        groups.setdefault((logical, member), []).append(row)

    logical_ids = sorted({key[0] for key in groups})
    open_conflicts: set[str] = set()
    if logical_ids:
        marks = ",".join("?" for _ in logical_ids)
        try:
            open_conflicts = {
                str(row["logical_id"])
                for row in catalog.query(
                    f"SELECT logical_id FROM representation_conflicts "
                    f"WHERE status = 'open' AND logical_id IN ({marks})",
                    tuple(logical_ids),
                )
            }
        except Exception:  # pragma: no cover - compatibility with old read-only catalogs
            open_conflicts = set()

    selected: list[dict[str, Any]] = []
    dropped: list[str] = []
    conflicts: list[str] = []
    for (logical, _member), candidates in groups.items():
        if len(candidates) == 1:
            selected.extend(candidates)
            continue
        if logical in open_conflicts:
            selected.extend(candidates)
            conflicts.append(logical)
            continue
        winner = min(
            candidates,
            key=lambda row: (
                DECODE_COST_RANK.get(str(row.get("container_format") or "unknown"), 99),
                int(row.get("size") or 0),
                str(row.get("path") or ""),
            ),
        )
        selected.append(winner)
        dropped.extend(
            str(row.get("path") or "") for row in candidates if row is not winner
        )
    return RepresentationSelection(tuple(selected), tuple(dropped), tuple(conflicts))
