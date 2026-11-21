"""Choose one physical representation for each logical publication."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Collection, Mapping, Sequence, Set
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
    refused: Collection[str] = (),
) -> RepresentationSelection:
    """Collapse publisher-declared format alternatives, never datasets/members.

    The grouping key is the catalog's logical publication identity plus archive
    member. A multi-member archive therefore contributes every selected member,
    while loose ``.dbc``/``.csv``/Parquet alternatives for one publication
    contribute once. A conflict blocks analytical execution unless an expert
    explicitly requests ``on_conflict="all"`` for inspection.

    ``refused`` names paths that were read and whose columns are not their family's (ADR-0190). They are not
    candidates again, and an export among them is the measurement the family clause of
    `_exports_behind_native` guesses at: the family's layout is the native files', so its native files are read
    before the other exports. A publication left with no candidate selects nothing.
    """
    if on_conflict not in {"error", "all"}:
        raise ValueError("on_conflict must be 'error' or 'all'")
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    export_refused: set[tuple[str, str]] = set()
    for raw in rows:
        row = dict(raw)
        logical = str(row.get("logical_id") or row.get("path") or "")
        member = str(row.get("member") or "")
        if str(row.get("path") or "") in refused:
            if _representation_kind(row) not in NATIVE_KINDS:
                export_refused.add((logical, member))
            continue
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
    measured = _measured_signatures(catalog, [str(row.get("path") or "") for rows_ in groups.values()
                                              if len(rows_) > 1 for row in rows_])
    selected: list[dict[str, Any]] = []
    dropped: list[str] = []
    conflicts: list[str] = []
    for (logical, member_key), candidates in groups.items():
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
        exports = _exports_behind_native(
            candidates, unreachable, export_families, family_layout_is_native=(logical, member_key) in export_refused)
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
        # Only a signature read from the file itself is a claim about its layout. A file the census never read carries
        # its family's signature by inference (`family_files`), and two byte-identical mirrors cannot hold two layouts:
        # SIH-RD 2014's /SIHSUS/MHJ_14_16/RDAL1401.dbc (963,086 bytes, never read) sits in the family of the
        # 2013-2014 DBF/XML exports while its mirror /SIHSUS/200801_/Dados/RDAL1401.dbc (963,086 bytes, read: 113
        # fields) is in the current family, and comparing the two signatures refused every SIH-RD 2014 month
        # (toxoplasmosis study, 2026-11-05).
        signatures = {
            measured[str(row.get("path") or "")]
            for row in candidates
            if str(row.get("path") or "") in measured
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


@dataclass(frozen=True, slots=True)
class FamilyFiles:
    """One family's files: every member the catalog lists, and the ones this request selected (in year, path order)."""

    members: list[dict[str, Any]]
    selected: list[dict[str, Any]]


@dataclass(frozen=True, slots=True)
class PublicationSelection:
    """`select_publications`' answer: each family's files, and what choosing among representations dropped or refused."""

    families: dict[str, FamilyFiles]
    dropped: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()


def select_publications(
    catalog: CatalogStore,
    family_ids: Sequence[str],
    *,
    ufs: Sequence[str] = (),
    years: Sequence[int] = (),
    months: Sequence[int] = (),
    exclude_paths: frozenset[str] = frozenset(),
    narrow: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
) -> PublicationSelection:
    """The files of ``family_ids`` that answer states, years and months (an empty axis asks for all), one
    representation per publication, chosen once across the families: a publication filed under two families (the
    same file in two generations) is chosen once.

    ``exclude_paths`` are files read and refused (ADR-0190): never selected, and the evidence that puts a native file
    ahead of its exports. ``narrow`` is applied to the matching rows before the choice (the reader that wants one
    reading of a year published nationally and per state); it may report what it leaves out."""
    from .normalize.time import month_of

    uf_set = {str(u) for u in ufs} if ufs else None
    year_set = {int(y) for y in years} if years else None
    month_set = {int(m) for m in months} if months else None

    def on_axes(row: Mapping[str, Any]) -> bool:
        return (
            (uf_set is None or (row["geo_code"] or "") in uf_set)
            and (year_set is None or row["year"] in year_set)
            and (month_set is None or month_of(row["normalized_date"]) in month_set)
        )

    chosen: set[tuple[str, str, str]] = set()
    dropped: tuple[str, ...] = ()
    conflicts: tuple[str, ...] = ()
    if family_ids:
        marks = ",".join("?" for _ in family_ids)
        global_rows = catalog.query(
            f"""
            SELECT ff.family_id, ff.path, ff.member, fa.geo_code, fa.year,
                   fa.normalized_date, fa.logical_id, fa.container_format,
                   files.size, families.schema_signature
              FROM family_files ff
              JOIN families ON families.family_id=ff.family_id
              LEFT JOIN file_facts fa ON fa.path=ff.path
              LEFT JOIN files ON files.path=ff.path
             WHERE ff.family_id IN ({marks})
            """,
            tuple(family_ids),
        )
        asked = [dict(row) for row in global_rows if on_axes(row)]
        matched = [row for row in asked if str(row["path"]) not in exclude_paths]
        if narrow is not None:
            matched = narrow(matched)
        # the refused ones are evidence for the choice, not candidates: an export refused for its columns puts the
        # publication's native file ahead of its other exports (ADR-0190)
        choice = choose_representations(
            catalog, [*matched, *(row for row in asked if str(row["path"]) in exclude_paths)],
            refused=exclude_paths)
        chosen = {(str(row["family_id"]), str(row["path"]), str(row.get("member") or "")) for row in choice.selected}
        dropped, conflicts = choice.dropped, choice.conflicts
    families: dict[str, FamilyFiles] = {}
    for family_id in family_ids:
        members = [
            dict(r)
            for r in catalog.query(
                """
                SELECT ff.path, ff.member, fa.geo_code, fa.year, fa.normalized_date,
                       fa.logical_id, fa.container_format, files.size
                  FROM family_files ff
                  LEFT JOIN file_facts fa ON fa.path = ff.path
                  LEFT JOIN files ON files.path = ff.path
                 WHERE ff.family_id = ?
                 ORDER BY fa.year, ff.path
                """,
                (family_id,),
            )
        ]
        selected = [
            m for m in members
            if on_axes(m) and (str(family_id), str(m["path"]), str(m["member"] or "")) in chosen
        ]
        families[family_id] = FamilyFiles(members=members, selected=selected)
    return PublicationSelection(families, dropped, conflicts)


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


def _lacks(exc: sqlite3.OperationalError) -> bool:
    """Whether the catalog lacks the table or column asked (an older catalog), as opposed to failing to answer: a
    locked or unreadable one is not an empty one, and must not be read as "every file reachable"."""
    return "no such table" in str(exc) or "no such column" in str(exc)


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
        except sqlite3.OperationalError as exc:      # a catalog without fetch history ranks by size
            if not _lacks(exc):
                raise
            return out
    return out


#: The publisher's own record formats. The Dados Abertos exports of the same
#: publication are not equivalent (ADR-0135).
NATIVE_KINDS = frozenset({"dbc", "dbf"})


def _exports_behind_native(
    candidates: Sequence[dict[str, Any]], unreachable: set[str], export_families: Set[str] = frozenset(),
    *, family_layout_is_native: bool = False,
) -> list[dict[str, Any]]:
    """The exports to drop because a native file of the publication can be fetched.

    An export is kept only when every native file has failed on both the FTP
    and the mirror (an open ``fetch`` gap): the mirror holds no
    ``SINAN/DADOS/FINAIS/CHAGBR23.dbc`` (2026-10-03).

    A native-format file in a family that holds XML/CSV/JSON exports IS an
    export copy: SIH's /SIHSUS/DBF/RDAP1401.dbf (95 fields) is laid out like
    the /SIHSUS/XML/ exports of 2013-2014, not like the 113-field .dbc, and
    counting it native made SIH-RD 2014 refuse as a conflict (2026-10-04).

    That is a guess from the family's membership, and about DBF only: a ``.dbc`` is never an export copy (none lies
    under ``Dados_Abertos``); SINAN-DENG's families hold the Dados Abertos CSVs, and counting its DBCs as exports chose
    ``DENGBR20.csv.zip`` (with 538,654 discarded notifications and no ``DT_DIGITA``) over ``FINAIS/DENGBR20.dbc``. When an
    export of this publication has been read and refused for
    its columns (``family_layout_is_native``), the family's layout is known to be the native files', and the guess
    no longer applies: SINAN's families are the DBC's schema with the Dados Abertos exports hung on it, and
    CHIK 2016's CSV carries 38 of the DBC's 122 columns (ADR-0190).
    """

    def is_export(row: Mapping[str, Any]) -> bool:
        kind = _representation_kind(row)
        if kind not in NATIVE_KINDS:
            return True
        # the guess is about uncompressed DBF copies (SIH's /SIHSUS/DBF/): a DBC is DATASUS's own compressed file,
        # never an export (no .dbc lies under Dados_Abertos), and taking SINAN's for exports read DENG 2020 from its CSV
        return kind != "dbc" and not family_layout_is_native and str(row.get("family_id") or "") in export_families

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
        except sqlite3.OperationalError as exc:      # a catalog without families has no export layouts
            if not _lacks(exc):
                raise
            return out
    return out


def _measured_signatures(catalog: CatalogStore, paths: Sequence[str]) -> dict[str, str]:
    """``{path: schema signature}`` for the ``paths`` whose header the census read without error (``file_schemas``)."""
    out: dict[str, str] = {}
    unique = sorted(set(paths))
    for start in range(0, len(unique), 500):
        chunk = unique[start:start + 500]
        marks = ",".join("?" for _ in chunk)
        try:
            out |= {str(r["path"]): str(r["schema_signature"]) for r in catalog.query(
                f"SELECT path, schema_signature FROM file_schemas WHERE path IN ({marks}) "
                "AND schema_signature IS NOT NULL AND schema_signature <> '' AND (error IS NULL OR error = '')",
                tuple(chunk))}
        except sqlite3.OperationalError as exc:      # a catalog without a census has measured nothing
            if not _lacks(exc):
                raise
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
        except sqlite3.OperationalError as exc:      # a catalog without gaps treats every file as reachable
            if not _lacks(exc):
                raise
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
    except sqlite3.OperationalError as exc:          # a catalog without dates cannot decide
        if not _lacks(exc):
            raise
        return None
    dated = sorted(
        ((modified.get(str(row.get("path") or ""), ""), index) for index, row in enumerate(candidates)),
    )
    if not dated[-1][0] or (len(dated) > 1 and dated[-1][0] == dated[-2][0]):
        return None
    return candidates[dated[-1][1]]  # type: ignore[return-value]


def other_edition(first: Mapping[str, Any], second: Mapping[str, Any]) -> bool:
    """Are these two rows of one publication two EDITIONS, not one file twice or two formats of it?

    The same kind of file at another path with another size: DATASUS republished it (SIH-RD 2014-2016, corrected in
    2018), as `choose_representations` reads it. A different kind is an alternative representation of the same
    records, and the same size at another path is a mirror: neither changes what the records are.
    """
    return (
        str(first.get("path") or "") != str(second.get("path") or "")
        and _representation_kind(first) == _representation_kind(second)
        and first.get("size") != second.get("size")
    )


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
