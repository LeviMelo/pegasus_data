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

Then held-out validations (variables that were not keys) and the verdict
fixed before any result: *viable* when every kept pass is at most 5% chance
and the strongest validation agrees in at least 90% of pairs; *use with
caution* at 20% and 75%; *not viable* otherwise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa

from ..semantics.curation import read_yaml
from .roles import dataset_roles, role_table

LINKS_FILE = Path(__file__).resolve().parent.parent / "curation" / "links.yml"
CHANCE_DROP = 20.0
VIABLE = (5.0, 90.0)
CAUTION = (20.0, 75.0)


@dataclass(frozen=True, slots=True)
class Side:
    dataset: str
    where: str = ""
    explode_days: tuple[str, str, str] | None = None  # (start role, end role, new role)
    group: tuple[str, ...] = ()                       # one record per group (a delivery)


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


def _side(body: dict[str, Any]) -> Side:
    explode = body.get("explode_days")
    return Side(
        dataset=str(body["dataset"]).upper(),
        where=str(body.get("where") or ""),
        explode_days=tuple(explode) if explode else None,  # type: ignore[arg-type]
        group=tuple(body.get("group") or ()),
    )


@lru_cache(maxsize=1)
def load_links() -> dict[str, LinkSpec]:
    data = read_yaml(LINKS_FILE)
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


class LinkNotViable(RuntimeError):
    """A linkage whose measured error fails the verdict thresholds (ADR-0107).

    Raised instead of returning pairs, because pairs from a non-viable
    linkage look exactly like pairs from a viable one. The report is attached
    (``.result``) so the caller can see why, and ``allow_not_viable=True``
    returns it anyway for study.
    """

    def __init__(self, result: LinkResult) -> None:
        self.result = result
        passes = "; ".join(f"{p.name}: {p.pairs} pairs, {p.control_pairs} by chance" for p in result.passes)
        super().__init__(
            f"{result.spec} is not viable here (chance {result.chance_percent}%, "
            f"validations {result.validations}); passes: {passes}. "
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

    @property
    def linked_share(self) -> float:
        return self.pairs.num_rows / self.left_records if self.left_records else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "spec": self.spec, "left_records": self.left_records, "right_records": self.right_records,
            "pairs": self.pairs.num_rows, "linked_share": round(self.linked_share, 4),
            "passes": [vars(p) for p in self.passes], "chance_percent": self.chance_percent,
            "validations": self.validations, "verdict": self.verdict,
        }


def _prepare(con: duckdb.DuckDBPyConnection, name: str, table: pa.Table, side: Side) -> int:
    """Register one side as a view with an `_id` per record (or per group)."""
    con.register(f"{name}_raw", table)
    where = f"WHERE {side.where}" if side.where else ""
    base = f"SELECT *, _blob_sha256 || ':' || CAST(_row AS VARCHAR) AS _id FROM {name}_raw {where}"
    if side.group:
        # One record stands for its group (the live births of one delivery):
        # the smallest id, with the group's size kept for validation.
        keys = ", ".join(_q(g) for g in side.group)
        base = (f"SELECT * EXCLUDE (_n), _n AS _group_size FROM (SELECT *, count(*) OVER (PARTITION BY {keys}) AS _n, "
                f"row_number() OVER (PARTITION BY {keys} ORDER BY _id) AS _k FROM ({base})) WHERE _k = 1")
    if side.explode_days:
        start, end, new = side.explode_days
        base = (f"SELECT *, CAST(unnest(generate_series(CAST({_q(start)} AS TIMESTAMP), CAST({_q(end)} AS TIMESTAMP), "
                f"INTERVAL 1 DAY)) AS DATE) AS {_q(new)} FROM ({base}) WHERE {_q(start)} IS NOT NULL "
                f"AND {_q(end)} IS NOT NULL AND {_q(end)} >= {_q(start)} AND {_q(end)} - {_q(start)} <= 120")
    con.execute(f"CREATE OR REPLACE TEMP VIEW {name} AS {base}")
    return con.execute(f"SELECT count(DISTINCT _id) FROM {name}").fetchone()[0]


def _join(con: duckdb.DuckDBPyConnection, keys: tuple[tuple[str, str], ...], shift: tuple[str, int] | None) -> str:
    """SQL for the 1:1 join of the still-unlinked records on `keys`."""
    lk = []
    for left, _right in keys:
        expr = _q(left)
        if shift and left == shift[0]:
            expr = f"CAST({_q(left)} + INTERVAL {shift[1]} DAY AS DATE)"
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


def run(spec: LinkSpec, left: pa.Table, right: pa.Table) -> LinkResult:
    """Link two role tables under `spec`."""
    con = duckdb.connect()
    n_left = _prepare(con, "L", left, spec.left)
    n_right = _prepare(con, "R", right, spec.right)
    con.execute("CREATE TEMP TABLE linked (l VARCHAR, r VARCHAR, pass VARCHAR)")
    reports: list[PassReport] = []
    for p in spec.passes:
        real = con.execute(f"SELECT * FROM ({_join(con, p.keys, None)})").fetch_arrow_table()
        control = con.execute(
            f"SELECT count(*) FROM ({_join(con, p.keys, (spec.control_role, spec.control_shift_days))})"
        ).fetchone()[0]
        n = real.num_rows
        chance = 100.0 * control / n if n else None
        kept = bool(n) and control < n and (chance is None or chance < CHANCE_DROP)
        reports.append(PassReport(p.name, n, int(control), round(chance, 2) if chance is not None else None, kept))
        if kept:
            con.register("_new", real)
            con.execute("INSERT INTO linked SELECT l, r, ? FROM _new", [p.name])
            con.unregister("_new")
    pairs = con.execute("SELECT * FROM linked").fetch_arrow_table()
    kept_pairs = sum(r.pairs for r in reports if r.kept)
    kept_control = sum(r.control_pairs for r in reports if r.kept)
    chance = round(100.0 * kept_control / kept_pairs, 2) if kept_pairs else None
    validations = validate(con, spec)
    worst_pass = max((r.chance_percent or 0.0) for r in reports if r.kept) if any(r.kept for r in reports) else None
    verdict = judge(kept_pairs, worst_pass, validations)
    return LinkResult(spec.name, n_left, n_right, pairs, reports, validations, chance, verdict)


def validate(con: duckdb.DuckDBPyConnection, spec: LinkSpec) -> dict[str, dict[str, float | int | None]]:
    """Held-out agreement over the pairs in the temp table `linked` (l, r)."""
    validations: dict[str, dict[str, float | int | None]] = {}
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
            FROM linked k JOIN (SELECT DISTINCT ON (_id) * FROM L) l ON l._id = k.l
                          JOIN (SELECT DISTINCT ON (_id) * FROM R) r ON r._id = k.r
            WHERE {usable}""").fetchone()
        validations[v.name] = {"pairs_compared": int(row[0]),
                               "agreement_percent": round(100.0 * row[1], 2) if row[1] is not None else None}
    return validations


def judge(pairs: int, worst_chance: float | None, validations: dict[str, dict[str, float | int | None]]) -> str:
    """The verdict fixed before any result (ADR-0107)."""
    agreement = [float(v["agreement_percent"]) for v in validations.values() if v["agreement_percent"] is not None]
    best = max(agreement) if agreement else None
    if not pairs or best is None or worst_chance is None:
        return "not viable"
    if worst_chance <= VIABLE[0] and best >= VIABLE[1]:
        return "viable"
    if worst_chance <= CAUTION[0] and best >= CAUTION[1]:
        return "use with caution"
    return "not viable"


def link(
    name: str,
    *,
    period: object,
    geography: object,
    right_period: object = None,
    allow_not_viable: bool = False,
    **query_kwargs: Any,
) -> LinkResult:
    """Link two datasets under the declared spec ``name`` (``curation/links.yml``).

    Both sides are read through :func:`query` at ``period`` and ``geography``
    (``right_period`` when the right side needs another). Returns the pairs,
    as record identities ``_blob_sha256:_row`` with the pass that linked them,
    and a report of every pass, its negative control, the held-out validations
    and the verdict. A linkage that is not viable raises
    :class:`LinkNotViable` unless ``allow_not_viable=True``.

    Example::

        result = link("sih_deaths_to_sim", period=2022, geography="RR")
        result.summary()["verdict"]     # 'viable'
        result.pairs                    # l, r, pass
    """
    try:
        spec = load_links()[name]
    except KeyError:
        raise KeyError(f"no link spec {name!r}; declared: {sorted(load_links())}") from None
    left = role_table(spec.left.dataset, period=period, geography=geography,
                      roles=_roles_needed(spec, "left"), **query_kwargs)
    right = role_table(spec.right.dataset, period=right_period or period, geography=geography,
                       roles=_roles_needed(spec, "right"), **query_kwargs)
    result = run(spec, left, right)
    if result.verdict == "not viable" and not allow_not_viable:
        raise LinkNotViable(result)
    return result


__all__ = ["LinkNotViable", "LinkResult", "LinkSpec", "PassReport", "link", "load_links", "run"]
