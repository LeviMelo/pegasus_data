"""Concurrent, resumable FTP crawl with first-class coverage gaps (D6).

Shape: a bounded worker pool, one control connection per worker, a shared queue
of directories deduplicated by normalised path. Failed listings go to a retry
queue with bounded exponential backoff; what survives exhaustion is persisted as
a ``coverage_gaps`` row so that coverage is queryable rather than buried in a log.

Resumability is a property of the catalog, not of a checkpoint file: on
``--resume`` the crawl skips directories already listed in this run window and
re-queues every unresolved gap.
"""

from __future__ import annotations

import queue
import threading
import time
import uuid
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import PurePosixPath

from ..catalog.store import Catalog, utcnow
from .ftp_client import FtpClient, ListingUnavailable
from .listing import ListingEntry, normalize_path
from .reconcile import (
    FileState,
    Reconciliation,
    classify,
    detect_moves,
    mark_gone,
    persist_reconciliation,
    snapshot,
)


@dataclass(slots=True)
class CrawlStats:
    run_id: str
    directories: int = 0
    files: int = 0
    gaps: int = 0
    retries: int = 0
    started_at: str = ""
    finished_at: str = ""
    method_counts: dict[str, int] = field(default_factory=dict)
    reconciliation: Reconciliation = field(default_factory=Reconciliation)

    def as_dict(self) -> dict[str, object]:
        return {
            "run_id": self.run_id,
            "directories": self.directories,
            "files": self.files,
            "gaps": self.gaps,
            "retries": self.retries,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "method_counts": dict(self.method_counts),
            "reconciliation": self.reconciliation.as_dict(),
        }


@dataclass(slots=True)
class _Work:
    path: str
    attempt: int = 0
    not_before: float = 0.0


class Crawler:
    """Walks the tree breadth-first across N connections."""

    def __init__(
        self,
        catalog: Catalog,
        *,
        host: str,
        connections: int = 8,
        timeout: int = 60,
        max_retries: int = 4,
        backoff_base: float = 1.5,
        on_progress: Callable[[CrawlStats], None] | None = None,
    ) -> None:
        self.catalog = catalog
        self.host = host
        self.connections = max(1, connections)
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.on_progress = on_progress
        self._lock = threading.Lock()
        self._seen: set[str] = set()
        self._queue: queue.PriorityQueue[tuple[float, int, _Work | None]] = queue.PriorityQueue()
        self._counter = 0
        self._inflight = 0
        self._done = threading.Event()
        self._before: dict[str, FileState] = {}
        self._gone: list[str] = []

    # ------------------------------------------------------------------ queue

    def _submit(self, work: _Work) -> None:
        with self._lock:
            self._counter += 1
            self._inflight += 1
            self._queue.put((work.not_before, self._counter, work))

    def _complete(self) -> None:
        with self._lock:
            self._inflight -= 1
            if self._inflight <= 0 and self._queue.empty():
                self._done.set()

    # ------------------------------------------------------------------- run

    def crawl(
        self,
        base_path: str,
        *,
        resume: bool = False,
        only_prefixes: Sequence[str] | None = None,
    ) -> CrawlStats:
        base_path = normalize_path(base_path)
        stats = CrawlStats(run_id=uuid.uuid4().hex[:12], started_at=utcnow())
        # What the catalog knew before this crawl, so the difference can be
        # reported rather than silently absorbed.
        self._before = snapshot(self.catalog, only_prefixes)

        roots: list[str] = []
        if only_prefixes:
            roots = [normalize_path(p) for p in only_prefixes]
        else:
            roots = [base_path]

        if resume:
            listed = {
                r["path"]
                for r in self.catalog.query("SELECT path FROM directories WHERE last_listed_at IS NOT NULL")
            }
            self._seen |= listed
            for gap in self.catalog.open_gaps("listing"):
                self._seen.discard(gap["path"])
                roots.append(gap["path"])

        for root in dict.fromkeys(roots):
            if root in self._seen and resume:
                continue
            self._seen.add(root)
            self._submit(_Work(root))

        threads = [
            threading.Thread(target=self._worker, args=(stats,), daemon=True, name=f"crawl-{i}")
            for i in range(self.connections)
        ]
        for t in threads:
            t.start()

        # Wait for drain, with a watchdog so a wedged worker cannot hang forever.
        while not self._done.wait(timeout=5.0):
            if self.on_progress:
                self.on_progress(stats)
        for _ in threads:
            self._queue.put((0.0, 0, None))
        for t in threads:
            t.join(timeout=30)

        # A file that vanished from one directory and appeared in another during
        # this crawl was moved, not deleted and re-created.
        moves = detect_moves(self.catalog, self._gone, stats.run_id)
        moved_from = {m[0] for m in moves}
        stats.reconciliation.moves = moves
        stats.reconciliation.moved = len(moves)
        stats.reconciliation.gone = sum(1 for p in self._gone if p not in moved_from)
        stats.reconciliation.gone_paths = [p for p in self._gone if p not in moved_from]

        stats.finished_at = utcnow()
        stats.gaps = self.catalog.count("coverage_gaps", "resolved=0 AND kind='listing'")
        with self.catalog.write() as conn:
            conn.execute(
                """
                INSERT INTO crawl_runs (run_id, host, base_path, started_at, finished_at,
                                        directories, files, gaps, connections, notes)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    stats.run_id, self.host, base_path, stats.started_at, stats.finished_at,
                    stats.directories, stats.files, stats.gaps, self.connections,
                    f"methods={stats.method_counts}",
                ),
            )
        persist_reconciliation(self.catalog, stats.run_id, stats.reconciliation)
        return stats

    # ---------------------------------------------------------------- worker

    def _worker(self, stats: CrawlStats) -> None:
        client = FtpClient(
            self.host,
            timeout=self.timeout,
            max_retries=self.max_retries,
            backoff_base=self.backoff_base,
        )
        try:
            client.connect()
        except Exception as exc:
            self.catalog.log_event("crawl", "worker could not connect", level="error", detail=str(exc))
            return
        try:
            while True:
                _, _, work = self._queue.get()
                if work is None:
                    return
                try:
                    delay = work.not_before - time.time()
                    if delay > 0:
                        time.sleep(min(delay, 30.0))
                    self._handle(client, work, stats)
                finally:
                    self._queue.task_done()
        finally:
            client.close()

    def _handle(self, client: FtpClient, work: _Work, stats: CrawlStats) -> None:
        try:
            entries, method = client.list_directory(work.path)
        except ListingUnavailable as exc:
            self._retry_or_gap(work, stats, methods=tuple(exc.attempts), error=str(exc))
            self._complete()
            return
        except Exception as exc:
            self._retry_or_gap(work, stats, methods=("unknown",), error=f"{type(exc).__name__}: {exc}")
            self._complete()
            return

        files: list[dict[str, object]] = []
        subdirs: list[str] = []
        untyped: list[ListingEntry] = []
        for e in entries:
            if e.is_dir is True:
                subdirs.append(e.path)
            elif e.is_dir is False:
                files.append(
                    {
                        "path": e.path,
                        "directory": work.path,
                        "filename": e.name,
                        "extension": _extension(e.name),
                        "size": e.size,
                        "modified": e.modified,
                        "listing_method": e.method or method,
                        "change_signal": e.change_signal,
                    }
                )
            else:
                untyped.append(e)

        # An entry we could not type is a coverage gap of its own kind: record it
        # rather than guessing, and try a per-file SIZE probe to settle it.
        for e in untyped:
            size = client.size(e.path)
            if size is not None:
                files.append(
                    {
                        "path": e.path,
                        "directory": work.path,
                        "filename": e.name,
                        "extension": _extension(e.name),
                        "size": size,
                        "modified": client.modified_time(e.path),
                        "listing_method": f"{method}+SIZE",
                        "change_signal": "size",
                    }
                )
            else:
                subdirs.append(e.path)

        # Classify against what we knew, before the upsert overwrites it.
        verdicts = Counter(
            classify(
                self._before.get(str(f["path"])),
                f.get("size"),  # type: ignore[arg-type]
                f.get("modified"),  # type: ignore[arg-type]
            )
            for f in files
        )
        with self._lock:
            report = stats.reconciliation
            report.new += verdicts["new"]
            report.unchanged += verdicts["unchanged"]
            report.changed += verdicts["changed"]
            report.unresolved += verdicts["unresolved"]
            if verdicts["changed"]:
                report.changed_paths.extend(
                    str(f["path"])
                    for f in files
                    if classify(
                        self._before.get(str(f["path"])),
                        f.get("size"),  # type: ignore[arg-type]
                        f.get("modified"),  # type: ignore[arg-type]
                    )
                    == "changed"
                )

        if files:
            self.catalog.upsert_files(files)

        # This directory listed successfully, so absence from it is evidence.
        # Nothing else in the crawl may mark a file gone: a failed listing says
        # nothing about its contents, and treating silence as deletion would turn
        # one dropped connection into a mass withdrawal.
        vanished = mark_gone(self.catalog, work.path, {str(f["path"]) for f in files})
        if vanished:
            with self._lock:
                self._gone.extend(vanished)
        self.catalog.upsert_directories(
            [
                {
                    "path": work.path,
                    "parent": str(PurePosixPath(work.path).parent),
                    "listing_method": method,
                    "entry_count": len(entries),
                    "file_count": len(files),
                    "dir_count": len(subdirs),
                }
            ]
        )
        self.catalog.resolve_gap(work.path)

        with self._lock:
            stats.directories += 1
            stats.files += len(files)
            stats.method_counts[method] = stats.method_counts.get(method, 0) + 1

        for child in subdirs:
            with self._lock:
                if child in self._seen:
                    continue
                self._seen.add(child)
            self._submit(_Work(child))
        self._complete()

    def _retry_or_gap(
        self, work: _Work, stats: CrawlStats, *, methods: tuple[str, ...], error: str
    ) -> None:
        if work.attempt + 1 < self.max_retries:
            with self._lock:
                stats.retries += 1
            delay = min(60.0, self.backoff_base ** (work.attempt + 1))
            self._submit(_Work(work.path, work.attempt + 1, time.time() + delay))
            return
        self.catalog.record_gap(work.path, kind="listing", methods=methods, error=error)


def _extension(filename: str) -> str | None:
    """Lower-cased suffix, keeping the composite forms DATASUS actually uses."""
    lower = filename.lower()
    for composite in (".csv.gz", ".json.gz", ".xml.gz", ".dbf.gz", ".dbc.gz", ".duck.zip", ".tar.gz"):
        if lower.endswith(composite):
            return composite
    suffix = PurePosixPath(lower).suffix
    return suffix or None
