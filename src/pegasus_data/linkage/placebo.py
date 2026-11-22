"""The placebo: one definition of a negative control for both engines (ADR-0186).

A link pairs records that agree on a key, and some agree by chance. The control counts them: it moves the left key that
carries the person's identity (a birth date, a death day) to a value the same person cannot hold, repeats the join, and
every pair it still finds is a coincidence. The count estimates the false pairs among the real ones only if two things
hold, and both are decided here, once, for the deterministic passes and the probabilistic blocks alike:

1. **The moved value stays where both sides hold values** (`shared_range`, `rotation`). A date moved by a fixed number
   of days leaves the partner side's period for the records near its end, and out of it meets no partner whatever the
   chance of a coincidence is: a flat +400 days left 2.1-3.1% of the neonatal admissions a partner-side birth on the
   shifted day (+7 days: 99.8%), so the date blocks had no placebo and the false-match rate read 1% by construction
   (2026-10-14). The displacement goes round the range (`lo + (v - lo + k) mod span`), by whole weeks for a date: the
   weekday is kept. The range is the partner's AND the left side's: national SIH 2022 holds admissions from 2008 (11.7
   of 12.5 million in 2022), so a 2022 birth turned half a year round 2008-2022 left the year for 2008, where nothing is,
   and the delivery link's placebo found half its coincidences (2026-11-09, OQ 97).
2. **The control must reach** what the real keys reach (`key_reach`, `block_report`): a placebo that finds a partner
   value for far fewer records than the real value does, or too few coincidences for a block, measured no chance at all,
   and its zero reads as "no false pairs". Such a run is not viable (`engine.judge`).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
from typing import Any

import duckdb

from .identity import quote


def _declared(key: str) -> float:
    """A placebo threshold from ``links.yml`` (``thresholds.placebo``): the displacement `days` of the probabilistic
    placebo, the least share of the real key's reach the moved key keeps (`key_reach`), the share of a block's
    coincidences its placebo must hold (`block_reach`) and the count below which a block is not judged
    (`block_min_expected`). Each is declared there with its evidence."""
    from ..semantics.curation import declared

    return declared("links.yml", "thresholds", "placebo", key)


def placebo_days() -> int:
    """The probabilistic placebo's displacement in days (``thresholds.placebo.days``, ADR-0186)."""
    return int(_declared("days"))



def partner_range(con: duckdb.DuckDBPyConnection, roles: Iterable[str], view: str = "R") -> tuple[Any, Any] | None:
    """First and last value of ``roles`` in ``view`` (the partner side; an interval's start and end both), or None when
    they hold no value."""
    union = " UNION ALL ".join(f"SELECT {quote(c)} AS v FROM {view}" for c in roles)
    lo, hi = con.execute(f"SELECT min(v), max(v) FROM ({union})").fetchone() or (None, None)
    return None if lo is None else (lo, hi)


def shared_range(con: duckdb.DuckDBPyConnection, left_roles: Iterable[str], right_roles: Iterable[str],
                 left: str = "L", right: str = "R") -> tuple[Any, Any] | None:
    """The range a moved value must stay inside: the overlap of the left values' range and the partner's (each from
    `partner_range`), so a moved value lands where the partner holds values as densely as the real one did. None when
    either side holds none or they do not overlap."""
    ours, theirs = partner_range(con, left_roles, left), partner_range(con, right_roles, right)
    if ours is None or theirs is None:
        return None
    lo, hi = max(ours[0], theirs[0]), min(ours[1], theirs[1])
    return (lo, hi) if lo <= hi else None


def _rotation_steps(within: tuple[Any, Any] | None, wanted: int) -> tuple[int, int] | None:
    """``(span, k)`` of `rotation`: the range's length and the step round it, or None when it cannot move."""
    if within is None:
        return None
    lo, hi = within
    calendar = isinstance(lo, date)
    span = (hi - lo).days + 1 if calendar else int(hi) - int(lo) + 1
    k = min(abs(wanted), span // 2)
    if calendar and k >= 7:
        k -= k % 7
    if k < 1:
        return None
    if wanted < 0:
        k = span - k
    return span, k


def rotation_inverse(expr: str, within: tuple[Any, Any] | None, wanted: int) -> str | None:
    """SQL for the value that `rotation` moves onto ``expr`` (a SQL expression): the rotation is a bijection of the range
    and the identity outside it, so its inverse turns the other way round by the same step. Lets a windowed join test
    whether a partner's value is a moved day of a record's window without listing the window day by day."""
    steps = _rotation_steps(within, wanted)
    if steps is None:
        return None
    span, k = steps
    lo, hi = within  # type: ignore[misc]
    back = span - k
    if isinstance(lo, date):
        a, b = f"DATE '{lo.isoformat()}'", f"DATE '{hi.isoformat()}'"
        moved = f"{a} + CAST(({expr} - {a} + {back}) % {span} AS INTEGER)"
    else:
        a, b = str(int(lo)), str(int(hi))
        moved = f"{a} + ({expr} - {a} + {back}) % {span}"
    return f"CASE WHEN {expr} BETWEEN {a} AND {b} THEN {moved} ELSE {expr} END"


def rotation(role: str, within: tuple[Any, Any] | None, wanted: int) -> str | None:
    """SQL for ``role`` moved by ``wanted`` round the range ``within`` (days for a date, units for an integer): a value
    inside the range goes to ``lo + (v - lo + k) mod span``, one outside it stays (it meets no partner either way).
    ``k`` is ``wanted`` or, when the range is shorter than twice that, half of it; a date's is a whole number of weeks.
    A negative ``wanted`` moves the other way round. None when the range has no value or is too short to move inside."""
    steps = _rotation_steps(within, wanted)
    if steps is None:
        return None
    span, k = steps
    lo, hi = within  # type: ignore[misc]
    calendar = isinstance(lo, date)
    q = quote(role)
    if calendar:
        a, b = f"DATE '{lo.isoformat()}'", f"DATE '{hi.isoformat()}'"
        moved = f"{a} + CAST(({q} - {a} + {k}) % {span} AS INTEGER)"
    else:
        a, b = str(int(lo)), str(int(hi))
        moved = f"{a} + ({q} - {a} + {k}) % {span}"
    return f"CASE WHEN {q} BETWEEN {a} AND {b} THEN {moved} ELSE {q} END"


def moved_sql(source: str, moves: dict[str, str]) -> str:
    """``source`` with each role in ``moves`` replaced by its moved value (`rotation`)."""
    if not moves:
        return f"SELECT * FROM {source}"
    return f"SELECT * REPLACE ({', '.join(f'{sql} AS {quote(role)}' for role, sql in moves.items())}) FROM {source}"


def key_reach(con: duckdb.DuckDBPyConnection, left: str, right: str, moved: str, view: str = "L",
              right_view: str = "R") -> dict[str, float | int]:
    """Whether the control can find a partner at all, for the key pairing ``left`` with ``right``: the share of left
    records whose own value is among the partner's values (what a real pair needs) and whose moved value (``moved``,
    SQL) is (what a control pair needs). The second should be close to the first."""
    n, real, shifted = con.execute(f"""
        WITH rv AS (SELECT DISTINCT {quote(right)} AS v FROM {right_view} WHERE {quote(right)} IS NOT NULL),
             a AS (SELECT DISTINCT _id, {quote(left)} AS v, {moved} AS s FROM {view} WHERE {quote(left)} IS NOT NULL)
        SELECT count(*), count(r1.v), count(r2.v) FROM a LEFT JOIN rv r1 ON r1.v = a.v
                                                        LEFT JOIN rv r2 ON r2.v = a.s""").fetchone() or (0, 0, 0)
    return {"records": int(n), "real_reach": round(real / n, 4) if n else 0.0,
            "control_reach": round(shifted / n, 4) if n else 0.0}


def key_failures(reach: dict[str, dict[str, float | int]]) -> list[str]:
    return [f"the control cannot reach {key}: its shifted key finds a partner value for {v['control_reach']:.1%} of "
            f"the left records against {v['real_reach']:.1%} for the real key"
            for key, v in reach.items() if v["real_reach"] and v["control_reach"] < _declared("key_reach") * v["real_reach"]]


def block_report(blocks: Any, real: list[tuple[int, int]], control: list[tuple[int, int]]
                 ) -> tuple[list[dict[str, Any]], list[str]]:
    """Per candidate block, whether the placebo reaches it, and the failures in words. A left record has at most one
    true partner, so of a block's real candidates at least ``candidates - left records`` are coincidences, and the
    placebo (which holds only coincidences) must hold about as many. Fewer than the declared `block_reach` of them: it does not reach
    the block, and the threshold chosen against it would let through the false pairs the block creates."""
    block_reach = _declared("block_reach")
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for block, (cand, left), (ctl, _l) in zip(blocks, real, control, strict=True):
        expected = max(cand - left, 0)
        reaches = expected < _declared("block_min_expected") or ctl >= block_reach * expected
        label = " + ".join(f"{a}~{b}" for a, b in block)
        rows.append({"block": label, "candidates": cand, "left_records": left, "control_candidates": ctl,
                     "coincidences_at_least": expected, "reaches": reaches})
        if not reaches:
            failures.append(f"the placebo does not reach block [{label}]: {ctl:,} control candidates against at least "
                            f"{expected:,} coincidences among {cand:,} real candidates")
    if sum(r["candidates"] for r in rows) and not sum(r["control_candidates"] for r in rows):
        failures.append("the placebo generated no candidate pair")
    return rows, failures


__all__ = ["block_report", "key_failures", "key_reach", "placebo_days",
           "shared_range",
           "moved_sql", "partner_range", "rotation"]
