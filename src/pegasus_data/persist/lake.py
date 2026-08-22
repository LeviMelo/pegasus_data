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

import os

import json
import re
from collections.abc import Iterable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path

import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from ..catalog.store import Catalog, utcnow

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
        collected = [b for b in batches if b.num_rows]
        if not collected:
            return None
        table = pa.Table.from_batches(collected)
        directory = self.partition_dir(system, family_id, schema_signature, uf, year)
        if replace:
            part = 0
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"part-{part:05d}.parquet"

        # Stage first, delete second. This used to clear the partition — the
        # Parquet files AND their catalog rows — and only then start writing. A
        # disk-full, an interrupt or an Arrow raise in between left the
        # previously valid partition gone, and a write that succeeded while the
        # catalog update failed left a file that `ds.dataset()` still globs and
        # reads, with no metadata behind it.
        #
        # The staging name deliberately does not end in `.parquet`, so a reader
        # scanning the directory mid-write cannot pick it up.
        staged = directory / f".{target.name}.staging"
        try:
            pq.write_table(
                table,
                staged,
                compression=self.compression,
                use_dictionary=True,
                write_statistics=True,
                row_group_size=self.row_group_size,
                version="2.6",
            )
            if not staged.exists() or staged.stat().st_size == 0:
                raise OSError(f"staged partition {staged} is empty after write")
            if replace:
                self._clear_partition(system, family_id, schema_signature, uf, year)
            os.replace(staged, target)
        finally:
            # A failed write must not leave debris behind for the next run to
            # trip over; the old partition is still there and still valid.
            if staged.exists():
                staged.unlink()
        written = WrittenPartition(
            family_id=family_id,
            schema_signature=schema_signature,
            uf=uf,
            year=year,
            relative_path=str(target.relative_to(self.root)).replace("\\", "/"),
            row_count=table.num_rows,
            byte_size=target.stat().st_size,
        )
        if self.catalog is not None:
            self.catalog.executemany(
                """
                INSERT INTO lake_partitions (family_id, schema_signature, uf, year, relative_path,
                                             row_count, byte_size, source_paths, written_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(family_id, schema_signature, uf, year, relative_path) DO UPDATE SET
                    row_count=excluded.row_count, byte_size=excluded.byte_size,
                    source_paths=excluded.source_paths, written_at=excluded.written_at
                """,
                [
                    (
                        family_id, schema_signature, uf, year, written.relative_path,
                        written.row_count, written.byte_size, json.dumps(list(source_paths)), utcnow(),
                    )
                ],
            )
        return written

    def _clear_partition(
        self, system: str, family_id: str, schema_signature: str, uf: str, year: int
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
        available = set(dataset.schema.names)
        projection = None
        if columns:
            missing = [c for c in columns if c not in available]
            if missing:
                raise KeyError(
                    f"columns not present in the lake for {family_id}: {missing}. "
                    "Check the schema generation with Catalog.coverage()."
                )
            projection = list(columns)
            # Companion columns (`*_label`, `*_ibge7`) exist only where the
            # dictionary covered the field, so they are requested, not required.
            projection += [c for c in (optional_columns or []) if c in available]
        return dataset.to_table(columns=projection, filter=expression)

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
