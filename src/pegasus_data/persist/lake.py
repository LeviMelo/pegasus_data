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
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from ..catalog.store import Catalog, utcnow
from .staging import staged_file, staged_tree

_SAFE = re.compile(r"[^A-Za-z0-9_.=-]+")


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


class Lake:
    """Writes and reads the Parquet lake, and records every partition it writes."""

    def __init__(
        self,
        root: str | Path,
        catalog: Catalog | None = None,
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
            writer = pq.ParquetWriter(
                staged,
                first.schema,
                compression=self.compression,
                use_dictionary=True,
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
            with staged_tree(directory) as staged_directory:
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

    def _clear_partition(
        self,
        system: str,
        family_id: str,
        schema_signature: str,
        uf: str,
        year: int,
        *,
        keep: Path | None = None,
    ) -> int:
        """Drop the Parquet and the catalog rows for one partition, together.

        Both or neither: a file left on disk without its catalog row still gets
        read by ``ds.dataset()``, which globs the directory and does not consult
        the catalog at all. Clearing only the catalog would hide the duplication
        rather than remove it.
        """
        directory = self.partition_dir(system, family_id, schema_signature, uf, year)
        removed = 0
        if directory.is_dir():
            for stale in directory.glob("*.parquet"):
                if keep is not None and stale.resolve() == keep.resolve():
                    # The replacement itself. Clearing now happens AFTER the
                    # swap, so the file that just landed must survive it.
                    continue
                stale.unlink()
                removed += 1
        if self.catalog is not None:
            self.catalog.execute(
                "DELETE FROM lake_partitions WHERE family_id=? AND schema_signature=? "
                "AND uf=? AND year=?",
                (family_id, schema_signature, uf, year),
            )
        return removed

    def next_part_number(
        self, system: str, family_id: str, schema_signature: str, uf: str, year: int
    ) -> int:
        directory = self.partition_dir(system, family_id, schema_signature, uf, year)
        if not directory.is_dir():
            return 0
        existing = sorted(directory.glob("part-*.parquet"))
        return len(existing)

    # ------------------------------------------------------------------- read

    def dataset(self, system: str, family_id: str, schema_signature: str | None = None) -> ds.Dataset:
        base = self.root / _safe(system) / _safe(family_id)
        if schema_signature:
            base = base / f"schema_signature={_safe(schema_signature)}"
        if not base.exists():
            raise FileNotFoundError(f"no lake data at {base}")
        return ds.dataset(base, format="parquet", partitioning="hive")

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
    ) -> pa.Table:
        dataset = self.dataset(system, family_id, schema_signature)
        expression = None
        if uf is not None:
            ufs = [uf] if isinstance(uf, str) else list(uf)
            expression = ds.field("uf").isin(ufs)
        if years is not None:
            year_list = list(years)
            year_filter = ds.field("year").isin(year_list)
            expression = year_filter if expression is None else (expression & year_filter)
        # `None` means EVERYTHING; `[]` means NOTHING. Testing truthiness
        # conflated them, so a generation where none of the requested fields
        # physically exists asked for an empty projection and got every column
        # instead — the opposite of what the caller wanted, and the shape that
        # structural null-filling depends on.
        projection = self._projection(dataset, family_id, columns, optional_columns)
        return dataset.to_table(columns=projection, filter=expression)

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
                "Check the schema generation with Catalog.coverage()."
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
    ) -> ds.Scanner:
        """:meth:`read` without materialising the table.

        Same projection and same partition filters, handed to a Scanner instead
        of `to_table()`, so a caller can iterate batches under bounded memory.
        `where` is an extra predicate on the data columns, pushed into the scan
        rather than applied afterwards.
        """
        dataset = self.dataset(system, family_id, schema_signature)
        expression = None
        if uf is not None:
            ufs = [uf] if isinstance(uf, str) else list(uf)
            expression = ds.field("uf").isin(ufs)
        if years is not None:
            year_filter = ds.field("year").isin(list(years))
            expression = year_filter if expression is None else (expression & year_filter)
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

    def size_on_disk(self) -> int:
        return sum(p.stat().st_size for p in self.root.rglob("*.parquet"))

    def iter_parquet(self) -> Iterator[Path]:
        yield from self.root.rglob("*.parquet")
