"""Comparison levels on whole Arrow arrays (ADR-0111).

The levels of every comparison type (listed in ``model.py``), computed on whole
arrays: a national candidate set is tens of millions of pairs, which a Python
loop cannot score. This is the one definition; it replaced scalar comparators
it was checked equal to on synthetic typos of every kind (EVALUATION 2026-09-30,
national runs).
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
    """Dates as an (n, 8) array of DDMMYYYY digits; a missing row is all -1.

    Calendar arithmetic on the whole array: formatting each date as text in
    Python cost a third of a link's time (profile, 2026-10-02).
    """
    if isinstance(dates, pa.ChunkedArray):
        dates = dates.combine_chunks()
    missing = pc.is_null(dates).to_numpy(zero_copy_only=False)
    days = pc.fill_null(pc.cast(dates, pa.date32()), 0).cast(pa.int32()).to_numpy(zero_copy_only=False)
    d64 = days.astype("datetime64[D]")
    months = d64.astype("datetime64[M]")
    year = d64.astype("datetime64[Y]").astype(np.int64) + 1970
    month = months.astype(np.int64) % 12 + 1
    day = (d64 - months).astype(np.int64) + 1
    arr = np.stack([day // 10, day % 10, month // 10, month % 10,
                    year // 1000 % 10, year // 100 % 10, year // 10 % 10, year % 10], axis=1).astype(np.int16)
    arr[missing] = -1
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


def _levels_municipality_given(a: pa.Array, b: pa.Array, place: pa.Array, side: str) -> np.ndarray:
    """Residence against residence, knowing where one side's record was cared for.

    Two records agreeing on the hospital's own municipality is weak evidence
    where residence is often written as the place of care; agreeing elsewhere
    is strong; and a residence equal to the place of care on the side that
    carries it may be the hospital written in, so a true pair can disagree
    there. m and u of each level are learned, so the data decide how much each
    is worth (ADR-0115).
    """
    out = _levels_municipality(a, b)
    known = ~pc.is_null(place).to_numpy(zero_copy_only=False)
    at_a = pc.fill_null(pc.equal(a, place), False).to_numpy(zero_copy_only=False)
    at_b = pc.fill_null(pc.equal(b, place), False).to_numpy(zero_copy_only=False)
    at_own = at_b if side == "right" else at_a
    usable = known & (out != MISSING)
    eq = usable & (out == "equal")
    out[eq & at_a] = "equal, at the place of care"
    out[eq & ~at_a] = "equal, elsewhere"
    out[usable & ~eq & at_own] = f"{side} is the place of care"
    return out


#: ICD-10's definitions (P07.0 "birth weight 999 g or less", P07.1 "1000-2499 g",
#: P07.2 "less than 28 completed weeks", P07.3 "28 completed weeks or more but
#: less than 37"); the codes, not a tuned band.
_ICD_SIZE = {
    "icd_birth_weight": (("P070", 0, 999), ("P071", 1000, 2499), 2500, "g"),
    "icd_gestation": (("P072", 0, 27), ("P073", 28, 36), 37, "weeks"),
}


def _levels_icd_size(kind: str, codes: pa.Array, measure: pa.Array) -> np.ndarray:
    """An admission's diagnoses against a birth's weight or weeks (ADR-0117)."""
    (c1, lo1, hi1), (c2, lo2, hi2), low_below, unit = _ICD_SIZE[kind]
    text = pc.fill_null(codes, "")
    has1 = pc.match_substring(text, c1).to_numpy(zero_copy_only=False)
    has2 = pc.match_substring(text, c2).to_numpy(zero_copy_only=False)
    missing = pc.or_(pc.is_null(codes), pc.is_null(measure)).to_numpy(zero_copy_only=False)
    v = pc.fill_null(pc.cast(measure, pa.int64()), -1).to_numpy(zero_copy_only=False)
    out = np.where(v < low_below, f"no size code, under {low_below} {unit}",
                   f"no size code, {low_below} {unit} or more").astype(object)
    out[has2] = np.where((v[has2] >= lo2) & (v[has2] <= hi2), f"{c2}, fits", f"{c2}, does not fit")
    out[has1] = np.where((v[has1] >= lo1) & (v[has1] <= hi1), f"{c1}, fits", f"{c1}, does not fit")
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


def levels(kind: str, a: pa.Array, b: pa.Array | tuple[pa.Array, pa.Array],
           given: pa.Array | None = None, given_side: str = "right") -> np.ndarray:
    """The level of every pair; ``b`` is ``(start, end)`` for an interval.

    ``given`` is one record's value of a conditioning role (the place of care,
    for a municipality), carried by ``given_side``.
    """
    if kind in _ICD_SIZE:
        return _levels_icd_size(kind, a, b)  # type: ignore[arg-type]
    if kind == "municipality" and given is not None:
        return _levels_municipality_given(a, b, given, given_side)  # type: ignore[arg-type]
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
