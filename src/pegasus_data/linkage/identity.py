"""Record identity and the linkage DuckDB connection.

Kept apart from ``roles.py`` on purpose: the role-table cache is keyed on the
code that builds role tables, and the identity rule and connection settings
do not change those tables. While they lived in ``roles.py``, every edit to
them threw away every cached national role table (2026-10-03).
"""

from __future__ import annotations

import duckdb
import pyarrow as pa
import pyarrow.compute as pc


def connect() -> duckdb.DuckDBPyConnection:
    """A DuckDB connection for linkage, bounded in memory.

    DuckDB's default limit is 80% of RAM: the national newborn link's joins
    grew one process to 25 GB on a 32 GB machine and started it paging
    (2026-10-03). Capped at 40% of physical memory, a large join spills to
    the work directory instead.
    """
    import os

    from ..config import load_settings

    con = duckdb.connect()
    try:
        total = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")  # type: ignore[attr-defined]
    except (AttributeError, ValueError, OSError):
        import ctypes

        class _Mem(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

        mem = _Mem()
        mem.dwLength = ctypes.sizeof(_Mem)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))  # type: ignore[attr-defined]
        total = int(mem.ullTotalPhys)
    spill = load_settings().work_dir / "duckdb_spill"
    spill.mkdir(parents=True, exist_ok=True)
    con.execute(f"SET memory_limit = '{max(1, int(total * 0.4) // 2**30)}GB'")
    con.execute(f"SET temp_directory = '{spill.as_posix()}'")
    return con


#: SQL for a record's identity over a relation with provenance columns; the
#: same rule as :func:`record_ids`. Exact duplicates within one source file
#: are numbered by their row order (key, key#2, key#3...): CIHA 2022 publishes
#: 735,049 rows identical to another row of the same file (131 among its
#: deaths), and one key would have merged them. The n-th copy in the national
#: file and in its state's file get the same identity.
RECORD_ID_SQL = ("coalesce(_record_key || CASE WHEN _dup > 1 THEN '#' || CAST(_dup AS VARCHAR) ELSE '' END, "
                 "_blob_sha256 || ':' || CAST(_row AS VARCHAR))")
DUP_SQL = "row_number() OVER (PARTITION BY _source_path, _record_key ORDER BY _row) AS _dup"


def record_ids(table: pa.Table) -> pa.Array:
    """Each record's identity: its content key where the lake or decoder
    stamped one (``_record_key``, OQ-65), numbered for exact duplicates within
    a source file, else ``_blob_sha256:_row``."""
    fallback = pc.binary_join_element_wise(pc.cast(table.column("_blob_sha256"), pa.string()),
                                           pc.cast(table.column("_row"), pa.string()), ":")
    if "_record_key" not in table.column_names:
        return fallback

    con = connect()
    con.register("t", pa.table({"_record_key": pc.cast(table.column("_record_key"), pa.string()),
                                "_source_path": pc.cast(table.column("_source_path"), pa.string()),
                                "_row": table.column("_row"),
                                "_blob_sha256": pc.cast(table.column("_blob_sha256"), pa.string()),
                                "_pos": pa.array(range(table.num_rows), pa.int64())}))
    return con.execute(f"SELECT {RECORD_ID_SQL} AS id FROM (SELECT *, {DUP_SQL} FROM t) ORDER BY _pos"
                       ).fetch_arrow_table().column("id").combine_chunks()


__all__ = ["DUP_SQL", "RECORD_ID_SQL", "connect", "record_ids"]
