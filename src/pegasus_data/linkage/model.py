"""Probabilistic linkage with learned evidence (ADR-0107, ADR-0111).

The deterministic engine (``engine.py``) accepts a pair when a whole key
agrees exactly. This module weighs every comparison instead, in bits:

    evidence(f) = log2( P(level of f | same person) / P(level of f | different people) )

where a *level* is how two values compare, by the role's type (a birth date
equal, one digit off on an adjacent key, day and month swapped, …). The score of
a pair is the sum of its fields' evidence.

Nothing here is tuned by hand for a particular link:

* **m, the error channel of a field**, is learned from *leave-one-field-out
  anchors*: pairs linked by a key that does not contain the field, chosen from
  the spec's deterministic passes whose negative control is under 1%. Among
  those pairs, how the field compares IS how that field behaves for the same
  person, measured without assuming it.
* **u, how a field compares by coincidence**, is learned from the negative
  control: the same candidate generation with the left birth date shifted, so
  every candidate is a different person.
* **The threshold** is where the estimated false-match rate (control scores
  above it, over real scores above it) stays under the target.
* **Candidates** come from intrinsic keys and their typo variants (``blocks``),
  never from geography.

Levels by type (``compare``), each with a "missing" level that contributes
nothing:

- date: equal · one digit, adjacent key · one digit, other key · neighbouring
  digits swapped · day and month swapped · year off by one · other
- sex, code, label, facility: equal · different
- municipality: equal · same state · different state
- integer (grams, weeks, years): equal · within 1% · within 10% · a digit
  dropped or added · other
- interval (a date against start..end): inside on the first day · on the
  second day · later · one day outside · within a week outside · other
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import duckdb
import pyarrow as pa

MISSING = "missing"
_PAD = {"7": "84", "8": "795", "9": "86", "4": "751", "5": "8462", "6": "953", "1": "42", "2": "5130", "3": "62", "0": "2"}


def _adjacent(x: str, y: str) -> bool:
    return y in _PAD.get(x, "") or (x.isdigit() and y.isdigit() and abs(int(x) - int(y)) == 1)


def compare_date(a: Any, b: Any) -> str:
    if a is None or b is None:
        return MISSING
    sa, sb = a.strftime("%d%m%Y"), b.strftime("%d%m%Y")
    if sa == sb:
        return "equal"
    diff = [i for i in range(8) if sa[i] != sb[i]]
    if len(diff) == 1:
        return "one digit, adjacent key" if _adjacent(sa[diff[0]], sb[diff[0]]) else "one digit, other key"
    if len(diff) == 2 and diff[1] == diff[0] + 1 and sa[diff[0]] == sb[diff[1]] and sa[diff[1]] == sb[diff[0]]:
        return "neighbouring digits swapped"
    if sa[:2] == sb[2:4] and sa[2:4] == sb[:2] and sa[4:] == sb[4:]:
        return "day and month swapped"
    if sa[:4] == sb[:4] and abs(int(sa[4:]) - int(sb[4:])) == 1:
        return "year off by one"
    return "other"


def compare_integer(a: Any, b: Any) -> str:
    if a is None or b is None:
        return MISSING
    if a == b:
        return "equal"
    hi = max(abs(a), abs(b)) or 1
    rel = abs(a - b) / hi
    if rel <= 0.01:
        return "within 1%"
    if rel <= 0.10:
        return "within 10%"
    sa, sb = str(a), str(b)
    if abs(len(sa) - len(sb)) == 1:
        longer, shorter = (sa, sb) if len(sa) > len(sb) else (sb, sa)
        if any(longer[:i] + longer[i + 1:] == shorter for i in range(len(longer))):
            return "digit dropped or added"
    return "other"


def compare_municipality(a: Any, b: Any) -> str:
    if a is None or b is None:
        return MISSING
    if a == b:
        return "equal"
    return "same state" if str(a)[:2] == str(b)[:2] else "different state"


def compare_interval(a: Any, b: Any) -> str:
    """A date against an interval (start, end): the birth day inside the admission."""
    if a is None or b is None or b[0] is None or b[1] is None:
        return MISSING
    start, end = b
    if start <= a <= end:
        # Where in the stay: a delivery admission usually starts on the birth
        # day or the day before, while a coincidental stay is uniform.
        offset = (a - start).days
        return "inside, first day" if offset == 0 else "inside, second day" if offset == 1 else "inside, later"
    gap = (start - a).days if a < start else (a - end).days
    if gap <= 1:
        return "one day outside"
    if gap <= 7:
        return "within a week outside"
    return "other"


def compare_exact(a: Any, b: Any) -> str:
    if a is None or b is None:
        return MISSING
    return "equal" if a == b else "different"


COMPARATORS = {
    "date": compare_date,
    "integer": compare_integer,
    "municipality": compare_municipality,
    "interval": compare_interval,
}


def comparator(kind: str):
    return COMPARATORS.get(kind, compare_exact)


@dataclass(frozen=True, slots=True)
class Comparison:
    left: str
    right: str          # a role, or "start..end" for an interval
    kind: str

    @property
    def name(self) -> str:
        return f"{self.left} ~ {self.right}"

    @property
    def right_roles(self) -> tuple[str, ...]:
        return tuple(self.right.split("..")) if self.kind == "interval" else (self.right,)


@dataclass
class FieldModel:
    """m and u per level, and the resulting evidence in bits."""

    comparison: Comparison
    m: dict[str, float] = field(default_factory=dict)
    u: dict[str, float] = field(default_factory=dict)
    anchors: int = 0
    controls: int = 0

    def bits(self, level: str) -> float:
        if level == MISSING:
            return 0.0
        m = self.m.get(level, 0.0)
        u = self.u.get(level, 0.0)
        # Laplace-style floors: a level never seen among anchors (or controls)
        # is rare, not impossible; the floor is half an observation.
        m = max(m, 0.5 / max(self.anchors, 1))
        u = max(u, 0.5 / max(self.controls, 1))
        return math.log2(m / u)

    def as_dict(self) -> dict[str, Any]:
        levels = sorted(set(self.m) | set(self.u))
        return {"comparison": self.comparison.name, "anchors": self.anchors, "controls": self.controls,
                "levels": {lv: {"m": round(self.m.get(lv, 0.0), 5), "u": round(self.u.get(lv, 0.0), 6),
                                "bits": round(self.bits(lv), 2)} for lv in levels}}


def level_distribution(pairs: list[tuple[Any, Any]], cmp) -> tuple[dict[str, float], int]:
    counts: dict[str, int] = {}
    usable = 0
    for a, b in pairs:
        lv = cmp(a, b)
        if lv == MISSING:
            continue
        usable += 1
        counts[lv] = counts.get(lv, 0) + 1
    return ({k: v / usable for k, v in counts.items()} if usable else {}), usable


def fetch_pairs(con: duckdb.DuckDBPyConnection, pairs_sql: str, comp: Comparison) -> list[tuple[Any, Any]]:
    """Values of one comparison for the pairs a query returns (columns l, r)."""
    return con.execute(f"""
        SELECT l."{comp.left}", r."{comp.right}"
        FROM ({pairs_sql}) p
        JOIN (SELECT DISTINCT ON (_id) * FROM L) l ON l._id = p.l
        JOIN (SELECT DISTINCT ON (_id) * FROM R) r ON r._id = p.r""").fetchall()


def score(models: list[FieldModel], left_row: dict[str, Any], right_row: dict[str, Any]) -> tuple[float, dict[str, str]]:
    total = 0.0
    levels: dict[str, str] = {}
    for fm in models:
        c = fm.comparison
        lv = comparator(c.kind)(left_row.get(c.left), right_row.get(c.right))
        levels[c.name] = lv
        total += fm.bits(lv)
    return total, levels


def threshold_for(real: list[float], control: list[float], target: float) -> tuple[float | None, float | None]:
    """The lowest score at which the estimated false-match rate is at most `target`.

    Estimated FDR(t) = #control scores >= t / #real scores >= t. The whole
    range is scanned: the ratio is not monotone (a single coincidence at the
    top reads 100% until enough real pairs join it), so stopping at the first
    excess refused every threshold on RR 2022.
    """
    if not real:
        return None, None
    real_sorted = sorted(real, reverse=True)
    control_sorted = sorted(control, reverse=True)
    best_t, best_fdr = None, None
    j = 0
    for i, t in enumerate(real_sorted, start=1):
        while j < len(control_sorted) and control_sorted[j] >= t:
            j += 1
        fdr = j / i
        if fdr <= target:
            best_t, best_fdr = t, fdr
    return best_t, best_fdr


def as_table(rows: list[dict[str, Any]]) -> pa.Table:
    return pa.Table.from_pylist(rows) if rows else pa.table({"l": pa.array([], pa.string()),
                                                             "r": pa.array([], pa.string()),
                                                             "bits": pa.array([], pa.float64())})


__all__ = ["Comparison", "FieldModel", "compare_date", "compare_integer", "compare_municipality",
           "comparator", "level_distribution", "score", "threshold_for"]
