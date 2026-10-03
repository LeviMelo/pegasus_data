"""Comparison levels on whole Arrow arrays (ADR-0111).

The levels of every comparison type (listed in ``model.py``), computed on whole
arrays: a national candidate set is tens of millions of pairs, which a Python
loop cannot score. This is the one definition; it replaced scalar comparators
it was checked equal to on synthetic typos of every kind (EVALUATION 2026-09-30,
national runs).
"""

from __future__ import annotations

from typing import NamedTuple

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


def _days_of(dates: pa.Array) -> tuple[np.ndarray, np.ndarray]:
    """Days since 1970 and the missing mask."""
    if isinstance(dates, pa.ChunkedArray):
        dates = dates.combine_chunks()
    missing = pc.is_null(dates).to_numpy(zero_copy_only=False)
    days = pc.fill_null(pc.cast(dates, pa.date32()), 0).cast(pa.int32()).to_numpy(zero_copy_only=False)
    return days, missing


def _digits_of_days(days: np.ndarray) -> np.ndarray:
    """(n, 8) DDMMYYYY digits, computed once per distinct day and gathered:
    candidate dates repeat (a block shares them), and the calendar arithmetic
    per row was most of a date comparison's cost (profile 2026-10-03)."""
    uniq, inverse = np.unique(days, return_inverse=True)
    d64 = uniq.astype("datetime64[D]")
    months = d64.astype("datetime64[M]")
    year = d64.astype("datetime64[Y]").astype(np.int64) + 1970
    month = months.astype(np.int64) % 12 + 1
    day = (d64 - months).astype(np.int64) + 1
    arr = np.stack([day // 10, day % 10, month // 10, month % 10,
                    year // 1000 % 10, year // 100 % 10, year // 10 % 10, year % 10], axis=1).astype(np.int16)
    return arr[inverse]


def _digits(dates: pa.Array) -> np.ndarray:
    """Dates as an (n, 8) array of DDMMYYYY digits; a missing row is all -1."""
    days, missing = _days_of(dates)
    arr = _digits_of_days(days)
    arr[missing] = -1
    return arr


class Levels(NamedTuple):
    """The level of every pair, as small integer codes into ``names``.

    Millions of pairs share a dozen levels: Python strings per pair cost an
    object array, a factorise and a sort for every comparison (a quarter of
    a link's time, profile 2026-10-03). Codes are gathered instead.
    """

    codes: np.ndarray
    names: tuple[str, ...]

    def strings(self) -> np.ndarray:
        """The levels as strings (for small samples: anchors, tests)."""
        return np.asarray(self.names, dtype=object)[self.codes] if len(self.codes) else np.zeros(0, dtype=object)


class _Build:
    """Codes filled by mask, one name at a time, like the string arrays were."""

    __slots__ = ("codes", "names", "_index")

    def __init__(self, n: int, default: str) -> None:
        self.codes = np.zeros(n, dtype=np.int16)
        self.names: list[str] = [default]
        self._index = {default: 0}

    def code(self, name: str) -> int:
        idx = self._index.get(name)
        if idx is None:
            idx = self._index[name] = len(self.names)
            self.names.append(name)
        return idx

    def set(self, mask: np.ndarray, name: str) -> None:
        self.codes[mask] = self.code(name)

    def is_(self, name: str) -> np.ndarray:
        idx = self._index.get(name)
        return self.codes == idx if idx is not None else np.zeros(len(self.codes), dtype=bool)

    def put(self, rows: np.ndarray, sub: Levels) -> None:
        """Write another result's levels into ``rows``."""
        remap = np.array([self.code(n) for n in sub.names], dtype=np.int16)
        self.codes[rows] = remap[sub.codes]

    def done(self) -> Levels:
        return Levels(self.codes, tuple(self.names))


def _levels_date(a: pa.Array, b: pa.Array) -> Levels:
    days_a, miss_a = _days_of(a)
    days_b, miss_b = _days_of(b)
    missing = miss_a | miss_b
    out = _Build(len(days_a), "other")
    equal = (days_a == days_b) & ~missing
    out.set(equal, "equal")
    # Only the unequal pairs need their digits compared.
    rest = np.nonzero(~equal & ~missing)[0]
    if len(rest):
        out.put(rest, _levels_date_digits(_digits_of_days(days_a[rest]), _digits_of_days(days_b[rest])))
    out.set(missing, MISSING)
    return out.done()


def _levels_date_digits(da: np.ndarray, db: np.ndarray) -> Levels:
    """Levels of unequal, non-missing date pairs, from their digits."""
    out = _Build(len(da), "other")
    diff = da != db
    k = diff.sum(axis=1)
    one = np.nonzero(k == 1)[0]
    if len(one):
        pos = diff[one].argmax(axis=1)
        adjacent = _ADJ[da[one, pos], db[one, pos]]
        out.set(one[adjacent], "one digit, adjacent key")
        out.set(one[~adjacent], "one digit, other key")
    two = np.nonzero(k == 2)[0]
    if len(two):
        p0 = diff[two].argmax(axis=1)
        p1 = 7 - diff[two][:, ::-1].argmax(axis=1)
        swapped = (p1 == p0 + 1) & (da[two, p0] == db[two, p1]) & (da[two, p1] == db[two, p0])
        out.set(two[swapped], "neighbouring digits swapped")
    dm = ((da[:, 0:2] == db[:, 2:4]).all(axis=1) & (da[:, 2:4] == db[:, 0:2]).all(axis=1)
          & (da[:, 4:] == db[:, 4:]).all(axis=1) & (k > 0))
    out.set(dm & out.is_("other"), "day and month swapped")
    ya = da[:, 4] * 1000 + da[:, 5] * 100 + da[:, 6] * 10 + da[:, 7]
    yb = db[:, 4] * 1000 + db[:, 5] * 100 + db[:, 6] * 10 + db[:, 7]
    yoff = (da[:, :4] == db[:, :4]).all(axis=1) & (np.abs(ya - yb) == 1)
    out.set(yoff & out.is_("other"), "year off by one")
    return out.done()


def _ndigits(v: np.ndarray) -> np.ndarray:
    """Decimal digits of non-negative integers (0 has one)."""
    n = np.ones(len(v), dtype=np.int64)
    x = v // 10
    while (x > 0).any():
        n += x > 0
        x //= 10
    return n


def _digit_dropped(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Whether one number is the other with one digit dropped, as the
    decimal strings would say: removing the digit at each position (from the
    right) of the longer number, for at most 19 positions, not per row."""
    out = np.zeros(len(x), dtype=bool)
    nonneg = (x >= 0) & (y >= 0)
    nx, ny = _ndigits(np.where(nonneg, x, 0)), _ndigits(np.where(nonneg, y, 0))
    cand = nonneg & (np.abs(nx - ny) == 1)
    longer = np.where(nx > ny, x, y)
    shorter = np.where(nx > ny, y, x)
    width = np.maximum(nx, ny)
    for k in range(int(width[cand].max()) if cand.any() else 0):
        p = 10 ** k
        dropped = (longer // (p * 10)) * p + longer % p
        out |= cand & (k < width) & (dropped == shorter)
    # A negative value keeps the string test ("-" is a character there).
    for j in np.nonzero(~nonneg & (x != y))[0]:
        a, b = str(x[j]), str(y[j])
        if abs(len(a) - len(b)) == 1:
            lg, sh = (a, b) if len(a) > len(b) else (b, a)
            out[j] = any(lg[:i] + lg[i + 1:] == sh for i in range(len(lg)))
    return out


def _levels_integer(a: pa.Array, b: pa.Array) -> Levels:
    missing = pc.or_(pc.is_null(a), pc.is_null(b)).to_numpy(zero_copy_only=False)
    va = pc.fill_null(pc.cast(a, pa.int64()), -1).to_numpy(zero_copy_only=False)
    vb = pc.fill_null(pc.cast(b, pa.int64()), -1).to_numpy(zero_copy_only=False)
    out = _Build(len(va), "other")
    hi = np.maximum(np.maximum(np.abs(va), np.abs(vb)), 1)
    rel = np.abs(va - vb) / hi
    out.set(rel <= 0.10, "within 10%")
    out.set(rel <= 0.01, "within 1%")
    out.set(va == vb, "equal")
    rest = np.nonzero(out.is_("other") & ~missing)[0]
    if len(rest):
        out.set(rest[_digit_dropped(va[rest], vb[rest])], "digit dropped or added")
    out.set(missing, MISSING)
    return out.done()


def _levels_municipality(a: pa.Array, b: pa.Array) -> Levels:
    missing = pc.or_(pc.is_null(a), pc.is_null(b)).to_numpy(zero_copy_only=False)
    eq = pc.fill_null(pc.equal(a, b), False).to_numpy(zero_copy_only=False)
    same = pc.fill_null(pc.equal(pc.utf8_slice_codeunits(a, 0, 2), pc.utf8_slice_codeunits(b, 0, 2)),
                        False).to_numpy(zero_copy_only=False)
    out = _Build(len(eq), "different state")
    out.set(same, "same state")
    out.set(eq, "equal")
    out.set(missing, MISSING)
    return out.done()


def _levels_municipality_given(a: pa.Array, b: pa.Array, place: pa.Array, side: str) -> Levels:
    """Residence against residence, knowing where one side's record was cared for.

    Two records agreeing on the hospital's own municipality is weak evidence
    where residence is often written as the place of care; agreeing elsewhere
    is strong; and a residence equal to the place of care on the side that
    carries it may be the hospital written in, so a true pair can disagree
    there. m and u of each level are learned, so the data decide how much each
    is worth (ADR-0115).
    """
    base = _levels_municipality(a, b)
    out = _Build(len(base.codes), base.names[0])
    out.put(np.arange(len(base.codes)), base)
    known = ~pc.is_null(place).to_numpy(zero_copy_only=False)
    at_a = pc.fill_null(pc.equal(a, place), False).to_numpy(zero_copy_only=False)
    at_b = pc.fill_null(pc.equal(b, place), False).to_numpy(zero_copy_only=False)
    at_own = at_b if side == "right" else at_a
    usable = known & ~out.is_(MISSING)
    eq = usable & out.is_("equal")
    out.set(eq & at_a, "equal, at the place of care")
    out.set(eq & ~at_a, "equal, elsewhere")
    out.set(usable & ~eq & at_own, f"{side} is the place of care")
    return out.done()


#: ICD-10's definitions (P07.0 "birth weight 999 g or less", P07.1 "1000-2499 g",
#: P07.2 "less than 28 completed weeks", P07.3 "28 completed weeks or more but
#: less than 37"); the codes, not a tuned band.
_ICD_SIZE = {
    "icd_birth_weight": (("P070", 0, 999), ("P071", 1000, 2499), 2500, "g"),
    "icd_gestation": (("P072", 0, 27), ("P073", 28, 36), 37, "weeks"),
}


def _levels_icd_size(kind: str, codes: pa.Array, measure: pa.Array) -> Levels:
    """An admission's diagnoses against a birth's weight or weeks (ADR-0117)."""
    (c1, lo1, hi1), (c2, lo2, hi2), low_below, unit = _ICD_SIZE[kind]
    text = pc.fill_null(codes, "")
    has1 = pc.match_substring(text, c1).to_numpy(zero_copy_only=False)
    has2 = pc.match_substring(text, c2).to_numpy(zero_copy_only=False)
    missing = pc.or_(pc.is_null(codes), pc.is_null(measure)).to_numpy(zero_copy_only=False)
    v = pc.fill_null(pc.cast(measure, pa.int64()), -1).to_numpy(zero_copy_only=False)
    out = _Build(len(v), f"no size code, {low_below} {unit} or more")
    out.set(v < low_below, f"no size code, under {low_below} {unit}")
    fits2 = (v >= lo2) & (v <= hi2)
    out.set(has2 & fits2, f"{c2}, fits")
    out.set(has2 & ~fits2, f"{c2}, does not fit")
    fits1 = (v >= lo1) & (v <= hi1)
    out.set(has1 & fits1, f"{c1}, fits")
    out.set(has1 & ~fits1, f"{c1}, does not fit")
    out.set(missing, MISSING)
    return out.done()


def _days(x: pa.Array) -> np.ndarray:
    return pc.fill_null(pc.cast(pc.cast(x, pa.date32()), pa.int32()), 0).to_numpy(zero_copy_only=False).astype(np.int64)


def _levels_interval(a: pa.Array, start: pa.Array, end: pa.Array) -> Levels:
    missing = pc.or_(pc.or_(pc.is_null(a), pc.is_null(start)), pc.is_null(end)).to_numpy(zero_copy_only=False)
    ia, s, e = _days(a), _days(start), _days(end)
    inside = (ia >= s) & (ia <= e)
    gap = np.where(ia < s, s - ia, ia - e)
    out = _Build(len(ia), "other")
    out.set(~inside & (gap <= 7), "within a week outside")
    out.set(~inside & (gap <= 1), "one day outside")
    off = ia - s
    out.set(inside, "inside, later")
    out.set(inside & (off == 1), "inside, second day")
    out.set(inside & (off == 0), "inside, first day")
    out.set(missing, MISSING)
    return out.done()


def _levels_exact(a: pa.Array, b: pa.Array) -> Levels:
    missing = pc.or_(pc.is_null(a), pc.is_null(b)).to_numpy(zero_copy_only=False)
    eq = pc.fill_null(pc.equal(a, b), False).to_numpy(zero_copy_only=False)
    out = _Build(len(eq), "different")
    out.set(eq, "equal")
    out.set(missing, MISSING)
    return out.done()


def _levels_number_distance(a: pa.Array, b: pa.Array) -> Levels:
    """How far apart two serial numbers are (an AIH and the one issued beside it)."""
    va = pc.cast(pc.if_else(pc.utf8_is_digit(pc.cast(a, pa.string())), pc.cast(a, pa.string()), None), pa.int64())
    vb = pc.cast(pc.if_else(pc.utf8_is_digit(pc.cast(b, pa.string())), pc.cast(b, pa.string()), None), pa.int64())
    missing = pc.or_(pc.is_null(va), pc.is_null(vb)).to_numpy(zero_copy_only=False)
    d = np.abs(pc.fill_null(va, 0).to_numpy(zero_copy_only=False) - pc.fill_null(vb, 0).to_numpy(zero_copy_only=False))
    out = _Build(len(d), "other")
    out.set(d <= 1000, "within 1000")
    out.set(d <= 100, "within 100")
    out.set(d <= 10, "within 10")
    out.set(d == 0, "equal")
    out.set(missing, MISSING)
    return out.done()


#: Bins of right minus left, in days, for ``order``: negative bins are the
#: right event before the left one.
_ORDER_BINS = ((-10**9, -366, "before by more than a year"), (-365, -29, "before by 29-365 days"),
               (-28, -8, "before by 8-28 days"), (-7, -1, "before by 1-7 days"), (0, 0, "same day"),
               (1, 7, "after by 1-7 days"), (8, 28, "after by 8-28 days"), (29, 365, "after by 29-365 days"),
               (366, 10**9, "after by more than a year"))


def _levels_order(a: pa.Array, b: pa.Array) -> Levels:
    """Where the right event falls relative to the left one, in day bins."""
    missing = pc.or_(pc.is_null(a), pc.is_null(b)).to_numpy(zero_copy_only=False)
    d = _days(b) - _days(a)
    out = _Build(len(d), "")
    for lo, hi, name in _ORDER_BINS:
        out.set((d >= lo) & (d <= hi), name)
    out.set(missing, MISSING)
    return out.done()


def _levels_joint(a: pa.Array, b: pa.Array) -> Levels:
    """The pair of values itself: one level per (left, right) combination."""
    sa, sb = pc.cast(a, pa.string()), pc.cast(b, pa.string())
    missing = pc.or_(pc.is_null(sa), pc.is_null(sb)).to_numpy(zero_copy_only=False)
    joined = pc.binary_join_element_wise(pc.fill_null(sa, ""), pc.fill_null(sb, ""), " / ")
    encoded = pc.dictionary_encode(joined).combine_chunks() if isinstance(joined, pa.ChunkedArray) \
        else pc.dictionary_encode(joined)
    out = _Build(len(missing), MISSING)
    codes = np.array([out.code(str(n)) for n in encoded.dictionary.to_pylist()], dtype=np.int16)
    out.codes = codes[encoded.indices.to_numpy(zero_copy_only=False)] if len(codes) else out.codes
    out.set(missing, MISSING)
    return out.done()


def levels(kind: str, a: pa.Array, b: pa.Array | tuple[pa.Array, pa.Array],
           given: pa.Array | None = None, given_side: str = "right") -> Levels:
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
    if kind == "number_distance":
        return _levels_number_distance(a, b)  # type: ignore[arg-type]
    if kind == "order":
        return _levels_order(a, b)  # type: ignore[arg-type]
    if kind == "joint":
        return _levels_joint(a, b)  # type: ignore[arg-type]
    return _levels_exact(a, b)  # type: ignore[arg-type]


__all__ = ["Levels", "levels"]
