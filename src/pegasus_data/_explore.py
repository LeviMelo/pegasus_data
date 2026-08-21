"""What is on DATASUS — answered without downloading anything.

DATASUS cannot tell you what it publishes. There is no index, no manifest, no
API that enumerates the tree; there is an FTP server with thirty-five years of
files in directories that have been reorganised more than once. Finding out what
exists has historically meant clicking through it, which is why most people who
use this data use one system, for the years someone told them about.

This module knows, because it crawled the whole thing: 207,251 files, each
resolved to a system, a series, a year, a state and a schema. That knowledge
compresses to about a megabyte, so it **ships with the package**. On a fresh
install, with no crawl and no network, ``explore()`` answers immediately.

The four questions, in the order people ask them::

    explore()                      # what systems exist at all?
    explore("SIHSUS")              # what does SIH publish?
    explore("SIH-RD")              # which years, which states, how much?
    explore("SIH-RD", year=2023)   # which files, exactly?

**Where the answer comes from is part of the answer.** A local crawl is current
and authoritative; the shipped map is a snapshot from when the package was built
and DATASUS moves things. Every result names its source and its date rather than
presenting a two-year-old snapshot as the state of the server.
"""

from __future__ import annotations

import json
import textwrap as _textwrap
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa

from .config import Settings, load_settings

__all__ = ["explore", "Exploration", "tree_snapshot"]

Level = Literal["systems", "datasets", "coverage", "files"]
Source = Literal["auto", "local", "packaged"]

#: Columns of the shipped map, in the order the resource stores them.
_TREE_COLUMNS = (
    "path", "system", "series", "uf", "year", "yyyymm", "size", "role", "format",
    "logical_id",
)


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


def _resource(name: str) -> Path | None:
    from importlib.resources import files as _files

    try:
        path = _files("pegasus_data.resources") / name
    except (ModuleNotFoundError, FileNotFoundError):
        return None
    try:
        return Path(str(path)) if Path(str(path)).exists() else None
    except OSError:
        return None


def tree_snapshot() -> tuple[list[dict[str, Any]], str | None]:
    """The shipped map, with the date of the crawl that produced it."""
    path = _resource("tree.parquet")
    if path is None:
        return [], None
    import pyarrow.parquet as pq

    table = pq.read_table(path)
    rows = table.to_pylist()
    as_of = None
    manifest = _resource("manifest.json")
    if manifest is not None:
        try:
            as_of = json.loads(manifest.read_text(encoding="utf-8")).get("crawled_at")
        except (json.JSONDecodeError, OSError):
            as_of = None
    return rows, as_of


def _from_catalog(settings: Settings) -> tuple[list[dict[str, Any]], str | None] | None:
    """The local crawl, when there is one. Always preferred: it is current."""
    if not settings.catalog_path.exists():
        return None
    from .catalog.store import Catalog

    store = Catalog(settings.catalog_path, read_only=True)
    try:
        if not store.count("files", "gone_at IS NULL"):
            return None
        rows = [
            {
                "path": r["path"], "system": r["system"], "series": r["series_prefix"],
                "uf": r["geo_code"], "year": r["year"], "yyyymm": r["normalized_date"],
                "size": r["size"], "role": r["role"], "format": r["container_format"],
                "logical_id": r["logical_id"],
            }
            for r in store.query(
                """
                SELECT f.path, fa.system, fa.series_prefix, fa.geo_code, fa.year,
                       fa.normalized_date, f.size, fa.role, fa.container_format,
                       fa.logical_id
                  FROM files f LEFT JOIN file_facts fa ON fa.path = f.path
                 WHERE f.gone_at IS NULL
                """
            )
        ]
        as_of = store.scalar(
            "SELECT MAX(finished_at) FROM crawl_runs WHERE finished_at IS NOT NULL"
        )
        return rows, as_of
    finally:
        store.close()


def _resolve(target: str | None) -> tuple[str | None, str | None]:
    """``"SIH-RD"`` → ``("SIHSUS", "RD")``; ``"SIHSUS"`` → ``("SIHSUS", None)``."""
    if not target:
        return None, None
    from .retrieve import parse_dataset

    system, series = parse_dataset(target)
    return system, series


def _of_dataset(
    rows: list[dict[str, object]], system: str | None, want_series: str
) -> list[dict[str, object]]:
    """Rows belonging to one dataset, matched through the ontology.

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
            bound = [
                r
                for r in rows
                if onto.bind(
                    str(r.get("system") or ""), str(r.get("series") or "")
                ).dataset
                == code
            ]
            if bound:
                return bound
    return [r for r in rows if (r.get("series") or "").upper() == want_series]


def _axis_warnings(
    rows: list[dict[str, Any]],
    system: str | None,
    series: str | None,
    *,
    uf: str | None,
    year: int | None,
) -> list[str]:
    """Flag a filter on an axis these files are not split on.

    ``explore()`` reports rather than raises: its job is to say what is there,
    and "0 files, because this series is published nationally" is a more useful
    answer than an exception. ``fetch()`` raises instead, because by then the
    caller is about to act on the result.
    """
    if not (system and series) or not rows or not (uf or year is not None):
        return []
    from .ontology import DatasetAxes

    axes = DatasetAxes.measure(f"{system}.{series}", rows)
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
    source: Source = "auto",
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

    ``source`` is ``"auto"`` — a local crawl if one exists, otherwise the map
    shipped with the package. ``"packaged"`` forces the snapshot, which is how
    you ask what the tree looked like at release rather than now.
    """
    resolved = settings or load_settings(root=Path(root) if root else None)
    rows: list[dict[str, Any]] = []
    as_of: str | None = None
    origin = ""

    if source in ("auto", "local"):
        local = _from_catalog(resolved)
        if local is not None:
            rows, as_of = local
            origin = "local crawl"
    if not rows and source in ("auto", "packaged"):
        rows, as_of = tree_snapshot()
        origin = "packaged snapshot"
    if not rows:
        raise FileNotFoundError(
            "no map of DATASUS is available: this build ships none and no local "
            "crawl exists. Run `pegasus-data crawl`, or install a build that "
            "carries the snapshot."
        )

    system, parsed_series = _resolve(target)
    want_series = (series or parsed_series or "").upper() or None
    if role:
        rows = [r for r in rows if (r.get("role") or "") == role]
    known_systems = sorted({str(r["system"]) for r in rows if r.get("system")})
    if system:
        rows = [r for r in rows if (r.get("system") or "").upper() == system]
        if not rows:
            near = [s for s in known_systems if system[:3] in s or s[:3] in system]
            return Exploration(
                level="systems", rows=[], source=origin, as_of=as_of, target=target,
                unknown=near or known_systems,
            )
    if want_series:
        rows = _of_dataset(rows, system, want_series)

    # Measured before the filters run, on the dataset's full set of files: once
    # uf= has narrowed the rows to none there is nothing left to measure, and
    # "no files" would look identical whether the axis is absent or the state
    # genuinely has no data.
    warnings = _axis_warnings(rows, system, want_series, uf=uf, year=year)

    if uf:
        rows = [r for r in rows if (r.get("uf") or "").upper() == uf.upper()]
    if year is not None:
        rows = [r for r in rows if r.get("year") == year]

    total_files = len(rows)
    total_bytes = sum(int(r.get("size") or 0) for r in rows)

    if system and (year is not None or uf):
        level: Level = "files"
        listed = sorted(rows, key=lambda r: str(r.get("path")))
        out = [
            {
                "path": r["path"], "series": r.get("series"), "uf": r.get("uf"),
                "yyyymm": r.get("yyyymm"), "megabytes": round((r.get("size") or 0) / 2**20, 2),
                "format": r.get("format"),
            }
            for r in listed
        ]
    elif system and want_series:
        level = "coverage"
        # Chronological, not by volume: coverage is a question about *time*, and
        # the gap someone is looking for is a missing year, which only shows up
        # when the years are in order.
        out = _group(
            rows, ("year",),
            extra=lambda group: {
                "ufs": len({g.get("uf") for g in group if g.get("uf")}),
                "months": len({g.get("yyyymm") for g in group if g.get("yyyymm")}),
            },
            order=lambda e: (e["year"] is None, e["year"]),
        )
    elif system:
        level = "datasets"
        out = _by_dataset(rows, system)
    else:
        level = "systems"
        out = _by_system(rows)

    return Exploration(
        level=level, rows=out, source=origin, as_of=as_of, target=target,
        warnings=warnings,
        total_files=total_files, total_bytes=total_bytes,
    )


def _ontology():
    """The declaration, or ``None`` if it cannot be read.

    ``explore()`` must keep answering from a bare crawl even when the
    declaration is missing or malformed — a broken YAML file is a curation
    problem, not a reason the map of the server stops working.
    """
    from .ontology import Ontology

    try:
        return Ontology.load()
    except Exception:  # noqa: BLE001 - a broken declaration must not blank the map
        return None


def _by_dataset(rows: list[dict[str, Any]], system: str) -> list[dict[str, Any]]:
    """Group a system's files by DECLARED dataset, not by filename prefix.

    This is the difference between an answer and a puzzle. Grouping on ``series``
    listed ``HANT``, ``DENG``, ``LEPT`` — filename fragments the caller has to
    already understand — and it listed 992 of them for SIA, because ``series``
    is filename-derived and only 181 of 1,505 observed pairs are clean. The
    institution publishes far fewer things than the tree appears to contain.

    The observed spellings are kept in ``seen_as``: they are evidence of how the
    dataset was recognised, and someone reconciling a path against the map still
    needs them. They are simply no longer the headline.
    """
    onto = _ontology()
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        series = str(row.get("series") or "")
        code = ""
        if onto is not None:
            code = onto.bind(str(row.get("system") or ""), series).dataset or ""
        if not code:
            code = f"{system}.{series}" if series else system
        entry = groups.setdefault(code, {
            "dataset": code, "name": None, "files": 0, "_bytes": 0,
            "_years": [], "_ufs": set(), "_seen": set(),
        })
        entry["files"] += 1
        entry["_bytes"] += int(row.get("size") or 0)
        entry["_years"].append(row.get("year"))
        if row.get("uf"):
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


def _by_system(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The top level, named as the institution names it.

    The crawl says ``SIASUS`` because that is the directory; the institution
    says ``SIA``. The directory name has changed before. ``crawled_as`` keeps
    the tree's spelling visible so a path is still traceable back to a row.
    """
    onto = _ontology()
    groups: dict[str, dict[str, Any]] = {}
    for row in rows:
        crawled = str(row.get("system") or "")
        if not crawled:
            continue
        node = onto.system_of(crawled) if onto is not None else None
        code = node.code if node else crawled
        entry = groups.setdefault(code, {
            "_node": node, "_crawled": set(), "files": 0, "_bytes": 0,
            "_years": [], "_datasets": set(),
        })
        entry["_crawled"].add(crawled)
        entry["files"] += 1
        entry["_bytes"] += int(row.get("size") or 0)
        entry["_years"].append(row.get("year"))
        bound = onto.bind(crawled, str(row.get("series") or "")).dataset if onto else ""
        entry["_datasets"].add(bound or str(row.get("series") or ""))

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
    return sorted(out, key=lambda e: -e["files"])


def _span(years: list[Any]) -> str:
    real = sorted({int(y) for y in years if y})
    if not real:
        return "—"
    return f"{real[0]}–{real[-1]}" if real[0] != real[-1] else str(real[0])


def _group(rows, keys, *, extra=None, order=None) -> list[dict[str, Any]]:
    buckets: dict[tuple, list[dict[str, Any]]] = {}
    for row in rows:
        buckets.setdefault(tuple(row.get(k) for k in keys), []).append(row)
    out = []
    for key, group in buckets.items():
        entry = dict(zip(keys, key, strict=True))
        entry["files"] = len(group)
        entry["gigabytes"] = round(sum(int(g.get("size") or 0) for g in group) / 2**30, 2)
        if extra:
            entry.update(extra(group))
        out.append(entry)
    return sorted(out, key=order or (lambda e: (-int(e["files"]), str(list(e.values())[0]))))
