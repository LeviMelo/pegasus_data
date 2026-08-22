"""Content-addressed blob store.

Every fetched byte-string lands at ``blobs/sha256/<aa>/<hash>`` with a catalog
row recording the source path, fetch time, and serving method. Two consequences,
both load-bearing:

* **Change detection without mtime.** Where the protocol gives no timestamp, the
  hash *is* the change signal (D4). A logical path maps to many blob hashes over
  time, and that history is the record of DATASUS silently republishing an old
  competência.
* **Free deduplication.** The same AIH records published as ``.dbc``, ``.dbf``,
  ``.xml`` and ``.csv`` (D3) share nothing byte-wise, but a file re-fetched after
  an interrupted run does — and nothing is fetched twice, ever (P2).
"""

from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
from collections.abc import Iterator
from pathlib import Path

from ..catalog.store import Catalog


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path, *, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


class BlobStore:
    """A sha256-keyed store on the local filesystem."""

    def __init__(self, root: str | Path, catalog: Catalog | None = None) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.catalog = catalog

    # ------------------------------------------------------------------ paths

    def path_for(self, digest: str) -> Path:
        return self.root / "sha256" / digest[:2] / digest

    def has(self, digest: str) -> bool:
        return self.path_for(digest).is_file()

    # ------------------------------------------------------------------ write

    def put_bytes(
        self,
        data: bytes,
        *,
        source_path: str,
        serving_method: str | None = None,
        elapsed_ms: float | None = None,
        remote_size: int | None = None,
        remote_modified: str | None = None,
    ) -> str:
        """Store `data`, return its digest. Idempotent: a re-put writes nothing."""
        digest = sha256_bytes(data)
        target = self.path_for(digest)
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".part")
            try:
                with os.fdopen(fd, "wb") as fh:
                    fh.write(data)
                os.replace(tmp, target)
            except (PermissionError, FileExistsError):
                # Two fetchers raced to store identical bytes. Windows refuses the
                # rename when the destination is open; since the store is content
                # addressed, whoever got there first wrote exactly the same file.
                Path(tmp).unlink(missing_ok=True)
                if not target.is_file():
                    raise
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        if self.catalog is not None:
            self.catalog.record_fetch(
                source_path=source_path,
                sha256=digest,
                byte_size=len(data),
                serving_method=serving_method,
                elapsed_ms=elapsed_ms,
                remote_size=remote_size,
                remote_modified=remote_modified,
            )
        return digest

    def staging_path(self, hint: str) -> Path:
        """A scratch path on the store's own filesystem, for a streamed fetch.

        Deliberately under the blob root: ``os.replace`` is only atomic within
        one filesystem, and a temp file on ``%TEMP%`` while the store sits on a
        data disk turns the final move into a copy — of exactly the large file
        we streamed to disk to avoid copying.
        """
        staging = self.root / "incoming"
        staging.mkdir(parents=True, exist_ok=True)
        safe = hashlib.sha256(hint.encode("utf-8")).hexdigest()[:24]
        return staging / f"{safe}.part"

    def adopt(
        self,
        staged: Path,
        digest: str,
        byte_size: int,
        *,
        source_path: str,
        serving_method: str | None = None,
        elapsed_ms: float | None = None,
        remote_size: int | None = None,
        remote_modified: str | None = None,
    ) -> str:
        """Move an already-hashed staged file into the store under `digest`.

        The counterpart to a streamed download: the bytes were hashed on their
        way to disk, so there is nothing left to do but the rename. `digest` is
        trusted because the caller computed it over the same stream it wrote —
        it is not re-derived from the file, which would read it a second time.
        """
        target = self.path_for(digest)
        if target.is_file():
            staged.unlink(missing_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.replace(staged, target)
            except (PermissionError, FileExistsError):
                # Another worker stored identical bytes first. Content
                # addressing means its file and ours are the same file.
                staged.unlink(missing_ok=True)
                if not target.is_file():
                    raise
        if self.catalog is not None:
            self.catalog.record_fetch(
                source_path=source_path,
                sha256=digest,
                byte_size=byte_size,
                serving_method=serving_method,
                elapsed_ms=elapsed_ms,
                remote_size=remote_size,
                remote_modified=remote_modified,
            )
        return digest

    def put_file(self, src: Path, *, source_path: str, serving_method: str | None = None) -> str:
        digest = sha256_file(src)
        target = self.path_for(digest)
        if not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            # Staged and renamed, like put_bytes. A direct copy that is
            # interrupted leaves a PARTIAL file at a path whose name asserts the
            # complete SHA-256 of the source — the one thing a content-addressed
            # store must never contain, because every later reader trusts the
            # name instead of re-hashing.
            fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".part")
            os.close(fd)
            try:
                shutil.copy2(src, tmp)
                os.replace(tmp, target)
            except (PermissionError, FileExistsError):
                Path(tmp).unlink(missing_ok=True)
                if not target.is_file():
                    raise
            except BaseException:
                Path(tmp).unlink(missing_ok=True)
                raise
        if self.catalog is not None:
            self.catalog.record_fetch(
                source_path=source_path,
                sha256=digest,
                byte_size=target.stat().st_size,
                serving_method=serving_method,
            )
        return digest

    # ------------------------------------------------------------------- read

    def read(self, digest: str) -> bytes:
        return self.path_for(digest).read_bytes()

    def open(self, digest: str) -> Iterator[bytes]:
        with self.path_for(digest).open("rb") as fh:
            while True:
                block = fh.read(1 << 20)
                if not block:
                    return
                yield block

    def materialize(self, digest: str, suffix: str = "", *, work_dir: Path | None = None) -> Path:
        """Give a reader a real file path with a meaningful suffix.

        Several third-party readers (``datasus_dbc``, ``dbfread``, ``duckdb``)
        insist on a filesystem path and some sniff the extension. A hardlink
        keeps this free where the filesystem allows it, and falls back to a copy.
        """
        source = self.path_for(digest)
        base = work_dir or (self.root.parent / "work")
        base.mkdir(parents=True, exist_ok=True)
        target = base / f"{digest[:16]}{suffix}"
        if target.exists():
            return target
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)
        return target

    # -------------------------------------------------------------- accounting

    def size_on_disk(self) -> int:
        total = 0
        for p in (self.root / "sha256").rglob("*"):
            if p.is_file():
                total += p.stat().st_size
        return total

    def known_for(self, source_path: str) -> str | None:
        """The most recent digest fetched for a logical path, if any."""
        if self.catalog is None:
            return None
        digest = self.catalog.latest_blob_for(source_path)
        if digest and self.has(digest):
            return digest
        return None
