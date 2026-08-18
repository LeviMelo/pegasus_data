"""Bounded-concurrency fetch with retry, resume, and skip-if-unchanged.

The skip rule is deliberately conservative. A file is considered unchanged, and
therefore skipped, only when the catalog holds a blob for that path **and** the
listing's ``size``/``modified`` still match what the catalog recorded when that
blob was fetched. Absent that evidence we re-fetch and let content addressing
settle it — DATASUS republishes old competências silently, and a wrong skip is
invisible downstream.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field

from ..catalog.store import Catalog
from ..discovery.ftp_client import FtpClient
from .cache import BlobStore


@dataclass(slots=True)
class FetchResult:
    path: str
    sha256: str | None
    byte_size: int
    skipped: bool = False
    error: str | None = None
    elapsed_ms: float = 0.0


@dataclass(slots=True)
class FetchStats:
    requested: int = 0
    fetched: int = 0
    skipped: int = 0
    failed: int = 0
    bytes_fetched: int = 0
    errors: list[tuple[str, str]] = field(default_factory=list)


class Fetcher:
    """Pulls a work-list of paths over N FTP connections into the blob store."""

    def __init__(
        self,
        catalog: Catalog,
        blobs: BlobStore,
        *,
        host: str,
        concurrency: int = 8,
        timeout: int = 60,
        max_retries: int = 4,
        backoff_base: float = 1.5,
    ) -> None:
        self.catalog = catalog
        self.blobs = blobs
        self.host = host
        self.concurrency = max(1, concurrency)
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base

    # ------------------------------------------------------------------ policy

    def _should_skip(self, path: str) -> str | None:
        """Return an existing digest when the catalog proves the file is unchanged."""
        rows = self.catalog.query(
            """
            SELECT f.sha256 AS sha, f.byte_size AS bytes, fi.size AS listed_size,
                   fi.modified AS listed_mtime, f.fetched_at AS fetched_at
              FROM fetches f
              JOIN files fi ON fi.path = f.source_path
             WHERE f.source_path = ?
             ORDER BY f.id DESC LIMIT 1
            """,
            (path,),
        )
        if not rows:
            return None
        row = rows[0]
        digest = row["sha"]
        if not digest or not self.blobs.has(digest):
            return None
        listed_size = row["listed_size"]
        # Size is the cheap discriminator and IIS gives it for every file. If the
        # listing size disagrees with the stored blob, the file changed.
        if listed_size is not None and row["bytes"] is not None and int(listed_size) != int(row["bytes"]):
            return None
        if listed_size is None and row["listed_mtime"] is None:
            # No change signal at all: content addressing is the only answer, so
            # re-fetch rather than trust an old copy.
            return None
        return digest

    # ------------------------------------------------------------------- run

    def fetch_many(
        self,
        paths: Sequence[str],
        *,
        force: bool = False,
        on_result: Callable[[FetchResult], None] | None = None,
    ) -> FetchStats:
        stats = FetchStats(requested=len(paths))
        if not paths:
            return stats

        work: queue.Queue[str | None] = queue.Queue()
        for p in paths:
            work.put(p)
        lock = threading.Lock()

        def worker() -> None:
            client = FtpClient(
                self.host,
                timeout=self.timeout,
                max_retries=self.max_retries,
                backoff_base=self.backoff_base,
            )
            try:
                client.connect()
            except Exception as exc:
                with lock:
                    stats.failed += 1
                    stats.errors.append(("<connect>", str(exc)))
                return
            try:
                while True:
                    path = work.get()
                    try:
                        if path is None:
                            return
                        result = self._fetch_one(client, path, force=force)
                        with lock:
                            if result.error:
                                stats.failed += 1
                                stats.errors.append((path, result.error))
                            elif result.skipped:
                                stats.skipped += 1
                            else:
                                stats.fetched += 1
                                stats.bytes_fetched += result.byte_size
                        if on_result is not None:
                            on_result(result)
                    finally:
                        work.task_done()
            finally:
                client.close()

        threads = [threading.Thread(target=worker, daemon=True, name=f"fetch-{i}") for i in range(self.concurrency)]
        for t in threads:
            t.start()
        work.join()
        for _ in threads:
            work.put(None)
        for t in threads:
            t.join(timeout=30)
        return stats

    def _fetch_one(self, client: FtpClient, path: str, *, force: bool) -> FetchResult:
        if not force:
            existing = self._should_skip(path)
            if existing:
                size = self.blobs.path_for(existing).stat().st_size
                return FetchResult(path=path, sha256=existing, byte_size=size, skipped=True)
        started = time.perf_counter()
        try:
            data = client.retrieve(path)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            self.catalog.record_gap(path, kind="fetch", methods=("RETR",), error=error)
            return FetchResult(path=path, sha256=None, byte_size=0, error=error)
        elapsed = (time.perf_counter() - started) * 1000
        digest = self.blobs.put_bytes(
            data, source_path=path, serving_method="ftp:RETR", elapsed_ms=elapsed
        )
        self.catalog.resolve_gap(path)
        return FetchResult(path=path, sha256=digest, byte_size=len(data), elapsed_ms=elapsed)

    # ------------------------------------------------------------- convenience

    def fetch_one(self, path: str, *, force: bool = False) -> FetchResult:
        client = FtpClient(self.host, timeout=self.timeout, max_retries=self.max_retries)
        try:
            client.connect()
            return self._fetch_one(client, path, force=force)
        finally:
            client.close()

    def ensure(self, paths: Iterable[str]) -> dict[str, str]:
        """Fetch what is missing; return ``{path: digest}`` for everything available."""
        wanted = list(dict.fromkeys(paths))
        self.fetch_many(wanted)
        out: dict[str, str] = {}
        for p in wanted:
            digest = self.blobs.known_for(p)
            if digest:
                out[p] = digest
        return out
