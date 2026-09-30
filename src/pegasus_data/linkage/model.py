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
- municipality: equal · same state · different state; conditioned on the place
  of care (``given``, EVALUATION 2026-09-30, residence given the place of care):
  equal, at the place of care · equal, elsewhere · right is the place of care ·
  same state · different state
- integer (grams, weeks, years): equal · within 1% · within 10% · a digit
  dropped or added · other
- interval (a date against start..end): inside on the first day · on the
  second day · later · one day outside · within a week outside · other
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

MISSING = "missing"
_PAD = {"7": "84", "8": "795", "9": "86", "4": "751", "5": "8462", "6": "953", "1": "42", "2": "5130", "3": "62", "0": "2"}


@dataclass(frozen=True, slots=True)
class Comparison:
    left: str
    right: str          # a role, or "start..end" for an interval
    kind: str
    given: str | None = None   # a right-side role the levels are conditioned on

    @property
    def name(self) -> str:
        return f"{self.left} ~ {self.right}" + (f" | {self.given}" if self.given else "")

    @property
    def right_roles(self) -> tuple[str, ...]:
        roles = tuple(self.right.split("..")) if self.kind == "interval" else (self.right,)
        return roles + ((self.given,) if self.given else ())


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


__all__ = ["MISSING", "Comparison", "FieldModel", "threshold_for"]
