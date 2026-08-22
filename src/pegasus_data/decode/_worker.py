"""A decoder in its own process, so a timeout can actually end the work.

``run_with_timeout`` stops the caller waiting; it cannot stop a decoder. Python
cannot kill a thread, and DBC inflation happens inside a native extension that
never yields — so an "abandoned" file went on consuming a core, hundreds of
megabytes and temporary disk after the API had reported it abandoned and moved
on. Repeated pathological files accumulate that.

An OS process can be killed. This module is the thing on the other side of that
boundary: it reads decode jobs on stdin, writes Arrow back on stdout, and dies
without complaint when the parent decides it has had long enough.

Run as ``python -m pegasus_data.decode._worker``, deliberately rather than
through :mod:`multiprocessing`. A library imported from a notebook, a REPL or a
frozen Windows application cannot rely on the caller having a guarded
``__main__``, and multiprocessing's spawn start method re-imports it.

**The wire format.** Every frame is a 4-byte big-endian length followed by that
many bytes; a zero length is a terminator. A job is one JSON frame. A reply is
one JSON header frame, then for each table a sequence of Arrow IPC stream frames
ended by a terminator, then a final terminator for the reply.

Batches are framed individually on purpose: neither side ever holds the whole
decoded table, which is the property the in-process path has and would be a
shame to lose in exchange for killability.
"""

from __future__ import annotations

import json
import struct
import sys
from typing import BinaryIO

_LEN = struct.Struct(">I")


def write_frame(stream: BinaryIO, payload: bytes) -> None:
    stream.write(_LEN.pack(len(payload)))
    if payload:
        stream.write(payload)
    stream.flush()


def read_frame(stream: BinaryIO) -> bytes | None:
    """The next frame, ``b""`` for a terminator, or ``None`` at end of stream."""
    header = stream.read(_LEN.size)
    if len(header) < _LEN.size:
        return None
    (size,) = _LEN.unpack(header)
    if size == 0:
        return b""
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        block = stream.read(remaining)
        if not block:
            return None
        chunks.append(block)
        remaining -= len(block)
    return b"".join(chunks)


def _field_meta(field: object) -> dict[str, object]:
    return {
        "name": getattr(field, "name", ""),
        "physical_type": getattr(field, "physical_type", None),
        "width": getattr(field, "width", None),
        "decimals": getattr(field, "decimals", None),
        "order": getattr(field, "order", 0),
    }


def _run_job(job: dict[str, object], out: BinaryIO) -> None:
    import pyarrow as pa

    from .registry import ReaderRegistry

    columns = job.get("columns")
    registry = ReaderRegistry(row_limit=job.get("row_limit"))
    outcome = registry.open_path(
        str(job["blob_path"]),
        logical_path=str(job.get("logical_path") or job["blob_path"]),
        columns=frozenset(columns) if columns else None,
    )

    header = {
        "ok": True,
        "container": outcome.container,
        "attempts": [
            {"reader": a.reader, "ok": a.ok, "detail": getattr(a, "detail", "")}
            for a in outcome.attempts
        ],
        "open_questions": [list(q) for q in outcome.open_questions],
        "members": [
            {"name": m.name, "size": m.size, "container": m.container, "role": m.role}
            for m in outcome.members
        ],
        "tables": [
            {
                "path": t.path,
                "member": t.member,
                "reader": t.reader,
                "row_count": t.row_count,
                "warnings": list(t.warnings),
                "fields": [_field_meta(f) for f in t.fields],
            }
            for t in outcome.tables
        ],
    }
    write_frame(out, json.dumps(header).encode("utf-8"))

    for table in outcome.tables:
        for batch in table.batches():
            if not batch.num_rows:
                continue
            sink = pa.BufferOutputStream()
            with pa.ipc.new_stream(sink, batch.schema) as writer:
                writer.write_batch(batch)
            write_frame(out, sink.getvalue().to_pybytes())
        write_frame(out, b"")  # end of this table's batches
    write_frame(out, b"")  # end of reply


def main() -> int:
    stdin = sys.stdin.buffer
    stdout = sys.stdout.buffer
    while True:
        frame = read_frame(stdin)
        if frame is None:
            return 0
        if not frame:
            continue
        try:
            job = json.loads(frame.decode("utf-8"))
        except ValueError:
            write_frame(stdout, json.dumps({"ok": False, "error": "bad job"}).encode())
            write_frame(stdout, b"")
            continue
        try:
            _run_job(job, stdout)
        except BaseException as exc:  # noqa: BLE001 - reported, not raised across the pipe
            write_frame(
                stdout,
                json.dumps(
                    {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
                ).encode("utf-8"),
            )
            write_frame(stdout, b"")


if __name__ == "__main__":  # pragma: no cover - process entry point
    raise SystemExit(main())
