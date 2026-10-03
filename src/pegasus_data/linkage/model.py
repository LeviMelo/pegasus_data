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
  of care carried by one side (``given``, ADR-0115): equal, at the place of
  care · equal, elsewhere · <that side> is the place of care · same state ·
  different state
- integer (grams, weeks, years): equal · within 1% · within 10% · a digit
  dropped or added · other
- icd_birth_weight, icd_gestation (an admission's diagnoses against a birth's
  weight or weeks, by ICD-10's own definitions of P07.0-P07.3; ADR-0117): the
  code present and the measure inside it · present and outside · absent and the
  measure low · absent and not low
- interval (a date against start..end): inside on the first day · on the
  second day · later · one day outside · within a week outside · other
- number_distance (two serial numbers, such as AIHs a hospital issues in
  sequence): equal · within 10 · within 100 · within 1000 · other
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

MISSING = "missing"
#: A code list against a measurement: evidence, never a join key (ADR-0117).
ICD_SIZE_KINDS = ("icd_birth_weight", "icd_gestation")
#: Kinds that weigh evidence but cannot join records (anchors, blocks).
#: ``order`` (the signed days from one event to another) and ``joint`` (the
#: pair of categories, a confusion channel) carry impossibility as evidence:
#: a death before the admission began, a death at home after a stay that ended
#: in death, get the bits the anchors measured, never a hard veto (theory §2.2).
EVIDENCE_ONLY_KINDS = (*ICD_SIZE_KINDS, "number_distance", "order", "joint")
_PAD = {"7": "84", "8": "795", "9": "86", "4": "751", "5": "8462", "6": "953", "1": "42", "2": "5130", "3": "62", "0": "2"}


@dataclass(frozen=True, slots=True)
class Comparison:
    left: str
    right: str          # a role, or "start..end" for an interval
    kind: str
    given: str | None = None   # a role the levels are conditioned on (the place of care)
    given_side: str = "right"  # the record that carries it: "left" or "right"

    @property
    def name(self) -> str:
        return f"{self.left} ~ {self.right}" + (f" | {self.given_side}.{self.given}" if self.given else "")

    @property
    def is_key(self) -> bool:
        """Whether equality on it can join records (anchors, blocks)."""
        return self.kind not in EVIDENCE_ONLY_KINDS

    @property
    def right_roles(self) -> tuple[str, ...]:
        return tuple(self.right.split("..")) if self.kind == "interval" else (self.right,)

    def side_roles(self, side: str) -> tuple[str, ...]:
        """Every role this comparison reads from one side."""
        own = (self.left,) if side == "left" else self.right_roles
        return own + ((self.given,) if self.given and self.given_side == side else ())


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
        seen = m > 0.0
        # Laplace-style floors: a level never seen among anchors (or controls)
        # is rare, not impossible; the floor is half an observation.
        m = max(m, 0.5 / max(self.anchors, 1))
        u = max(u, 0.5 / max(self.controls, 1))
        bits = math.log2(m / u)
        # A level no anchor showed cannot count FOR a match: its floor exceeded
        # a rarer u and scored "P07.2, does not fit" +2.04 bits (ADR-0117).
        return bits if seen else min(bits, 0.0)

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


__all__ = ["ICD_SIZE_KINDS", "MISSING", "Comparison", "FieldModel", "threshold_for"]
