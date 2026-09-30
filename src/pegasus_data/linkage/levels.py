"""Comparison levels on whole Arrow arrays (ADR-0111).

The same levels as the scalar comparators in ``model.py``, vectorised: a
national candidate set is tens of millions of pairs, which a Python loop
cannot score. ``levels(kind, a, b)`` agrees with ``comparator(kind)(a, b)``
value for value; the agreement was checked on synthetic typos of every kind
when this module was written (EVALUATION 2026-09-30, national runs).
"""

from __future__ import annotations

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

from .model import _PAD, MISSING

_ADJ = np.zeros((10, 10), dtype=bool)
for _x, _ys in _PAD.items():
    for _y in _ys:
        _ADJ[int(_x), int(_y)] = True
for _d in range(10):
    for _e in (_d - 1, _d + 1):
        if 0 <= _e <= 9:
            _ADJ[_d, _e] = True


def _digits(dates: pa.Array) -> np.ndarray:
    """Dates as an (n, 8) array of DDMMYYYY digits; a missing row is all -1."""
    text = pc.fill_null(pc.strftime(pc.cast(dates, pa.timestamp("s")), format="%d%m%Y"), "--------")
    joined = "".join(text.to_pylist()).encode("ascii")
    arr = np.frombuffer(joined, dtype=np.uint8).reshape(len(text), 8).astype(np.int16) - 48
    arr[arr < 0] = -1
    return arr


def _levels_date(a: pa.Array, b: pa.Array) -> np.ndarray:
    da, db = _digits(a), _digits(b)
    n = len(da)
    out = np.full(n, "other", dtype=object)
    missing = (da[:, 0] < 0) | (db[:, 0] < 0)
    diff = da != db
    k = diff.sum(axis=1)
    out[k == 0] = "equal"
    one = np.nonzero(k == 1)[0]
    if len(one):
        pos = diff[one].argmax(axis=1)
        x, y = da[one, pos], db[one, pos]
        out[one] = np.where(_ADJ[x, y], "one digit, adjacent key", "one digit, other key")
    two = np.nonzero(k == 2)[0]
    if len(two):
        p0 = diff[two].argmax(axis=1)
        p1 = 7 - diff[two][:, ::-1].argmax(axis=1)
        swapped = (p1 == p0 + 1) & (da[two, p0] == db[two, p1]) & (da[two, p1] == db[two, p0])
        out[two[swapped]] = "neighbouring digits swapped"
    dm = ((da[:, 0:2] == db[:, 2:4]).all(axis=1) & (da[:, 2:4] == db[:, 0:2]).all(axis=1)
          & (da[:, 4:] == db[:, 4:]).all(axis=1) & (k > 0))
    out[dm & (out == "other")] = "day and month swapped"
    ya = da[:, 4] * 1000 + da[:, 5] * 100 + da[:, 6] * 10 + da[:, 7]
    yb = db[:, 4] * 1000 + db[:, 5] * 100 + db[:, 6] * 10 + db[:, 7]
    yoff = (da[:, :4] == db[:, :4]).all(axis=1) & (np.abs(ya - yb) == 1)
    out[yoff & (out == "other")] = "year off by one"
    out[missing] = MISSING
    return out


def _levels_integer(a: pa.Array, b: pa.Array) -> np.ndarray:
    missing = pc.or_(pc.is_null(a), pc.is_null(b)).to_numpy(zero_copy_only=False)
    va = pc.fill_null(pc.cast(a, pa.int64()), -1).to_numpy(zero_copy_only=False)
    vb = pc.fill_null(pc.cast(b, pa.int64()), -1).to_numpy(zero_copy_only=False)
    out = np.full(len(va), "other", dtype=object)
    hi = np.maximum(np.maximum(np.abs(va), np.abs(vb)), 1)
    rel = np.abs(va - vb) / hi
    out[rel <= 0.10] = "within 10%"
    out[rel <= 0.01] = "within 1%"
    out[va == vb] = "equal"
    rest = np.nonzero((out == "other") & ~missing)[0]
    for j in rest:
        x, y = str(va[j]), str(vb[j])
        if abs(len(x) - len(y)) == 1:
            longer, shorter = (x, y) if len(x) > len(y) else (y, x)
            if any(longer[:i] + longer[i + 1:] == shorter for i in range(len(longer))):
                out[j] = "digit dropped or added"
    out[missing] = MISSING
    return out


def _levels_municipality(a: pa.Array, b: pa.Array) -> np.ndarray:
    missing = pc.or_(pc.is_null(a), pc.is_null(b)).to_numpy(zero_copy_only=False)
    eq = pc.fill_null(pc.equal(a, b), False).to_numpy(zero_copy_only=False)
    same = pc.fill_null(pc.equal(pc.utf8_slice_codeunits(a, 0, 2), pc.utf8_slice_codeunits(b, 0, 2)), False)
    out = np.where(eq, "equal", np.where(same.to_numpy(zero_copy_only=False), "same state", "different state"))
    out = out.astype(object)
    out[missing] = MISSING
    return out


def _days(x: pa.Array) -> np.ndarray:
    return pc.fill_null(pc.cast(pc.cast(x, pa.date32()), pa.int32()), 0).to_numpy(zero_copy_only=False).astype(np.int64)


def _levels_interval(a: pa.Array, start: pa.Array, end: pa.Array) -> np.ndarray:
    missing = pc.or_(pc.or_(pc.is_null(a), pc.is_null(start)), pc.is_null(end)).to_numpy(zero_copy_only=False)
    ia, s, e = _days(a), _days(start), _days(end)
    inside = (ia >= s) & (ia <= e)
    gap = np.where(ia < s, s - ia, ia - e)
    out = np.full(len(ia), "other", dtype=object)
    out[~inside & (gap <= 7)] = "within a week outside"
    out[~inside & (gap <= 1)] = "one day outside"
    off = ia - s
    out[inside] = "inside, later"
    out[inside & (off == 1)] = "inside, second day"
    out[inside & (off == 0)] = "inside, first day"
    out[missing] = MISSING
    return out


def _levels_exact(a: pa.Array, b: pa.Array) -> np.ndarray:
    missing = pc.or_(pc.is_null(a), pc.is_null(b)).to_numpy(zero_copy_only=False)
    eq = pc.fill_null(pc.equal(a, b), False).to_numpy(zero_copy_only=False)
    out = np.where(eq, "equal", "different").astype(object)
    out[missing] = MISSING
    return out


def levels(kind: str, a: pa.Array, b: pa.Array | tuple[pa.Array, pa.Array]) -> np.ndarray:
    """The level of every pair; ``b`` is ``(start, end)`` for an interval."""
    if kind == "interval":
        start, end = b  # type: ignore[misc]
        return _levels_interval(a, start, end)
    if kind == "date":
        return _levels_date(a, b)  # type: ignore[arg-type]
    if kind == "integer":
        return _levels_integer(a, b)  # type: ignore[arg-type]
    if kind == "municipality":
        return _levels_municipality(a, b)  # type: ignore[arg-type]
    return _levels_exact(a, b)  # type: ignore[arg-type]


__all__ = ["levels"]
