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
import uuid
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.parquet as pq

from .._bounded import Bounded
from .._lazy import LazyModule
from ..catalog.store import CatalogStore, utcnow
from .staging import _remove_tree, _retry_on_permission, staged_file, staged_tree

if TYPE_CHECKING:
    import pyarrow.dataset as ds
else:
    ds = LazyModule("pyarrow.dataset")

_SAFE = re.compile(r"[^A-Za-z0-9_.=-]+")

#: Where a partition is staged while it is written: beside the system directories, so no glob over a family reaches it.
STAGING_DIR = ".staging"


def _safe(part: str) -> str:
    return _SAFE.sub("_", str(part))


#: A record's content key (`normalize.engine.record_key_sql`): computed on read, not stored (`Lake._read_derived`).
RECORD_KEY = "_record_key"


def _has_renders(dataset: ds.Dataset) -> bool:
    """Whether any file of ``dataset`` keeps a typed column's text by render (`raw_text`), from the files' footers."""
    from ..raw_text import META_KEY

    return any(META_KEY in (f.physical_schema.metadata or {}) for f in dataset.get_fragments())


def _file_keys(path: str, fields: Sequence[str]) -> pa.Array:
    """The record key of every row of one partition file, in its row order (`normalize.engine.record_key_sql`)."""
    import duckdb

    from ..normalize.engine import record_key_sql

    con = duckdb.connect()
    try:
        con.execute("SET preserve_insertion_order = true")
        return con.execute(f"SELECT {record_key_sql(fields)} AS k FROM read_parquet('{Path(path).as_posix()}', "
                           "hive_partitioning = false)").to_arrow_table().column("k").combine_chunks()
    finally:
        con.close()


def parquet_writer(path: Path, schema: pa.Schema, compression: str = "zstd",
                   closed_dictionary: Sequence[str] | None = None) -> pq.ParquetWriter:
    """The lake's Parquet encoding, for every writer of a partition file (`persist.kept.parquet_options`: zstd 9, the
    encoding stamped in the schema). `_row` counts up within each file: delta-encoded it is a few bits a row, against
    4.6% of an SIH partition dictionary-encoded (measured 2026-10-04, SP 2022). Delta encoding excludes the dictionary.
    The row groups are made by `RowGroups`, which gathers batches to `ROW_GROUP_ROWS`.

    ``closed_dictionary`` writes the closed encoding instead (`persist.kept.CLOSED_ENCODING`, ADR-0238): zstd 22 and the
    dictionary on those columns only (`probe_dictionary`); its `RowGroups` take `CLOSED_ROW_GROUP_ROWS`. The
    probe of 65,536 rows chose 34 of SIH-SP's 43 columns in 8 s, that of 262,144 rows 35 in 30 s."""
    from .kept import CLOSED_ENCODING, CLOSED_ZSTD_LEVEL, ENCODING, ZSTD_LEVEL

    sequential = [n for n in schema.names if n == "_row"]
    closed = closed_dictionary is not None
    stamp = CLOSED_ENCODING if closed else ENCODING
    schema = schema.with_metadata({**(schema.metadata or {}), b"pegasus.encoding": stamp.encode()})
    level = (CLOSED_ZSTD_LEVEL if closed else ZSTD_LEVEL) if compression == "zstd" else None
    dictionary = [n for n in (closed_dictionary if closed else schema.names) if n not in sequential and n in schema.names]
    return pq.ParquetWriter(
        path, schema, compression=compression, compression_level=level, use_dictionary=dictionary,
        column_encoding=dict.fromkeys(sequential, "DELTA_BINARY_PACKED"),
        write_statistics=True, version="2.6",
    )


def probe_dictionary(source: pq.ParquetFile, columns: Sequence[str], rows: int = 65_536) -> list[str]:
    """The columns of ``source`` whose dictionary encoding is smaller than plain, each written alone at the closed level
    over the file's first ``rows`` rows (ADR-0238). Dictionary pays on coded columns and loses on near-unique ones (an
    AIH number, a postcode); the probe decides per file, nothing is declared. `_row` is delta-encoded and never asked."""
    import io

    from .kept import CLOSED_ZSTD_LEVEL

    probe = next(source.iter_batches(batch_size=rows, columns=list(columns)), None)
    if probe is None:
        return [c for c in columns if c != "_row"]
    chosen = []
    for name in probe.schema.names:
        if name == "_row":
            continue
        one = pa.table([probe.column(name)], names=[name])
        sizes = []
        for dictionary in (True, False):
            sink = io.BytesIO()
            pq.write_table(one, sink, compression="zstd", compression_level=CLOSED_ZSTD_LEVEL, use_dictionary=dictionary,
                           row_group_size=rows)
            sizes.append(sink.tell())
        if sizes[0] <= sizes[1]:
            chosen.append(name)
    return chosen


class RowGroups:
    """Batches written to ``writer`` as row groups of `ROW_GROUP_ROWS`: a batch became its own group (65,536 rows a
    group where 262,144 were asked; 9% larger files, 2026-11-22). Call `flush` before closing."""

    def __init__(self, writer: pq.ParquetWriter, rows: int | None = None) -> None:
        from .kept import ROW_GROUP_ROWS

        self.writer, self.rows, self.held, self.count = writer, rows or ROW_GROUP_ROWS, [], 0

    def write(self, batch: pa.RecordBatch) -> None:
        self.held.append(batch)
        self.count += batch.num_rows
        if self.count >= self.rows:
            self.flush()

    def flush(self) -> None:
        if self.held:
            table = pa.Table.from_batches(self.held).replace_schema_metadata(self.writer.schema.metadata)
            self.writer.write_table(table, row_group_size=self.rows)
            self.held, self.count = [], 0


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


def _delist_superseded(conn: Any, family_id: str, uf: str, year: int, sources: set[str]) -> int:
    """Remove from the catalog every other family's partition of the same dataset, place and year built only from files
    this partition was just built from: one source file is one reading, held once. A file regrouped into another schema
    family (SINASC's DNBR2013, from `NOV/` to `1996_/` families) was built again under the new family while the old
    partition stayed listed, and every read of 2013 returned each birth twice (5,808,054 rows, 2026-11-22). The file
    left unlisted is read by nothing (reads plan from the catalog) and `drop_redundant_partitions` removes it once the
    listed reading contains its rows. Returns the rows delisted."""
    if not sources:
        return 0
    dataset = family_id.rsplit("_", 1)[0]
    gone = []
    for other, path, listed in conn.execute(
            "SELECT family_id, relative_path, source_paths FROM lake_partitions WHERE uf=? AND year=? AND family_id<>?",
            (uf, year, family_id)).fetchall():
        held = set(json.loads(listed or "[]"))
        if str(other).rsplit("_", 1)[0] == dataset and held and held <= sources:
            gone.append((other, path))
    conn.executemany("DELETE FROM lake_partitions WHERE family_id=? AND relative_path=?", gone)
    return len(gone)


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
_SCHEMAS: Bounded[tuple[str, int, int], tuple[str, ...]] = Bounded(4096)


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
        source_digests: Mapping[str, str] | None = None,
        on_staged: Callable[[list[Path]], None] | None = None,
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

        ``source_digests`` (``{source id: digest}``) is recorded with the files. ``on_staged(files)`` is called with the
        written files while the partition being replaced is still in place, before the swap: what keeps the versions
        it held as deltas (`persist.versions`). It raising leaves the old partition as it was.
        """
        # STREAMED, not collected. This materialised every batch of a state-year
        # partition into a list before opening the writer, so the "storage
        # boundary is streamed" comment below described the writer while the
        # caller had already paid the whole partition in memory. Only the first
        # batch is held, and only to learn the schema the writer needs.
        # the record key is a function of the record's fields and is computed on read (`_read_derived`): stored, it was
        # 40% of the lake (OQ #99)
        stream = (b.select([n for n in b.schema.names if n != RECORD_KEY]) if RECORD_KEY in b.schema.names else b
                  for b in batches)
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
        extra_files: list[Path] = []

        def open_writer(staged: Path, schema: pa.Schema) -> pq.ParquetWriter:
            return parquet_writer(staged, schema, self.compression)

        def write_parquet(staged: Path, *, split: bool) -> None:
            """The batches into ``staged``; with ``split`` a batch whose schema differs from the file's opens the next
            part file beside it. A family's files of one year can differ by a column (SIA-AQ 2013-2015: AP_NATJUR in
            some months, not others; 2026-11-21), and a Parquet file's schema is fixed by its first batch: the build
            raised. A column a month lacks stays absent in that file, never written as nulls."""
            nonlocal rows_written
            writer = open_writer(staged, first.schema)
            groups = RowGroups(writer, self.row_group_size)
            current = first.schema
            try:
                groups.write(first)
                rows_written += first.num_rows
                for batch in stream:
                    if not batch.num_rows:
                        continue
                    if not batch.schema.equals(current, check_metadata=False):
                        if not split:
                            raise ValueError(f"{family_id} {uf} {year}: a batch's schema differs from the partition's "
                                             "and this write appends to one file")
                        groups.flush()
                        writer.close()
                        nxt = staged.with_name(f"part-{part + len(extra_files) + 1:05d}.parquet")
                        extra_files.append(nxt)
                        writer = open_writer(nxt, batch.schema)
                        groups = RowGroups(writer, self.row_group_size)
                        current = batch.schema
                    groups.write(batch)
                    rows_written += batch.num_rows
                groups.flush()
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
                write_parquet(staged_directory / target.name, split=True)
                if on_staged is not None:
                    on_staged([staged_directory / target.name, *(staged_directory / f.name for f in extra_files)])
        else:
            directory.mkdir(parents=True, exist_ok=True)
            with staged_file(target) as staged:
                write_parquet(staged, split=False)
        files = [directory / target.name, *(directory / f.name for f in extra_files)]
        written = WrittenPartition(
            family_id=family_id,
            schema_signature=schema_signature,
            uf=uf,
            year=year,
            relative_path=str(target.relative_to(self.root)).replace("\\", "/"),
            row_count=rows_written,
            byte_size=sum(f.stat().st_size for f in files),
        )
        # one catalog row per file, with that file's rows: a partition split by a schema change (`write_parquet`) is
        # verified file by file (`prune`)
        rows_of = [(str(f.relative_to(self.root)).replace("\\", "/"), pq.ParquetFile(f).metadata.num_rows,
                    f.stat().st_size) for f in files]
        # the partition's sources and their versions, on each of its files' rows as `source_paths` is
        digests_json = None
        if source_digests is not None:
            digests_json = json.dumps(dict(sorted(source_digests.items())))
        if self.catalog is not None:
            with self.catalog.write() as conn:
                if replace:
                    conn.execute(
                        "DELETE FROM lake_partitions WHERE family_id=? "
                        "AND schema_signature=? AND uf=? AND year=?",
                        (family_id, schema_signature, uf, year),
                    )
                conn.executemany(
                    """
                INSERT INTO lake_partitions (family_id, schema_signature, uf, year, relative_path,
                                             row_count, byte_size, source_paths, written_at,
                                             build_fingerprint, source_digests)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(family_id, schema_signature, uf, year, relative_path) DO UPDATE SET
                    row_count=excluded.row_count, byte_size=excluded.byte_size,
                    source_paths=excluded.source_paths, written_at=excluded.written_at,
                    build_fingerprint=excluded.build_fingerprint, source_digests=excluded.source_digests
                    """,
                    [(
                        family_id, schema_signature, uf, year, rel, n, size, json.dumps(list(source_paths)), utcnow(),
                        build_fingerprint, digests_json,
                    ) for rel, n, size in rows_of],
                )
                _delist_superseded(conn, family_id, uf, year, set(source_paths))
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
        asked = [alias.get(c, c) for c in columns] if columns is not None else None
        # what the lake computes rather than stores: the record key, and a typed column's text as filed (`_read_derived`)
        wants_key = (columns is None or RECORD_KEY in columns or RECORD_KEY in (optional_columns or ()))
        wants_raw = any(n.endswith("__RAW") for n in (dataset.schema.names if columns is None else
                                                      [*columns, *(optional_columns or ())])) and _has_renders(dataset)
        if (wants_key and RECORD_KEY not in available) or wants_raw:
            table = self._read_derived(dataset, family_id, asked, optional_columns, expression,
                                       key=wants_key and RECORD_KEY not in available)
        else:
            projection = self._projection(dataset, family_id, asked, optional_columns)
            table = dataset.to_table(columns=projection, filter=expression)
        if alias:
            back = {v: k for k, v in alias.items()}
            table = table.rename_columns([back.get(name, name) for name in table.column_names])
        return table

    def _read_derived(
        self, dataset: ds.Dataset, family_id: str, columns: Sequence[str] | None,
        optional_columns: Sequence[str] | None, expression: ds.Expression | None, *, key: bool = True,
    ) -> pa.Table:
        """`read` with what the lake computes rather than stores, file by file, since each is a function of its own file:

        * the record key (``key``), from the file's own fields (`normalize.engine.record_key_sql`; OQ #99: stored, 40% of
          the lake as 32 hex characters a row). A whole file is hashed by DuckDB in one pass beside the columns read with
          their own types; a filtered read, batch by batch. A file that still stores a key gives it as stored;
        * the value as filed of a typed intake column, ``<NAME>__RAW``, which a landing keeps only where its render of
          the typed value does not give it back (`raw_text`): given back whole, ``coalesce(raw, render(typed))``."""
        from ..normalize.engine import key_fields, record_keys
        from ..raw_text import quote, renders_of, restored

        asked = None if columns is None else [c for c in columns if c != RECORD_KEY]
        optional = [c for c in (optional_columns or ()) if c != RECORD_KEY]
        projection = self._projection(dataset, family_id, asked, optional)
        pieces: list[pa.Table] = []
        for fragment in dataset.get_fragments():
            physical = fragment.physical_schema
            stored = RECORD_KEY in physical.names
            fields = key_fields(physical.names)
            renders = renders_of(physical.metadata)
            schema = pa.unify_schemas([dataset.schema, physical])
            keep = projection if projection is not None else [n for n in schema.names if n != RECORD_KEY]
            # a raw value is given back from its typed column, read for it when not asked
            typed = [n for n in renders if f"{n}__RAW" in keep and n not in keep and n in physical.names]
            wanted = [*keep, *typed]
            if key and expression is None and not stored and fields:
                # the whole file: DuckDB hashes it in one parallel pass, in the file's row order, and the columns asked are
                # read with their own types beside it (3.3 times the batch path: 857,219 SIH-RD rows in 3.5 s, not 11.5)
                table = fragment.to_table(schema=schema, columns=wanted)
                keys = _file_keys(fragment.path, fields)
                if len(keys) != table.num_rows:
                    raise RuntimeError(f"{fragment.path}: {len(keys)} keys for {table.num_rows} rows")
                table = table.append_column(RECORD_KEY, keys)
            else:
                read = list(dict.fromkeys([*wanted, *(([RECORD_KEY] if stored else fields) if key else [])]))
                batches = []
                for batch in fragment.to_batches(schema=schema, columns=read, filter=expression):
                    if not batch.num_rows:
                        continue
                    arrays = [batch.column(c) for c in wanted]
                    names = list(wanted)
                    if key:
                        arrays.append(batch.column(RECORD_KEY) if stored else record_keys(batch, fields))
                        names.append(RECORD_KEY)
                    batches.append(pa.RecordBatch.from_arrays(arrays, names=names))
                if not batches:
                    continue
                table = pa.Table.from_batches(batches)
            if renders:
                table = restored(table, renders, quote)
            if table.num_rows:
                pieces.append(table.select([*keep, *([RECORD_KEY] if key else [])]))
        if not pieces:
            empty = dataset.schema
            names = [n for n in (projection if projection is not None else empty.names) if n != RECORD_KEY]
            return pa.table({n: pa.array([], empty.field(n).type) for n in names}
                            | ({RECORD_KEY: pa.array([], pa.string())} if key else {}))
        return pa.concat_tables(pieces, promote_options="default")

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


def drop_redundant_partitions(catalog: CatalogStore, lake_dir: str | Path, *, dry_run: bool = False,
                              held: set[tuple[str, str]] | None = None) -> dict[str, int]:
    """Delete the lake partitions whose records the dataset's catalogued reading of that year already holds.

    Two cases, one rule. A partition on disk that the catalog does not list (a build whose catalog write was lost, a
    generation left behind) is read by nothing that plans from the catalog, but every scan of the folder and the
    footer census of ``info`` counted it: SIM-DO 2009 held an unlisted DOBR beside its 27 listed state partitions and
    2012 ten unlisted state partitions beside its listed DOBR, so 1.9 M deaths were held and counted twice
    (2026-11-21). And a listed state partition of a year whose listed national partition holds the same records is
    the second reading of a year SIM and SINASC publish twice (``coverage.national_or_states``).

    A partition goes when its year's reading (the listed partitions ``query()`` reads) contains each of its rows,
    compared as a multiset on every published column the two share, or when every file it was built from is still on
    the server (the catalog's crawl lists it): nothing reads it, and a build reproduces it. SIM's state and national files of a year are
    not always the same records: the national DBF of 2011-2017 declares the cause lines narrower than the state files
    (``LINHAA`` 10 characters in DOBR2012, 20 in DOES2012), so a third cause on a line is cut (DATA_SOURCES.md). An
    unlisted partition whose year has no listed reading holds records the catalog lost: kept and counted under
    ``unlisted_kept``, for a build of that year to register again.
    """
    import duckdb

    root = Path(lake_dir)
    listed = [dict(r) for r in catalog.query(
        "SELECT family_id, schema_signature, uf, year, relative_path, row_count, source_paths FROM lake_partitions")]
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
    # a listed partition outside its year's one reading (coverage.national_or_states, on the files' declared widths):
    # a state file beside the national one, or the narrower national file once the state files are built
    from .._query_engine.coverage import declared_widths, national_or_states

    widths = declared_widths(catalog)
    sources: dict[str, list[str]] = {
        str(r["relative_path"]): json.loads(r["source_paths"] or "[]")
        for r in catalog.query("SELECT relative_path, source_paths FROM lake_partitions")
    }
    for rows in by_year.values():
        reading = national_or_states(rows, lambda r: r["uf"], sources_of=lambda r: sources.get(str(r["relative_path"]), []),
                                     widths=widths)
        kept = {id(r) for r in reading}
        refs = [root / str(r["relative_path"]) for r in reading]
        candidates += [(root / str(r["relative_path"]), refs, r) for r in rows if id(r) not in kept]

    out = {"partitions": 0, "rows": 0, "bytes": 0, "unlisted_kept": 0, "listed_kept": 0}
    # a partition holding a source that a delta stands on stays: its versions are read from it (ADR-0234). Roraima's
    # preliminary SIM and SINASC state files were landed as snapshot versions and dropped beside the national file,
    # and their two deltas lost their base (2026-11-22)
    based = {str(r["source_id"]) for r in catalog.query("SELECT DISTINCT source_id FROM lake_versions")}
    if based:
        def stands_on(row: dict | None) -> bool:
            return row is not None and bool(based & set(json.loads(row.get("source_paths") or "[]")))

        bases = [c for c in candidates if stands_on(c[2])]
        out["versions_base_kept"] = len(bases)
        candidates = [c for c in candidates if not stands_on(c[2])]
    hashed: dict[tuple[tuple[str, ...], tuple[str, ...]], str] = {}
    serial = iter(range(1 << 30))
    con = duckdb.connect()
    con.execute("SET memory_limit='1GB'; SET threads=2; SET enable_progress_bar=false")
    for path, refs, row in candidates:
        contained = False
        if refs:
            shared = set.intersection(*(set(pq.read_schema(f).names) for f in refs))
            # the files' own fields, read without Hive columns: DuckDB matches names case-insensitively, and a file's
            # own `UF` (SINAN's national dengue and chikungunya files) read as the partition's `uf`, "BR"
            cols = sorted(c for c in pq.read_schema(path).names if c in shared and not c.startswith("_"))
            if cols:
                key = "md5(concat_ws('|', " + ", ".join(f"coalesce(\"{c}\"::VARCHAR, '~')" for c in cols) + "))"
                # the reference's multiset is hashed once per (files, columns): the 27 state partitions of a year
                # checked against one national file read it once, not 27 times
                ref_key = (tuple(str(f) for f in refs), tuple(cols))
                if ref_key not in hashed:
                    while len(hashed) >= 2:      # two years' references at most in memory
                        con.execute(f"DROP TABLE {hashed.pop(next(iter(hashed)))}")
                    hashed[ref_key] = f"_ref{next(serial)}"
                    files = ", ".join(f"'{f.as_posix()}'" for f in refs)
                    con.execute(f"CREATE TEMP TABLE {hashed[ref_key]} AS SELECT {key} k, count(*) n "
                                f"FROM read_parquet([{files}], union_by_name=true, hive_partitioning=false) GROUP BY 1")
                short = con.execute(
                    f"""WITH s AS (SELECT {key} k, count(*) n FROM read_parquet('{path.as_posix()}', hive_partitioning=false) GROUP BY 1)
                        SELECT coalesce(sum(s.n - coalesce(b.n, 0)), 0) FROM s LEFT JOIN {hashed[ref_key]} b USING (k)
                        WHERE s.n > coalesce(b.n, 0)""").fetchone()[0]  # type: ignore[index]
                contained = not short
        records_held = contained
        if not contained and refs:
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
        versions_held: set[tuple[str, str]] = set()
        if held is not None and records_held:
            from .versions import file_digests

            for part_file in siblings:
                versions_held.update(file_digests(part_file).items())
        # moved aside whole first, then removed: a reader holding a file open (Windows refuses) left half the files
        # deleted and the catalog row standing. A directory that stays locked is left as it was, and counted.
        aside = Path(lake_dir) / STAGING_DIR / f"{path.parent.name}.__redundant__.{uuid.uuid4().hex[:10]}"
        aside.parent.mkdir(parents=True, exist_ok=True)
        try:
            _retry_on_permission(lambda src=path.parent, dst=aside: src.rename(dst))
        except OSError:
            out["partitions"] -= 1
            out["locked"] = out.get("locked", 0) + 1
            continue
        _remove_tree(aside)
        if held is not None and records_held:
            # its records were found in the reading kept, record for record: the versions it was built from are held
            # there, and their downloads can go (`BlobStore.prune_verified(held_versions=)`, ADR-0234)
            held.update(versions_held)
        if row is not None:
            with catalog.write() as conn:
                conn.execute("DELETE FROM lake_partitions WHERE family_id=? AND schema_signature=? AND uf=? AND year=?",
                             (row["family_id"], row["schema_signature"], row["uf"], row["year"]))
    con.close()
    return out


def _reencode_file(path_text: str, dry_run: bool, compression: str, closed: bool = False) -> dict[str, Any]:
    """One partition file rewritten as the lake writes now (`reencode_lake`): ``{"state": "current" | "differing" |
    "rewritten" | "counted", "before", "after"}``. Runs in a worker process: a file is one task. ``closed`` writes the
    closed encoding (ADR-0238); a file already closed is current either way, never written back to the open one."""
    import json
    import os

    import duckdb

    from ..normalize.engine import key_fields, record_key_sql
    from ..raw_text import META_KEY, choose, compacted_sql, quote
    from .kept import CLOSED_ENCODING, CLOSED_ROW_GROUP_ROWS, ENCODING

    path = Path(path_text)
    if not path.is_file():
        return {"state": "absent"}
    source = pq.ParquetFile(path)
    names = source.schema_arrow.names
    keyed = RECORD_KEY in names
    meta = source.schema_arrow.metadata or {}
    stamp = meta.get(b"pegasus.encoding")
    encoded = stamp == CLOSED_ENCODING.encode() or (not closed and stamp == ENCODING.encode())
    raw_whole = META_KEY not in meta and any(n.endswith("__RAW") and n.removesuffix("__RAW") in names for n in names)
    if not keyed and encoded and not raw_whole:
        source.close()
        return {"state": "current"}
    con = duckdb.connect()
    con.execute("SET memory_limit='1GB'; SET threads=1; SET enable_progress_bar=false")
    try:
        if keyed:
            fields = key_fields(names)
            differ = con.execute(
                f"SELECT count(*) FROM read_parquet('{path.as_posix()}', hive_partitioning=false) "
                f"WHERE _record_key IS DISTINCT FROM {record_key_sql(fields) if fields else 'NULL'}").fetchone()[0]  # type: ignore[index]
            if differ:
                return {"state": "differing"}
        before = path.stat().st_size
        if dry_run:
            return {"state": "counted", "before": before}
        keep = [n for n in names if n != RECORD_KEY]
        schema = source.schema_arrow.remove(names.index(RECORD_KEY)) if keyed else source.schema_arrow
        renders: dict[str, str] = {}
        types: dict[str, str] = {}
        if raw_whole:
            relation = f"read_parquet('{path.as_posix()}', hive_partitioning=false)"
            described = {str(r[0]): str(r[1]) for r in con.execute(f"DESCRIBE SELECT * FROM {relation}").fetchall()}
            types = {n.removesuffix("__RAW"): str(described[n.removesuffix("__RAW")]) for n in names
                     if n.endswith("__RAW") and n.removesuffix("__RAW") in described and not n.startswith("_")}
            renders = choose(con, relation, types, quote)
            if renders:
                schema = schema.with_metadata({**(schema.metadata or {}), META_KEY: json.dumps(
                    {n: {"render": r, "type": types[n]} for n, r in renders.items()}, sort_keys=True).encode()})
        swaps = ", ".join(f"{compacted_sql(n, r, types[n], quote)} AS {quote(n + '__RAW')}" for n, r in renders.items())
        temporary = path.with_name(f".{path.name}.reencode")
        if closed:
            writer = parquet_writer(temporary, schema, compression, closed_dictionary=probe_dictionary(source, keep))
            groups = RowGroups(writer, CLOSED_ROW_GROUP_ROWS)
        else:
            writer = parquet_writer(temporary, schema, compression)
            groups = RowGroups(writer)
        try:
            for batch in source.iter_batches(batch_size=65_536, columns=keep):
                if swaps:
                    con.register("_b", batch)
                    compacted = con.execute(f"SELECT * REPLACE ({swaps}) FROM _b").to_arrow_table()
                    con.unregister("_b")
                    for n in renders:          # only the raw columns change: the others keep their own types
                        at = batch.schema.names.index(f"{n}__RAW")
                        batch = batch.set_column(at, batch.schema.field(at),
                                                 compacted.column(f"{n}__RAW").combine_chunks().cast(batch.schema.field(at).type))
                groups.write(batch)
            groups.flush()
        finally:
            writer.close()
            source.close()
        if pq.ParquetFile(temporary).metadata.num_rows != pq.ParquetFile(path).metadata.num_rows:
            temporary.unlink()
            raise RuntimeError(f"{path}: the re-encoded file does not hold the original's rows")
        # A reader holding the file open (another session's analysis) makes Windows refuse the rename: the rewrite of
        # 2026-11-22 stopped on its 13,040th file. Tried again for half a minute, then left as it was and counted; the
        # next run takes it.
        import time

        for attempt in range(15):
            try:
                os.replace(temporary, path)
                break
            except PermissionError:
                if attempt == 14:
                    temporary.unlink(missing_ok=True)
                    return {"state": "locked", "before": before}
                time.sleep(2)
        return {"state": "rewritten", "before": before, "after": path.stat().st_size}
    finally:
        con.close()


def reencode_lake(catalog: CatalogStore, lake_dir: str | Path, *, dry_run: bool = False,
                  compression: str = "zstd", workers: int | None = None,
                  closed_before: int | None = None) -> dict[str, int]:
    """Rewrite, value for value, the listed partition files not written as the lake writes now: those that store what
    the lake computes (the record key, `Lake._read_derived`) and those of another encoding than `persist.kept.ENCODING`
    (smaller row groups, a lower zstd level; their ``pegasus.encoding`` stamp says), and those whose typed columns keep
    their text as filed whole (``<NAME>__RAW``), which keep it only where a render does not give it back (`raw_text`;
    the renders are chosen over the file and named in its metadata). Batch by batch into row groups of
    the encoding's size, into a temporary file beside the partition that replaces it in one rename, so a reader sees the
    old file or the new one; the catalog's byte size follows. A file that stores a key is rewritten only when the key its
    fields hash to is the key it stores, on every row (`record_key_sql`): one that differed would change the identity of
    its records, and is kept and counted instead.

    Files are rewritten in ``workers`` processes at once (`_reencode_file`), by default as many as the cores less two and
    the free memory at 1 GiB a worker allow (a worker streams one file and holds about one row group): pyarrow compresses a file's columns in one thread, and one file at a
    time used 1.4 of 20 cores (2026-11-22). The catalog is written here, in one process.

    ``closed_before``: partitions of earlier years are closed and take the closed encoding (zstd 19, 1M-row groups, the
    dictionary chosen per column on a probe; ADR-0238); later years, still revised, keep the open one. Largest first."""
    import os
    from concurrent.futures import ProcessPoolExecutor, as_completed

    import psutil

    root = Path(lake_dir)
    out = {"files": 0, "rewritten": 0, "kept_differing": 0, "bytes_before": 0, "bytes_after": 0}
    listed = catalog.query("SELECT relative_path, year, byte_size FROM lake_partitions ORDER BY byte_size DESC, relative_path")
    rows = [str(r["relative_path"]) for r in listed]
    closing = {str(r["relative_path"]) for r in listed
               if closed_before is not None and r["year"] is not None and int(r["year"]) < closed_before}
    if workers is None:
        by_memory = int(psutil.virtual_memory().available // 2**30)
        workers = max(1, min((os.cpu_count() or 2) - 2, by_memory))
    out["workers"] = workers
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_reencode_file, str(root / rel), dry_run, compression, rel in closing): rel for rel in rows}
        for future in as_completed(futures):
            rel = futures[future]
            done = future.result()
            state = done["state"]
            if state in ("absent", "current"):
                continue
            out["files"] += 1
            if state == "differing":
                out["kept_differing"] += 1
                continue
            out["bytes_before"] += int(done.get("before") or 0)
            if state == "locked":
                out["locked"] = out.get("locked", 0) + 1
                continue
            if state != "rewritten":
                continue
            out["bytes_after"] += int(done["after"])
            out["rewritten"] += 1
            with catalog.write() as conn:
                conn.execute("UPDATE lake_partitions SET byte_size = byte_size - ? + ? WHERE relative_path = ?",
                             (int(done["before"]), int(done["after"]), rel))
    return out
