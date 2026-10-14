"""The placebo: one definition of a negative control for both engines (ADR-0186).

A link pairs records that agree on a key, and some agree by chance. The control counts them: it moves the left key that
carries the person's identity (a birth date, a death day) to a value the same person cannot hold, repeats the join, and
every pair it still finds is a coincidence. The count estimates the false pairs among the real ones only if two things
hold, and both are decided here, once, for the deterministic passes and the probabilistic blocks alike:

1. **The moved value stays inside the partner's own range** (`rotation`). A date moved by a fixed number of days leaves
   the partner side's period for the records near its end, and out of it meets no partner whatever the chance of a
   coincidence is: a flat +400 days left 2.1-3.1% of the neonatal admissions a partner-side birth on the shifted day
   (+7 days: 99.8%), so the date blocks had no placebo and the false-match rate read 1% by construction (2026-10-14).
   The displacement goes round the range (`lo + (v - lo + k) mod span`), by whole weeks for a date: the weekday is kept.
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

#: The probabilistic placebo's displacement in days: half a year (26 weeks), so the day and month change (a year would
#: hand back the same day-month and earn typo credit) and the weekday does not. A deterministic pass moves its control
#: key by the spec's `shift_days` (a week): it joins on equality, so no typo level can be earned, and measured on five
#: links a week counts as many chance pairs as half a year in the passes that count many and more in the strong
#: ones (ADR-0186).
PLACEBO_DAYS = 182
#: The least share of the real key's reach the moved key must keep (`key_reach`)
KEY_REACH = 0.5
#: A block's placebo must produce at least this share of its real candidates' coincidences. The coincidences are at
#: least `candidates - left records` (a left record has at most one true partner), whatever the true-link rate is;
#: a faithful placebo has about that many, half is the slack for the season and weekday mix a rotation changes.
BLOCK_REACH = 0.5
#: ... and is judged only when the coincidences expected are at least this many (below it a Poisson count falls short
#: of half by chance)
BLOCK_MIN_EXPECTED = 30


def partner_range(con: duckdb.DuckDBPyConnection, roles: Iterable[str], view: str = "R") -> tuple[Any, Any] | None:
    """First and last value of ``roles`` in ``view`` (the partner side; an interval's start and end both), or None when
    they hold no value."""
    union = " UNION ALL ".join(f"SELECT {quote(c)} AS v FROM {view}" for c in roles)
    lo, hi = con.execute(f"SELECT min(v), max(v) FROM ({union})").fetchone() or (None, None)
    return None if lo is None else (lo, hi)


def rotation(role: str, within: tuple[Any, Any] | None, wanted: int) -> str | None:
    """SQL for ``role`` moved by ``wanted`` round the range ``within`` (days for a date, units for an integer): a value
    inside the range goes to ``lo + (v - lo + k) mod span``, one outside it stays (it meets no partner either way).
    ``k`` is ``wanted`` or, when the range is shorter than twice that, half of it; a date's is a whole number of weeks.
    A negative ``wanted`` moves the other way round. None when the range has no value or is too short to move inside."""
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


def key_reach(con: duckdb.DuckDBPyConnection, left: str, right: str, moved: str) -> dict[str, float | int]:
    """Whether the control can find a partner at all, for the key pairing ``left`` with ``right``: the share of left
    records whose own value is among the partner's values (what a real pair needs) and whose moved value (``moved``,
    SQL) is (what a control pair needs). The second should be close to the first."""
    n, real, shifted = con.execute(f"""
        WITH rv AS (SELECT DISTINCT {quote(right)} AS v FROM R WHERE {quote(right)} IS NOT NULL),
             a AS (SELECT DISTINCT _id, {quote(left)} AS v, {moved} AS s FROM L WHERE {quote(left)} IS NOT NULL)
        SELECT count(*), count(r1.v), count(r2.v) FROM a LEFT JOIN rv r1 ON r1.v = a.v
                                                        LEFT JOIN rv r2 ON r2.v = a.s""").fetchone() or (0, 0, 0)
    return {"records": int(n), "real_reach": round(real / n, 4) if n else 0.0,
            "control_reach": round(shifted / n, 4) if n else 0.0}


def key_failures(reach: dict[str, dict[str, float | int]]) -> list[str]:
    return [f"the control cannot reach {key}: its shifted key finds a partner value for {v['control_reach']:.1%} of "
            f"the left records against {v['real_reach']:.1%} for the real key"
            for key, v in reach.items() if v["real_reach"] and v["control_reach"] < KEY_REACH * v["real_reach"]]


def block_report(blocks: Any, real: list[tuple[int, int]], control: list[tuple[int, int]]
                 ) -> tuple[list[dict[str, Any]], list[str]]:
    """Per candidate block, whether the placebo reaches it, and the failures in words. A left record has at most one
    true partner, so of a block's real candidates at least ``candidates - left records`` are coincidences, and the
    placebo (which holds only coincidences) must hold about as many. Fewer than `BLOCK_REACH` of them: it does not reach
    the block, and the threshold chosen against it would let through the false pairs the block creates."""
    rows: list[dict[str, Any]] = []
    failures: list[str] = []
    for block, (cand, left), (ctl, _l) in zip(blocks, real, control, strict=True):
        expected = max(cand - left, 0)
        reaches = expected < BLOCK_MIN_EXPECTED or ctl >= BLOCK_REACH * expected
        label = " + ".join(f"{a}~{b}" for a, b in block)
        rows.append({"block": label, "candidates": cand, "left_records": left, "control_candidates": ctl,
                     "coincidences_at_least": expected, "reaches": reaches})
        if not reaches:
            failures.append(f"the placebo does not reach block [{label}]: {ctl:,} control candidates against at least "
                            f"{expected:,} coincidences among {cand:,} real candidates")
    if sum(r["candidates"] for r in rows) and not sum(r["control_candidates"] for r in rows):
        failures.append("the placebo generated no candidate pair")
    return rows, failures


__all__ = ["BLOCK_MIN_EXPECTED", "BLOCK_REACH", "KEY_REACH", "PLACEBO_DAYS", "block_report", "key_failures", "key_reach",
           "moved_sql", "partner_range", "rotation"]
