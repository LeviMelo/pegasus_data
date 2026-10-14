"""The curation epoch: the one key under which a process holds what it derived from the curation files.

``curation/`` is data that ships with the package and is read many times by many loaders (the roles, the event types,
the grids, the inline codelists, the ontology, the declared fields, the care flows). Each used to keep its own
``lru_cache`` with its own key and its own invalidation: a key that was nothing (``maxsize=1``: a process that changed
its curation directory kept serving the old one), a root, or every file's modification time (``Ontology.load`` stat-ed
190 files on each call). Here they have one key and one way to forget:

* :func:`curation_epoch`: the curation directory in use and the digest of its content, computed once per process and
  directory (the files are package data, they do not change inside a process; a REPL that edits them calls
  :func:`forget_curation`);
* :func:`curated`: memoise a loader of curation for the epoch. The value is built once and then SHARED, never copied:
  a caller must not edit it, nor hand out its lists and mappings;
* :func:`forget_curation`: drop the digests and every memo (tests that write a curation directory, a REPL).
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from functools import lru_cache, wraps
from pathlib import Path
from typing import Any, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

#: The curation a codelist is built from: harvested tables, variables' inline codes, curated codelists. A role, a link
#: or a dataset declaration labels nothing, so editing one leaves the reference tables current.
CODELIST_CURATION = ("codes", "variables", "codelists.yml")


@lru_cache(maxsize=16)
def _fingerprint(root: str, parts: tuple[str, ...] | None = None) -> str:
    digest = hashlib.blake2b(digest_size=16)
    paths = Path(root).rglob("*.yml") if parts is None else (
        q for part in parts for q in ((Path(root) / part).rglob("*.yml") if (Path(root) / part).is_dir()
                                      else [Path(root) / part] if (Path(root) / part).exists() else []))
    for path in sorted(paths):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def curation_fingerprint(root: Path) -> str:
    """A digest of the curation files, so a changed meaning can be noticed.

    Content, not mtime: the YAML ships inside a wheel and its timestamps say when it was unpacked, which is unrelated
    to whether anything was edited. Cached per path because it is asked on every fetch and the answer cannot change
    inside one process: the files are package data.
    """
    return _fingerprint(str(root))


def codelist_fingerprint(root: Path) -> str:
    """A digest of the curation the reference tables are written from (`CODELIST_CURATION`): a role edit changed the
    whole-curation digest and rewrote every SINAN lookup (about 70 s a time, 2026-10-08)."""
    return _fingerprint(str(root), CODELIST_CURATION)


def curation_epoch(root: Path | str | None = None) -> tuple[str, str]:
    """``(the curation directory, the digest of its content)``: what every curation-derived memo is keyed on. The
    directory in use (`config.curation_root`) when none is named."""
    if root is None:
        from ..config import curation_root

        root = curation_root()
    return str(root), _fingerprint(str(root))


_MEMOS: list[Callable[[], None]] = []


def curated(function: F | None = None, *, rooted: bool = False, maxsize: int = 8) -> Any:
    """Memoise a loader of curation for the epoch: the function runs once per distinct arguments and epoch.

    ``rooted``: the first argument is the curation directory the function reads (``None``: the one in use), so the
    epoch is that directory's. The value is shared between callers and must not be edited. ``cache_clear`` drops this
    memo alone; :func:`forget_curation` drops them all."""
    def decorate(fn: F) -> F:
        memo = lru_cache(maxsize=maxsize)(lambda epoch, *args, **kwargs: fn(*args, **kwargs))

        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            return memo(curation_epoch(args[0] if rooted and args and args[0] is not None else None), *args, **kwargs)

        wrapper.cache_clear = memo.cache_clear  # type: ignore[attr-defined]
        _MEMOS.append(memo.cache_clear)
        return wrapper  # type: ignore[return-value]

    return decorate(function) if function is not None else decorate


def forget_curation() -> None:
    """Forget the digests and everything held under them: the next read parses the files again."""
    _fingerprint.cache_clear()
    for clear in _MEMOS:
        clear()
