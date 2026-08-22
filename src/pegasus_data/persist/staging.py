"""One durability model for every derived artifact.

The lake and the reference tables are both *derived* — rebuildable from the
catalog and the blob store — and both were rewritten in place by code that had
independently worked out how not to destroy the old copy before the new one
existed. They arrived at the same rule by different routes and expressed it
twice:

* a partition staged under a dotted name, validated for non-emptiness, then
  ``os.replace``d over the target;
* a reference tree staged in a sibling directory, then renamed over the old
  one, with a separate merge path for a scoped rebuild.

Two implementations of one rule is how they drift, and it is the reason the
recovery logic in each had to be reasoned about separately. The rule itself is
short enough to state once:

**A derived artifact is replaced only by an artifact that already exists in
full.** Until the swap, the old one is intact and readable. After a failure,
the old one is still intact and no debris is left for the next run to trip
over.

These helpers do not make the swap *transactional* across artifacts — nothing
here spans two targets — and they do not pretend to. They make each individual
replacement atomic, which is the property both call sites were hand-rolling.
"""

from __future__ import annotations

import os
import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

__all__ = ["staged_file", "staged_tree"]


@contextmanager
def staged_file(target: Path, *, require_nonempty: bool = True) -> Iterator[Path]:
    """Yield a path to write; on clean exit it atomically becomes ``target``.

    The staging name is dotted and does NOT carry the target's suffix, because
    a reader scanning the directory mid-write must not be able to pick it up —
    a half-written `.parquet` in a Hive partition is a file `ds.dataset()` will
    happily try to read.

    ``require_nonempty`` refuses a swap when the writer produced nothing. A
    zero-byte file replacing a good partition is worse than no write at all: it
    reads as an empty dataset rather than as a failure.
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.parent / f".{target.name}.staging"
    if staged.exists():
        staged.unlink()
    try:
        yield staged
        if require_nonempty and (not staged.exists() or staged.stat().st_size == 0):
            raise OSError(f"staged artifact {staged} is empty after write")
        os.replace(staged, target)
    finally:
        # A failed write must not leave debris behind; the old artifact is
        # still there and still valid.
        if staged.exists():
            staged.unlink()


def _merge_units(staging: Path, depth: int) -> Iterator[Path]:
    """Directories at ``depth`` below ``staging`` — the units a merge replaces.

    A directory shallower than ``depth`` that has no subdirectories of its own
    is yielded too. Otherwise a staged tree that happens to be flatter than the
    merge depth would contribute nothing and its content would be dropped.
    """

    def walk(directory: Path, level: int) -> Iterator[Path]:
        if level == depth:
            yield directory
            return
        children = [c for c in sorted(directory.iterdir()) if c.is_dir()]
        if not children:
            yield directory
            return
        for child in children:
            yield from walk(child, level + 1)

    for entry in sorted(staging.iterdir()):
        if entry.is_dir():
            yield from walk(entry, 1)
        else:
            yield entry


@contextmanager
def staged_tree(
    target: Path, *, merge: bool = False, merge_depth: int | None = None
) -> Iterator[Path]:
    """Yield a directory to fill; on clean exit it replaces ``target``.

    ``merge=False`` swaps the whole tree: the old one is renamed aside, the new
    one takes its place, and only then is the old one removed. A reader holding
    the old path keeps reading a complete tree the entire time.

    ``merge=True`` is for a SCOPED rebuild, which must not delete what it was
    not asked about. Only the subtrees the rebuild actually produced replace
    their counterparts; everything else is left alone. Swapping here would
    silently drop every table outside the scope — which is the whole failure
    this distinction exists to prevent.

    ``merge_depth`` says at WHICH level those subtrees live, and getting it
    wrong is destructive in exactly the way merging was meant to avoid. The
    reference warehouse is laid out ``<codelist>/system=<sys>/window=<w>``; a
    rebuild scoped to one system stages ``<codelist>/system=SIHSUS`` only, so
    merging at depth 1 replaces the whole ``<codelist>`` directory and deletes
    every OTHER system's copy of that codelist. The unit of replacement has to
    be the unit of scope. ``merge=True`` means depth 1; pass ``merge_depth``
    when the scope is deeper.
    """
    if merge_depth is None:
        merge_depth = 1 if merge else 0
    target = Path(target)
    staging = target.with_name(target.name + ".__staging__")
    previous = target.with_name(target.name + ".__previous__")
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True, exist_ok=True)
    try:
        yield staging
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    if previous.exists():
        shutil.rmtree(previous)
    if merge_depth and target.exists():
        for unit in list(_merge_units(staging, merge_depth)):
            destination = target / unit.relative_to(staging)
            if destination.exists():
                if destination.is_dir():
                    shutil.rmtree(destination)
                else:
                    destination.unlink()
            destination.parent.mkdir(parents=True, exist_ok=True)
            unit.rename(destination)
        shutil.rmtree(staging, ignore_errors=True)
        return
    if target.exists():
        target.rename(previous)
    staging.rename(target)
    if previous.exists():
        shutil.rmtree(previous, ignore_errors=True)
