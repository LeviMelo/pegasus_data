"""The one place a DuckDB connection is opened (ADR-0245).

DuckDB's own defaults are made for a machine it has to itself: a connection may take 80% of the RAM before it spills,
and an in-memory one spills into ``.tmp`` under whatever folder the process was started in. On 2026-11-28 the package
opened connections in 38 places; 10 set a limit, each its own (1, 1.5, 2 GB, a share of the machine), and three had
grown a private ``connect`` helper. Two sessions' jobs each within "80% of RAM" is the machine paging (2026-11-22,
2026-11-27).

`connect` gives every connection the same floor: a memory limit, this process's own spill directory under the home's
work folder (`Settings.duckdb_spill`), no progress bar. A caller states only what its job needs beyond that. A query
that cannot spill and does not fit fails with DuckDB's out-of-memory error naming the limit, which is the caller's
cue to pass ``memory_gb`` for that job, measured: it never takes the machine with it.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = ["DEFAULT_MEMORY_GB", "MACHINE_SHARE", "connect"]

#: A connection's memory before it spills, where the caller names none (``PEGASUS_DUCKDB_MEMORY_GB`` overrides).
DEFAULT_MEMORY_GB = 2.0

#: No connection is given more than this share of the machine's RAM, whatever is asked.
MACHINE_SHARE = 0.4


@lru_cache(maxsize=1)
def _process_spill() -> str | None:
    """The process's spill directory in its home, or None while that home does not exist: opening a connection never
    creates a home (a test run under a redirected profile made ``%LOCALAPPDATA%/pegasus-data/work`` this way,
    2026-11-28). Without one DuckDB keeps its own default, a ``.tmp`` it creates only if it spills."""
    from .config import load_settings

    settings = load_settings()
    return settings.duckdb_spill().as_posix() if settings.root.is_dir() else None


@lru_cache(maxsize=1)
def _machine_gb() -> float:
    import psutil

    return psutil.virtual_memory().total / 2**30


def connect(database: str | Path = ":memory:", *, read_only: bool = False, memory_gb: float | None = None,
            threads: int | None = None, ordered: bool | None = None, spill_gb: float | None = None,
            settings: Any = None) -> Any:
    """A DuckDB connection with the package's floor.

    ``memory_gb``: the limit before it spills (default `DEFAULT_MEMORY_GB`), never above `MACHINE_SHARE` of the RAM
    nor below 0.5. ``threads``: DuckDB's own count unless given. ``ordered``: ``preserve_insertion_order`` (DuckDB's
    default is true; false lets a large copy use less memory, where the caller orders its rows itself). ``spill_gb``
    bounds the spill directory's size. ``settings`` names the home whose work folder takes the spill (default: the
    process's settings, resolved once)."""
    import duckdb

    con = duckdb.connect(str(database), read_only=read_only)
    asked = memory_gb if memory_gb is not None else float(os.environ.get("PEGASUS_DUCKDB_MEMORY_GB") or DEFAULT_MEMORY_GB)
    limit_mb = int(max(0.5, min(asked, MACHINE_SHARE * _machine_gb())) * 1024)
    spill = settings.duckdb_spill().as_posix() if settings is not None else _process_spill()
    options = [f"SET memory_limit='{limit_mb}MiB'", "SET enable_progress_bar=false"]
    if spill:
        options.append(f"SET temp_directory='{spill}'")
    if threads is not None:
        options.append(f"SET threads={int(threads)}")
    if ordered is not None:
        options.append(f"SET preserve_insertion_order={'true' if ordered else 'false'}")
    if spill_gb is not None:
        options.append(f"SET max_temp_directory_size='{int(spill_gb)}GiB'")
    con.execute("; ".join(options))
    return con
