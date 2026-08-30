"""Killable decoders: a small pool of worker processes the parent can end.

The timeout this package advertises was never cancellation. ``run_with_timeout``
starts a daemon thread, joins it with a deadline, and on expiry stops waiting —
which is all Python can do, because a thread cannot be killed and DBC inflation
runs inside a native extension that never yields. So a file recorded as
"abandoned after 1200s" went on holding a core, an inflated DBF and temporary
disk, invisibly, while the API moved on. Several of those accumulate.

A process can be killed. This is the parent side: it hands one physical source
to a worker, waits with a deadline, and if the deadline passes it terminates the
process and starts a fresh one. "Abandoned" then means the work stopped.

The unit of work is one PHYSICAL SOURCE, not one logical member, so an archive
holding seven selected members is still opened, decompressed and parsed once —
the optimisation that made archive handling affordable is preserved rather than
traded away for killability.

Measured cost of the boundary on a real 208-column CNES-ST payload: Arrow IPC
serialise plus deserialise came to 1% of decode time. Workers are persistent, so
interpreter startup is paid once rather than per file.
"""

from __future__ import annotations

import json
import queue
import struct
import subprocess
import sys
import tempfile
import threading
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ._worker import read_frame, write_frame
from .base import logical_source_id

if TYPE_CHECKING:  # pragma: no cover - typing only
    import pyarrow as pa

__all__ = ["DecoderPool", "IsolatedDecodeError", "decoder_pool"]


class IsolatedDecodeError(RuntimeError):
    """The worker could not decode this source, and said why."""


@dataclass
class _RemoteTable:
    """A decoded table whose rows live on the other side of a pipe.

    Shaped like :class:`~pegasus_data.decode.base.DecodedTable` because the
    normalisation layer takes one and should not know or care which side of a
    process boundary the bytes were parsed on.
    """

    path: str
    member: str
    reader: str
    fields: list[Any]
    row_count: int | None
    warnings: list[str] = field(default_factory=list)
    retains: object | None = None
    _spool_path: Path | None = None

    @property
    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]

    @property
    def source_id(self) -> str:
        return logical_source_id(self.path, self.member)

    def batches(self) -> Iterator[pa.RecordBatch]:
        if self._spool_path is None:
            return
        import pyarrow as pa

        with self._spool_path.open("rb") as source:
            while header := source.read(8):
                if len(header) != 8:
                    raise IsolatedDecodeError(
                        f"{self.source_id}: truncated local decoder spool"
                    )
                (size,) = struct.unpack(">Q", header)
                frame = source.read(size)
                if len(frame) != size:
                    raise IsolatedDecodeError(
                        f"{self.source_id}: truncated local decoder spool frame"
                    )
                with pa.ipc.open_stream(pa.BufferReader(frame)) as stream:
                    yield from stream

    def to_table(self, *, row_limit: int | None = None) -> pa.Table:
        """Materialise, matching :meth:`DecodedTable.to_table` exactly.

        The docstring above promises this class is shaped like DecodedTable so
        callers need not care which side of the process boundary parsed the
        bytes -- and the population build took that promise at its word,
        called ``to_table()``, and died on the isolated path only. Same
        semantics as the original, including the empty-source shape: all
        declared fields as empty string columns.
        """
        import pyarrow as pa

        collected: list[pa.RecordBatch] = []
        seen = 0
        for batch in self.batches():
            if row_limit is not None and seen + batch.num_rows > row_limit:
                batch = batch.slice(0, row_limit - seen)
            collected.append(batch)
            seen += batch.num_rows
            if row_limit is not None and seen >= row_limit:
                break
        if not collected:
            return pa.table({f.name: pa.array([], type=pa.string()) for f in self.fields})
        return pa.Table.from_batches(collected)


@dataclass
class _RemoteOutcome:
    path: str
    container: str = ""
    tables: list[_RemoteTable] = field(default_factory=list)
    attempts: list[Any] = field(default_factory=list)
    members: list[Any] = field(default_factory=list)
    open_questions: list[tuple[str, str]] = field(default_factory=list)
    retains: object | None = None


class _Worker:
    """One decoder process, and the lock that keeps one job in it at a time."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.proc: subprocess.Popen[bytes] | None = None

    def start(self) -> subprocess.Popen[bytes]:
        if self.proc is None or self.proc.poll() is not None:
            self.proc = subprocess.Popen(
                [sys.executable, "-m", "pegasus_data.decode._worker"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=0,
            )
        return self.proc

    def kill(self) -> None:
        """End the process. The whole point: this actually stops the work."""
        proc, self.proc = self.proc, None
        if proc is None:
            return
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:  # noqa: BLE001 - it is going away regardless
            pass


class DecoderPool:
    """A bounded set of reusable decoder processes.

    Bounded low for the same reason the in-process decode pool is: each decode
    transiently holds a whole inflated DBF, so matching CPU count trades wall
    time for peak memory on exactly the wide requests where memory is already
    the binding constraint.
    """

    def __init__(self, size: int = 4) -> None:
        self.size = max(1, size)
        self._workers: list[_Worker] = [_Worker() for _ in range(self.size)]
        self._free: queue.LifoQueue[_Worker] = queue.LifoQueue()
        for worker in self._workers:
            self._free.put(worker)

    def close(self) -> None:
        for worker in self._workers:
            worker.kill()

    def __enter__(self) -> DecoderPool:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def decode(
        self,
        blob_path: str | Path,
        *,
        logical_path: str,
        columns: Sequence[str] | None = None,
        members: Sequence[str] | None = None,
        row_limit: int | None = None,
        timeout: float | None = None,
    ) -> _RemoteOutcome:
        """Decode one physical source, or raise if it outlives ``timeout``.

        On expiry the process is killed and replaced. That is the difference
        this module exists for: the caller stops waiting AND the work stops.
        """
        worker = self._free.get()
        try:
            with worker.lock:
                try:
                    return self._run(
                        worker,
                        blob_path,
                        logical_path,
                        columns,
                        members,
                        row_limit,
                        timeout,
                    )
                except BaseException:
                    # A failed or incomplete framed reply is not recoverable.
                    # Even an ordinary error reply leaves protocol state whose
                    # correctness should not be guessed at.  Discard the
                    # process; this _Worker object will start a fresh one for
                    # its next borrower.
                    worker.kill()
                    raise
        finally:
            self._free.put(worker)

    def _run(
        self,
        worker: _Worker,
        blob_path: str | Path,
        logical_path: str,
        columns: Sequence[str] | None,
        members: Sequence[str] | None,
        row_limit: int | None,
        timeout: float | None,
    ) -> _RemoteOutcome:
        from ..progress import ItemTimeout
        from .base import FieldMeta

        proc = worker.start()
        assert proc.stdin is not None and proc.stdout is not None
        job = json.dumps(
            {
                "blob_path": str(blob_path),
                "logical_path": logical_path,
                "columns": sorted(columns) if columns else None,
                "members": sorted(members) if members else None,
                "row_limit": row_limit,
            }
        ).encode("utf-8")

        # The read runs on a helper thread ONLY so the deadline is enforceable;
        # unlike the thread watchdog this replaces, expiry has something it can
        # actually kill, and the helper dies with the pipe.
        box: dict[str, Any] = {}

        def _pump() -> None:
            try:
                write_frame(proc.stdin, job)  # type: ignore[arg-type]
                box["result"] = self._read_reply(proc.stdout, FieldMeta, logical_path)
            except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
                box["error"] = exc

        reader = threading.Thread(target=_pump, name="decode-io", daemon=True)
        reader.start()
        reader.join(timeout=timeout)
        if reader.is_alive():
            worker.kill()
            raise ItemTimeout(
                f"{logical_path}: no result after {timeout:.0f}s; decoder process killed"
            )
        if "error" in box:
            raise box["error"]
        return box["result"]

    @staticmethod
    def _read_reply(stdout: Any, field_meta: Any, logical_path: str) -> _RemoteOutcome:
        from .archives import ArchiveMember
        from .registry import DecodeAttempt

        head = read_frame(stdout)
        if head is None:
            raise IsolatedDecodeError(f"{logical_path}: decoder process ended unexpectedly")
        header = json.loads(head.decode("utf-8"))
        if not header.get("ok"):
            raise IsolatedDecodeError(f"{logical_path}: {header.get('error', 'decode failed')}")

        spool = tempfile.TemporaryDirectory(prefix="pegasus_decode_")
        outcome = _RemoteOutcome(
            path=logical_path, container=header.get("container") or "", retains=spool
        )
        outcome.attempts = [
            DecodeAttempt(a["reader"], a["ok"], a.get("detail", ""))
            for a in header.get("attempts", [])
        ]
        outcome.members = [
            ArchiveMember(m["name"], m["size"], m["container"], m["role"])
            for m in header.get("members", [])
        ]
        outcome.open_questions = [tuple(q) for q in header.get("open_questions", [])]

        try:
            for index, meta in enumerate(header.get("tables", [])):
                spool_path = Path(spool.name) / f"table-{index:04d}.frames"
                with spool_path.open("wb") as sink:
                    while True:
                        frame = read_frame(stdout)
                        if frame is None:
                            raise IsolatedDecodeError(
                                f"{logical_path}: decoder process ended mid-table"
                            )
                        if not frame:
                            break
                        # Keep at most one IPC batch frame in memory.  The
                        # outcome can be iterated repeatedly (archive members
                        # share it) without retaining a whole decoded source as
                        # Python/Arrow objects in the parent.
                        sink.write(struct.pack(">Q", len(frame)))
                        sink.write(frame)
                outcome.tables.append(
                    _RemoteTable(
                        path=meta["path"],
                        member=meta.get("member", ""),
                        reader=meta.get("reader", "dbf"),
                        row_count=meta.get("row_count"),
                        warnings=list(meta.get("warnings", [])),
                        fields=[
                            field_meta(
                                name=f["name"],
                                physical_type=f.get("physical_type"),
                                width=f.get("width"),
                                decimals=f.get("decimals"),
                                order=f.get("order", i),
                            )
                            for i, f in enumerate(meta.get("fields", []))
                        ],
                        retains=spool,
                        _spool_path=spool_path,
                    )
                )
            terminator = read_frame(stdout)
            if terminator != b"":
                raise IsolatedDecodeError(
                    f"{logical_path}: malformed decoder reply terminator"
                )
        except BaseException:
            spool.cleanup()
            raise
        return outcome


_POOL: DecoderPool | None = None
_POOL_LOCK = threading.Lock()


def decoder_pool(size: int = 4) -> DecoderPool:
    """The process-wide pool, started on first use.

    Shared because interpreter startup is the one real cost of this design and
    paying it per call would swamp the decode it protects.
    """
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = DecoderPool(size)
        return _POOL
