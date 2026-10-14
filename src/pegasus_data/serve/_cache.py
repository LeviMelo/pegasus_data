"""Bounded caches for the HTTP layer.

Every cache here is bounded by BYTES, not by entry count: an entry is a
serialised response or a decoded table, and 256 of them is anything between a
megabyte and a gigabyte. Eviction drops the least recently used entry, one at
a time -- clearing everything when full made the next 16 requests pay full
price (the descriptor cache did exactly that).

``once`` is the single-flight lock: two identical requests that both miss run
the work once, and the second waits for the first's answer instead of decoding
the same territory a second time.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from typing import Any


class ByteCache:
    """An LRU mapping bounded by the summed ``size`` of its values."""

    def __init__(self, limit_bytes: int) -> None:
        self.limit = limit_bytes
        self._items: OrderedDict[Hashable, tuple[Any, int]] = OrderedDict()
        self._used = 0
        self._lock = threading.Lock()
        self._flights: dict[Hashable, threading.Lock] = {}

    def get(self, key: Hashable) -> Any | None:
        with self._lock:
            hit = self._items.get(key)
            if hit is None:
                return None
            self._items.move_to_end(key)
            return hit[0]

    def put(self, key: Hashable, value: Any, size: int) -> None:
        """Store ``value``; a value larger than the whole budget is not kept."""
        if size > self.limit:
            return
        with self._lock:
            old = self._items.pop(key, None)
            if old is not None:
                self._used -= old[1]
            self._items[key] = (value, size)
            self._used += size
            while self._used > self.limit and self._items:
                _, (_, dropped) = self._items.popitem(last=False)
                self._used -= dropped

    def once(self, key: Hashable, build: Callable[[], tuple[Any, int]]) -> Any:
        """``get(key)``, or run ``build() -> (value, size)`` exactly once for all concurrent callers."""
        hit = self.get(key)
        if hit is not None:
            return hit
        with self._lock:
            flight = self._flights.setdefault(key, threading.Lock())
        with flight:
            hit = self.get(key)
            if hit is not None:
                return hit
            try:
                value, size = build()
                self.put(key, value, size)
                return value
            finally:
                with self._lock:
                    self._flights.pop(key, None)

    def __len__(self) -> int:
        return len(self._items)

    @property
    def used(self) -> int:
        return self._used
