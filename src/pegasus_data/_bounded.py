"""A process cache that holds at most ``maxsize`` entries, the least recently used evicted first."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, TypeVar

K = TypeVar("K")
V = TypeVar("V")
_MISSING: Any = object()


class Bounded(OrderedDict[K, V]):
    """A dict of at most ``maxsize`` entries. A read (``d[k]``, ``d.get(k)``) makes an entry the most recently used;
    a write past the size evicts the least recently used. The one shape of every count-bounded cache here (was three:
    clear everything at N, drop the oldest written, and this)."""

    def __init__(self, maxsize: int) -> None:
        super().__init__()
        self.maxsize = maxsize

    def _touch(self, key: K) -> None:
        try:
            self.move_to_end(key)
        except KeyError:        # evicted by another thread between the read and the touch: the value read stands
            pass

    def __getitem__(self, key: K) -> V:
        value = super().__getitem__(key)
        self._touch(key)
        return value

    def get(self, key: K, default: Any = None) -> Any:
        value = super().get(key, _MISSING)
        if value is _MISSING:
            return default
        self._touch(key)
        return value

    def __setitem__(self, key: K, value: V) -> None:
        super().__setitem__(key, value)
        self.move_to_end(key)
        while len(self) > self.maxsize:
            self.popitem(last=False)
