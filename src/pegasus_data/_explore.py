"""What is on DATASUS — answered without downloading anything.

DATASUS cannot tell you what it publishes. There is no index, no manifest, no
API that enumerates the tree; there is an FTP server with thirty-five years of
files in directories that have been reorganised more than once. Finding out what
exists has historically meant clicking through it, which is why most people who
use this data use one system, for the years someone told them about.

This module knows, because it crawled the whole thing: 208,095 files on
2026-09-28, each resolved to a system, a series, a year, a state and a schema.
That knowledge is the catalog, and a fresh install's catalog starts as a copy of
the maintainer's (the seed, ADR-0067). So on a fresh install, with no crawl and
no network, ``explore()`` answers immediately.

The four questions, in the order people ask them::

    explore()                      # what systems exist at all?
    explore("SIHSUS")              # what does SIH publish?
    explore("SIH-RD")              # which years, which states, how much?
    explore("SIH-RD", year=2023)   # which files, exactly?

**When the answer is from is part of the answer.** Every result names the date
of the crawl behind it; ``pegasus-data crawl`` brings it up to date (half a
minute for the whole tree).
"""

from __future__ import annotations

import textwrap as _textwrap
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa

from ._request import _ontology
from .config import Settings, load_settings

__all__ = ["explore", "Exploration", "lake_coverage", "publications"]

Level = Literal["systems", "datasets", "coverage", "files"]



@dataclass(slots=True)
class Exploration:
    """The answer, and where it came from."""

    level: Level
    rows: list[dict[str, Any]]
    source: str
    as_of: str | None = None
    target: str | None = None
    total_files: int = 0
    total_bytes: int = 0
    #: Set when the requested thing is not in the map at all, with near misses.
    unknown: list[str] = field(default_factory=list)
    #: Set when a filter was applied to an axis the dataset's files are not split
    #: on. The rows are then empty for a structural reason, not a factual one,
    #: and saying so is the difference between "Acre has no fetal deaths" and
    #: "fetal deaths are not published per state".
    warnings: list[str] = field(default_factory=list)

    @property
    def table(self) -> pa.Table:
        if not self.rows:
            return pa.table({})
        names = list(self.rows[0])
        return pa.table({n: pa.array([r.get(n) for r in self.rows]) for n in names})

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "target": self.target,
            "source": self.source,
            "as_of": self.as_of,
            "rows": self.rows,
            "total_files": self.total_files,
            "total_gigabytes": round(self.total_bytes / 2**30, 2),
            "warnings": self.warnings,
        }

    def __len__(self) -> int:
        return len(self.rows)

    def __iter__(self):
        return iter(self.rows)

    def __repr__(self) -> str:
        head = (
            f"<explore {self.target or 'DATASUS'} — {len(self.rows)} {self.level}, "
            f"{self.total_files:,} files, {self.total_bytes / 2**30:.1f} GiB "
            f"[{self.source}]>"
        )
        notes = ""
        if self.warnings:
            wrapped: list[str] = []
            for w in self.warnings:
                lines = _textwrap.wrap(w, 74) or [w]
                wrapped.append("  ! " + lines[0])
                wrapped.extend("    " + line for line in lines[1:])
            notes = "\n" + "\n".join(wrapped)
        if not self.rows:
            hint = f"  nothing matched; did you mean: {', '.join(self.unknown[:6])}" if self.unknown else ""
            return head + notes + ("\n" + hint if hint else "")
        keys = list(self.rows[0])[:5]
        widths = {
            k: max(len(k), *(len(str(r.get(k, ""))) for r in self.rows[:12])) for k in keys
        }
        lines = ["  " + "  ".join(k.ljust(widths[k]) for k in keys)]
        for row in self.rows[:12]:
            lines.append(
                "  " + "  ".join(str(row.get(k, "")).ljust(widths[k]) for k in keys)
            )
        if len(self.rows) > 12:
            lines.append(f"  … {len(self.rows) - 12} more")
        return head + notes + "\n" + "\n".join(lines)


_FROM = " FROM files f LEFT JOIN file_facts fa ON fa.path = f.path WHERE f.gone_at IS NULL"
#: A file's place and its month, as the counts below read them: present when non-empty (and, for the month, not 0)
_HAS_UF = "(fa.geo_code IS NOT NULL AND fa.geo_code <> '')"
_HAS_MONTH = "(fa.normalized_date IS NOT NULL AND fa.normalized_date <> '' AND fa.normalized_date <> 0)"


def _scope(system: str | None, role: str | None, uf: str | None = None, year: int | None = None,
           series: Sequence[str | None] | None = None) -> tuple[str, list[Any]]:
    """The WHERE clause narrowing the crawl's files in SQL to ``system``, ``role``, a state, a year and, for a dataset,
    the filename series that belong to it. The map holds 207,000 files: every call used to read them all into Python
    and filter there (an `explore`: 2.8 s); it now asks the store for the counts it prints (about 0.1 s)."""
    where, params = "", []
    if system:
        where += " AND upper(fa.system) = ?"
        params.append(system.upper())
    if role:
        where += " AND fa.role = ?"
        params.append(role)
    if uf:
        where += " AND upper(coalesce(fa.geo_code, '')) = ?"
        params.append(uf.upper())
    if year is not None:
        where += " AND fa.year = ?"
        params.append(year)
    if series is not None:
        named = [x for x in series if x is not None]
        clause = f"fa.series_prefix IN ({','.join('?' for _ in named)})" if named else "0"
        if len(named) < len(series):          # None: no series, which the store holds as NULL or as ''
            clause += " OR coalesce(fa.series_prefix, '') = ''"
        where += f" AND ({clause})"
        params += named
    return where, params


def _pairs(store: Any, system: str | None, role: str | None) -> list[tuple[str, str]]:
    """The (system, filename series) pairs of the narrowed files: about 1,500 of the 207,000 files."""
    where, params = _scope(system, role)
    return [(str(r[0] or ""), str(r[1] or "")) for r in store.query(
        f"SELECT fa.system, fa.series_prefix{_FROM}{where} GROUP BY 1, 2", params)]


def _known_systems(settings: Settings, role: str | None) -> list[str]:
    """The systems the catalog lists (for a system it does not know: the nearest are suggested)."""
    from .catalog.store import CatalogStore

    store = CatalogStore(settings.catalog_path, read_only=True)
    try:
        sql = "SELECT DISTINCT system FROM file_facts WHERE system IS NOT NULL" + (" AND role = ?" if role else "")
        return sorted(str(r[0]) for r in store.query(sql, [role] if role else []))
    finally:
        store.close()


def _resolve(target: str | None) -> tuple[str | None, str | None]:
    """``"SIH-RD"`` → ``("SIHSUS", "RD")``; ``"SIHSUS"`` → ``("SIHSUS", None)``."""
    if not target:
        return None, None
    from .retrieve import parse_dataset

    system, series = parse_dataset(target)
    return system, series


def _of_dataset(pairs: list[tuple[str, str]], system: str | None, want_series: str) -> list[tuple[str, str]]:
    """The (system, series) pairs belonging to one dataset, matched through the ontology.

    ``series`` is derived from filenames, so one dataset is spread across many
    spellings of itself — SIA's monthly production is ``PA`` but also
    ``PASP2509A`` and 700-odd other whole filenames. Comparing the string, as
    this did, showed a fraction of what the dataset actually holds, and the
    shortfall was invisible: the map simply looked smaller.

    Same reasoning as :func:`pegasus_data.retrieve._families`, and the same
    fallback — if the ontology cannot name the dataset, the plain match still
    answers.
    """
    from .ontology import Ontology

    try:
        onto = Ontology.load()
    except Exception:  # pragma: no cover - a broken declaration must not block the map
        onto = None

    if onto is not None:
        found = onto.resolve(f"{system}.{want_series}" if system else want_series)
        if found and found[0] == "dataset":
            code = found[1].code
            bound = [pair for pair in pairs if onto.bind(*pair).dataset == code]
            if bound:
                return bound
    return [pair for pair in pairs if pair[1].upper() == want_series]


def _axis_warnings(
    store: Any,
    pairs: Sequence[tuple[str, str]],
    system: str | None,
    series: str | None,
    role: str | None,
    *,
    uf: str | None,
    year: int | None,
) -> list[str]:
    """Flag a filter on an axis these files are not split on.

    ``explore()`` reports rather than raises: its job is to say what is there,
    and "0 files, because this series is published nationally" is a more useful
    answer than an exception. ``fetch()`` raises instead, because by then the
    caller is about to act on the result.

    Measured on the dataset's whole set of files (``pairs``), by the store: which of the files carry a state, a
    year, a month.
    """
    if not (system and series) or not pairs or not (uf or year is not None):
        return []
    from .ontology import DatasetAxes

    where, params = _scope(system, role, series=[pair[1] or None for pair in pairs])
    axes = DatasetAxes(dataset=f"{system}.{series}")
    for has_uf, has_year, has_month, n in store.query(
        f"SELECT {_HAS_UF}, coalesce(fa.year, 0) <> 0, coalesce(length(CAST(fa.normalized_date AS TEXT)), 0) >= 6, "
        f"count(*){_FROM}{where} GROUP BY 1, 2, 3", params):
        axes.observe(uf=bool(has_uf), year=bool(has_year), month=bool(has_month), n=int(n))
    out = []
    for name, asked in (("uf", bool(uf)), ("year", year is not None)):
        if asked and name not in axes.names:
            out.append(
                axes.explain(name)
                + f" Filtering on {name} here matches no file; {name} is a column"
                " inside the data, so load it and filter the table instead."
            )
    return out


def explore(
    target: str | None = None,
    *,
    series: str | None = None,
    year: int | None = None,
    uf: str | None = None,
    role: str | None = "data",
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> Exploration:
    """Ask what DATASUS has, at whatever level of detail the question implies.

    ``explore()`` lists the information systems. Naming a system lists its
    series. Naming a dataset (``"SIH-RD"``) gives its coverage — years, states,
    files, volume. Adding ``year=`` gives the files themselves, with sizes, which
    is what you want before committing to a download.

    ``role`` defaults to ``"data"``; pass ``None`` to include the dictionary,
    documentation and auxiliary files that sit alongside it.
    """
    from .catalog.store import CatalogStore

    resolved = settings or load_settings(root=Path(root) if root else None)
    system, parsed_series = _resolve(target)
    want_series = (series or parsed_series or "").upper() or None
    store = CatalogStore(resolved.catalog_path, read_only=True)
    try:
        if not store.has_rows("files", "gone_at IS NULL"):
            raise FileNotFoundError(
                "the catalog lists no files: run `pegasus-data crawl` (half a minute for the whole tree)"
            )
        as_of = store.scalar("SELECT MAX(finished_at) FROM crawl_runs WHERE finished_at IS NOT NULL")
        origin = "catalog"
        if system and not store.query(f"SELECT 1{_FROM}{_scope(system, role)[0]} LIMIT 1", _scope(system, role)[1]):
            known_systems = _known_systems(resolved, role)
            near = [s for s in known_systems if system[:3] in s or s[:3] in system]
            return Exploration(
                level="systems", rows=[], source=origin, as_of=as_of, target=target,
                unknown=near or known_systems,
            )
        pairs = _of_dataset(_pairs(store, system, role), system, want_series) if want_series else []
        named = {pair[1] or None for pair in pairs}
        # a dataset: the files of its series, within the system the target named
        in_dataset = sorted(named, key=lambda x: (x is None, x or "")) if want_series else None

        # Measured before the filters run, on the dataset's full set of files: once
        # uf= has narrowed the rows to none there is nothing left to measure, and
        # "no files" would look identical whether the axis is absent or the state
        # genuinely has no data.
        warnings = _axis_warnings(store, pairs, system, want_series, role, uf=uf, year=year)
        narrowed = _scope(system, role, uf, year, in_dataset)

        if system and (year is not None or uf):
            level: Level = "files"
            listed = store.query(
                "SELECT f.path, fa.series_prefix, fa.geo_code, fa.normalized_date, f.size, fa.container_format"
                f"{_FROM}{narrowed[0]} ORDER BY f.path", narrowed[1])
            out = [
                {
                    "path": r["path"], "series": r["series_prefix"], "uf": r["geo_code"],
                    "yyyymm": r["normalized_date"], "megabytes": round((r["size"] or 0) / 2**20, 2),
                    "format": r["container_format"],
                }
                for r in listed
            ]
            total_files, total_bytes = len(listed), sum(int(r["size"] or 0) for r in listed)
        elif system and want_series:
            level = "coverage"
            # Chronological, not by volume: coverage is a question about *time*, and
            # the gap someone is looking for is a missing year, which only shows up
            # when the years are in order.
            out = [
                {"year": r["year"], "files": r["n"], "gigabytes": round(int(r["bytes"]) / 2**30, 2),
                 "ufs": r["ufs"], "months": r["months"]}
                for r in store.query(
                    f"SELECT fa.year AS year, count(*) AS n, coalesce(sum(f.size), 0) AS bytes, "
                    f"count(DISTINCT CASE WHEN {_HAS_UF} THEN fa.geo_code END) AS ufs, "
                    f"count(DISTINCT CASE WHEN {_HAS_MONTH} THEN fa.normalized_date END) AS months"
                    f"{_FROM}{narrowed[0]} GROUP BY fa.year ORDER BY fa.year IS NULL, fa.year", narrowed[1])
            ]
            total_files, total_bytes = _totals(store, narrowed)
        else:
            by_uf = bool(system)
            tally = [dict(r) for r in store.query(
                f"SELECT fa.system AS system, fa.series_prefix AS series, {'fa.geo_code' if by_uf else 'NULL'} AS uf, "
                f"count(*) AS n, coalesce(sum(f.size), 0) AS bytes, min(nullif(fa.year, 0)) AS y0, "
                f"max(nullif(fa.year, 0)) AS y1{_FROM}{narrowed[0]} GROUP BY 1, 2, 3", narrowed[1])]
            if want_series:                # a dataset named without a system: the files of the pairs that belong to it
                keep = set(pairs)
                tally = [t for t in tally if (str(t["system"] or ""), str(t["series"] or "")) in keep]
            total_files, total_bytes = sum(t["n"] for t in tally), sum(int(t["bytes"]) for t in tally)
            if system:
                level = "datasets"
                out = _by_dataset(tally, system)
            else:
                level = "systems"
                out = _by_system(tally)
    finally:
        store.close()

    return Exploration(
        level=level, rows=out, source=origin, as_of=as_of, target=target,
        warnings=warnings,
        total_files=total_files, total_bytes=total_bytes,
    )


def _totals(store: Any, narrowed: tuple[str, list[Any]]) -> tuple[int, int]:
    n, size = store.query(f"SELECT count(*), coalesce(sum(f.size), 0){_FROM}{narrowed[0]}", narrowed[1])[0]
    return int(n), int(size)


def _by_dataset(tally: list[dict[str, Any]], system: str) -> list[dict[str, Any]]:
    """Group a system's files by DECLARED dataset, not by filename prefix.

    This is the difference between an answer and a puzzle. Grouping on ``series``
    listed ``HANT``, ``DENG``, ``LEPT`` — filename fragments the caller has to
    already understand — and it listed 992 of them for SIA, because ``series``
    is filename-derived and only 181 of 1,505 observed pairs are clean. The
    institution publishes far fewer things than the tree appears to contain.

    The observed spellings are kept in ``seen_as``: they are evidence of how the
    dataset was recognised, and someone reconciling a path against the map still
    needs them. They are simply no longer the headline.

    ``tally`` is the store's count of files by (system, series, state): a pair is bound to its dataset once.
    """
    onto = _ontology()
    groups: dict[str, dict[str, Any]] = {}
    for row in tally:
        series = str(row["series"] or "")
        code = ""
        if onto is not None:
            code = onto.bind(str(row["system"] or ""), series).dataset or ""
        if not code:
            code = f"{system}.{series}" if series else system
        entry = groups.setdefault(code, {
            "dataset": code, "name": None, "files": 0, "_bytes": 0,
            "_years": [], "_ufs": set(), "_seen": set(),
        })
        entry["files"] += row["n"]
        entry["_bytes"] += int(row["bytes"])
        entry["_years"] += [row["y0"], row["y1"]]
        if row["uf"]:
            entry["_ufs"].add(row["uf"])
        if series:
            entry["_seen"].add(series)

    out = []
    for code, entry in sorted(groups.items()):
        node = onto.datasets.get(code) if onto is not None else None
        seen = sorted(entry["_seen"])
        out.append({
            "dataset": code,
            "name": (node.translated_name or node.official_name) if node else None,
            "files": entry["files"],
            "gigabytes": round(entry["_bytes"] / 2**30, 2),
            "years": _span(entry["_years"]),
            "ufs": len(entry["_ufs"]),
            # Capped: SIA.PA has been seen under 736 filename spellings, and
            # printing all of them would bury the answer it belongs to.
            "seen_as": ", ".join(seen[:4]) + (f" +{len(seen) - 4}" if len(seen) > 4 else ""),
        })
    return sorted(out, key=lambda e: -e["files"])


def _by_system(tally: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The top level, named as the institution names it.

    The crawl says ``SIASUS`` because that is the directory; the institution
    says ``SIA``. The directory name has changed before. ``crawled_as`` keeps
    the tree's spelling visible so a path is still traceable back to a row.

    ``tally`` is the store's count of files by (system, series): each pair is bound to its dataset once, not each file.
    """
    onto = _ontology()
    groups: dict[str, dict[str, Any]] = {}
    for row in tally:
        crawled = str(row["system"] or "")
        if not crawled:
            continue
        node = onto.system_of(crawled) if onto is not None else None
        code = node.code if node else crawled
        entry = groups.setdefault(code, {
            "_node": node, "_crawled": set(), "files": 0, "_bytes": 0,
            "_years": [], "_datasets": set(),
        })
        entry["_crawled"].add(crawled)
        entry["files"] += row["n"]
        entry["_bytes"] += int(row["bytes"])
        entry["_years"] += [row["y0"], row["y1"]]
        bound = onto.bind(crawled, str(row["series"] or "")).dataset if onto else ""
        entry["_datasets"].add(bound or str(row["series"] or ""))

    out = []
    for code, entry in groups.items():
        node = entry["_node"]
        out.append({
            "system": code,
            "name": (node.translated_name or node.official_name) if node else None,
            "files": entry["files"],
            "gigabytes": round(entry["_bytes"] / 2**30, 2),
            "datasets": len({d for d in entry["_datasets"] if d}),
            "years": _span(entry["_years"]),
            "crawled_as": ", ".join(sorted(entry["_crawled"])),
        })
    return sorted(out, key=lambda e: (-e["files"], e["system"]))


def _span(years: list[Any]) -> str:
    real = sorted({int(y) for y in years if y})
    if not real:
        return "—"
    return f"{real[0]}–{real[-1]}" if real[0] != real[-1] else str(real[0])


def lake_coverage(dataset: str, *, root: str | Path | None = None,
                  settings: Settings | None = None) -> dict[int, dict[str, int]]:
    """What the lake already holds of ``dataset``, by year: partitions, states, rows and bytes (the catalog's
    ``lake_partitions`` whose Parquet is on disk). A caller deciding what a reading costs needs it beside ``explore``'s
    published volume: a year in the lake is read in seconds, a year outside it is a download and a decode. A partition
    the catalog records and the disk no longer holds is not the lake's: 448 of SIH-RD's 487 had been deleted and still
    counted, so a study priced national SIH years as free and its lanes, forbidden to download, failed (2026-10-15)."""
    from .catalog.store import CatalogStore

    resolved = settings or load_settings(root=Path(root) if root else None)
    system, series = _resolve(dataset)
    if not system:
        raise ValueError(f"not a dataset: {dataset!r}")
    prefix = f"{system}_{series}_" if series else f"{system}_"
    store = CatalogStore(resolved.catalog_path, read_only=True)
    try:
        lake = Path(resolved.lake_dir)
        rows = [r for r in store.query("SELECT family_id, year, uf, row_count, byte_size, relative_path FROM lake_partitions")
                if str(r["family_id"]).startswith(prefix) and (lake / str(r["relative_path"])).exists()]
    finally:
        store.close()
    out: dict[int, dict[str, Any]] = {}
    for r in rows:
        y = out.setdefault(int(r["year"]), {"partitions": 0, "ufs": set(), "rows": 0, "bytes": 0})
        y["partitions"] += 1
        y["ufs"].add(str(r["uf"]))
        y["rows"] += int(r["row_count"] or 0)
        y["bytes"] += int(r["byte_size"] or 0)
    return {k: {**v, "ufs": len(v["ufs"])} for k, v in sorted(out.items())}


#: The server's directory of files still being collected (SIM, SINASC and SINAN publish their open years there).
PRELIMINARY_TREE = "PRELIM"
_PROVENANCE = ("_source_path", "_blob_sha256", "_ingested_at")


def _years(years: int | Sequence[int] | range | None) -> list[int] | None:
    if years is None:
        return None
    return [int(years)] if isinstance(years, int) else sorted({int(y) for y in years})


def _final_after_years(dataset: str) -> int | None:
    """The years after which the source closes a year of ``dataset`` (its event types' ``source_notes``; the largest
    when several declare one), None when the curation declares none."""
    from .semantics.event_types import event_types

    try:
        declared = event_types(dataset)
    except KeyError:
        return None
    found = [int(e["source_notes"]["final_after_years"]) for e in declared
             if (e.get("source_notes") or {}).get("final_after_years")]
    return max(found) if found else None


def _finality(path: str, year: int | None, seen_at: str | None, final_after: int | None) -> tuple[str, str]:
    """Whether the source marks a file preliminary or final, and the declaration that says so.

    Two declarations count: the server's preliminary tree, and a year closed ``final_after_years`` later. Neither
    declared: ``undeclared``, never final by default."""
    if PRELIMINARY_TREE in {part.upper() for part in path.split("/")}:
        return "preliminary", f"published under the server's {PRELIMINARY_TREE} tree"
    if final_after is None:
        return "undeclared", "no document states when a year of this dataset closes (no final_after_years declared)"
    if year is None or not seen_at:
        return "undeclared", "the file's year or the date it was seen is unknown"
    closes, seen = year + final_after, int(str(seen_at)[:4])
    if seen > closes:
        return "final", f"{year} + final_after_years {final_after} = {closes}, before {seen}, the year the file was seen"
    return "preliminary", (f"{year} + final_after_years {final_after} = {closes}, not before {seen}, "
                           f"the year the file was seen: the year was still open")


def _lake_sources(
    settings: Settings, partitions: Sequence[Any],
) -> tuple[dict[tuple[str, str], dict[str, Any]], dict[str, str]]:
    """What the lake's own rows say of the files they were decoded from: ``{(source path, blob sha256): rows and the
    first ingestion time}``, counted from the dictionaries of the provenance columns, row group by row group (the
    values of a file are constant: 119 million rows of the national SIH-RD 2014-2023 count in 5 s), and ``{path:
    why}`` for the sources of a listed partition whose file cannot be read (never silently absent)."""
    import json

    import numpy as np
    import pyarrow.parquet as pq

    found: dict[tuple[str, str], dict[str, Any]] = {}
    unread: dict[str, str] = {}
    names = list(_PROVENANCE)
    for part in partitions:
        file = settings.lake_dir / str(part["relative_path"])
        try:
            local: dict[tuple[str, str], dict[str, Any]] = {}
            parquet = pq.ParquetFile(file, read_dictionary=names)
            missing = [c for c in names if c not in parquet.schema_arrow.names]
            if missing:
                raise KeyError(f"the partition lacks {missing}")
            for group in range(parquet.num_row_groups):
                columns = [c.combine_chunks() for c in parquet.read_row_group(group, columns=names).columns]
                dictionaries = [c.dictionary.to_pylist() for c in columns]
                if all(len(d) == 1 for d in dictionaries):
                    tally = {(0, 0, 0): len(columns[0])}
                else:
                    sizes = [len(d) for d in dictionaries]
                    key = (columns[0].indices.to_numpy(zero_copy_only=False).astype(np.int64) * sizes[1]
                           + columns[1].indices.to_numpy(zero_copy_only=False)) * sizes[2]                         + columns[2].indices.to_numpy(zero_copy_only=False)
                    unique, counts = np.unique(key, return_counts=True)
                    tally = {(int(k) // (sizes[1] * sizes[2]), int(k) // sizes[2] % sizes[1], int(k) % sizes[2]): int(n)
                             for k, n in zip(unique, counts, strict=True)}
                for (i, j, k), n in tally.items():
                    cell = local.setdefault((dictionaries[0][i], dictionaries[1][j]), {"rows": 0, "at": dictionaries[2][k]})
                    cell["rows"] += n
                    cell["at"] = min(cell["at"], dictionaries[2][k])
            for key_, cell in local.items():
                merged = found.setdefault(key_, {"rows": 0, "at": cell["at"]})
                merged["rows"] += cell["rows"]
                merged["at"] = min(merged["at"], cell["at"])
        except (OSError, KeyError, ValueError) as exc:
            for path in json.loads(part["source_paths"] or "[]"):
                unread[str(path)] = f"the lake partition {part['relative_path']} cannot be read ({type(exc).__name__}: {exc})"
    return found, unread


def publications(
    dataset: str,
    years: int | Sequence[int] | range | None = None,
    *,
    ufs: str | Sequence[str] | None = None,
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> pa.Table:
    """Which published files ``dataset`` was read from, for ``years``: one row per file, read-only.

    The rows are the files the lake holds records of (the provenance every lake row carries: ``_source_path``,
    ``_blob_sha256``) and the files the catalog lists for those years that the lake does not hold, marked
    ``in_lake=False`` with the reason when one is known: a missing file is a recorded gap, never an absence.

    ``path``, ``uf``, ``year``, ``competence``
        the server path, the state (``BR``: national) and year it is published under, and the month (YYYYMM) of a
        monthly file (null for an annual one).
    ``listed_size``, ``listed_modified``, ``listed_at``
        the size and modification date the server listed, and when the catalog last listed the file.
    ``in_lake``, ``lake_note``
        whether the lake holds the file's records, and why not when it does not.
    ``blob_sha256``, ``rows_decoded``, ``decoded_at``
        the digest of the bytes decoded (the one the lake rows carry), the rows of them in the lake (of the whole file:
        a national file holds every state's), and when.
    ``fetched_at``, ``served_by``, ``fetched_size``
        when those bytes were fetched, from where (``mirror:...`` or the server), and their size.
    ``server_changed_since_fetch``
        the listing now differs from the one at the fetch: the server has rewritten the file since.
    ``status``, ``status_basis``
        ``preliminary``, ``final`` or ``undeclared`` and the declaration behind it: the server's PRELIM tree, or
        the dataset's ``final_after_years`` (the event types' ``source_notes``); none declared is ``undeclared``.

    ``ufs`` keeps the files published under those states and the national file, which holds every state: SIM and
    SINASC publish a year as a national file and as one file per state, the lake reads the national one alone, and
    ``ufs="AL"`` finds ``DOBR2014`` among the rows and ``DOAL2014`` marked as the same records.
    """
    from .catalog.store import CatalogStore
    from .retrieve import _families

    resolved = settings or load_settings(root=Path(root) if root else None)
    system, series = _resolve(dataset)
    if not system or not series:
        raise ValueError(f"not a dataset: {dataset!r}")
    wanted_years = _years(years)
    wanted_ufs = None if ufs is None else {u.upper() for u in ([ufs] if isinstance(ufs, str) else ufs)} | {"BR"}
    final_after = _final_after_years(dataset)

    store = CatalogStore(resolved.catalog_path, read_only=True)
    try:
        named = sorted({pair[1] or None for pair in _of_dataset(_pairs(store, system, "data"), system, series.upper())},
                       key=lambda x: (x is None, x or ""))
        where, params = _scope(system, "data", None, None, named)
        if wanted_years is not None:
            where += f" AND fa.year IN ({','.join('?' for _ in wanted_years)})"
            params += wanted_years
        listed = {
            str(r["path"]): dict(r) for r in store.query(
                "SELECT f.path, fa.geo_code, fa.year, fa.normalized_date, fa.logical_id, f.size, f.modified, f.last_seen"
                f"{_FROM}{where} ORDER BY f.path", params)
            if wanted_ufs is None or str(r["geo_code"] or "").upper() in wanted_ufs
        }
        families = [str(f["family_id"]) for f in _families(store, system, series)]
        partitions = [
            dict(r) for start in range(0, len(families), 500) for r in store.query(
                "SELECT uf, year, relative_path, source_paths FROM lake_partitions WHERE family_id IN "
                f"({','.join('?' for _ in families[start:start + 500])})", families[start:start + 500])
            if (wanted_years is None or int(r["year"]) in wanted_years)
            and (wanted_ufs is None or str(r["uf"]).upper() in wanted_ufs)
        ]
        held, unread = _lake_sources(resolved, partitions)
        paths = sorted({*listed, *(p for p, _ in held), *unread})
        facts: dict[str, dict[str, Any]] = {}   # the file name's facts for a path the listing no longer has
        fetches: dict[str, list[dict[str, Any]]] = {}
        errors: dict[str, str] = {}
        for start in range(0, len(paths), 500):
            chunk = paths[start:start + 500]
            marks = ",".join("?" for _ in chunk)
            for r in store.query(
                "SELECT f.path, fa.geo_code, fa.year, fa.normalized_date, fa.logical_id, f.size, f.modified, f.last_seen "
                f"FROM files f LEFT JOIN file_facts fa ON fa.path = f.path WHERE f.path IN ({marks})", chunk):
                facts[str(r["path"])] = dict(r)
            for r in store.query("SELECT source_path, sha256, byte_size, fetched_at, serving_method, remote_size, "
                                 f"remote_modified FROM fetches WHERE source_path IN ({marks}) ORDER BY id", chunk):
                fetches.setdefault(str(r["source_path"]), []).append(dict(r))
            for r in store.query(f"SELECT path, error FROM decode_attempts WHERE ok = 0 AND path IN ({marks})", chunk):
                errors[str(r["path"])] = str(r["error"] or "decoding failed")
    finally:
        store.close()

    national_held = {int(p["year"]) for p in partitions if str(p["uf"]).upper() == "BR"}
    read_from = {
        facts.get(path, {}).get("logical_id") or path: path for path in sorted({p for p, _ in held})
    }
    rows: list[dict[str, Any]] = []
    for path in paths:
        of_file = {**facts.get(path, {}), **listed.get(path, {})}
        geo, year, month = str(of_file.get("geo_code") or "") or None, of_file.get("year"), of_file.get("normalized_date")
        for sha, cell in [(s, c) for (p, s), c in sorted(held.items()) if p == path] or [(None, None)]:
            fetch = next((f for f in fetches.get(path, []) if f["sha256"] == sha), None) if sha else None
            if cell is not None:
                note = None
            elif path in unread:
                note = unread[path]
            elif path in errors:
                note = f"decoding failed: {errors[path]}"
            elif read_from.get(of_file.get("logical_id") or path) not in (None, path):
                note = (f"another publication of {of_file['logical_id']} (a second directory or format); "
                        f"the lake reads {read_from[of_file['logical_id']]}")
            elif geo not in ("BR", None) and year in national_held:
                note = ("the same records are in the national file of the year, which the lake reads alone "
                        "(a year published nationally and per state is read once)")
            else:
                note = "listed by the server, not decoded into the lake"
            status, basis = _finality(path, int(year) if year else None,
                                      fetch["fetched_at"] if fetch else of_file.get("last_seen"), final_after)
            changed = None
            if fetch and fetch["remote_size"] is not None and of_file.get("size") is not None:
                changed = (of_file["size"] != fetch["remote_size"]
                           or (fetch["remote_modified"] is not None and of_file.get("modified") != fetch["remote_modified"]))
            rows.append({
                "dataset": dataset, "path": path, "uf": geo, "year": int(year) if year else None,
                "competence": int(month) if month and int(month) % 100 else None,
                "listed": path in listed, "listed_size": of_file.get("size"), "listed_modified": of_file.get("modified"),
                "listed_at": of_file.get("last_seen"), "in_lake": cell is not None, "lake_note": note,
                "blob_sha256": sha, "rows_decoded": cell["rows"] if cell else None,
                "decoded_at": cell["at"] if cell else None,
                "fetched_at": fetch["fetched_at"] if fetch else None, "served_by": fetch["serving_method"] if fetch else None,
                "fetched_size": fetch["byte_size"] if fetch else None, "server_changed_since_fetch": changed,
                "status": status, "status_basis": basis,
            })
    schema = pa.schema([
        ("dataset", pa.string()), ("path", pa.string()), ("uf", pa.string()), ("year", pa.int32()),
        ("competence", pa.int32()), ("listed", pa.bool_()), ("listed_size", pa.int64()), ("listed_modified", pa.string()),
        ("listed_at", pa.string()), ("in_lake", pa.bool_()), ("lake_note", pa.string()), ("blob_sha256", pa.string()),
        ("rows_decoded", pa.int64()), ("decoded_at", pa.string()), ("fetched_at", pa.string()), ("served_by", pa.string()),
        ("fetched_size", pa.int64()), ("server_changed_since_fetch", pa.bool_()), ("status", pa.string()),
        ("status_basis", pa.string()),
    ])
    return pa.Table.from_pylist(rows, schema=schema).sort_by(
        [("uf", "ascending"), ("year", "ascending"), ("competence", "ascending"), ("path", "ascending")])
