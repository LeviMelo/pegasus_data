"""How many transfers run at once: found by the throughput they give, not fixed.

A server caps each connection (DATASUS's FTP about 1.7 MB/s) and the line caps them all, at a ceiling that moved between
3 and 7 MB/s in one evening (2026-11-21) with other downloads on the machine. A fixed count is either short of the
ceiling or past it, where more connections only share it. `adaptive_map` starts at a few tasks in flight and adds one
while the total rate keeps rising, takes one away when it falls, and adds none while free memory is under the decode
admission's floor (`decode.admission.free_floor_bytes`). It never removes one for memory: the admission already makes
each decode wait for free memory, and a guard that also removed tasks held a synthetic run at one task on a machine
short of memory (2026-11-22).
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
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
                 cap: int = 24, pace: Pace | None = None) -> Iterator[R]:
    """``fn`` over ``items`` in threads, yielding each result as it completes (not in order). ``measure`` says how many
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
    with ThreadPoolExecutor(max_workers=max(cap, start), thread_name_prefix="adaptive") as pool:
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


__all__ = ["Pace", "adaptive_map"]
