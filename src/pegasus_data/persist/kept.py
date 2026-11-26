"""Kept artefacts: written whole or not at all, named by their version, older versions removed only after the new one
exists.

Every derived file on disk (a cube, a role table, a concept cache, an intake sidecar, a stamp file) follows the same
three rules, and each module had written its own copy of them, some with a temp name shared between processes and some
deleting the old version before the new one was written:

* ``write_atomic``: the file appears complete or not at all, through a temp name unique to the process and the call
  (``staging.staged_file``, the one mechanism);
* ``kept``: the path is computed from a key and a version digest; a file there is the answer, otherwise it is built,
  written atomically, and only THEN are its older siblings removed;
* ``cap_by_recency``: a folder of rebuildable files is held to a size, least recently used first.

The caller keeps its own file-name format; nothing here names a file.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from .staging import staged_file

__all__ = ["cap_by_recency", "kept", "prune_siblings", "write_atomic", "write_json_atomic", "write_parquet_atomic",
           "write_text_atomic"]


def write_atomic(path: str | Path, write: Callable[[Path], object], *, require_nonempty: bool = True) -> None:
    """Call ``write(tmp)`` on a hidden temp path beside ``path`` (unique per process and per call), then replace
    ``path`` with it. A failure leaves no temp and the old file untouched."""
    with staged_file(Path(path), require_nonempty=require_nonempty) as tmp:
        write(tmp)


#: The one Parquet encoding of what the home writes (lake partitions, role tables, links, cubes, registries): zstd at
#: level 9 and row groups of 262,144 rows. Measured on SIH-RD SP 2024 (2.86 M rows): 65,536-row groups at level 3 wrote
#: 113 MB, 262,144-row groups 102.8 MB, and level 9 96.2 MB, in the same write time and with faster reads (level 15:
#: 94.6 MB in twice the time; 2026-11-22). Written into each file's metadata as ``pegasus.encoding``, so a re-encode
#: knows the files written before (`persist.lake.reencode_lake`).
ZSTD_LEVEL = 9
ROW_GROUP_ROWS = 262_144
ENCODING = f"zstd{ZSTD_LEVEL}-rg{ROW_GROUP_ROWS}"

#: The encoding of a closed lake partition (a year no longer revised), written once by `persist.lake.reencode_lake`
#: (ADR-0238): zstd 19, row groups of 1,048,576 rows, and the dictionary kept only on the columns where it is smaller on
#: a probe of the file. Whole AL 2023 files: SIH-SP 16.71 to 13.69 MB (-18%), SIH-RD 5.11 to 4.58 (-10%), CNES-PF 24.93
#: to 21.55 (-14%). Level 22 gave 13.71 MB where 19 gave 13.74, in 34 s against 27; both read at about the speed of 9.
CLOSED_ZSTD_LEVEL = 19
CLOSED_ROW_GROUP_ROWS = 1_048_576
CLOSED_ENCODING = f"zstd{CLOSED_ZSTD_LEVEL}-rg{CLOSED_ROW_GROUP_ROWS}-dictprobe"


def parquet_options(**options: Any) -> dict[str, Any]:
    """``options`` for `pq.write_table`/`pq.ParquetWriter` with the home's encoding wherever the caller set none."""
    out = {"compression": "zstd", "row_group_size": ROW_GROUP_ROWS, **options}
    if out.get("compression") == "zstd" and "compression_level" not in options:
        out["compression_level"] = ZSTD_LEVEL
    return out


def stamped(table: Any) -> Any:
    """``table`` with ``pegasus.encoding`` in its schema metadata."""
    return table.replace_schema_metadata({**(table.schema.metadata or {}), b"pegasus.encoding": ENCODING.encode()})


def write_parquet_atomic(table: Any, path: str | Path, **options: Any) -> None:
    """``pq.write_table(table, path, **options)``, whole or not at all, in the home's encoding unless ``options`` say
    otherwise (`parquet_options`)."""
    import pyarrow.parquet as pq

    write_atomic(path, lambda tmp: pq.write_table(stamped(table), tmp, **parquet_options(**options)))


def write_json_atomic(obj: Any, path: str | Path, **options: Any) -> None:
    """``json.dumps(obj, **options)`` written as UTF-8, whole or not at all."""
    write_text_atomic(json.dumps(obj, **options), path)


def write_text_atomic(text: str, path: str | Path) -> None:
    """``text`` written as UTF-8, whole or not at all."""
    write_atomic(path, lambda tmp: tmp.write_text(text, encoding="utf-8"), require_nonempty=False)


def remove_if_free(path: Path) -> bool:
    """Delete a cache file nothing needs, unless another process holds it open: Windows then refuses (``PermissionError``),
    and the file is left for a later prune, never an error in the caller. Two studies reading one field at once, one
    rebuilding its cube, had crashed the other on the stale sibling it was reading (2026-11-22). True when removed."""
    try:
        path.unlink(missing_ok=True)
        return True
    except PermissionError:
        return False


def prune_siblings(keep: Path, siblings: Iterable[Path]) -> None:
    """Remove every path of ``siblings`` except ``keep``; one held open by a reader is left (`remove_if_free`)."""
    for stale in list(siblings):
        if stale != keep:
            remove_if_free(stale)


def kept(target: Path, build: Callable[[], Any], *, read: Callable[[Path], Any], write: Callable[[Any, Path], object],
         siblings: str | Callable[[Path], Iterable[Path]] | None = None) -> Any:
    """The artefact at ``target`` (named by the caller from its key and version digest): read if present, else built,
    written atomically and returned. ``siblings`` (a glob relative to the target's folder, or a function of the target)
    names the older versions to remove, and they go only after the new file is in place: a build or a write that fails
    removes nothing."""
    if target.exists():
        return read(target)
    value = build()
    write_atomic(target, lambda tmp: write(value, tmp))
    if siblings is not None:
        prune_siblings(target, target.parent.glob(siblings) if isinstance(siblings, str) else siblings(target))
    return value


def cap_by_recency(files: Iterable[Path], limit_bytes: float, *, keep: Path | None = None) -> None:
    """Delete the least recently modified of ``files`` (except ``keep``) until what is left fits ``limit_bytes``."""
    sized = []
    for f in files:
        try:
            st = f.stat()
        except FileNotFoundError:        # removed by another process meanwhile
            continue
        sized.append((st.st_mtime, st.st_size, f))
    sized.sort(key=lambda x: x[0])
    total = sum(size for _, size, _ in sized)
    for _, size, f in sized:
        if total <= limit_bytes:
            break
        if f != keep and remove_if_free(f):
            total -= size
