"""Link discovery: which datasets share people, and through which fields, measured.

A link spec (``curation/links.yml``) asserts which event two datasets share and
which field on one side means which field on the other. Discovery measures that
instead of asserting it:

1. Every role of a comparable type (date, sex, facility, municipality,
   integer, label) on one side is paired with every role of the same type on
   the other.
2. A *key* is a combination of such pairings: one or two date pairings, with
   or without sex, one place pairing and one attribute pairing (an integer or
   a label: weight, weeks, age, delivery type). Integers compare exactly. Records are grouped by the key on each
   side. A left record *meets* the right side when its key value occurs
   there; a pair is *mutual* when the key value occurs exactly once on each
   side, so neither record has a look-alike (counting one side only inflates a
   key that a large left side shares with a few right records: every newborn of
   a city and day "meets" its one infant death).
3. The same count is repeated with every left date in the key shifted by
   +/-7 days (a week keeps the weekday). A true partner then disagrees, while
   coincidental agreement keeps its rate: the placebo count is what the key
   finds by chance.
4. Two measures, real minus placebo:
   - ``excess_mutual``: pairs a key isolates more often than chance allows
     (the key *identifies* shared people);
   - ``excess_right_meets``: right records whose key value occurs on the left
     side more often than chance (the datasets *share* people through these
     fields, even where look-alikes keep the key from telling them apart, as
     same-day births do for an infant death). Datasets that
   describe the same events through the right pairing show an excess that is a
   large share of the left side; a pairing that means nothing shows ~0.

Intervals. Where the right side has ``<entity>.start`` and ``<entity>.end``
dates (an admission), it also offers ``<entity>.day``: one row per day of the
interval (capped at ``MAX_INTERVAL_DAYS``), so a key can test "this date falls
inside that stay", not only equality with one end (a mother is often admitted
the day before she gives birth).

No record is filtered and no meaning is assumed: geography and period only
choose the publications read (CLAUDE.md §6). The counts are aggregates, so a
national year is a few group-bys per key, not a join of records.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import Any

import duckdb
import pyarrow as pa

from .roles import dataset_roles, role_table

COMPARABLE = ("date", "sex", "facility", "municipality", "integer", "label")
#: Types that join a key only as one optional attribute (birth weight, weeks,
#: the mother's age, delivery type): numerous pairings, most meaningless,
#: which the placebo sorts out.
ATTRIBUTE = ("integer", "label")
SHIFT_DAYS = 7
MAX_INTERVAL_DAYS = 60


@dataclass(frozen=True, slots=True)
class KeyResult:
    left: str
    right: str
    key: tuple[tuple[str, str], ...]
    left_records: int          # left records with every key field filled
    right_records: int         # right records with every key field filled
    real_any: int
    real_mutual: int
    placebo_any: float
    placebo_mutual: float
    real_right_meets: int = 0
    placebo_right_meets: float = 0.0

    @property
    def excess_mutual(self) -> float:
        return self.real_mutual - self.placebo_mutual

    def summary(self) -> dict[str, Any]:
        smaller = min(self.left_records, self.right_records)
        share = self.excess_mutual / smaller if smaller else 0.0
        ratio = self.real_mutual / self.placebo_mutual if self.placebo_mutual else None
        return {
            "key": " + ".join(f"{a}~{b}" for a, b in self.key),
            "left_records": self.left_records,
            "right_records": self.right_records,
            "real_mutual": self.real_mutual,
            "placebo_mutual": round(self.placebo_mutual, 1),
            "excess_mutual": round(self.excess_mutual, 1),
            "excess_share_of_smaller": round(share, 4),
            "real_over_placebo": round(ratio, 1) if ratio is not None else None,
            "real_any": self.real_any,
            "placebo_any": round(self.placebo_any, 1),
            "real_right_meets": self.real_right_meets,
            "placebo_right_meets": round(self.placebo_right_meets, 1),
            "excess_right_meets": round(self.real_right_meets - self.placebo_right_meets, 1),
            # excess in placebo standard deviations (Poisson): ranks sharing by
            # how unlikely it is by chance, not by size
            "z_right_meets": round((self.real_right_meets - self.placebo_right_meets)
                                   / (self.placebo_right_meets + 1) ** 0.5, 1),
        }


#: Properties never offered as identity evidence: a field under study is held
#: out of linking, so links are not selected for agreeing on it
#: (docs/plans/linkage-theory.md §5; race is measured across systems instead).
HELD_OUT = ("race",)


def _comparable(dataset: str) -> dict[str, str]:
    """Role -> type for the comparable roles, one role per source column."""
    seen: set[str] = set()
    out: dict[str, str] = {}
    for name, role in dataset_roles(dataset).roles.items():
        if name.rsplit(".", 1)[-1] in HELD_OUT:
            continue
        if role.type in COMPARABLE and role.column not in seen:
            seen.add(role.column)
            out[name] = role.type
    return out


def _pairings(left: dict[str, str], right: dict[str, str]) -> dict[str, list[tuple[str, str]]]:
    return {t: [(a, b) for a, ta in left.items() for b, tb in right.items() if ta == tb == t] for t in COMPARABLE}


def _keys(left: dict[str, str], right: dict[str, str]) -> list[tuple[tuple[str, str], ...]]:
    """Every key (exhaustive; ``discover_links(exhaustive=True)``)."""
    pairs = _pairings(left, right)
    dates = pairs["date"]
    date_sets = [(d,) for d in dates] + [
        (d1, d2) for d1, d2 in itertools.combinations(dates, 2) if d1[0] != d2[0] and d1[1] != d2[1]
    ]
    places: list[tuple[tuple[str, str], ...]] = [()] + [(p,) for p in pairs["facility"] + pairs["municipality"]]
    sexes: list[tuple[tuple[str, str], ...]] = [()] + [(s,) for s in pairs["sex"]]
    attrs: list[tuple[tuple[str, str], ...]] = [()] + [(x,) for t in ATTRIBUTE for x in pairs[t]]
    return [d + s + p + x for d in date_sets for s in sexes for p in places for x in attrs]


#: Staged search (default): how many date sets get sex and place added, and how
#: many of the resulting keys get one attribute.
TOP_DATE_SETS = 5
TOP_KEYS_FOR_ATTRIBUTES = 3


def _z(r: KeyResult) -> float:
    """How far beyond chance a key's records meet the other side (Poisson z)."""
    return (r.real_right_meets - r.placebo_right_meets) / (r.placebo_right_meets + 1) ** 0.5


def _shares(r: KeyResult) -> bool:
    """A key whose records meet the other side far beyond chance."""
    return _z(r) >= 5 or r.excess_mutual > 0


def _top(results: list[KeyResult], n: int) -> list[KeyResult]:
    """The n strongest by sharing (z) and the n strongest by isolation (excess
    mutual): a date set that shares people but cannot yet tell them apart
    (birth date against birth date, where same-day births collide) is the one
    an attribute completes, so ranking by isolation alone dropped it."""
    by_z = sorted(results, key=_z, reverse=True)[:n]
    by_mutual = sorted(results, key=lambda r: r.excess_mutual, reverse=True)[:n]
    return list({r.key: r for r in by_z + by_mutual}.values())


def _intervals(types: dict[str, str]) -> list[str]:
    """Entities with both a ``.start`` and an ``.end`` date role."""
    return [n[: -len(".start")] for n, t in types.items()
            if t == "date" and n.endswith(".start") and types.get(n[: -len(".start")] + ".end") == "date"]


def _count(con: duckdb.DuckDBPyConnection, key: tuple[tuple[str, str], ...], ltypes: dict[str, str],
           days: dict[str, str]) -> dict[int, tuple[int, int, int, int, int]]:
    """Counts for the real key and both placebo shifts, in one pass per side.

    The right side is grouped once (shifts move the left side only); the left
    side is projected under the three shifts and grouped in one query.
    """
    lcols = [a for a, _ in key]
    rcols = [b for _, b in key]
    ks = ", ".join(f"k{i}" for i in range(len(key)))
    on = " AND ".join(f"a.k{i} = b.k{i}" for i in range(len(key)))
    source = next((days[b] for b in rcols if b in days), "R")
    lnn = " AND ".join(f'"{a}" IS NOT NULL' for a in lcols)
    rnn = " AND ".join(f'"{b}" IS NOT NULL' for b in rcols)
    rsel = ", ".join(f'"{b}" AS k{i}' for i, b in enumerate(rcols))

    def lsel(shift: int) -> str:
        exprs = [f'("{a}" + INTERVAL ({shift}) DAY)::DATE' if ltypes[a] == "date" and shift else f'"{a}"'
                 for a in lcols]
        return f"SELECT {shift} AS s, " + ", ".join(f"{e} AS k{i}" for i, e in enumerate(exprs)) +             f" FROM L WHERE {lnn}"

    shifts = (0, SHIFT_DAYS, -SHIFT_DAYS)
    union = " UNION ALL ".join(lsel(sh) for sh in shifts)
    sql = f"""
        WITH b AS (SELECT {ks}, count(*) n FROM (SELECT {rsel} FROM {source} WHERE {rnn}) GROUP BY ALL),
             a AS (SELECT s, {ks}, count(*) n FROM ({union}) GROUP BY ALL),
             tot AS (SELECT s, sum(n) nl FROM a GROUP BY s),
             j AS (SELECT a.s, sum(a.n) any_, count(*) FILTER (WHERE a.n = 1 AND b.n = 1) mutual, sum(b.n) rmeets
                   FROM a JOIN b ON {on} GROUP BY a.s)
        SELECT tot.s, tot.nl, (SELECT coalesce(sum(n), 0) FROM b), coalesce(j.any_, 0), coalesce(j.mutual, 0),
               coalesce(j.rmeets, 0)
        FROM tot LEFT JOIN j USING (s)"""
    out = dict.fromkeys(shifts, (0, 0, 0, 0, 0))
    for sh, nl, nr, any_, mutual, rmeets in con.execute(sql).fetchall():
        out[int(sh)] = (int(nl), int(nr), int(any_), int(mutual), int(rmeets))
    return out


def discover_links(left: str, right: str, *, period: object, geography: object,
                   tables: dict[str, pa.Table] | None = None, exhaustive: bool = False,
                   **query_kwargs: Any) -> list[KeyResult]:
    """Measure comparable keys between two datasets; best keys first.

    The default search is staged: every single date pairing with sex and place;
    pairs of the dates that shared people in any of those forms, the
    TOP_DATE_SETS best of them with sex and place; one attribute added to the
    TOP_KEYS_FOR_ATTRIBUTES best keys by sharing and by isolation. ``exhaustive=True``
    measures every combination (SIH ~ CIHA: over 4.5 h unfinished, 2026-10-02).

    ``tables`` may carry already-loaded role tables (dataset -> table) so a
    sweep over several pairs reads each dataset once.
    """
    lt, rt = _comparable(left), _comparable(right)
    tables = tables if tables is not None else {}
    for ds, roles in ((left, lt), (right, rt)):
        if ds not in tables:
            tables[ds] = role_table(ds, period=period, geography=geography, roles=list(roles), **query_kwargs)
    con = duckdb.connect()
    con.register("L", tables[left].select(list(lt)))
    con.register("R", tables[right].select(list(rt)))
    days: dict[str, str] = {}
    for i, entity in enumerate(_intervals(rt)):
        day, view = f"{entity}.day", f"RX{i}"
        con.execute(f"""CREATE TEMP TABLE {view} AS SELECT R.*, d::DATE AS "{day}" FROM R,
            unnest(generate_series("{entity}.start"::TIMESTAMP,
                   least("{entity}.end", ("{entity}.start" + INTERVAL {MAX_INTERVAL_DAYS} DAY)::DATE)::TIMESTAMP,
                   INTERVAL 1 DAY)) t(d)
            WHERE "{entity}.start" IS NOT NULL AND "{entity}.end" >= "{entity}.start"
            """)
        days[day] = view
        rt = {**rt, day: "date"}
    measured: dict[tuple[tuple[str, str], ...], KeyResult] = {}

    def measure(keys: list[tuple[tuple[str, str], ...]]) -> list[KeyResult]:
        out = []
        for key in keys:
            if key in measured:
                out.append(measured[key])
                continue
            c = _count(con, key, lt, days)
            nl, nr, real_any, real_mutual, real_rm = c[0]
            p_plus, p_minus = c[SHIFT_DAYS], c[-SHIFT_DAYS]
            res = KeyResult(left, right, key, nl, nr, real_any, real_mutual,
                            (p_plus[2] + p_minus[2]) / 2, (p_plus[3] + p_minus[3]) / 2,
                            real_rm, (p_plus[4] + p_minus[4]) / 2)
            measured[key] = res
            out.append(res)
        return out

    if exhaustive:
        measure(_keys(lt, rt))
    else:
        pairs = _pairings(lt, rt)
        places = [()] + [(p,) for p in pairs["facility"] + pairs["municipality"]]
        sexes = [()] + [(x,) for x in pairs["sex"]]
        # Every single date pairing with sex and place: a date alone can share
        # people invisibly (every 2022 birth "meets" some death) until a place
        # is added, so nothing is cut before this stage.
        first = measure([(d,) + s_ + p_ for d in pairs["date"] for s_ in sexes for p_ in places])
        live = sorted({r.key[0] for r in first if _shares(r)})
        doubles = [(d1, d2) for d1, d2 in itertools.combinations(live, 2) if d1[0] != d2[0] and d1[1] != d2[1]]
        double_sets = _top([r for r in measure(doubles) if _shares(r)], TOP_DATE_SETS)
        measure([r.key + s_ + p_ for r in double_sets for s_ in sexes for p_ in places])
        best = _top([r for r in measured.values() if _shares(r)], TOP_KEYS_FOR_ATTRIBUTES)
        attrs = [(x,) for t in ATTRIBUTE for x in pairs[t]]
        measure([r.key + a_ for r in best for a_ in attrs])
    results = sorted(measured.values(), key=lambda r: r.excess_mutual, reverse=True)
    return results
