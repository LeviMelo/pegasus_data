"""Deterministic linkage with negative controls (ADR-0107, ADR-0110).

A link spec (``curation/links.yml``) names two sides (a dataset and a filter
over its roles), a cascade of passes (keys pairing a left role with a right
role, strictest first), the key shifted by the negative control, and held-out
validations. For each pass:

1. **Join 1:1.** Only records whose key combination is unique on their own
   side take part: a combination shared by two records is ambiguous and
   dropped, never resolved by guessing.
2. **Only what is left.** A pass sees only the records earlier passes left
   unlinked, on both sides.
3. **Negative control.** The same join over the same remaining records, with
   one left key shifted (a birth date by 7 days): nobody is the same person as
   someone born a week later, so every control pair is a coincidence, and
   their count estimates the chance pairs in the real pass. Running the
   control over the *same* remaining records matters: re-running the cascade
   for the control starves later passes and overstates them (omnisus's first
   draft, EVALUATION 2026-09-30).
4. **Dropped passes.** A pass whose control finds 20% or more of its pairs, or
   as many pairs as itself, is dropped with its pairs.

Then held-out validations and the verdict fixed before any result: *viable* when every kept pass is at most 5%
chance and the strongest held-out validation agrees in at least 90% of pairs; *use with caution* at 20% and 75%;
*not viable* otherwise. A validation is held out only if no role it reads is a pass key, a compared field, a block or
a side's filter: those agree by construction (the neonatal link's "born in the admitting hospital" was a key and
agreed 99.6-100%, and carried "viable" over a held-out 81-87%). A validation compares at least `MIN_COMPARED` pairs, or
it is not evidence. A control that cannot reach its partner's values (a date moved out of the partner's period) is no
control, and the run is not viable: an empty placebo reads as "no false pairs".
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa

from ..semantics.curation import read_yaml
from .identity import DUP_SQL, RECORD_ID_SQL, connect
from .roles import dataset_roles, role_table, unusable_roles


def links_file() -> Path:
    from ..config import curation_root

    return curation_root() / "links.yml"
CHANCE_DROP = 20.0
VIABLE = (5.0, 90.0)
CAUTION = (20.0, 75.0)
#: pairs a validation must compare to count (a proportion of fewer says nothing)
MIN_COMPARED = 30
#: the least share of the real keys' reach that the control's shifted key must keep (`_control_reach`)
CONTROL_REACH = 0.5


@dataclass(frozen=True, slots=True)
class Side:
    dataset: str
    where: str = ""
    explode_days: tuple[str, str, str] | None = None  # (start role, end role, new role)
    group: tuple[str, ...] = ()                       # one record per group (a delivery)
    latest: str = ""                                  # the group's record with the latest value of this role stands for it
    pad_years: tuple[int, int] = (0, 0)               # years read before and after the left period


@dataclass(frozen=True, slots=True)
class Pass:
    name: str
    keys: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class Validation:
    name: str
    left: str | None = None
    right: str | None = None
    tolerance: float | None = None
    sql: str | None = None  # a condition over the pair (l.*, r.*), for one-sided checks


@dataclass(frozen=True, slots=True)
class LinkSpec:
    name: str
    description: str
    left: Side
    right: Side
    passes: tuple[Pass, ...]
    control_role: str
    control_shift_days: int
    validations: tuple[Validation, ...]
    #: whether the two sides record one event (a death in hospital: the admission and the certificate) or two events of
    #: one person (a birth, then an infant death); a count of each side shares events only in the first case
    same_event: bool = False
    #: the side every record of which should find a partner (each infant death has its birth), so that its linked share
    #: measures the link's sensitivity by residence (`side_counts`); "" when neither side should (two systems that
    #: share some events). A reader of the other side's linked share reads it through this sensitivity
    sensitivity: str = ""


def _side(body: dict[str, Any]) -> Side:
    explode = body.get("explode_days")
    return Side(
        dataset=str(body["dataset"]).upper(),
        where=str(body.get("where") or ""),
        explode_days=tuple(explode) if explode else None,  # type: ignore[arg-type]
        group=tuple(body.get("group") or ()),
        latest=str(body.get("latest") or ""),
        pad_years=tuple(int(x) for x in body.get("pad_years") or (0, 0)),  # type: ignore[arg-type]
    )


def stored_key(name: str, method: str, period: object, geography: object, *,
               right_period: object = None, right_geography: object = None) -> Any:
    """The key a run of ``name`` is stored under: the scope, and the partner's
    scope when it differs, including a side's padded period. Every reader of
    stored runs (entities, inheritance) must use it: computing the key from the
    left scope alone missed every padded spec, and entities lost the infant
    deaths and newborns without a word (2026-10-03)."""
    from . import store

    if right_period is None:
        spec = load_links()[name]
        if spec.right.pad_years != (0, 0):
            right_period = padded_period(period, spec.right)
    return store.run_key(name, method, period if right_period is None else (period, right_period),
                         geography if right_geography is None else (geography, right_geography))


def padded_period(period: object, side: Side) -> object:
    """The period a side is read at: the left period widened by the side's
    ``pad_years`` (a death in January of a baby born the December before has
    its birth record in the previous year's file; linkage-theory §3.2)."""
    before, after = side.pad_years
    if not before and not after:
        return period
    from .._query_engine.model import _period

    p = _period(period)
    if p is None:
        return period
    return (str(p.start // 100 - before), str(p.end // 100 + after))


@lru_cache(maxsize=1)
def raw_links() -> dict[str, Any]:
    """`links.yml` as one process read it: the specs a run uses and the digest its store key carries come from this one
    snapshot (a file edited while a run was going stored old specs under the new digest, 2026-10-09)."""
    return read_yaml(links_file())


@lru_cache(maxsize=1)
def load_links() -> dict[str, LinkSpec]:
    data = raw_links()
    out: dict[str, LinkSpec] = {}
    for name, body in (data.get("links") or {}).items():
        passes = tuple(
            Pass(str(p["name"]), tuple((str(k[0]), str(k[1])) for k in p["keys"])) for p in body["passes"]
        )
        control = body["control"]
        validations = tuple(
            Validation(str(v["name"]), v.get("left"), v.get("right"), v.get("tolerance"), v.get("sql"))
            for v in body.get("validate") or ()
        )
        out[name] = LinkSpec(
            name, str(body.get("description", "")).strip(), _side(body["left"]), _side(body["right"]),
            passes, str(control["role"]), int(control.get("shift_days", 7)), validations,
            bool(body["same_event"]), str(body.get("sensitivity") or ""),
        )
    return out


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _roles_needed(spec: LinkSpec, side: str) -> list[str]:
    pick = 0 if side == "left" else 1
    names = {key[pick] for p in spec.passes for key in p.keys}
    for v in spec.validations:
        if side == "left" and v.left:
            names.add(v.left)
        if side == "right" and v.right:
            names.add(v.right)
    s = spec.left if side == "left" else spec.right
    if s.explode_days:
        names.discard(s.explode_days[2])
        names.update(s.explode_days[:2])
    names.update(s.group)
    if s.latest:
        names.add(s.latest)
    declared = dataset_roles(s.dataset).roles
    for text in (s.where, *(v.sql or "" for v in spec.validations)):
        names.update(r for r in declared if f'"{r}"' in text)
    if side == "left":
        names.add(spec.control_role)
    return sorted(n for n in names if n in declared)


@dataclass
class PassReport:
    name: str
    pairs: int
    control_pairs: int
    chance_percent: float | None
    kept: bool
    #: why the pass did not run: a key role the scope lacks ("absent") or no value of which normalised ("all null")
    skipped: str = ""


class LinkNotViable(RuntimeError):
    """A linkage whose measured error fails the verdict thresholds (ADR-0107).

    Raised instead of returning pairs, because pairs from a non-viable
    linkage look exactly like pairs from a viable one. The report is attached
    (``.result``) so the caller can see why, and ``allow_not_viable=True``
    returns it anyway for study.
    """

    def __init__(self, result: Any) -> None:
        self.result = result
        summary = result.summary()
        chance = summary.get("chance_percent", summary.get("estimated_fdr_percent"))
        super().__init__(
            f"{summary['spec']} is not viable here (chance {chance}%, "
            f"validations {summary['validations']}, {summary['pairs']} pairs; "
            f"{'; '.join(summary.get('verdict_reasons') or []) or 'no reason recorded'}). "
            "Pass allow_not_viable=True to inspect the pairs."
        )


@dataclass
class LinkResult:
    spec: str
    left_records: int
    right_records: int
    pairs: pa.Table
    passes: list[PassReport] = field(default_factory=list)
    validations: dict[str, dict[str, float | int | None]] = field(default_factory=dict)
    chance_percent: float | None = None
    verdict: str = "not viable"
    chance_upper95_percent: float | None = None
    #: what failed the verdict, in words (empty when viable)
    reasons: list[str] = field(default_factory=list)
    #: per year, the roles the scope lacked and the `codes` roles built from fewer columns than declared
    role_gaps: dict[str, Any] = field(default_factory=dict)
    #: the control's reach per shifted key: the share of left records whose shifted value finds a partner value, against the same for the real value
    control_reach: dict[str, Any] = field(default_factory=dict)

    @property
    def linked_share(self) -> float:
        return self.pairs.num_rows / self.left_records if self.left_records else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "spec": self.spec, "left_records": self.left_records, "right_records": self.right_records,
            "pairs": self.pairs.num_rows, "linked_share": round(self.linked_share, 4),
            "passes": [vars(p) for p in self.passes], "chance_percent": self.chance_percent,
            "chance_upper95_percent": self.chance_upper95_percent,
            "validations": self.validations, "verdict": self.verdict, "verdict_reasons": self.reasons,
            "role_gaps": self.role_gaps, "control_reach": self.control_reach,
        }


def _prepare(con: duckdb.DuckDBPyConnection, name: str, table: pa.Table, side: Side, *, materialise: bool = True) -> int:
    """Register one side as a relation with an `_id` per record (or per group). A table by default: the identity's
    window function, the group window and the day explosion are evaluated once, not by each of the six queries a pass
    and a validation issue (a key query over the view took 1.4-1.8 s per 3 M rows, over the table 0.4 s). The
    probabilistic engine asks for a view and materialises it as it keys it by integers (`probabilistic._materialise`)."""
    con.register(f"{name}_raw", table)
    where = f"WHERE {side.where}" if side.where else ""
    if "_record_key" in table.column_names:
        # The identity rule of roles.record_ids; numbered before the side's
        # filter, so a record's number does not depend on the spec.
        base = (f"SELECT * EXCLUDE (_dup), {RECORD_ID_SQL} AS _id FROM (SELECT *, {DUP_SQL} FROM {name}_raw) "
                f"{where}")
    else:
        base = f"SELECT *, _blob_sha256 || ':' || CAST(_row AS VARCHAR) AS _id FROM {name}_raw {where}"
    if side.group:
        # One record stands for its group (the live births of one delivery):
        # the smallest id (or the latest by ``side.latest``), with the group's size kept for validation.
        # A record missing any key is its own group: null keys partitioned together made every birth of a facility and
        # day without the mother's birth date one "delivery" (SINASC 2010: 2.86 M births, 870 k groups), and its
        # members took one partner (2026-10-08)
        anynull = " OR ".join(f"{_q(g)} IS NULL" for g in side.group)
        keys = f"CASE WHEN {anynull} THEN _id END, " + ", ".join(_q(g) for g in side.group)
        order = f"{_q(side.latest)} DESC NULLS LAST, _id" if side.latest else "_id"
        base = (f"SELECT * EXCLUDE (_n), _n AS _group_size FROM (SELECT *, count(*) OVER (PARTITION BY {keys}) AS _n, "
                f"row_number() OVER (PARTITION BY {keys} ORDER BY {order}) AS _k FROM ({base})) WHERE _k = 1")
    if side.explode_days:
        start, end, new = side.explode_days
        base = (f"SELECT *, CAST(unnest(generate_series(CAST({_q(start)} AS TIMESTAMP), CAST({_q(end)} AS TIMESTAMP), "
                f"INTERVAL 1 DAY)) AS DATE) AS {_q(new)} FROM ({base}) WHERE {_q(start)} IS NOT NULL "
                f"AND {_q(end)} IS NOT NULL AND {_q(end)} >= {_q(start)} AND {_q(end)} - {_q(start)} <= 120")
    con.execute(f"CREATE OR REPLACE TEMP {'TABLE' if materialise else 'VIEW'} {name} AS {base}")
    return con.execute(f"SELECT count(DISTINCT _id) FROM {name}").fetchone()[0]  # type: ignore[index]


def _shifted(role: str, days: int, integers: frozenset[str]) -> str:
    """SQL moving a key by the control's shift: a date by days; a year (SINAN's birth year, an integer) by that many
    units."""
    return f"({_q(role)} + {days})" if role in integers else f"CAST({_q(role)} + INTERVAL {days} DAY AS DATE)"


def _join(keys: tuple[tuple[str, str], ...], shift: tuple[str, int] | None, integers: frozenset[str]) -> str:
    """SQL for the 1:1 join of the still-unlinked records on `keys`."""
    lk: list[str] = []
    for left, _right in keys:
        expr = _shifted(left, shift[1], integers) if shift and left == shift[0] else _q(left)
        lk.append(f"{expr} AS k_{len(lk)}")
    rk = [f"{_q(right)} AS k_{i}" for i, (_l, right) in enumerate(keys)]
    kn = ", ".join(f"k_{i}" for i in range(len(keys)))
    notnull = " AND ".join(f"k_{i} IS NOT NULL" for i in range(len(keys)))
    return f"""
        WITH a AS (SELECT DISTINCT _id, {', '.join(lk)} FROM L WHERE _id NOT IN (SELECT l FROM linked)),
             b AS (SELECT DISTINCT _id, {', '.join(rk)} FROM R WHERE _id NOT IN (SELECT r FROM linked)),
             ua AS (SELECT * FROM a WHERE {notnull} QUALIFY count(*) OVER (PARTITION BY {kn}) = 1),
             ub AS (SELECT * FROM b WHERE {notnull} QUALIFY count(*) OVER (PARTITION BY {kn}) = 1)
        SELECT ua._id AS l, ub._id AS r FROM ua JOIN ub USING ({kn})"""


def _control_reach(con: duckdb.DuckDBPyConnection, spec: LinkSpec, integers: frozenset[str],
                   keys: set[tuple[str, str]]) -> dict[str, dict[str, float | int]]:
    """Whether the control can find a partner at all. A control that moves the key out of the partner side's values
    (a date shifted past the end of the partner's period) finds no false pair whatever the key's chance of a
    coincidence is, and its zero reads as "no false pairs". For each pairing of the control role, the share of left
    records whose own value is among the partner's values (what a real pair needs) and whose shifted value is
    (what a control pair needs); the second should be close to the first."""
    out: dict[str, dict[str, float | int]] = {}
    for left, right in sorted(keys):
        if left != spec.control_role:
            continue
        n, real, shifted = con.execute(f"""
            WITH rv AS (SELECT DISTINCT {_q(right)} AS v FROM R WHERE {_q(right)} IS NOT NULL),
                 a AS (SELECT DISTINCT _id, {_q(left)} AS v, {_shifted(left, spec.control_shift_days, integers)} AS s
                       FROM L WHERE {_q(left)} IS NOT NULL)
            SELECT count(*), count(r1.v), count(r2.v) FROM a LEFT JOIN rv r1 ON r1.v = a.v
                                                            LEFT JOIN rv r2 ON r2.v = a.s""").fetchone() or (0, 0, 0)
        out[f"{left} ~ {right}"] = {"records": int(n), "real_reach": round(real / n, 4) if n else 0.0,
                                    "control_reach": round(shifted / n, 4) if n else 0.0}
    return out


def _unreachable(reach: dict[str, dict[str, float | int]]) -> list[str]:
    return [f"the control cannot reach {key}: its shifted key finds a partner value for {v['control_reach']:.1%} of "
            f"the left records against {v['real_reach']:.1%} for the real key"
            for key, v in reach.items() if v["real_reach"] and v["control_reach"] < CONTROL_REACH * v["real_reach"]]


def roles_used(spec: LinkSpec) -> tuple[set[str], set[str]]:
    """The roles each side contributes as pass keys or through its filter: a validation reading one of them agrees by
    construction."""
    left = {k[0] for p in spec.passes for k in p.keys} | set(re.findall(r'"([^"]+)"', spec.left.where))
    right = {k[1] for p in spec.passes for k in p.keys} | set(re.findall(r'"([^"]+)"', spec.right.where))
    return left, right


def skipped_reason(keys: tuple[tuple[str, str], ...], left_bad: dict[str, str], right_bad: dict[str, str]) -> str:
    """Why a pass over ``keys`` cannot run on these tables: a key role the scope lacks or no value of which parsed."""
    why = [f"{role} {left_bad[role]}" for role, _r in keys if role in left_bad]
    why += [f"{role} {right_bad[role]}" for _l, role in keys if role in right_bad]
    return "; ".join(why)


def run(spec: LinkSpec, left: pa.Table, right: pa.Table) -> LinkResult:
    """Link two role tables under `spec`."""
    left_bad = unusable_roles(left, sorted({k[0] for p in spec.passes for k in p.keys}))
    right_bad = unusable_roles(right, sorted({k[1] for p in spec.passes for k in p.keys}))
    why_skipped = {p.name: skipped_reason(p.keys, left_bad, right_bad) for p in spec.passes}
    if all(why_skipped.values()):
        raise ValueError(f"{spec.name}: no pass can run on these tables ({why_skipped}); the scope lacks or cannot "
                         "read a role every pass keys on")
    con = connect()
    n_left = _prepare(con, "L", left, spec.left)
    n_right = _prepare(con, "R", right, spec.right)
    integers = frozenset(c for c in left.column_names if pa.types.is_integer(left.schema.field(c).type))
    con.execute("CREATE TEMP TABLE linked (l VARCHAR, r VARCHAR, pass VARCHAR)")
    reports: list[PassReport] = []
    for p in spec.passes:
        if why_skipped[p.name]:
            reports.append(PassReport(p.name, 0, 0, None, False, skipped=why_skipped[p.name]))
            continue
        real = con.execute(f"SELECT * FROM ({_join(p.keys, None, integers)})").to_arrow_table()
        control = con.execute(  # type: ignore[index]
            f"SELECT count(*) FROM ({_join(p.keys, (spec.control_role, spec.control_shift_days), integers)})"
        ).fetchone()[0]
        n = real.num_rows
        chance = 100.0 * control / n if n else None
        kept = bool(n) and control < n and (chance is None or chance < CHANCE_DROP)
        reports.append(PassReport(p.name, n, int(control), round(chance, 2) if chance is not None else None, kept))
        if kept:
            con.register("_new", real)
            con.execute("INSERT INTO linked SELECT l, r, ? FROM _new", [p.name])
            con.unregister("_new")
    pairs = con.execute("SELECT * FROM linked").to_arrow_table()
    kept_pairs = sum(r.pairs for r in reports if r.kept)
    kept_control = sum(r.control_pairs for r in reports if r.kept)
    chance = round(100.0 * kept_control / kept_pairs, 2) if kept_pairs else None
    validations = validate(con, spec)
    worst_pass = max((r.chance_percent or 0.0) for r in reports if r.kept) if any(r.kept for r in reports) else None
    upper = upper95(kept_control, kept_pairs)
    reach = _control_reach(con, spec, integers, {k for p in spec.passes if not why_skipped[p.name] for k in p.keys})
    verdict, reasons = judge(kept_pairs, worst_pass, validations, upper, placebo_failures=_unreachable(reach))
    reasons += [f"pass {name!r} skipped: {why}" for name, why in why_skipped.items() if why]
    from .roles import role_gaps

    gaps = {"left": role_gaps(left), "right": role_gaps(right)}
    return LinkResult(spec.name, n_left, n_right, pairs, reports, validations, chance, verdict, upper, reasons, gaps,
                      reach)


_QUOTED = re.compile(r'\b([lr])\."([^"]+)"')


def validation_roles(v: Validation) -> tuple[set[str], set[str]]:
    """The left and right roles a validation reads."""
    if v.sql:
        found = _QUOTED.findall(v.sql)
        return {name for side, name in found if side == "l"}, {name for side, name in found if side == "r"}
    return {v.left} if v.left else set(), {v.right} if v.right else set()


def validate(con: duckdb.DuckDBPyConnection, spec: LinkSpec,
             used: tuple[set[str], set[str]] | None = None) -> dict[str, dict[str, Any]]:
    """Agreement of each validation over the pairs in the temp table `linked` (l, r). ``used`` (left roles, right
    roles) are the roles the method being judged keys, compares or filters on (`roles_used` for the deterministic
    passes); a validation reading one is ``circular`` and never decides the verdict."""
    used_left, used_right = used if used is not None else roles_used(spec)
    con.execute("CREATE OR REPLACE TEMP TABLE _vl AS SELECT DISTINCT ON (_id) * FROM L")
    con.execute("CREATE OR REPLACE TEMP TABLE _vr AS SELECT DISTINCT ON (_id) * FROM R")
    validations: dict[str, dict[str, Any]] = {}
    for v in spec.validations:
        if v.sql:
            cond = v.sql
            usable = "TRUE"
        elif v.tolerance is not None:
            cond = f"abs(CAST(l.{_q(v.left or '')} AS DOUBLE) - CAST(r.{_q(v.right or '')} AS DOUBLE)) <= {v.tolerance}"
            usable = f"l.{_q(v.left or '')} IS NOT NULL AND r.{_q(v.right or '')} IS NOT NULL"
        else:
            cond = f"l.{_q(v.left or '')} = r.{_q(v.right or '')}"
            usable = f"l.{_q(v.left or '')} IS NOT NULL AND r.{_q(v.right or '')} IS NOT NULL"
        row = con.execute(f"""
            SELECT count(*), avg(CASE WHEN {cond} THEN 1.0 ELSE 0 END)
            FROM linked k JOIN _vl l ON l._id = k.l JOIN _vr r ON r._id = k.r
            WHERE {usable}""").fetchone()
        reads_left, reads_right = validation_roles(v)
        validations[v.name] = {"pairs_compared": int(row[0]),  # type: ignore[index]
                               "agreement_percent": round(100.0 * row[1], 2) if row[1] is not None else None,  # type: ignore[index]
                               "circular": bool(reads_left & used_left or reads_right & used_right)}
    return validations


def upper95(control: int, pairs: int) -> float | None:
    """95% upper bound, in percent, of a chance rate of `control` coincidences
    among `pairs` pairs (exact Poisson bound on the control count)."""
    if not pairs:
        return None
    from scipy.stats import chi2

    return round(100.0 * (chi2.ppf(0.975, 2 * (control + 1)) / 2) / pairs, 2)


def judge(
    pairs: int,
    worst_chance: float | None,
    validations: dict[str, dict[str, Any]],
    upper: float | None = None,
    *,
    placebo_failures: list[str] | tuple[str, ...] = (),
) -> tuple[str, list[str]]:
    """The verdict fixed before any result (ADR-0107), judged on the 95% upper bound of the chance rate when one is
    given (ADR-0113: 13 maternal deaths with no control pair read "0% chance" and were called viable, with a bound of
    28%), and its reasons. The validation that counts is the strongest HELD-OUT one that compared at least
    `MIN_COMPARED` pairs: a validation on a key or a compared field agrees by construction. A placebo that did not reach
    its blocks (``placebo_failures``) measured no chance at all: not viable."""
    reasons = list(placebo_failures)
    held = [float(v["agreement_percent"]) for v in validations.values()
            if not v.get("circular") and v["agreement_percent"] is not None
            and (v.get("pairs_compared") or 0) >= MIN_COMPARED]
    best = max(held) if held else None
    if not pairs:
        reasons.append("no pairs")
    if worst_chance is None:
        reasons.append("no chance estimate: no kept pass or no placebo threshold")
    if best is None:
        reasons.append(f"no held-out validation compares at least {MIN_COMPARED} pairs")
    if reasons:
        return "not viable", reasons
    assert best is not None and worst_chance is not None
    if upper is not None:
        worst_chance = max(worst_chance, upper)
    if worst_chance <= VIABLE[0] and best >= VIABLE[1]:
        return "viable", []
    found = [f"chance up to {worst_chance}% (viable: at most {VIABLE[0]}%)" if worst_chance > VIABLE[0] else "",
             f"strongest held-out validation {best}% (viable: at least {VIABLE[1]}%)" if best < VIABLE[1] else ""]
    if worst_chance <= CAUTION[0] and best >= CAUTION[1]:
        return "use with caution", [r for r in found if r]
    return "not viable", [r for r in found if r] + [f"outside the caution band (chance {CAUTION[0]}%, validation {CAUTION[1]}%)"]


def _side_table(side: Side, roles: list[str], *, period: object, geography: object, **query_kwargs: Any) -> pa.Table:
    """A side's role table with its filter applied where each year is read (`roles.role_table(where=)`): a side that
    keeps a few thousand of 12 million admissions never holds the year (a congenital toxoplasmosis link held 15 GB,
    2026-10-10). Kept under this name for pegasus_core's capture."""
    return role_table(side.dataset, period=period, geography=geography, roles=roles, where=side.where or None,
                      **query_kwargs)


def right_geography_for(spec: LinkSpec, geography: object, right_geography: object) -> object:
    """The geography the right side is read at. A state's records are paired with the nation's partners when the two
    datasets are not published by the same place: SIH and CIHA are filed by the hospital's state, SIM and SINASC by
    residence, so a Sergipe resident who died in an Alagoas hospital has her certificate in Sergipe's file and her
    admission in Alagoas's; reading the right side for the left's state alone lost every cross-state partner without
    a flag (2026-10-14 review). The same geography only when both datasets declare the same ``setting``."""
    if right_geography is not None or str(geography).upper() == "BR":
        return right_geography
    left_setting = dataset_roles(spec.left.dataset).setting
    right_setting = dataset_roles(spec.right.dataset).setting
    if left_setting and right_setting and left_setting.split(".", 1)[1] == right_setting.split(".", 1)[1]:
        return None
    return "BR"


def link(
    name: str,
    *,
    period: object,
    geography: object,
    right_period: object = None,
    right_geography: object = None,
    method: str = "deterministic",
    allow_not_viable: bool = False,
    refresh: bool = False,
    persist: bool = True,
    **query_kwargs: Any,
) -> Any:
    """Link two datasets under the declared spec ``name`` (``curation/links.yml``).

    Both sides are read through :func:`query` at ``period`` and ``geography``
    (``right_period`` when the right side needs another). Returns the pairs,
    as record identities ``_blob_sha256:_row`` with the pass that linked them,
    and a report of every pass, its negative control, the held-out validations
    and the verdict. A linkage that is not viable raises
    :class:`LinkNotViable` unless ``allow_not_viable=True``.

    ``method="probabilistic"`` runs the spec's probabilistic block
    (ADR-0111): evidence in bits learned from the data, a threshold set by the
    measured false-match rate; its pairs carry their score in bits.

    Results are kept in the lake (``<lake>/links/<spec>/``) and reused for the
    same spec content, method and scope; ``refresh=True`` recomputes, and
    ``persist=False`` keeps nothing.

    Example::

        result = link("sih_deaths_to_sim", period=2022, geography="RR")
        result.summary()["verdict"]     # 'viable'
        result.pairs                    # l, r, pass
    """
    from ..config import load_settings
    from . import store

    try:
        spec = load_links()[name]
    except KeyError:
        raise KeyError(f"no link spec {name!r}; declared: {sorted(load_links())}") from None
    if method not in ("deterministic", "probabilistic"):
        raise ValueError(f"method must be 'deterministic' or 'probabilistic', not {method!r}")
    settings = query_kwargs.get("settings") or load_settings(root=query_kwargs.get("root"))
    if right_period is None and spec.right.pad_years != (0, 0):
        right_period = padded_period(period, spec.right)
    right_geography = right_geography_for(spec, geography, right_geography)
    key = stored_key(name, method, period, geography, right_period=right_period, right_geography=right_geography)
    if not refresh:
        stored = store.load(settings, key)
        if stored is not None:
            result: Any = store.StoredResult(name, stored[0], stored[1])
            if result.verdict == "not viable" and not allow_not_viable:
                raise LinkNotViable(result)
            return result
    t0 = time.time()
    if method == "probabilistic":
        from .probabilistic import link_probabilistic

        result = link_probabilistic(name, period=period, geography=geography, right_period=right_period,
                                    right_geography=right_geography, **query_kwargs)
    else:
        left = _side_table(spec.left, _roles_needed(spec, "left"), period=period, geography=geography,
                           **query_kwargs)
        right = _side_table(spec.right, _roles_needed(spec, "right"), period=right_period or period,
                            geography=right_geography or geography, **query_kwargs)
        result = run(spec, left, right)
    if persist:
        # its wall time beside it: what a study prices a run it would compute by (pegasus_core `study._link_cost`),
        # and the scope it read: a state's records against the nation's partners, or against the state's own
        scope = {"geography": str(geography), "right_geography": str(right_geography) if right_geography is not None else None}
        store.save(settings, key, result.pairs, {**result.summary(), "scope": scope, "seconds": round(time.time() - t0, 1)})
        if (method == "probabilistic" and str(geography).upper() == "BR" and right_geography is None
                and result.verdict != "not viable"):
            # the reference slices of this period decide with: never from a run that failed its own verdict
            store.save_params(settings, key, result.summary())
    if result.verdict == "not viable" and not allow_not_viable:
        raise LinkNotViable(result)
    return result


def link_method(name: str) -> str:
    """The method a link is run by: probabilistic where its spec declares that block, deterministic otherwise (the
    women's deaths to their births as mothers declare keys only)."""
    body = (read_yaml(links_file()).get("links") or {}).get(name) or {}
    return "probabilistic" if body.get("probabilistic") else "deterministic"


def side_counts(name: str, *, period: object, side: str, by: str, method: str | None = None,
                persons: Any = None, **query_kwargs: Any) -> pa.Table:
    """One side of a stored national run by the value of role ``by`` (a residence): ``n`` the side's records the link
    can pair (its filter applied, a group's records as one, numbered as the run numbered them) and ``k`` the expected
    number paired (each record's largest p_match, 1 for a deterministic pair). n per residence is the denominator of
    the link's completeness there: a share of infant deaths that found their birth, by municipality and year, reads
    where the link has holes (a birth field's missing infant deaths were the link's, 2026-10-08). With ``persons``
    (`entities.build_entities` of the scope) a record also counts as paired when its person holds a record of the
    other side's kind through any route: an infant death the direct link missed but an admission and its death
    certificate reached. The run must be stored (`link`); a run not viable or absent raises."""
    from ..config import load_settings
    from . import store

    spec = load_links()[name]
    if side not in ("left", "right"):
        raise ValueError(f"side must be 'left' or 'right', not {side!r}")
    s = spec.left if side == "left" else spec.right
    settings = query_kwargs.get("settings") or load_settings(root=query_kwargs.get("root"))
    method = method or link_method(name)
    right_period = padded_period(period, spec.right) if spec.right.pad_years != (0, 0) else None
    stored = store.load(settings, stored_key(name, method, period, "BR", right_period=right_period))
    if stored is None:
        raise LookupError(f"{name} {period}: no stored {method} run (link it first)")
    if (stored[1] or {}).get("verdict") == "not viable":
        raise LinkNotViable(store.StoredResult(name, stored[0], stored[1]))
    declared = dataset_roles(s.dataset).roles
    if by not in declared:
        raise KeyError(f"{s.dataset} declares no role {by!r}")
    needed = sorted({by, *s.group, *([s.latest] if s.latest else []),
                     *(r for r in declared if s.where and f'"{r}"' in s.where)})
    scope = period if side == "left" else (right_period or period)
    table = role_table(s.dataset, period=scope, geography="BR", roles=needed, **query_kwargs)
    con = duckdb.connect()
    _prepare(con, "x", table, Side(s.dataset, s.where, None, s.group, s.latest, (0, 0)))
    pairs = stored[0]
    p = pairs.column("p_match") if "p_match" in pairs.column_names else pa.array([1.0] * pairs.num_rows)
    con.register("pm", pa.table({"id": pairs.column("l" if side == "left" else "r"), "p": p}))
    found = "0"
    if persons is not None:
        from .entities import _person_of_specs, person_pairs

        lds, lrole, rds, rrole = _person_of_specs()[name]
        mine, other = ((lds, lrole), (rds, rrole)) if side == "left" else ((rds, rrole), (lds, lrole))
        con.register("pp", pa.table({"id": person_pairs(persons, mine, other).column("l")}))
        # a record the direct link paired keeps its own p_match; one it missed counts when another route reached it
        found = "CASE WHEN f.id IS NOT NULL THEN 1.0 ELSE 0.0 END"
    joined = ("LEFT JOIN (SELECT DISTINCT CAST(id AS VARCHAR) AS id FROM pp) f ON f.id = CAST(x._id AS VARCHAR)"
              if persons is not None else "")
    return con.execute(f"""SELECT x.{_q(by)} AS unit, CAST(count(DISTINCT x._id) AS INTEGER) AS n,
            CAST(sum(coalesce(m.p, {found})) AS DOUBLE) AS k
        FROM (SELECT DISTINCT _id, {_q(by)} FROM x) x LEFT JOIN (SELECT id, max(p) AS p FROM pm GROUP BY id) m
        ON m.id = x._id {joined} GROUP BY 1 ORDER BY 1""").fetch_arrow_table()


__all__ = ["LinkNotViable", "LinkResult", "LinkSpec", "PassReport", "link", "link_method", "load_links", "run",
           "side_counts", "stored_key"]
