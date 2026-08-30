"""Choose one physical representation for each logical publication."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .catalog.store import Catalog, utcnow
from .inventory.families import DECODE_COST_RANK


@dataclass(frozen=True, slots=True)
class RepresentationSelection:
    selected: tuple[dict[str, Any], ...]
    dropped: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


class RepresentationConflictError(RuntimeError):
    """A logical publication has contradictory physical candidates."""


def choose_representations(
    catalog: Catalog,
    rows: Sequence[Mapping[str, Any]],
    *,
    on_conflict: str = "error",
) -> RepresentationSelection:
    """Collapse publisher-declared format alternatives, never datasets/members.

    The grouping key is the catalog's logical publication identity plus archive
    member. A multi-member archive therefore contributes every selected member,
    while loose ``.dbc``/``.csv``/Parquet alternatives for one publication
    contribute once. A conflict blocks analytical execution unless an expert
    explicitly requests ``on_conflict="all"`` for inspection.
    """
    if on_conflict not in {"error", "all"}:
        raise ValueError("on_conflict must be 'error' or 'all'")
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
        if logical in open_conflicts:
            conflicts.append(logical)
            if on_conflict == "all":
                selected.extend(candidates)
                continue
            raise RepresentationConflictError(
                f"logical publication {logical!r} has conflicting representations; "
                "runtime execution refused to avoid duplicate observations"
            )
        if len(candidates) == 1:
            selected.extend(candidates)
            continue
        formats = [str(row.get("container_format") or "unknown") for row in candidates]
        contradictions: list[str] = []
        if len(formats) != len(set(formats)):
            # Same format twice is only a contradiction when the objects can
            # actually DIFFER. DATASUS mirrors a year into two directories
            # during a tree transition -- SINASC 2022 sits byte-for-byte
            # identical under both 1996_/ and NOV/ -- and refusing a mirror
            # made every dataset in transition unbuildable. Identical size per
            # format is the mirror test available before any byte is fetched;
            # a size that differs is a real conflict and still refuses.
            by_format: dict[str, set[Any]] = {}
            for row in candidates:
                by_format.setdefault(
                    str(row.get("container_format") or "unknown"), set()
                ).add(row.get("size"))
            if any(len(sizes) > 1 for sizes in by_format.values()):
                contradictions.append("multiple objects of the same format")
        row_counts = {int(row["row_count"]) for row in candidates if row.get("row_count") is not None}
        if len(row_counts) > 1:
            contradictions.append(f"contradictory row counts {sorted(row_counts)}")
        signatures = {
            str(row["schema_signature"])
            for row in candidates
            if row.get("schema_signature")
        }
        if len(signatures) > 1:
            contradictions.append("contradictory schema signatures")
        if contradictions and logical not in open_conflicts:
            import json

            try:
                with catalog.write() as conn:
                    conn.execute(
                        "INSERT INTO representation_conflicts "
                        "(logical_id, representations, evidence, status, noted_at) "
                        "VALUES (?,?,?,?,?) ON CONFLICT(logical_id) DO NOTHING",
                        (
                            logical,
                            json.dumps(
                                [
                                    {
                                        "path": row.get("path"),
                                        "format": row.get("container_format"),
                                        "size": row.get("size"),
                                    }
                                    for row in candidates
                                ],
                                sort_keys=True,
                            ),
                            "; ".join(contradictions) + " claim one logical publication",
                            "open",
                            utcnow(),
                        ),
                    )
            except Exception:  # pragma: no cover - read-only catalogs still refuse
                pass
            open_conflicts.add(logical)
        if logical in open_conflicts:
            conflicts.append(logical)
            if on_conflict == "all":
                selected.extend(candidates)
                continue
            raise RepresentationConflictError(
                f"logical publication {logical!r} has conflicting representations; "
                "runtime execution refused to avoid duplicate observations"
            )
        winner = min(
            candidates,
            key=lambda row: (
                DECODE_COST_RANK.get(str(row.get("container_format") or "unknown"), 99),
                str(row.get("path") or ""),
            ),
        )
        selected.append(winner)
        dropped.extend(
            str(row.get("path") or "") for row in candidates if row is not winner
        )
    return RepresentationSelection(tuple(selected), tuple(dropped), tuple(conflicts))
