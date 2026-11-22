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
import tempfile
import time
import uuid
from collections.abc import Iterable
from pathlib import Path

from ..catalog.store import CatalogStore


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

    def __init__(self, root: str | Path, catalog: CatalogStore | None = None) -> None:
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

        UNIQUE per acquisition, not derived from the source path. A name that is
        a function of the source meant two Pegasus processes fetching the same
        file shared one partial: each would resume from the other's offset,
        append into the other's stream, and one would finalise bytes the other
        had half-written. Worker locking cannot help — the other process is not
        in this interpreter. The cost is that resume no longer spans separate
        runs; within a run, where ``retrieve_to_file`` retries, it still does,
        and that is where nearly all of the value was.
        """
        staging = self.root / "incoming"
        staging.mkdir(parents=True, exist_ok=True)
        safe = hashlib.sha256(hint.encode("utf-8")).hexdigest()[:16]
        unique = uuid.uuid4().hex[:12]
        return staging / f"{safe}-{unique}.part"

    def sweep_staging(self, older_than_seconds: float = 86_400) -> int:
        """Remove abandoned partials. Returns how many were dropped.

        Unique staging names mean a killed process leaves its partial behind
        with nothing to reclaim it — the deterministic name at least got reused.
        This is the reclamation, and it is time-based because a `.part` being
        written right now by another process must not be touched.
        """
        staging = self.root / "incoming"
        if not staging.is_dir():
            return 0
        cutoff = time.time() - older_than_seconds
        removed = 0
        for partial in staging.glob("*.part"):
            try:
                if partial.stat().st_mtime < cutoff:
                    partial.unlink()
                    removed += 1
            except OSError:  # pragma: no cover - raced with its owner
                continue
        return removed

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
        # Size is checked at the boundary. The digest is trusted because the
        # caller computed it over the same stream it wrote — re-hashing would
        # read the whole file a second time — but a staged file whose length
        # disagrees with what the caller says it wrote never becomes a blob
        # named for a complete SHA-256.
        actual = staged.stat().st_size if staged.exists() else -1
        if actual != byte_size:
            staged.unlink(missing_ok=True)
            raise OSError(
                f"staged {staged.name} is {actual} bytes, caller reported {byte_size}; "
                "refusing to adopt it under a digest it may not match"
            )
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

    # ------------------------------------------------------------------- read

    def read(self, digest: str) -> bytes:
        return self.path_for(digest).read_bytes()

    # -------------------------------------------------------------- accounting

    def size_on_disk(self) -> int:
        total = 0
        for p in (self.root / "sha256").rglob("*"):
            if p.is_file():
                total += p.stat().st_size
        return total

    def prune_verified(self, lake_dir: Path, *, paths: Iterable[str] | None = None, held: Iterable[str] = (),
                       dry_run: bool = False) -> dict[str, int]:
        """Delete the blobs whose records the lake holds: for every path the blob was fetched for, a verified partition
        holds that path at the blob's version, or a delta keeps that version (`persist.versions`, ADR-0234), or the
        caller holds the path (``held``: an extract that kept a file's matching records). ``paths`` limits it to the
        blobs fetched for those source paths: a build, a snapshot or an extract releasing its own files.

        A partition is verified when its Parquet file exists and holds the row count the catalog recorded when it was
        written. The test is by version, not by path: a download of a version the server has since replaced is the
        only copy of it until a delta keeps it, and a partition built from the new version does not hold it (it was
        pruned by path until 2026-11-22). The original DBC bytes cannot be regenerated from the lake: a refetch
        reproduces the current version only. Kits, registries, archives with several members and files only a query
        has read belong to no partition and are kept.
        """
        import json

        import pyarrow.parquet as pq

        from ..persist.versions import file_digests

        if self.catalog is None:
            raise RuntimeError("pruning needs the catalog that records what the lake was built from")
        want = None if paths is None else {str(p) for p in paths}
        holders = {str(p) for p in held}
        covered: set[tuple[str, str]] = set()
        by_path: set[str] = set()
        uncovered: set[tuple[str, str]] = set()
        for row in self.catalog.query(
                "SELECT relative_path, source_paths, source_digests, row_count FROM lake_partitions"):
            sources = set(json.loads(row["source_paths"] or "[]"))
            if want is not None and not sources & want:
                continue
            path = Path(lake_dir) / str(row["relative_path"])
            try:
                verified = path.is_file() and pq.ParquetFile(path).metadata.num_rows == int(row["row_count"] or -1)
                digests = json.loads(row["source_digests"]) if row["source_digests"] else file_digests(path)
            except Exception:  # noqa: BLE001 - an unreadable partition verifies nothing
                verified, digests = False, {}
            pairs = {(s, str(digests[s])) for s in sources if s in digests}
            (covered if verified else uncovered).update(pairs)
            if verified and sources and not digests:
                # a file that records no digest (an intake unit, ADR-0162) holds its sources by path, as before
                by_path.update(sources)
        covered -= uncovered
        for row in self.catalog.query("SELECT source_id, sha256, removed_path, kept_path FROM lake_versions"):
            removed_held = not row["removed_path"] or (Path(lake_dir) / str(row["removed_path"])).is_file()
            if removed_held and (Path(lake_dir) / str(row["kept_path"])).is_file():
                covered.add((str(row["source_id"]), str(row["sha256"])))
        by_blob: dict[str, set[str]] = {}
        if want is None:
            fetched = self.catalog.query("SELECT DISTINCT sha256, source_path FROM fetches")
        else:
            # every path each wanted blob was fetched for: a blob also fetched for a path outside ``paths`` stays
            # unless that path is covered too
            marks = ",".join("?" for _ in want) or "NULL"
            fetched = self.catalog.query(
                f"""SELECT DISTINCT sha256, source_path FROM fetches WHERE sha256 IN
                    (SELECT sha256 FROM fetches WHERE source_path IN ({marks}))""", sorted(want))
        for row in fetched:
            by_blob.setdefault(str(row["sha256"]), set()).add(str(row["source_path"]))
        out = {"blobs": 0, "bytes": 0, "kept": 0}
        for digest, sources in by_blob.items():
            path = self.path_for(digest)
            if not path.is_file():
                continue
            if all(source in holders or source in by_path or (source, digest) in covered for source in sources):
                size = path.stat().st_size
                if not dry_run:
                    try:
                        path.unlink()
                    except PermissionError:      # a reader holds it open (Windows): left, counted, gone next time
                        out["locked"] = out.get("locked", 0) + 1
                        continue
                out["blobs"] += 1
                out["bytes"] += size
            else:
                out["kept"] += 1
        return out

    def known_for(self, source_path: str) -> str | None:
        """The most recent digest fetched for a logical path, if any."""
        if self.catalog is None:
            return None
        digest = self.catalog.latest_blob_for(source_path)
        if digest and self.has(digest):
            return digest
        return None
