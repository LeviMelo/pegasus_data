"""No stage may hang silently: a per-item deadline and a heartbeat (§A).

This module exists because of one afternoon. ``pegasus-data all`` reached the
profile stage and stopped — no output, no error, no progress — for fifty
minutes. Diagnosing it took a thread dump, and the answer was a single FTP
transfer whose read never timed out. Everything about that is wrong, and the
wrongness is not the stalled socket. It is that a stall was *indistinguishable
from work*.

So the target is not "make that stall impossible". Stalls are not preventable:
DATASUS will drop a connection, a file will be pathological, a disk will fill.
The target is that a stall can never be silent and can never be terminal.

Two mechanisms, deliberately independent:

**The watchdog** bounds a single work item. When an item exceeds its deadline it
is abandoned, recorded as a ``coverage_gaps`` row with ``kind='timeout'`` and
whatever state was known, and the stage *continues*. A stage that skips 3 of 121
strata with three recorded reasons is shippable and honest. A stage that stops
with no output is neither. This inverts the usual instinct — the run matters
more than any item in it, because a missing item is visible in the gap report
and a missing run is visible only as silence.

**The heartbeat** bounds ignorance. Every stage says where it is at a fixed
interval: item N of M, elapsed, and *what it started last*. That last field is
the one that matters — it is the difference between "something is slow" and
"``RDAC1401.dbc`` is slow", and it would have turned that afternoon into a
minute. Printed unbuffered, because a stall that is still sitting in a stdio
buffer has not been reported.

Neither mechanism decides anything about the work. They observe it, bound it,
and write down what happened.
"""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeVar

from .catalog.store import Catalog

T = TypeVar("T")

#: How long one work item may take before it is abandoned. Generous: the point
#: is to catch a *stall*, not to punish a slow file. A 20-minute item is
#: pathological on this tree, where the largest single file is a few hundred MB.
DEFAULT_ITEM_TIMEOUT = 1200.0

#: How long a whole stage may go without finishing *any* item. Catches the case
#: an item timeout cannot: workers alive, queue draining, nothing completing.
DEFAULT_STALL_TIMEOUT = 1800.0

#: Seconds between heartbeats. Frequent enough that a person watching learns
#: something before losing patience; rare enough not to become the output.
DEFAULT_HEARTBEAT = 30.0


class ItemTimeout(RuntimeError):
    """One work item exceeded its deadline. Caught by the loop, never fatal."""


@dataclass(slots=True)
class StageProgress:
    """What a stage has done so far, and what it is doing right now."""

    stage: str
    total: int = 0
    completed: int = 0
    failed: int = 0
    timed_out: int = 0
    started_at: float = field(default_factory=time.monotonic)
    last_completion: float = field(default_factory=time.monotonic)
    current: str | None = None
    current_started: float | None = None
    timeouts: list[tuple[str, float]] = field(default_factory=list)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started_at

    def line(self) -> str:
        """One heartbeat line. Names the item in flight, not just the counts."""
        parts = [
            f"[{self.stage}]",
            f"{self.completed}/{self.total or '?'}",
            f"elapsed {_hms(self.elapsed)}",
        ]
        if self.failed:
            parts.append(f"failed {self.failed}")
        if self.timed_out:
            parts.append(f"timed out {self.timed_out}")
        if self.current is not None:
            waited = time.monotonic() - (self.current_started or time.monotonic())
            parts.append(f"on {self.current} ({_hms(waited)})")
        return "  ".join(parts)

    def as_dict(self) -> dict[str, object]:
        return {
            "stage": self.stage,
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "timed_out": self.timed_out,
            "elapsed_seconds": round(self.elapsed, 1),
            "timeouts": [{"item": i, "seconds": round(s, 1)} for i, s in self.timeouts],
        }


def _hms(seconds: float) -> str:
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m{seconds % 60:02d}s"
    return f"{seconds // 3600}h{(seconds % 3600) // 60:02d}m"


class Heartbeat:
    """Prints a stage's progress on a timer until stopped.

    A daemon thread rather than a callback on the work loop, precisely because
    the work loop is what might be stuck. Progress reported only when progress
    happens is not a heartbeat; it is a progress bar, and a progress bar tells
    you nothing about the case that matters.
    """

    def __init__(
        self,
        progress: StageProgress,
        *,
        interval: float = DEFAULT_HEARTBEAT,
        emit: Callable[[str], None] | None = None,
    ) -> None:
        self.progress = progress
        self.interval = interval
        self.emit = emit or _print_unbuffered
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def __enter__(self) -> Heartbeat:
        self._thread = threading.Thread(
            target=self._run, name=f"heartbeat-{self.progress.stage}", daemon=True
        )
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.emit(self.progress.line())
            except Exception:  # noqa: BLE001 - a broken pipe must not kill the run
                return


def _print_unbuffered(line: str) -> None:
    # flush explicitly: a heartbeat sitting in a buffer has not been reported,
    # and stdout is block-buffered whenever it is not a terminal — which is
    # exactly the case (piped, redirected, CI) where a stall is hardest to see.
    try:
        sys.stderr.write(line + "\n")
        sys.stderr.flush()
    except Exception:  # noqa: BLE001
        pass


def run_with_timeout(
    fn: Callable[[], T], *, seconds: float, label: str
) -> T:
    """Run ``fn``, raising :class:`ItemTimeout` if it outlives its deadline.

    The worker is a daemon thread and is **not** killed on timeout — Python
    cannot safely interrupt arbitrary code, and pretending otherwise is how a
    half-written file happens. It is abandoned: left to finish or not, holding
    nothing the caller needs. The cost is a leaked thread per timeout, which is
    bounded by how many timeouts a run tolerates and is much cheaper than the
    alternative of stopping.
    """
    box: dict[str, Any] = {}

    def _target() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
            box["error"] = exc

    worker = threading.Thread(target=_target, name=f"item-{label}"[:60], daemon=True)
    worker.start()
    worker.join(timeout=seconds)
    if worker.is_alive():
        raise ItemTimeout(f"{label}: no result after {_hms(seconds)}; abandoned")
    if "error" in box:
        raise box["error"]
    return box["value"]  # type: ignore[return-value]


def record_timeout(
    catalog: Catalog, *, stage: str, item: str, seconds: float, state: str = ""
) -> None:
    """Write an abandoned item into ``coverage_gaps`` so it is queryable.

    ``coverage_gaps`` already means "we know we do not have this, and why",
    which is exactly what an abandoned item is. Putting timeouts anywhere else
    would split the answer to "what is missing?" across two tables.
    """
    detail = f"{stage}: abandoned after {_hms(seconds)}"
    if state:
        detail = f"{detail}; last known state: {state}"
    catalog.record_gap(item, kind="timeout", methods=(stage,), error=detail)
    catalog.log_event(stage, "item abandoned on timeout", level="warn", detail=f"{item}: {detail}")


def guarded(
    catalog: Catalog,
    stage: str,
    items: Sequence[T] | Iterable[T],
    *,
    label: Callable[[T], str],
    total: int | None = None,
    item_timeout: float = DEFAULT_ITEM_TIMEOUT,
    stall_timeout: float = DEFAULT_STALL_TIMEOUT,
    heartbeat: float = DEFAULT_HEARTBEAT,
    emit: Callable[[str], None] | None = None,
) -> Iterator[tuple[T, StageProgress]]:
    """Iterate work items with a heartbeat running and stalls bounded.

    Yields ``(item, progress)``. The caller does the work; this decides when to
    give up on it and makes sure someone can see what is happening meanwhile.
    A caller that wants the per-item deadline enforced wraps its own body in
    :func:`run_with_timeout` — the split is deliberate, because only the caller
    knows what is safely abandonable.
    """
    sequence = list(items)
    progress = StageProgress(stage=stage, total=total if total is not None else len(sequence))
    with Heartbeat(progress, interval=heartbeat, emit=emit):
        for item in sequence:
            name = label(item)
            progress.current = name
            progress.current_started = time.monotonic()
            since_completion = time.monotonic() - progress.last_completion
            if since_completion > stall_timeout:
                catalog.log_event(
                    stage,
                    "stage abandoned: no item completed within the stall deadline",
                    level="error",
                    detail=f"{_hms(since_completion)} since the last completion; "
                    f"{progress.completed}/{progress.total} done",
                )
                (emit or _print_unbuffered)(
                    f"[{stage}] STALLED: nothing completed in {_hms(since_completion)}; stopping"
                )
                return
            yield item, progress
            progress.current = None
            progress.current_started = None
    (emit or _print_unbuffered)(f"[{stage}] done: {progress.line()}")
