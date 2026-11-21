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


def write_parquet_atomic(table: Any, path: str | Path, **options: Any) -> None:
    """``pq.write_table(table, path, **options)``, whole or not at all."""
    import pyarrow.parquet as pq

    write_atomic(path, lambda tmp: pq.write_table(table, tmp, **options))


def write_json_atomic(obj: Any, path: str | Path, **options: Any) -> None:
    """``json.dumps(obj, **options)`` written as UTF-8, whole or not at all."""
    write_text_atomic(json.dumps(obj, **options), path)


def write_text_atomic(text: str, path: str | Path) -> None:
    """``text`` written as UTF-8, whole or not at all."""
    write_atomic(path, lambda tmp: tmp.write_text(text, encoding="utf-8"), require_nonempty=False)


def prune_siblings(keep: Path, siblings: Iterable[Path]) -> None:
    """Remove every path of ``siblings`` except ``keep``."""
    for stale in list(siblings):
        if stale != keep:
            stale.unlink(missing_ok=True)


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
    files = sorted(files, key=lambda f: f.stat().st_mtime)
    total = sum(f.stat().st_size for f in files)
    for f in files:
        if total <= limit_bytes:
            break
        if f != keep:
            total -= f.stat().st_size
            f.unlink(missing_ok=True)
