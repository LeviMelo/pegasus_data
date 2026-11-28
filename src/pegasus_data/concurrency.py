"""How many transfers run at once: found by the throughput they give, not fixed.

A server caps each connection (DATASUS's FTP about 1.7 MB/s) and the line caps them all, at a ceiling that moved between
3 and 7 MB/s in one evening (2026-11-21) with other downloads on the machine. A fixed count is either short of the
ceiling or past it, where more connections only share it. `adaptive_map` starts at a few tasks in flight and adds one
while the total rate keeps rising, takes one away when it falls, and adds none while free memory is under the decode
admission's floor (`decode.admission.free_floor_bytes`). It never removes one for memory: the admission already makes
each decode wait for free memory, and a guard that also removed tasks held a synthetic run at one task on a machine
short of memory (2026-11-22).

What the tasks in flight may hold together is another matter, and `MemoryBudget`'s: a task that holds memory takes its
grant from the budget before it starts.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, TypeVar

T = TypeVar("T")
R = TypeVar("R")

#: a rise or fall of the total rate smaller than this is noise, and the count stays
STEP = 0.05


@dataclass
class Pace:
    """What `adaptive_map` did: the in-flight counts it tried and the rate each window measured (``measure`` a second)."""

    limits: list[int] = field(default_factory=list)
    rates: list[float] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"in_flight": self.limits[-1] if self.limits else None, "peak": max(self.limits, default=None),
                "rate_per_second": round(self.rates[-1], 3) if self.rates else None}


def adaptive_map(fn: Callable[[T], R], items: Iterable[T], *, measure: Callable[[R], float], start: int = 4,
                 cap: int = 24, pace: Pace | None = None, processes: bool = False) -> Iterator[R]:
    """``fn`` over ``items`` in threads (``processes=True``: in worker processes, ``fn`` and items picklable, ``cap``
    processes at most), yielding each result as it completes (not in order). Threads share one interpreter lock, so
    Python-bound work (decoding) gains from processes; a download-bound run does not (extract.EXTRACT_PROCESSES). ``measure`` says how many
    bytes a result moved. Every window of as many completions as tasks in flight, the window's rate is compared with the
    last: a rise of more than `STEP` adds a task (up to ``cap``), a fall of more than `STEP` removes one (down to 1).
    ``measure`` is any work a result stands for: bytes downloaded, or 1 for a task of a kind whose sizes are alike."""
    import psutil

    from .decode.admission import free_floor_bytes

    pace = pace if pace is not None else Pace()
    limit = max(1, start)
    source = iter(items)
    pending: set[Future[R]] = set()
    window_bytes, window_done, window_start = 0.0, 0, time.monotonic()      # the work of the window, in ``measure``
    last_rate: float | None = None
    exhausted = False
    if processes:
        from concurrent.futures import ProcessPoolExecutor
        executor = ProcessPoolExecutor(max_workers=max(cap, start))
    else:
        executor = ThreadPoolExecutor(max_workers=max(cap, start), thread_name_prefix="adaptive")
    with executor as pool:
        def fill() -> None:
            nonlocal exhausted
            while not exhausted and len(pending) < limit:
                try:
                    pending.add(pool.submit(fn, next(source)))
                except StopIteration:
                    exhausted = True
        fill()
        pace.limits.append(limit)
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                pending.discard(future)
                result = future.result()
                window_bytes += float(measure(result) or 0)
                window_done += 1
                yield result
            if window_done >= limit:
                elapsed = max(time.monotonic() - window_start, 1e-6)
                rate = window_bytes / elapsed
                short_of_memory = psutil.virtual_memory().available < free_floor_bytes()
                rising = last_rate is None or rate > last_rate * (1 + STEP)
                falling = last_rate is not None and rate < last_rate * (1 - STEP)
                if rising and not short_of_memory:
                    limit = min(cap, limit + 1)
                elif falling:
                    limit = max(1, limit - 1)
                last_rate = rate
                pace.limits.append(limit)
                pace.rates.append(rate)
                window_bytes, window_done, window_start = 0.0, 0, time.monotonic()
            fill()


class MemoryBudget:
    """The memory the tasks in flight of one process may hold together (ADR-0247).

    `adaptive_map` chooses how many tasks run at once by the rate they give; it knows nothing of what each may hold. A
    task that opens a connection with a memory limit holds, at worst, that limit: four SNGPC months in flight, each
    allowed 7 GB, were 28 GB on a 32 GB machine (2026-11-28). A task takes its grant from the budget before it opens
    the connection (`hold`) and waits while the grants in flight leave no room. The budget is the machine's free memory
    less the admission floor, measured when nothing is held, and never under one ``largest`` grant, so one task always
    runs. A grant the budget cannot fit waits for it to be empty and runs alone. It bounds one process: several
    processes are bounded by what starts them (a slot, the guard)."""

    def __init__(self, largest_gb: float) -> None:
        import threading

        self.largest = float(largest_gb)
        self.total = self.largest
        self.held = 0.0
        self.peak = 0.0
        self._room = threading.Condition()

    def _measure(self) -> None:
        import psutil

        from .decode.admission import free_floor_bytes

        self.total = max(self.largest, (psutil.virtual_memory().available - free_floor_bytes()) / 2**30)

    @contextmanager
    def hold(self, gb: float) -> Iterator[float]:
        gb = min(float(gb), self.largest)
        with self._room:
            while True:
                if self.held == 0:
                    self._measure()
                if self.held == 0 or self.held + gb <= self.total:
                    break
                self._room.wait(timeout=30)
            self.held += gb
            self.peak = max(self.peak, self.held)
        try:
            yield gb
        finally:
            with self._room:
                self.held -= gb
                if self.held < 1e-9:
                    self.held = 0.0
                self._room.notify_all()


__all__ = ["MemoryBudget", "Pace", "adaptive_map"]
