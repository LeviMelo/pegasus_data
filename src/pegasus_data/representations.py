"""Choose one physical representation for each logical publication."""

from __future__ import annotations

from collections.abc import Mapping, Sequence, Set
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from .catalog.store import CatalogStore
from .inventory.families import DECODE_COST_RANK


@dataclass(frozen=True, slots=True)
class RepresentationSelection:
    selected: tuple[dict[str, Any], ...]
    dropped: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


class RepresentationConflictError(RuntimeError):
    """A logical publication has contradictory physical candidates."""


def _majority_layout(catalog: CatalogStore, editions: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """Of editions in DIFFERENT layouts, those in the layout most of the dataset uses.

    SINASC publishes Roraima 1995 as DNRRR1995.dbc under 1994_1995/Dados and
    ANT/ (CONTADOR, 54 files that year) and again as ANT/DNRRR1995.dbc with the
    older CODIGO column (27 files): the same 7,020 records twice. The family with
    more publications is the layout the rest of the dataset is read in (ADR-0081).
    """
    families = {str(row.get("family_id") or "") for row in editions}
    signatures = {str(row.get("schema_signature") or "") for row in editions}
    if len(families) <= 1 or len(signatures) <= 1 or "" in families:
        return list(editions)
    marks = ",".join("?" for _ in families)
    sizes = {
        str(r["family_id"]): int(r["n"])
        for r in catalog.query(
            f"SELECT family_id, COUNT(*) AS n FROM family_files WHERE family_id IN ({marks}) GROUP BY family_id",
            tuple(sorted(families)),
        )
    }
    best = max(sorted(families), key=lambda f: sizes.get(f, 0))
    return [row for row in editions if str(row.get("family_id") or "") == best]


def choose_representations(
    catalog: CatalogStore,
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

    # Conflicts are derived here, from catalog facts re-read on every call; a
    # read never writes them back (ARCHITECTURE §5, 2026-10-04).
    open_conflicts: set[str] = set()

    cached = _cached_paths(catalog, [str(row.get("path") or "") for rows_ in groups.values()
                                     if len(rows_) > 1 for row in rows_])
    export_families = _export_families(catalog, [str(row.get("family_id") or "") for rows_ in groups.values()
                                                 if len(rows_) > 1 for row in rows_])
    unreachable = _unreachable_paths(catalog, [str(row.get("path") or "") for rows_ in groups.values()
                                               if len(rows_) > 1 for row in rows_])
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
        # A zero-byte file is a placeholder, not an alternative, when the same publication has a
        # non-empty one: SIHSUS/2010/XML holds 324 empty RD*.xml beside 200801_/Dados's DBCs,
        # and ranking by bytes on the wire chose the empty file every time (PegaSUS, 2026-10-04).
        empty = [row for row in candidates if row.get("size") == 0]
        if empty and len(empty) < len(candidates):
            dropped.extend(str(row.get("path") or "") for row in empty)
            candidates = [row for row in candidates if row.get("size") != 0]
            if len(candidates) == 1:
                selected.extend(candidates)
                continue
        exports = _exports_behind_native(candidates, unreachable, export_families)
        if exports:
            dropped.extend(str(row.get("path") or "") for row in exports)
            candidates = [row for row in candidates if not any(row is e for e in exports)]
            if len(candidates) == 1:
                selected.extend(candidates)
                continue
        formats = [_representation_kind(row) for row in candidates]
        contradictions: list[str] = []
        if len(formats) != len(set(formats)):
            # Same format twice is only a contradiction when the objects can
            # actually DIFFER. DATASUS mirrors a year into two directories
            # during a tree transition -- SINASC 2022 sits byte-for-byte
            # identical under both 1996_/ and NOV/ -- and refusing a mirror
            # made every dataset in transition unbuildable. Identical size per
            # format is the mirror test available before any byte is fetched.
            # A size that differs is a revision: the newest edition by the
            # server's date wins, and only undated or tied editions refuse.
            by_format: dict[str, set[Any]] = {}
            for row in candidates:
                by_format.setdefault(_representation_kind(row), set()).add(row.get("size"))
            for fmt, sizes in by_format.items():
                if len(sizes) <= 1:
                    continue
                # Two editions of one publication: DATASUS republished it. SIH-RD
                # 2014-2016 sits in /SIHSUS/MHJ_14_16/ (all 972 files dated
                # 2017-10) and again, corrected, in 200801_/Dados/ (2018). The
                # newest edition is the publisher's current word; refusing made
                # SIH unreadable for three years (live run 2026-09-28, ADR-0068).
                editions = [row for row in candidates if _representation_kind(row) == fmt]
                majority = _majority_layout(catalog, editions)
                if len(majority) < len(editions):
                    superseded = [row for row in editions if not any(row is m for m in majority)]
                    dropped.extend(str(row.get("path") or "") for row in superseded)
                    candidates = [row for row in candidates if not any(row is old for old in superseded)]
                    editions = majority
                    if len({row.get("size") for row in editions}) <= 1:
                        continue
                newest = _newest_edition(catalog, editions)
                if newest is None:
                    contradictions.append("multiple objects of the same format")
                    break
                superseded = [row for row in editions if row is not newest]
                dropped.extend(str(row.get("path") or "") for row in superseded)
                candidates = [row for row in candidates if not any(row is old for old in superseded)]
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
        if contradictions:
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
        winner = min(candidates, key=lambda row: _wire_cost(row, cached))
        selected.append(winner)
        dropped.extend(
            str(row.get("path") or "") for row in candidates if row is not winner
        )
    return RepresentationSelection(tuple(selected), tuple(dropped), tuple(conflicts))


def _wire_cost(row: Mapping[str, Any], cached: set[str]) -> tuple[int, int, int, str]:
    """Bytes on the wire first, then decode cost (ADR-0133).

    A copy already in the blob store costs nothing to fetch. Otherwise the
    smaller file wins: SIH-RD Acre 2008-01 is 114 KB as ``.dbc``, 1.05 MB as
    ``.csv`` and 5.1 MB as ``.xml``, and choosing by decode cost alone fetched
    the CSV/XML copies, which the HTTPS mirror (ADR-0122) does not hold, so
    those years came back empty while the FTP was down (2026-10-03).
    """
    path = str(row.get("path") or "")
    size = row.get("size")
    return (
        0 if path in cached else 1,
        int(size) if size is not None else 2**62,
        DECODE_COST_RANK.get(str(row.get("container_format") or "unknown"), 99),
        path,
    )


def _cached_paths(catalog: CatalogStore, paths: Sequence[str]) -> set[str]:
    """Which of ``paths`` were fetched into the blob store before."""
    if not paths:
        return set()
    out: set[str] = set()
    unique = sorted(set(paths))
    for start in range(0, len(unique), 500):
        chunk = unique[start:start + 500]
        marks = ",".join("?" for _ in chunk)
        try:
            out |= {str(r["source_path"]) for r in catalog.query(
                f"SELECT DISTINCT source_path FROM fetches WHERE source_path IN ({marks})", tuple(chunk))}
        except Exception:  # noqa: BLE001 - a catalog without fetch history ranks by size
            return out
    return out


#: The publisher's own record formats. The Dados Abertos exports of the same
#: publication are not equivalent (ADR-0135).
NATIVE_KINDS = frozenset({"dbc", "dbf"})


def _exports_behind_native(
    candidates: Sequence[dict[str, Any]], unreachable: set[str], export_families: Set[str] = frozenset(),
) -> list[dict[str, Any]]:
    """The exports to drop because a native file of the publication can be fetched.

    An export is kept only when every native file has failed on both the FTP
    and the mirror (an open ``fetch`` gap): the mirror holds no
    ``SINAN/DADOS/FINAIS/CHAGBR23.dbc`` (2026-10-03).

    A native-format file in a family that holds XML/CSV/JSON exports IS an
    export copy: SIH's /SIHSUS/DBF/RDAP1401.dbf (95 fields) is laid out like
    the /SIHSUS/XML/ exports of 2013-2014, not like the 113-field .dbc, and
    counting it native made SIH-RD 2014 refuse as a conflict (2026-10-04).
    """

    def is_export(row: Mapping[str, Any]) -> bool:
        return (_representation_kind(row) not in NATIVE_KINDS
                or str(row.get("family_id") or "") in export_families)

    natives = [row for row in candidates if not is_export(row)]
    if not any(str(row.get("path") or "") not in unreachable for row in natives):
        return []
    return [row for row in candidates if is_export(row)]


def _export_families(catalog: CatalogStore, family_ids: Sequence[str]) -> set[str]:
    """Which of these families hold XML, CSV or JSON export files anywhere on the tree."""
    unique = sorted({f for f in family_ids if f})
    out: set[str] = set()
    for start in range(0, len(unique), 500):
        chunk = unique[start:start + 500]
        marks = ",".join("?" for _ in chunk)
        try:
            out |= {str(r["family_id"]) for r in catalog.query(
                f"SELECT DISTINCT family_id FROM family_files WHERE family_id IN ({marks}) "
                "AND (lower(path) LIKE '%.xml' OR lower(path) LIKE '%.xml.zip' OR lower(path) LIKE '%.csv' "
                "OR lower(path) LIKE '%.csv.zip' OR lower(path) LIKE '%.json' OR lower(path) LIKE '%.json.zip')",
                tuple(chunk))}
        except Exception:  # noqa: BLE001 - a catalog without families has no export layouts
            return out
    return out


def _unreachable_paths(catalog: CatalogStore, paths: Sequence[str]) -> set[str]:
    """Which of ``paths`` failed to download from every source and have not since."""
    out: set[str] = set()
    unique = sorted(set(paths))
    for start in range(0, len(unique), 500):
        chunk = unique[start:start + 500]
        marks = ",".join("?" for _ in chunk)
        try:
            out |= {str(r["path"]) for r in catalog.query(
                f"SELECT path FROM coverage_gaps WHERE kind = 'fetch' AND resolved = 0 AND path IN ({marks})",
                tuple(chunk))}
        except Exception:  # noqa: BLE001 - a catalog without gaps treats every file as reachable
            return out
    return out


def _newest_edition(catalog: CatalogStore, candidates: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """The most recently modified candidate, when the server dates them apart.

    Only a same-format revision is resolved this way; ``None`` (no dates, or a
    tie) leaves the conflict to refuse as before.
    """
    paths = [str(row.get("path") or "") for row in candidates]
    marks = ",".join("?" for _ in paths)
    try:
        modified = {
            str(r["path"]): str(r["modified"] or "")
            for r in catalog.query(f"SELECT path, modified FROM files WHERE path IN ({marks})", tuple(paths))
        }
    except Exception:  # noqa: BLE001 - a catalog without dates cannot decide
        return None
    dated = sorted(
        ((modified.get(str(row.get("path") or ""), ""), index) for index, row in enumerate(candidates)),
    )
    if not dated[-1][0] or (len(dated) > 1 and dated[-1][0] == dated[-2][0]):
        return None
    return candidates[dated[-1][1]]  # type: ignore[return-value]


def _representation_kind(row: Mapping[str, Any]) -> str:
    """What a candidate IS, for telling editions from alternatives.

    The outer container is not enough: SINAN's Dados Abertos ship one
    publication as ``.csv.zip``, ``.json.zip`` and ``.xml.zip``, all container
    ``zip`` and all different sizes, and reading them as three editions of one
    format refused ``SINAN-TUBE`` 2022 outright (live run 2026-09-28). The full
    suffix separates them; cost ranking still uses the container.
    """
    from .inventory.naming import strip_container_suffixes

    _stem, suffix, _container = strip_container_suffixes(PurePosixPath(str(row.get("path") or "")).name)
    return (suffix or "").lstrip(".").lower() or str(row.get("container_format") or "unknown")
