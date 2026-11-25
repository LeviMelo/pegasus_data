"""What the home holds of each published file, in one model (ADR-0236).

A published file is held one of two ways:

- **whole**, by the lake: a partition lists it among its sources, at the digest it was read at
  (`lake_partitions.source_paths`, `source_digests`, ADR-0234);
- **partly**, by its dataset's extract store: the rows a predicate keeps, at a digest, in parts written only here
  (`<lake>/extracts/<SYSTEM>-<SERIES>/`, one store per dataset, ``holdings.sqlite`` beside the parts).

A predicate is a union of atoms, each a column and a code prefix (`Predicate`): what an extract keeps is a record any of
whose filters matches (`build_extract`), so the union of two extracts' filters is the predicate of both. A new filter
over a file stores only the rows it adds (``new AND NOT held``) and widens the file's predicate; a file the lake holds
whole at the same digest holds every row any predicate keeps, and its parts are absorbed (`absorb`). A file is held at a
version: the server listing a file as another version than the one held (`stale`) makes that file's holding void, and
exactly its rows are read again.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

__all__ = ["ExtractStore", "Predicate", "lake_whole", "stale", "with_year"]


# ------------------------------------------------------------------ the predicate algebra


@dataclass(frozen=True)
class Predicate:
    """The rows of a file a holding keeps: every row (``atoms is None``), or those any of whose atoms matches, an atom
    being ``(column, prefix)``: the column (upper case) starts with the prefix (`normalise_prefix`). Canonical: a prefix
    another prefix of the same column already implies is not kept, so two spellings of one set are one value."""

    atoms: frozenset[tuple[str, str]] | None

    @classmethod
    def of(cls, filters: Mapping[str, Sequence[str]]) -> Predicate:
        from .._query_engine.request import normalise_prefix

        atoms = {(str(c).upper(), normalise_prefix(p)) for c, ps in filters.items() for p in ps}
        return cls(_canonical(atoms))

    @classmethod
    def whole(cls) -> Predicate:
        return cls(None)

    @classmethod
    def from_json(cls, text: str | None) -> Predicate:
        value = json.loads(text) if text else None
        return cls.whole() if value is None else cls.of(value)

    @property
    def is_whole(self) -> bool:
        return self.atoms is None

    @property
    def is_empty(self) -> bool:
        return self.atoms is not None and not self.atoms

    def filters(self) -> dict[str, list[str]]:
        """``{column: prefixes}``, the form `build_extract` and a row filter take."""
        out: dict[str, list[str]] = {}
        for column, prefix in sorted(self.atoms or ()):
            out.setdefault(column, []).append(prefix)
        return out

    def to_json(self) -> str | None:
        return None if self.atoms is None else json.dumps(self.filters(), sort_keys=True)

    def __str__(self) -> str:
        if self.atoms is None:
            return "TRUE"
        return " OR ".join(f"{c} {'|'.join(ps)}*" for c, ps in self.filters().items()) or "FALSE"

    def union(self, other: Predicate) -> Predicate:
        if self.atoms is None or other.atoms is None:
            return Predicate.whole()
        return Predicate(_canonical(self.atoms | other.atoms))

    def implies(self, other: Predicate) -> bool:
        """Is every row this keeps one ``other`` keeps? Exact for unions of prefix atoms: an atom is implied when
        ``other`` has an atom on its column whose prefix starts it."""
        if other.atoms is None:
            return True
        if self.atoms is None:
            return False
        return all(_atom_implied(a, other.atoms) for a in self.atoms)

    def beyond(self, other: Predicate) -> Predicate:
        """The atoms of this predicate ``other`` does not imply: what a read must ask for to add this to ``other``. The
        rows to store are those it matches and ``other`` does not (`mask`): an atom can overlap one of ``other``'s on
        another column (a row with SP_ATOPROF 0702040126 whose SP_PROCREA is 0415)."""
        if self.atoms is None:
            return Predicate.whole() if other.atoms is not None else Predicate(frozenset())
        if other.atoms is None:
            return Predicate(frozenset())
        return Predicate(frozenset(a for a in self.atoms if not _atom_implied(a, other.atoms)))

    def covers(self, filters: Mapping[str, Sequence[str]], join: str = "all") -> bool:
        """Does this holding keep every row the query's row filter (``{column: prefixes}``, combined by ``join``) can
        keep? Under "any" every column's prefixes must be implied; under "all" one column's are enough (a row the
        query keeps matches that column)."""
        asked = {c: Predicate.of({c: v}) for c, v in filters.items() if v}
        if not asked:
            return self.is_whole
        implied = [p.implies(self) for p in asked.values()]
        return all(implied) if join == "any" else any(implied)

    def mask(self, table: pa.Table) -> pa.Array:
        """The rows of ``table`` this predicate keeps (a column the table lacks keeps none of its atoms' rows)."""
        from .._query_engine.request import prefix_match

        if self.atoms is None:
            return pa.array([True] * table.num_rows, pa.bool_())
        out = pa.array([False] * table.num_rows, pa.bool_())
        names = {c.upper(): c for c in table.column_names}
        for column, prefixes in self.filters().items():
            if column in names:
                hit = pc.fill_null(prefix_match(pc.cast(table.column(names[column]), pa.string()), prefixes), False)
                out = pc.or_(out, hit)
        return out


def _atom_implied(atom: tuple[str, str], atoms: Iterable[tuple[str, str]]) -> bool:
    return any(c == atom[0] and atom[1].startswith(p) for c, p in atoms)


def _canonical(atoms: set[tuple[str, str]] | frozenset[tuple[str, str]]) -> frozenset[tuple[str, str]]:
    return frozenset(a for a in atoms if not any(b != a and _atom_implied(a, [b]) for b in atoms))


def with_year(table: pa.Table, year: int) -> pa.Table:
    """``table`` with the publication's ``year`` as its last column, a dictionary of int32: the form held rows have
    always come in (the extract folders' ``year=`` partition read back by pyarrow)."""
    if "year" in table.column_names:
        table = table.drop_columns(["year"])
    year_column = pa.DictionaryArray.from_arrays(pa.array([0] * table.num_rows, pa.int32()),
                                                 pa.array([int(year)], pa.int32()))
    return table.append_column("year", year_column)


# ------------------------------------------------------------------ versions


def stale(catalog: Any, held: Mapping[str, str]) -> set[str]:
    """The paths of ``held`` (path -> digest) the server now lists as another version than the digest held: the size
    the fetch of that digest saw differs from the listing, or its time does other than as the server's two clocks
    (`listing.same_instant`). A digest no fetch records cannot be judged and is taken as current, the lake's rule
    (`coverage._republished_since_build`)."""
    from ..discovery.listing import same_instant

    out: set[str] = set()
    items = sorted(held.items())
    for start in range(0, len(items), 400):
        chunk = items[start:start + 400]
        marks = ",".join("(?, ?)" for _ in chunk)
        rows = catalog.query(
            f"""WITH h(path, sha) AS (VALUES {marks})
                SELECT h.path, fi.size AS listed_size, fi.modified AS listed_mtime,
                       (SELECT f.remote_size FROM fetches f WHERE f.source_path = h.path AND f.sha256 = h.sha
                         ORDER BY f.fetched_at DESC LIMIT 1) AS size,
                       (SELECT f.remote_modified FROM fetches f WHERE f.source_path = h.path AND f.sha256 = h.sha
                         ORDER BY f.fetched_at DESC LIMIT 1) AS mtime
                  FROM h JOIN files fi ON fi.path = h.path""",
            [v for pair in chunk for v in pair])
        for r in rows:
            if r["size"] is None and r["mtime"] is None:
                continue
            if r["listed_size"] is not None and r["size"] is not None and int(r["listed_size"]) != int(r["size"]) or r["listed_mtime"] and r["mtime"] and not same_instant(str(r["listed_mtime"]), str(r["mtime"])):
                out.add(str(r["path"]))
    return out


def lake_whole(catalog: Any, lake_dir: str | Path, family_prefix: str,
               paths: Iterable[str] | None = None) -> dict[str, tuple[str, list[Path]]]:
    """The published files the lake holds whole at the version the server lists: path -> (digest, the partition files
    holding it). ``family_prefix`` names the dataset's families (``SIHSUS_SP_``). A partition whose file is not on disk
    holds nothing; a source the server has republished since is not held. A partition with no recorded digests
    (`versions.record_partition_digests` fills them) is not counted: judging it would read every file's provenance on
    every query."""
    lake = Path(lake_dir)
    if "source_digests" not in {str(r["name"]) for r in catalog.query("PRAGMA table_info(lake_partitions)")}:
        return {}                         # a catalog from before ADR-0234 records no version: nothing is held whole
    wanted = set(paths) if paths is not None else None
    files: dict[str, list[Path]] = {}
    digests: dict[str, str] = {}
    for row in catalog.query("SELECT relative_path, source_paths, source_digests FROM lake_partitions "
                             "WHERE family_id LIKE ? ESCAPE '\\'",
                             (family_prefix.replace("_", "\\_") + "%",)):
        sources = [s for s in json.loads(row["source_paths"] or "[]") if wanted is None or s in wanted]
        if not sources or not row["source_digests"] or not (lake / str(row["relative_path"])).is_file():
            continue
        found = json.loads(row["source_digests"])
        for s in sources:
            if s in found:
                files.setdefault(s, []).append(lake / str(row["relative_path"]))
                digests[s] = found[s]
    void = stale(catalog, digests)
    return {s: (digests[s], files[s]) for s in digests if s not in void}


# ------------------------------------------------------------------ the extract store


_SCHEMA = """
CREATE TABLE IF NOT EXISTS held (
    path TEXT PRIMARY KEY, year INTEGER, uf TEXT, period TEXT,
    sha256 TEXT,          -- the version the parts were read from
    predicate TEXT,       -- Predicate.to_json(): the rows of the file the parts hold
    rows INTEGER,         -- the file's records (decoded)
    kept INTEGER,         -- the rows the parts hold
    bytes INTEGER,        -- the parts' size
    parts TEXT,           -- JSON list of part names, disjoint
    code TEXT,            -- pegasus_data's version that wrote the last part
    written_at TEXT);
CREATE TABLE IF NOT EXISTS failed (path TEXT PRIMARY KEY, predicate TEXT, why TEXT, at TEXT);
"""


@dataclass(frozen=True)
class FileHolding:
    path: str
    year: int
    uf: str
    period: str
    sha256: str | None
    predicate: Predicate
    rows: int
    kept: int
    bytes: int
    parts: tuple[str, ...]

    def entry(self) -> dict[str, Any]:
        """The manifest entry form callers of `build_extract`, `held_files` and `held_rows` read."""
        return {"year": self.year, "uf": self.uf, "period": self.period, "rows": self.rows, "kept": self.kept,
                "sha256": self.sha256, "held": str(self.predicate), "parts": list(self.parts)}


class ExtractStore:
    """The rows of a dataset's published files kept by predicate (module docstring)."""

    def __init__(self, lake_dir: str | Path, dataset: str) -> None:
        from .._request import parse_dataset

        system, series = parse_dataset(dataset)
        self.dataset = dataset
        self.root = Path(lake_dir) / "extracts" / f"{system}-{series or system}"
        self.db = self.root / "holdings.sqlite"

    def _connect(self) -> sqlite3.Connection:
        self.root.mkdir(parents=True, exist_ok=True)
        con = sqlite3.connect(self.db, timeout=60)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript(_SCHEMA)
        return con

    def exists(self) -> bool:
        return self.db.is_file()

    def holdings(self, path: str | None = None) -> dict[str, FileHolding]:
        """Every file's holding (``path``: that file's only)."""
        if not self.exists():
            return {}
        where, args = ("WHERE path = ?", (path,)) if path is not None else ("", ())
        with closing(self._connect()) as con:
            return {str(r["path"]): FileHolding(
                str(r["path"]), int(r["year"]), str(r["uf"]), str(r["period"]), r["sha256"],
                Predicate.from_json(r["predicate"]) if r["predicate"] is not None else Predicate.whole(),
                int(r["rows"] or 0), int(r["kept"] or 0), int(r["bytes"] or 0), tuple(json.loads(r["parts"] or "[]")))
                for r in con.execute(f"SELECT * FROM held {where}", args)}

    def failures(self) -> dict[str, str]:
        if not self.exists():
            return {}
        with closing(self._connect()) as con:
            return {str(r["path"]): str(r["why"]) for r in con.execute("SELECT path, why FROM failed")}

    def part_name(self, path: str, year: int, n: int) -> str:
        stem = path.rsplit("/", 1)[-1].replace("!", ".").rsplit(".", 1)[0]
        tag = hashlib.sha1(path.encode()).hexdigest()[:6]
        return f"year={int(year)}/{stem}-{tag}.{n}.parquet"

    def read(self, holding: FileHolding) -> pa.Table | None:
        """The rows the store holds of one file (None: it holds none), the publication's ``year`` last, as a read of
        the folders before ADR-0236 gave it (pyarrow took it from the part's ``year=`` folder)."""
        pieces = []
        for name in holding.parts:
            table = pq.read_table(self.root / name, partitioning=None)
            if "_source_path" in table.column_names:
                # a part is one file's rows; a publication split into members carries the member in its source id
                source = pc.cast(table.column("_source_path"), pa.string())
                mine = pc.or_(pc.equal(source, holding.path), pc.starts_with(source, holding.path + "!"))
                table = table.filter(pc.fill_null(mine, False))
            if table.num_rows:
                pieces.append(table)
        if not pieces:
            return None
        table = pieces[0] if len(pieces) == 1 else pa.concat_tables(pieces, promote_options="permissive")
        return with_year(table, holding.year)

    def add(self, *, path: str, year: int, uf: str, period: str, sha256: str | None, predicate: Predicate,
            rows: int, table: pa.Table | None, replace: bool = False) -> FileHolding:
        """Record that the store now holds ``predicate`` of ``path``: ``table`` (rows the store did not hold) written as
        a new part, or, with ``replace``, as the file's only part (a new version, read whole for its predicate). The
        record is written as the part lands, so a running build is visible (OQ 108)."""
        from .. import __version__
        from ..persist.kept import write_parquet_atomic

        existing = self.holdings(path).get(path)
        old = None if replace else existing
        dropped = list(existing.parts) if replace and existing else []
        parts = list(old.parts) if old else []
        kept = old.kept if old else 0
        size = old.bytes if old else 0
        if table is not None and table.num_rows:
            n = 0
            while (name := self.part_name(path, year, n)) in parts or name in dropped:
                n += 1
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            write_parquet_atomic(table, target, compression="zstd")
            parts.append(name)
            kept += table.num_rows
            size += target.stat().st_size
        held = old.predicate.union(predicate) if old else predicate
        with closing(self._connect()) as con, con:
            con.execute("INSERT OR REPLACE INTO held VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (path, int(year), uf, str(period), sha256, held.to_json(), int(rows), kept, size,
                         json.dumps(parts), __version__, datetime.now(UTC).isoformat(timespec="seconds")))
            con.execute("DELETE FROM failed WHERE path = ?", (path,))
        for name in dropped:
            if name not in parts:
                (self.root / name).unlink(missing_ok=True)
        return self.holdings(path)[path]

    def fail(self, path: str, predicate: Predicate, why: str) -> None:
        with closing(self._connect()) as con, con:
            con.execute("INSERT OR REPLACE INTO failed VALUES (?,?,?,?)",
                        (path, predicate.to_json(), why[:300], datetime.now(UTC).isoformat(timespec="seconds")))

    def drop(self, path: str) -> int:
        """Forget ``path`` and delete its parts; returns the bytes freed."""
        holding = self.holdings(path).get(path)
        if holding is None:
            return 0
        freed = 0
        for name in holding.parts:
            part = self.root / name
            if part.is_file():
                freed += part.stat().st_size
                part.unlink()
        with closing(self._connect()) as con, con:
            con.execute("DELETE FROM held WHERE path = ?", (path,))
        return freed
