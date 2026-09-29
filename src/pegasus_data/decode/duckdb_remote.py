"""Read a remote DuckDB database's schema from a few ranged reads (ADR-0083).

DATASUS publishes ``SIHSUS/base_aih1.duck``: 12 GB, a star schema of 221.5
million admissions (``stg_aih``, 74 columns) and twelve dimension tables. The
catalog needs its tables and columns, not its rows. A DuckDB file keeps its
catalog in metadata blocks named by a 12 KB header, and every block carries a
checksum, so:

1. write the header into a SPARSE local file of the database's full size;
2. attach it read-only; DuckDB reports "Corrupt database file ... at location N"
   for the first block it needs that is not there yet;
3. fetch that 256 KB block by ranged FTP read (``REST``) and retry.

Measured 2026-09-29: 8 blocks (2 MB) describe ``base_aih1.duck``. The file
stays sparse; it is extended by one write at its end, because ``truncate()`` on
Windows zero-fills and allocated all 12 GB.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

HEADER_BYTES = 3 * 4096
BLOCK_BYTES = 262144
MAX_BLOCKS = 64
_LOCATION = re.compile(r"location:?\s*(\d+)|block at location (\d+)", re.I)


@dataclass(frozen=True, slots=True)
class RemoteTable:
    name: str
    columns: tuple[tuple[str, str], ...]  # (name, duckdb type)
    estimated_rows: int


def _sparse(path: Path, size: int) -> None:
    path.touch()
    if os.name == "nt":
        subprocess.run(["fsutil", "sparse", "setflag", str(path)], check=True, capture_output=True)
    with open(path, "r+b") as f:
        f.seek(size - 1)
        f.write(b"\0")


def remote_duckdb_tables(
    fetch_range: Callable[[int, int], bytes],
    size: int,
    *,
    workdir: str | Path | None = None,
    max_blocks: int = MAX_BLOCKS,
) -> tuple[list[RemoteTable], int]:
    """Every table of the remote database, and the bytes fetched to learn it."""
    import duckdb

    fetched: set[int] = set()
    total = 0
    with tempfile.TemporaryDirectory(dir=workdir) as tmp:
        local = Path(tmp) / "remote.duck"
        _sparse(local, size)

        def put(offset: int, length: int) -> None:
            nonlocal total
            data = fetch_range(offset, length)
            with open(local, "r+b") as f:
                f.seek(offset)
                f.write(data)
            total += len(data)

        put(0, HEADER_BYTES)
        for _ in range(max_blocks + 1):
            con = duckdb.connect()
            try:
                con.execute(f"ATTACH '{local.as_posix()}' AS r (READ_ONLY)")
                rows = con.execute(
                    "SELECT table_name, column_name, data_type FROM information_schema.columns "
                    "WHERE table_catalog = 'r' ORDER BY table_name, ordinal_position"
                ).fetchall()
                sizes = dict(con.execute(
                    "SELECT table_name, estimated_size FROM duckdb_tables() WHERE database_name = 'r'"
                ).fetchall())
                tables: dict[str, list[tuple[str, str]]] = {}
                for table, column, dtype in rows:
                    tables.setdefault(str(table), []).append((str(column), str(dtype)))
                return [
                    RemoteTable(name, tuple(cols), int(sizes.get(name) or 0))
                    for name, cols in tables.items()
                ], total
            except duckdb.Error as exc:
                m = _LOCATION.search(str(exc))
                location = int(next(g for g in m.groups() if g)) if m else None
                if location is None or len(fetched) >= max_blocks:
                    raise ValueError(f"remote DuckDB unreadable after {len(fetched)} blocks: {exc}") from exc
                block = (location - HEADER_BYTES) // BLOCK_BYTES
                if block in fetched:
                    raise ValueError(f"remote DuckDB block {block} still unreadable: {exc}") from exc
                fetched.add(block)
                put(HEADER_BYTES + block * BLOCK_BYTES, BLOCK_BYTES)
            finally:
                con.close()
    raise ValueError("remote DuckDB: block budget exhausted")
