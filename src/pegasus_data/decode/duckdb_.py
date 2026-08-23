"""``.duck`` and ``.duck.zip`` reader (D1).

Measured on the tree: 66 loose ``.duck`` files plus 12 ``.duck.zip``, including
eleven APAC DuckDB databases under ``Dados_Abertos/APAC_SIA/`` (dialysis,
nephrology, fistula, medication, bariatric …), 66 under
``Dados_Abertos/BackUp_Ducks_SIASUS_PA/``, and a 12 GB ``SIHSUS/base_aih1.duck``.

A DuckDB database is a *container of many tables*, so one file becomes many
DecodedTables — the same shape as an archive.

``[V]`` resolved by construction rather than by assumption: DuckDB refuses to
open a file written by a newer storage version. That is reported as an **open
question with the observed version string**, never as a hard failure and never
as a silently skipped file.
"""

from __future__ import annotations

import re
import struct
from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa

from .base import DecodedTable, DecodeError, FieldMeta

_VERSION_ERROR = re.compile(r"version|storage", re.I)


class DuckStorageVersionError(DecodeError):
    """The database was written by a DuckDB storage version this build cannot read."""

    def __init__(self, path: str, detail: str, observed_version: int | None) -> None:
        self.path = path
        self.detail = detail
        self.observed_version = observed_version
        super().__init__(
            f"{path}: DuckDB storage version {observed_version or 'unknown'} not readable "
            f"by the installed library ({detail})"
        )


def storage_version(path: str | Path) -> int | None:
    """Read the storage version from the DuckDB header without opening the file.

    Layout: the main header begins with the 4-byte magic ``DUCK`` followed by a
    little-endian ``uint64`` version number.
    """
    try:
        with Path(path).open("rb") as fh:
            head = fh.read(16)
    except OSError:
        return None
    if head[:4] != b"DUCK":
        return None
    try:
        return struct.unpack_from("<Q", head, 8)[0]
    except struct.error:
        return None


def list_tables(path: str | Path) -> list[tuple[str, str]]:
    """Return ``(schema, table)`` pairs, or raise a typed version error."""
    import duckdb

    try:
        conn = duckdb.connect(str(path), read_only=True)
    except Exception as exc:
        detail = str(exc)
        if _VERSION_ERROR.search(detail):
            raise DuckStorageVersionError(str(path), detail, storage_version(path)) from exc
        raise DecodeError(f"duckdb open failed for {path}: {detail}") from exc
    try:
        rows = conn.execute(
            """
            SELECT table_schema, table_name
              FROM information_schema.tables
             WHERE table_type IN ('BASE TABLE', 'VIEW')
             ORDER BY table_schema, table_name
            """
        ).fetchall()
        return [(str(s), str(t)) for s, t in rows]
    finally:
        conn.close()


def read_duckdb(
    path: str | Path,
    *,
    row_limit: int | None = None,
    batch_rows: int = 65_536,
    columns: frozenset[str] | None = None,
    members: frozenset[str] | None = None,
) -> list[DecodedTable]:
    """One :class:`DecodedTable` per selected database table.

    ``fields`` continues to describe the complete physical table so schema
    matching is stable, while the lazy query materialises only ``columns``.
    """
    import duckdb

    tables = list_tables(path)
    out: list[DecodedTable] = []
    for schema_name, table_name in tables:
        member = f"{schema_name}.{table_name}" if schema_name != "main" else table_name
        if members is not None and member not in members:
            continue
        qualified = f'"{schema_name}"."{table_name}"'
        conn = duckdb.connect(str(path), read_only=True)
        try:
            described = conn.execute(f"DESCRIBE {qualified}").fetchall()
            row_count = conn.execute(f"SELECT COUNT(*) FROM {qualified}").fetchone()
        finally:
            conn.close()
        fields = [
            FieldMeta(name=str(r[0]).upper(), physical_type=f"duckdb:{r[1]}", order=i)
            for i, r in enumerate(described)
        ]
        physical_names = [str(row[0]) for row in described]
        selected_names = [
            name for name in physical_names if columns is None or name.upper() in columns
        ]
        # Match the DBF projection contract: if nothing matches, read the full
        # table so a misspelled projection cannot masquerade as an empty source.
        if not selected_names:
            selected_names = physical_names
        select_list = ", ".join(f'"{name.replace(chr(34), chr(34) * 2)}"' for name in selected_names)
        output_names = [name.upper() for name in selected_names]

        # `fields` and `qualified` are bound as defaults: without that, every
        # generator built in this loop would close over the *last* table's names
        # and silently mislabel columns when finally iterated.
        def _make_iter(
            q: str = qualified,
            selection: str = select_list,
            names: list[str] = output_names,
        ) -> Iterator[pa.RecordBatch]:
            conn2 = duckdb.connect(str(path), read_only=True)
            try:
                sql = f"SELECT {selection} FROM {q}"
                if row_limit is not None:
                    sql += f" LIMIT {int(row_limit)}"
                reader = conn2.execute(sql).fetch_record_batch(batch_rows)
                while True:
                    try:
                        batch = reader.read_next_batch()
                    except StopIteration:
                        return
                    if batch.num_rows == 0:
                        return
                    yield batch.rename_columns(names)
            finally:
                conn2.close()

        out.append(
            DecodedTable(
                path=str(path),
                member=member,
                reader="duckdb",
                fields=fields,
                batches=_make_iter,
                row_count=int(row_count[0]) if row_count else None,
                container="duckdb",
            )
        )
    if not out and members is None:
        raise DecodeError(f"duckdb database holds no tables: {path}")
    return out
