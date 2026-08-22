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
from ..progress import (
    DEFAULT_HEARTBEAT,
    DEFAULT_STALL_TIMEOUT,
    Heartbeat,
    StageProgress,
)
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
    #: Bytes actually pulled over the network, and bytes served from the local
    #: content-addressed store. Reporting one number for both let a fully warm
    #: request claim megabytes "downloaded" with the network untouched.
    bytes_from_cache: int = 0
    #: Workers that could not establish a connection at all. Distinct from
    #: `failed`, which counts PATHS.
    workers_lost: int = 0
    #: Paths still outstanding when the batch was abandoned on a stall. Not
    #: failures — nothing was decided about them — and counted apart so a
    #: caller can retry exactly those.
    stalled: int = 0
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
        stall_timeout: float = DEFAULT_STALL_TIMEOUT,
        heartbeat_interval: float = DEFAULT_HEARTBEAT,
    ) -> None:
        self.catalog = catalog
        self.blobs = blobs
        self.host = host
        self.concurrency = max(1, concurrency)
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        #: How long the batch may go with no path completing before it gives up.
        #: Per-*path* time is already bounded by the socket timeout and retries;
        #: this bounds the case those cannot see — every worker alive, nothing
        #: finishing.
        self.stall_timeout = stall_timeout
        self.heartbeat_interval = heartbeat_interval
        #: What the last :meth:`ensure` actually did. Kept so callers can report
        #: cache hits, failures and stale fallbacks instead of inferring them.
        self.last_stats: FetchStats | None = None
        self.last_stale: list[str] = []

    # ------------------------------------------------------------------ policy

    def _should_skip(self, path: str) -> str | None:
        """Return an existing digest when the catalog proves the file is unchanged."""
        rows = self.catalog.query(
            """
            SELECT f.sha256 AS sha, f.byte_size AS bytes, fi.size AS listed_size,
                   fi.modified AS listed_mtime, f.fetched_at AS fetched_at,
                   f.remote_size AS then_size, f.remote_modified AS then_mtime
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
        listed_mtime = row["listed_mtime"]

        # THEN versus NOW, which is what the policy always claimed to do. It
        # used to compare the current listing's size against the stored blob's
        # byte count — a different question — and merely check that a modified
        # time existed. A republication whose byte count happens to match was
        # therefore skipped despite changed contents.
        then_size, then_mtime = row["then_size"], row["then_mtime"]
        if then_size is not None or then_mtime is not None:
            if (
                then_size is not None
                and listed_size is not None
                and int(then_size) != int(listed_size)
            ):
                return None
            if (
                then_mtime is not None
                and listed_mtime is not None
                and str(then_mtime) != str(listed_mtime)
            ):
                return None
            if then_mtime is None and listed_mtime is not None:
                # The server started reporting a time we cannot compare against.
                return None
            return digest

        # Fetched before this catalog recorded the listing it trusted. Fall back
        # to the old, weaker comparison rather than re-downloading everything.
        if listed_size is not None and row["bytes"] is not None and int(listed_size) != int(row["bytes"]):
            return None
        if listed_size is None and listed_mtime is None:
            # No change signal at all: content addressing is the only answer, so
            # re-fetch rather than trust an old copy.
            return None
        return digest

    def _listing(self, path: str) -> tuple[int | None, str | None]:
        """What the catalog's listing currently says about this path."""
        rows = self.catalog.query(
            "SELECT size, modified FROM files WHERE path = ?", (path,)
        )
        if not rows:
            return None, None
        return rows[0]["size"], rows[0]["modified"]

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

        lock = threading.Lock()

        def _emit(result: FetchResult) -> None:
            """Hand a result to the caller without letting it kill the worker.

            `on_result` used to be called bare inside the worker. A callback that
            raised took the thread with it, the exception never reached the
            caller, and the batch either limped on with fewer workers or reached
            a stall that named nothing.
            """
            if on_result is None:
                return
            try:
                on_result(result)
            except Exception as exc:  # noqa: BLE001 - a caller's bug, not ours
                with lock:
                    stats.errors.append((result.path, f"on_result raised: {exc}"))

        # ------------------------------------------------------------------
        # Settle the cache BEFORE opening a socket.
        #
        # Every worker used to construct an FtpClient and connect() before it
        # took anything off the queue, so a request whose bytes were already on
        # the SSD still opened up to eight FTP sessions that did no work — and
        # failed outright when DATASUS was unreachable. `_should_skip` reads the
        # catalog, not the network, so it can answer first.
        # ------------------------------------------------------------------
        pending: list[str] = []
        for path in paths:
            digest = None if force else self._should_skip(path)
            if digest:
                size = self.blobs.path_for(digest).stat().st_size
                stats.skipped += 1
                stats.bytes_from_cache += size
                _emit(FetchResult(path=path, sha256=digest, byte_size=size, skipped=True))
            else:
                pending.append(path)
        if not pending:
            return stats

        work: queue.Queue[str | None] = queue.Queue()
        for p in pending:
            work.put(p)
        #: Set when the batch is abandoned, so a worker stops taking new paths
        #: instead of continuing to write blobs and catalog rows after
        #: `fetch_many` has returned and the caller has moved on.
        cancelled = threading.Event()
        _last_seen = [0]
        _last_moved = [time.monotonic()]

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
                # Record and LEAVE. This used to drain the shared queue and mark
                # every path it saw as failed, on the reasoning that `work.join()`
                # would otherwise hang — but the scheduler below polls and never
                # joins the queue. So one worker losing its connection could empty
                # the queue and fail a batch that seven healthy workers were
                # about to complete.
                with lock:
                    stats.workers_lost += 1
                    stats.errors.append(("<connect>", str(exc)))
                return
            try:
                while not cancelled.is_set():
                    try:
                        path = work.get(timeout=0.25)
                    except queue.Empty:
                        continue
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
                                stats.bytes_from_cache += result.byte_size
                            else:
                                stats.fetched += 1
                                stats.bytes_fetched += result.byte_size
                        _emit(result)
                    finally:
                        work.task_done()
            finally:
                client.close()

        threads = [
            threading.Thread(target=worker, daemon=True, name=f"fetch-{i}")
            for i in range(self.concurrency)
        ]
        for t in threads:
            t.start()

        # NOT `work.join()`. An unbounded join is what turned one stalled FTP
        # transfer into a fifty-minute silence with no output and no error: the
        # queue never reported finished, so the call never returned and nothing
        # said why. Poll instead, so the wait is bounded, a heartbeat can report
        # what is outstanding, and a stall ends the batch with the remaining
        # paths recorded rather than ending the run.
        progress = StageProgress(stage="fetch", total=len(pending))
        deadline_hit = False
        with Heartbeat(progress, interval=self.heartbeat_interval):
            while True:
                with lock:
                    completed = stats.fetched + stats.skipped
                    progress.completed = completed
                    progress.failed = stats.failed
                    lost = stats.workers_lost
                done = progress.completed + progress.failed
                if done >= len(pending):
                    break
                if lost >= len(threads) or all(not t.is_alive() for t in threads):
                    # Nothing is left to do the work. Waiting for the stall
                    # timeout would only delay saying so.
                    break
                if done > _last_seen[0]:
                    _last_seen[0] = done
                    _last_moved[0] = time.monotonic()
                elif time.monotonic() - _last_moved[0] > self.stall_timeout:
                    deadline_hit = True
                    break
                time.sleep(0.25)

        if deadline_hit:
            cancelled.set()
            outstanding = len(pending) - (stats.fetched + stats.skipped + stats.failed)
            stats.stalled = outstanding
            message = (
                f"fetch stalled: no path completed in {self.stall_timeout:.0f}s; "
                f"{outstanding} of {len(pending)} still outstanding"
            )
            stats.errors.append(("<stall>", message))
            self.catalog.log_event("fetch", "batch abandoned on stall", level="error", detail=message)

        cancelled.set()
        for _ in threads:
            work.put(None)
        for t in threads:
            t.join(timeout=5)
        if any(t.is_alive() for t in threads):
            # Say so rather than let a late blob write surprise the caller.
            stats.errors.append(
                ("<workers>", "some fetch workers did not stop within 5s of being cancelled")
            )
        return stats

    def _fetch_one(self, client: FtpClient, path: str, *, force: bool) -> FetchResult:
        if not force:
            existing = self._should_skip(path)
            if existing:
                size = self.blobs.path_for(existing).stat().st_size
                return FetchResult(path=path, sha256=existing, byte_size=size, skipped=True)
        # Read the listing FIRST: it is a local catalog row, and knowing the
        # expected size lets the transfer below reject a short or spliced file.
        remote_size, remote_modified = self._listing(path)
        started = time.perf_counter()
        staged = self.blobs.staging_path(path)
        try:
            byte_size, digest = client.retrieve_to_file(
                path, staged, expected_size=remote_size
            )
        except Exception as exc:
            # The partial stays only if a retry could still use it; a failure
            # that got here has already exhausted the retries.
            staged.unlink(missing_ok=True)
            error = f"{type(exc).__name__}: {exc}"
            self.catalog.record_gap(path, kind="fetch", methods=("RETR",), error=error)
            return FetchResult(path=path, sha256=None, byte_size=0, error=error)
        elapsed = (time.perf_counter() - started) * 1000
        digest = self.blobs.adopt(
            staged,
            digest,
            byte_size,
            source_path=path,
            serving_method="ftp:RETR",
            elapsed_ms=elapsed,
            remote_size=remote_size,
            remote_modified=remote_modified,
        )
        self.catalog.resolve_gap(path)
        return FetchResult(path=path, sha256=digest, byte_size=byte_size, elapsed_ms=elapsed)

    # ------------------------------------------------------------- convenience

    def fetch_one(self, path: str, *, force: bool = False) -> FetchResult:
        client = FtpClient(self.host, timeout=self.timeout, max_retries=self.max_retries)
        try:
            client.connect()
            return self._fetch_one(client, path, force=force)
        finally:
            client.close()

    def ensure(
        self, paths: Iterable[str], *, allow_stale: bool = False
    ) -> dict[str, str]:
        """Fetch what is missing; return ``{path: digest}`` for what this run resolved.

        Driven by **this run's** decisions. It used to discard ``fetch_many``'s
        results and then ask ``blobs.known_for(p)`` for every path — a purely
        historical lookup that re-checks nothing. So a path whose freshness
        check said "stale, re-fetch", whose refresh then failed, still resolved
        to yesterday's blob and was decoded as though acquisition had succeeded.
        The code was most willing to use stale data exactly when its own logic
        said not to trust it.

        A digest is returned only when this run either verified a cache hit or
        completed a download. ``allow_stale=True`` restores the old behaviour
        for a caller who would rather have old data than none — and the paths it
        falls back on are recorded in :attr:`last_stale` so the decision can be
        reported rather than hidden.
        """
        wanted = list(dict.fromkeys(paths))
        resolved: dict[str, str] = {}
        failed: list[str] = []

        def _record(result: FetchResult) -> None:
            if result.sha256:
                resolved[result.path] = result.sha256
            else:
                failed.append(result.path)

        stats = self.fetch_many(wanted, on_result=_record)
        self.last_stats = stats
        self.last_stale = []

        if allow_stale:
            for path in wanted:
                if path in resolved:
                    continue
                digest = self.blobs.known_for(path)
                if digest:
                    resolved[path] = digest
                    self.last_stale.append(path)
        return resolved
