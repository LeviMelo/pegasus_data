"""L7 — the Parquet lake.

Layout (§7.3)::

    lake/<system>/<family>/schema_signature=<sig>/uf=<UF>/year=<YYYY>/part-<n>.parquet

Partitioning on UF and year is not decoration: those are the columns actually
used as predicates, so partition pruning eliminates whole files before any bytes
are read. Within a file, row-group statistics prune further and column projection
avoids reading unrequested columns at all.

ZSTD compression with dictionary encoding on coded string columns — which is most
of them, and where the size collapse comes from: a ``.dbc`` must be inflated from
byte zero to read one column, and a Parquet file's footer is a map.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq

from .._lazy import LazyModule
from ..catalog.store import CatalogStore, utcnow
from .staging import staged_file, staged_tree

if TYPE_CHECKING:
    import pyarrow.dataset as ds
else:
    ds = LazyModule("pyarrow.dataset")

_SAFE = re.compile(r"[^A-Za-z0-9_.=-]+")

#: Where a partition is staged while it is written: beside the system directories, so no glob over a family reaches it.
STAGING_DIR = ".staging"


def _safe(part: str) -> str:
    return _SAFE.sub("_", str(part))


@dataclass(slots=True)
class WrittenPartition:
    family_id: str
    schema_signature: str
    uf: str
    year: int
    relative_path: str
    row_count: int
    byte_size: int


#: An intake unit (ADR-0162) is a publication per record year: the unit's file, this mark and the year. Its records name the
#: file they were read from (``_SOURCE_PATH``), not the slice of it.
SLICE = "#year="


def record_source(publication: str) -> str:
    """The source a record of ``publication`` names as its own: the file, without the slice of it that is the publication."""
    return publication.partition(SLICE)[0]


@dataclass(frozen=True, slots=True)
class LakePartition:
    """One partition file the catalog lists (a row of ``lake_partitions``)."""

    family_id: str
    schema_signature: str
    uf: str
    year: int
    relative_path: str
    #: the source files (catalog paths) the partition was built from: what says a publication is in the lake
    sources: frozenset[str] = frozenset()


def published_files(lake_dir: str | Path, system: str, series: str, year: int) -> tuple[Path, list[Path]]:
    """A dataset-year's published partition files in the lake, every family and schema of it: (the system's directory,
    the files). A write in progress stages under a hidden directory the pattern does not match. The lake's layout is
    known here only."""
    lake = Path(lake_dir) / system
    files = sorted(lake.glob(f"{system}_{series or system}_*/**/year={year}/*.parquet")) if lake.exists() else []
    return lake, files


def unit_parts(lake_dir: str | Path, family: str, unit_key: str) -> list[Path]:
    """The partition files of one landed unit (``part-<unit key>-*``, the key already file-safe) in the families
    matching ``family`` (a glob over the family folder name), every system, schema and place. The lake's layout is
    known here only."""
    return list(Path(lake_dir).glob(f"*/{family}/schema_signature=*/uf=*/year=*/part-{unit_key}-*.parquet"))


def listed_partitions(catalog: CatalogStore, family_ids: Sequence[str]) -> dict[str, tuple[LakePartition, ...]]:
    """The partitions the catalog lists for ``family_ids`` (all states and years), by family.

    The one answer to "which files hold this family": ``lake_partitions`` is written with the file, so reading from
    it is a list lookup, where discovering the directory again for every read cost 0.3-0.7 s of a query (a walk of
    every ``schema_signature=/uf=/year=/part-*`` of the family). Remembered until the catalog changes (ADR-0163).
    """
    ids = tuple(sorted({str(f) for f in family_ids}))
    if not ids:
        return {}

    def load() -> dict[str, tuple[LakePartition, ...]]:
        found: dict[str, list[LakePartition]] = {}
        for start in range(0, len(ids), 500):
            chunk = ids[start:start + 500]
            marks = ",".join("?" for _ in chunk)
            for row in catalog.query(
                f"SELECT family_id, schema_signature, uf, year, relative_path, source_paths FROM lake_partitions "
                f"WHERE family_id IN ({marks})", chunk,
            ):
                try:
                    sources = frozenset(str(value) for value in json.loads(row["source_paths"] or "[]"))
                except (TypeError, json.JSONDecodeError):
                    sources = frozenset()
                found.setdefault(str(row["family_id"]), []).append(LakePartition(
                    str(row["family_id"]), str(row["schema_signature"]), str(row["uf"] or ""),
                    int(row["year"] or 0), str(row["relative_path"]).replace("\\", "/"), sources,
                ))
        return {fam: tuple(sorted(parts, key=lambda p: (p.uf, p.year, p.relative_path)))
                for fam, parts in found.items()}

    return catalog.memo(("lake_partitions", ids), load)


class PartialLakeError(RuntimeError):
    """The catalog lists lake partitions the disk does not hold.

    Raised rather than skipped: a generation that contributes nothing because its file went missing (a pruned or moved
    lake, a partition caught between the two renames of a rebuild) shortens the table and nothing in it says so.
    """

    def __init__(self, family_id: str, missing: Sequence[str]) -> None:
        self.family_id = family_id
        self.missing = list(missing)
        shown = ", ".join(self.missing[:3]) + (" ..." if len(self.missing) > 3 else "")
        super().__init__(
            f"the catalog lists {len(self.missing)} lake partition file(s) of {family_id} that are not on disk "
            f"({shown}); the table would be short. Rebuild them (`pegasus-data build`) or restore the lake."
        )


#: ``(path, mtime_ns, size) -> column names`` of a Parquet file's schema, read once per file state.
_SCHEMAS: dict[tuple[str, int, int], tuple[str, ...]] = {}


class Lake:
    """Writes and reads the Parquet lake, and records every partition it writes."""

    def __init__(
        self,
        root: str | Path,
        catalog: CatalogStore | None = None,
        *,
        compression: str = "zstd",
        row_group_size: int = 256 * 1024,
    ) -> None:
        self.root = Path(root)
        self.catalog = catalog
        self.compression = compression
        self.row_group_size = row_group_size
        self.root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ paths

    def family_dir(self, system: str, family_id: str, schema_signature: str) -> Path:
        return (
            self.root
            / _safe(system)
            / _safe(family_id)
            / f"schema_signature={_safe(schema_signature)}"
        )

    def partition_dir(
        self, system: str, family_id: str, schema_signature: str, uf: str, year: int
    ) -> Path:
        return self.family_dir(system, family_id, schema_signature) / f"uf={_safe(uf)}" / f"year={year}"

    # ------------------------------------------------------------------ write

    def write_batches(
        self,
        batches: Iterable[pa.RecordBatch],
        *,
        system: str,
        family_id: str,
        schema_signature: str,
        uf: str,
        year: int,
        part: int = 0,
        source_paths: Sequence[str] = (),
        replace: bool = True,
        build_fingerprint: str | None = None,
    ) -> WrittenPartition | None:
        """Write one partition, replacing whatever occupied it. None if no rows.

        ``replace`` is the default because appending is the more dangerous
        mistake here. A partition is identified by (family, schema_signature, uf,
        year), and the build writes each one exactly once per run — so a second
        write of the same partition is a *rebuild*, not a continuation. Left to
        append, a rebuild after a schema correction wrote ``part-00003`` beside a
        stale ``part-00000`` and registered both; ``ds.dataset()`` then read the
        union and returned every row twice. Duplication is much harder to notice
        than emptiness: the build reports success, the row counts merely look
        high, and nothing fails until someone counts deaths and gets double.
        """
        # STREAMED, not collected. This materialised every batch of a state-year
        # partition into a list before opening the writer, so the "storage
        # boundary is streamed" comment below described the writer while the
        # caller had already paid the whole partition in memory. Only the first
        # batch is held, and only to learn the schema the writer needs.
        stream = iter(batches)
        first = None
        for candidate in stream:
            if candidate.num_rows:
                first = candidate
                break
        if first is None:
            return None
        directory = self.partition_dir(system, family_id, schema_signature, uf, year)
        if replace:
            part = 0
        target = directory / f"part-{part:05d}.parquet"

        # Stage first, delete second. This used to clear the partition — the
        # Parquet files AND their catalog rows — and only then start writing. A
        # disk-full, an interrupt or an Arrow raise in between left the
        # previously valid partition gone, and a write that succeeded while the
        # catalog update failed left a file that `ds.dataset()` still globs and
        # reads, with no metadata behind it.
        #
        # Streamed batch by batch rather than concatenated first. The whole
        # pipeline carries RecordBatch abstractions through decode and
        # normalisation and then materialised the entire state-year partition
        # here — at the storage boundary, which is exactly where streaming is
        # worth most.
        #
        # `staged_file` owns the durability rule, shared with the reference
        # warehouse: nothing partial is ever visible at `target`, and a failure
        # leaves the old partition intact and no debris behind.
        rows_written = 0

        def write_parquet(staged: Path) -> None:
            nonlocal rows_written
            # `_row` counts up within each file: delta-encoded it is a few bits a
            # row, against 4.6% of an SIH partition dictionary-encoded (measured
            # 2026-10-04, SP 2022). Delta encoding excludes the dictionary.
            sequential = [n for n in first.schema.names if n == "_row"]
            writer = pq.ParquetWriter(
                staged,
                first.schema,
                compression=self.compression,
                use_dictionary=[n for n in first.schema.names if n not in sequential],
                column_encoding=dict.fromkeys(sequential, "DELTA_BINARY_PACKED"),
                write_statistics=True,
                version="2.6",
            )
            try:
                writer.write_batch(first, row_group_size=self.row_group_size)
                rows_written += first.num_rows
                for batch in stream:
                    if not batch.num_rows:
                        continue
                    writer.write_batch(batch, row_group_size=self.row_group_size)
                    rows_written += batch.num_rows
            finally:
                writer.close()

        if replace:
            # The partition DIRECTORY is the replacement unit. Publishing a
            # new file and then sweeping its siblings exposed a moment where a
            # concurrent dataset scan saw both generations. A whole-tree rename
            # exposes either the complete old directory or the complete new
            # directory, never their union.
            #
            # Staged under `<lake>/.staging/`, not beside the partition: DuckDB's `**/*.parquet` glob over the family
            # walks hidden directories too, so a staging tree inside the family made every query on it fail while a
            # partition was written (and after a killed build).
            with staged_tree(directory, staging_root=self.root / STAGING_DIR) as staged_directory:
                write_parquet(staged_directory / target.name)
        else:
            directory.mkdir(parents=True, exist_ok=True)
            with staged_file(target) as staged:
                write_parquet(staged)
        written = WrittenPartition(
            family_id=family_id,
            schema_signature=schema_signature,
            uf=uf,
            year=year,
            relative_path=str(target.relative_to(self.root)).replace("\\", "/"),
            row_count=rows_written,
            byte_size=target.stat().st_size,
        )
        if self.catalog is not None:
            with self.catalog.write() as conn:
                if replace:
                    conn.execute(
                        "DELETE FROM lake_partitions WHERE family_id=? "
                        "AND schema_signature=? AND uf=? AND year=?",
                        (family_id, schema_signature, uf, year),
                    )
                conn.execute(
                    """
                INSERT INTO lake_partitions (family_id, schema_signature, uf, year, relative_path,
                                             row_count, byte_size, source_paths, written_at,
                                             build_fingerprint)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(family_id, schema_signature, uf, year, relative_path) DO UPDATE SET
                    row_count=excluded.row_count, byte_size=excluded.byte_size,
                    source_paths=excluded.source_paths, written_at=excluded.written_at,
                    build_fingerprint=excluded.build_fingerprint
                    """,
                    (
                        family_id, schema_signature, uf, year, written.relative_path,
                        written.row_count, written.byte_size, json.dumps(list(source_paths)), utcnow(),
                        build_fingerprint,
                    ),
                )
        return written

    def partition_is_current(
        self,
        *,
        system: str,
        family_id: str,
        schema_signature: str,
        uf: str,
        year: int,
        fingerprint: str,
    ) -> bool:
        """True when rebuilding this partition would reproduce what is there.

        The catalog row alone is not enough evidence. A lake directory deleted
        while the catalog survived would otherwise make every partition look
        current and the build would write nothing at all — so the files the row
        names are checked for existence, not assumed.
        """
        if self.catalog is None:
            return False
        rows = self.catalog.query(
            "SELECT relative_path, build_fingerprint FROM lake_partitions "
            "WHERE family_id=? AND schema_signature=? AND uf=? AND year=?",
            (family_id, schema_signature, uf, year),
        )
        if not rows:
            return False
        for row in rows:
            if row["build_fingerprint"] != fingerprint:
                return False
            if not (self.root / str(row["relative_path"])).is_file():
                return False
        return True

    # ------------------------------------------------------------------- read

    def dataset(self, system: str, family_id: str, schema_signature: str | None = None) -> ds.Dataset:
        """The directory's own view of a family: every Parquet file under it, listed or not.

        What a lake without a catalog (``Lake(root)``) has, and what the tests of the write path look at. Reads go
        through :meth:`listed` instead, so a stray or in-flight file the catalog does not list is never read, and
        a directory is never walked per query.
        """
        base = self.root / _safe(system) / _safe(family_id)
        if schema_signature:
            base = base / f"schema_signature={_safe(schema_signature)}"
        if not base.exists():
            raise FileNotFoundError(f"no lake data at {base}")
        return ds.dataset(base, format="parquet", partitioning="hive")

    # -------------------------------------------------- the catalog's list of partitions

    def listed(self, family_ids: Sequence[str]) -> dict[str, tuple[LakePartition, ...]] | None:
        """:func:`listed_partitions` of this lake's catalog; ``None`` for a lake without one."""
        return None if self.catalog is None else listed_partitions(self.catalog, family_ids)

    @staticmethod
    def narrow(
        parts: Iterable[LakePartition], uf: str | Sequence[str] | None = None,
        years: Sequence[int] | range | None = None, schema_signature: str | None = None,
    ) -> list[LakePartition]:
        """The partitions in the states and years asked (``None``: all of that axis)."""
        ufs = None if uf is None else {str(u).upper() for u in ([uf] if isinstance(uf, str) else uf)}
        wanted_years = None if years is None else {int(y) for y in years}
        return [
            p for p in parts
            if (ufs is None or p.uf.upper() in ufs)
            and (wanted_years is None or p.year in wanted_years)
            and (not schema_signature or p.schema_signature == schema_signature)
        ]

    def missing(self, parts: Iterable[LakePartition]) -> list[LakePartition]:
        """Listed partitions whose file is not on disk."""
        return [p for p in parts if not (self.root / p.relative_path).is_file()]

    def check_files(self, parts: Sequence[LakePartition], *, patience: float = 1.0) -> None:
        """Raise :class:`PartialLakeError` when a listed file is not on disk: a listed partition is never skipped.

        A rebuild replaces a partition's directory in two renames (the old one aside, the new one in): a reader that
        lists the file in the gap between them finds it absent for a few milliseconds. It looks again for up to
        ``patience`` seconds before calling the lake partial, so the gap is not a failure and a real loss still is.
        """
        import time

        deadline = time.monotonic() + patience
        gone = self.missing(parts)
        while gone and time.monotonic() < deadline:
            time.sleep(0.1)
            gone = self.missing(parts)
        if gone:
            raise PartialLakeError(gone[0].family_id, [p.relative_path for p in gone])

    def dataset_of(self, parts: Sequence[LakePartition]) -> ds.Dataset:
        """A dataset over exactly these partition files (no directory is walked)."""
        if not parts:
            raise FileNotFoundError("no lake partition is listed for this request")
        base = self.root.joinpath(*PurePosixPath(parts[0].relative_path).parts[:2])
        return ds.dataset(
            [str(self.root / p.relative_path) for p in parts], format="parquet",
            partitioning="hive", partition_base_dir=str(base),
        )

    def columns_of(self, parts: Sequence[LakePartition]) -> tuple[str, ...]:
        """The columns a family's files carry (the first present listed file's schema), with the partition keys.

        What the written Parquet says, for a generation the catalog holds no schema census for; read once per file
        state. Empty when no listed file is on disk.
        """
        for part in parts:
            path = self.root / part.relative_path
            try:
                stat = path.stat()
            except FileNotFoundError:
                continue                # any other OSError (a locked or unreadable file) is not "absent": it raises
            key = (str(path), stat.st_mtime_ns, stat.st_size)
            if key not in _SCHEMAS:
                if len(_SCHEMAS) > 4096:
                    _SCHEMAS.clear()
                _SCHEMAS[key] = tuple(pq.read_schema(path).names)
            return (*_SCHEMAS[key], "schema_signature", "uf", "year")
        return ()

    def _source(
        self, system: str, family_id: str, schema_signature: str | None,
        uf: str | Sequence[str] | None, years: Sequence[int] | range | None,
        partitions: Sequence[LakePartition] | None,
    ) -> tuple[ds.Dataset, ds.Expression | None]:
        """What to scan, and the state/year predicate it still needs (none when the files were listed)."""
        if partitions is None:
            listed = self.listed([family_id])
            if listed is not None:
                partitions = self.narrow(listed.get(family_id, ()), uf, years, schema_signature)
                if not partitions:
                    raise FileNotFoundError(
                        f"no lake partition is listed for {family_id} (uf={uf}, years={years}); "
                        "run `pegasus-data build`"
                    )
                self.check_files(partitions)
        if partitions is not None:
            return self.dataset_of(partitions), None
        # no catalog: the directory is the only evidence, and the axes are predicates over it
        expression = None
        if uf is not None:
            expression = ds.field("uf").isin([uf] if isinstance(uf, str) else list(uf))
        if years is not None:
            year_filter = ds.field("year").isin(list(years))
            expression = year_filter if expression is None else (expression & year_filter)
        return self.dataset(system, family_id, schema_signature), expression

    def read(
        self,
        *,
        system: str,
        family_id: str,
        schema_signature: str | None = None,
        uf: str | Sequence[str] | None = None,
        years: Sequence[int] | range | None = None,
        columns: Sequence[str] | None = None,
        optional_columns: Sequence[str] | None = None,
        where: ds.Expression | None = None,
        partitions: Sequence[LakePartition] | None = None,
    ) -> pa.Table:
        """The rows of a family in the states and years asked. ``partitions``: the files already chosen and checked
        (:meth:`check_files`); otherwise the catalog's list narrowed to ``uf`` and ``years``, every file of which must
        be on disk (:class:`PartialLakeError`)."""
        dataset, axes = self._source(system, family_id, schema_signature, uf, years, partitions)
        expression = where              # a caller's own predicate on the data columns, pushed into the scan
        if axes is not None:
            expression = axes if expression is None else (expression & axes)
        # `None` means EVERYTHING; `[]` means NOTHING. Testing truthiness
        # conflated them, so a generation where none of the requested fields
        # physically exists asked for an empty projection and got every column
        # instead — the opposite of what the caller wanted, and the shape that
        # structural null-filling depends on.
        # An intake family (ADR-0162) files its provenance upper-case (`_SOURCE_PATH`, `_READ_ON`), as the source's own columns are:
        # a read that asks for the lake's `_source_path` takes the upper-case column and hands it back under the name asked
        available = set(dataset.schema.names)
        alias = {c: c.upper() for c in (columns or ()) if c.startswith("_") and c not in available and c.upper() in available}
        projection = self._projection(dataset, family_id, [alias.get(c, c) for c in columns] if columns is not None else None,
                                      optional_columns)
        table = dataset.to_table(columns=projection, filter=expression)
        if alias:
            back = {v: k for k, v in alias.items()}
            table = table.rename_columns([back.get(name, name) for name in table.column_names])
        return table

    def _projection(
        self,
        dataset: ds.Dataset,
        family_id: str,
        columns: Sequence[str] | None,
        optional_columns: Sequence[str] | None,
    ) -> list[str] | None:
        """The column list to read, or ``None`` for every column.

        An EMPTY list is a real answer and must survive: it says this
        generation carries none of the requested fields, which the caller
        handles by null-filling rather than by reading the whole table.
        """
        if columns is None:
            return None
        available = set(dataset.schema.names)
        missing = [c for c in columns if c not in available]
        if missing:
            raise KeyError(
                f"columns not present in the lake for {family_id}: {missing}. "
                "Check the schema generation with CatalogStore.coverage()."
            )
        # DEDUPED, order preserved. A column can arrive both because the caller
        # asked for it and because rendering needs it — `year` is both — and
        # Arrow raises `Field "year" exists 2 times in schema` rather than
        # ignoring the repeat.
        projection: list[str] = []
        for name in [*columns, *[c for c in (optional_columns or []) if c in available]]:
            if name not in projection:
                projection.append(name)
        if not projection:
            # Nothing requested exists here. Read one partition column so the
            # scan still yields the right NUMBER of rows — an empty projection
            # returns an empty table, and those rows have to be null-filled,
            # not dropped.
            for anchor in ("year", "uf"):
                if anchor in available:
                    return [anchor]
        return projection

    def scanner(
        self,
        *,
        system: str,
        family_id: str,
        schema_signature: str | None = None,
        uf: str | Sequence[str] | None = None,
        years: Sequence[int] | range | None = None,
        columns: Sequence[str] | None = None,
        optional_columns: Sequence[str] | None = None,
        where: ds.Expression | None = None,
        batch_size: int = 131_072,
        partitions: Sequence[LakePartition] | None = None,
    ) -> ds.Scanner:
        """:meth:`read` without materialising the table.

        Same files, projection and predicate, handed to a Scanner instead
        of `to_table()`, so a caller can iterate batches under bounded memory.
        `where` is an extra predicate on the data columns, pushed into the scan
        rather than applied afterwards.
        """
        dataset, axes = self._source(system, family_id, schema_signature, uf, years, partitions)
        expression = axes
        if where is not None:
            expression = where if expression is None else (expression & where)
        projection = self._projection(dataset, family_id, columns, optional_columns)
        return dataset.scanner(
            columns=projection, filter=expression, batch_size=batch_size
        )

    # ------------------------------------------------------------- accounting

    def partitions(self, family_id: str | None = None) -> list[dict[str, object]]:
        if self.catalog is None:
            return []
        clause = " WHERE family_id = ?" if family_id else ""
        params = (family_id,) if family_id else ()
        return [
            dict(r)
            for r in self.catalog.query(f"SELECT * FROM lake_partitions{clause}", params)
        ]


def drop_redundant_partitions(catalog: CatalogStore, lake_dir: str | Path, *, dry_run: bool = False) -> dict[str, int]:
    """Delete the lake partitions whose records the dataset's catalogued reading of that year already holds.

    Two cases, one rule. A partition on disk that the catalog does not list (a build whose catalog write was lost, a
    generation left behind) is read by nothing that plans from the catalog, but every scan of the folder and the
    footer census of ``info`` counted it: SIM-DO 2009 held an unlisted DOBR beside its 27 listed state partitions and
    2012 ten unlisted state partitions beside its listed DOBR, so 1.9 M deaths were held and counted twice
    (2026-11-21). And a listed state partition of a year whose listed national partition holds the same records is
    the second reading of a year SIM and SINASC publish twice (``coverage.national_or_states``).

    A listed partition goes only when the reference (the listed national partitions of its year) contains each of
    its rows, compared as a multiset on every published column the two share. An unlisted one goes when it is so
    contained, or when its year has a listed reading and every file it was built from is still on the server (the
    catalog's crawl lists it): nothing reads it, and a build reproduces it. SIM's state and national files of a year are
    not always the same records: the national DBF of 2011-2017 declares the cause lines narrower than the state files
    (``LINHAA`` 10 characters in DOBR2012, 20 in DOES2012), so a third cause on a line is cut (DATA_SOURCES.md). An
    unlisted partition whose year has no listed reading holds records the catalog lost: kept and counted under
    ``unlisted_kept``, for a build of that year to register again.
    """
    import duckdb

    root = Path(lake_dir)
    listed = [dict(r) for r in catalog.query(
        "SELECT family_id, schema_signature, uf, year, relative_path, row_count FROM lake_partitions")]
    known = {str(r["relative_path"]) for r in listed}

    def dataset(family: str) -> str:
        return family.rsplit("_", 1)[0]

    by_year: dict[tuple[str, int], list[dict[str, object]]] = {}
    for row in listed:
        if (root / str(row["relative_path"])).is_file():
            by_year.setdefault((dataset(str(row["family_id"])), int(row["year"] or 0)), []).append(row)

    # (file, the reference files it must be contained in, its catalog row or None when unlisted)
    candidates: list[tuple[Path, list[Path], dict[str, object] | None]] = []
    for path in sorted(root.glob("*/*_??????????/schema_signature=*/uf=*/year=*/*.parquet")):
        rel = path.relative_to(root).as_posix()
        if rel in known or not path.parent.name.split("=", 1)[1].isdigit():
            continue
        refs = by_year.get((dataset(path.parts[-5]), int(path.parent.name.split("=", 1)[1])), [])
        candidates.append((path, [root / str(r["relative_path"]) for r in refs], None))
    for rows in by_year.values():
        national = [root / str(r["relative_path"]) for r in rows if str(r["uf"]).upper() == "BR"]
        if national:
            candidates += [(root / str(r["relative_path"]), national, r) for r in rows
                           if str(r["uf"]).upper() not in {"", "BR", "NA"}]

    out = {"partitions": 0, "rows": 0, "bytes": 0, "unlisted_kept": 0, "listed_kept": 0}
    con = duckdb.connect()
    con.execute("SET memory_limit='1GB'; SET threads=2; SET enable_progress_bar=false")
    for path, refs, row in candidates:
        contained = False
        if refs:
            shared = set.intersection(*(set(pq.read_schema(f).names) for f in refs))
            cols = sorted(c for c in pq.read_schema(path).names if c in shared and not c.startswith("_")
                          and c not in {"schema_signature", "uf", "year"})
            if cols:
                key = "md5(concat_ws('|', " + ", ".join(f"coalesce(\"{c}\"::VARCHAR, '~')" for c in cols) + "))"
                files = ", ".join(f"'{f.as_posix()}'" for f in refs)
                short = con.execute(
                    f"""WITH s AS (SELECT {key} k, count(*) n FROM read_parquet('{path.as_posix()}') GROUP BY 1),
                             b AS (SELECT {key} k, count(*) n FROM read_parquet([{files}], union_by_name=true)
                                   WHERE {key} IN (SELECT k FROM s) GROUP BY 1)
                        SELECT coalesce(sum(s.n - coalesce(b.n, 0)), 0) FROM s LEFT JOIN b USING (k)
                        WHERE s.n > coalesce(b.n, 0)""").fetchone()[0]  # type: ignore[index]
                contained = not short
        if not contained and row is None and refs:
            sources = [str(r[0]) for r in con.execute(
                f"SELECT DISTINCT _source_path FROM read_parquet('{path.as_posix()}')").fetchall()]
            marks = ",".join("?" for _ in sources) or "NULL"
            listed_now = {str(r["path"]) for r in catalog.query(
                f"SELECT path FROM files WHERE gone_at IS NULL AND path IN ({marks})", tuple(sources))}
            contained = bool(sources) and set(sources) <= listed_now
            out["superseded"] = out.get("superseded", 0) + int(contained)
        if not contained:
            out["unlisted_kept" if row is None else "listed_kept"] += 1
            continue
        out["partitions"] += 1
        out["rows"] += pq.ParquetFile(path).metadata.num_rows
        siblings = [f for f in path.parent.iterdir() if f.is_file()]
        out["bytes"] += sum(f.stat().st_size for f in siblings)
        if dry_run:
            continue
        for f in siblings:
            f.unlink()
        path.parent.rmdir()
        if row is not None:
            with catalog.write() as conn:
                conn.execute("DELETE FROM lake_partitions WHERE family_id=? AND schema_signature=? AND uf=? AND year=?",
                             (row["family_id"], row["schema_signature"], row["uf"], row["year"]))
    con.close()
    return out
