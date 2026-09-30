"""Probabilistic linkage: learned evidence in bits, threshold by measured error (ADR-0111).

Runs a link spec's ``probabilistic`` block (``curation/links.yml``):

1. **u**, how each comparison falls by coincidence, from random left × right
   pairs (almost all different people).
2. **m**, how each comparison falls for the same person, from
   *leave-one-field-out anchors*: pairs linked 1:1 on every other compared
   field, their negative control under 1%. Among them the left-out field's
   levels are its error channel, measured without assuming it.
3. **Candidates** from several blocking keys (intrinsic roles; geography never
   filters), each pair scored as the sum of its fields' bits.
4. **Control.** The same candidate generation and scoring with the left birth
   date shifted by 400 days. A year, a month and a day all change, so a true
   match compares as "other" and never earns typo credit; what the control
   still scores high is coincidence.
5. **Threshold** where the estimated false-match rate (control pairs over real
   pairs above it, both resolved 1:1) is at most ``target_fdr``; then 1:1
   resolution by descending score.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import duckdb
import pyarrow as pa

from ..semantics.curation import read_yaml
from .engine import LINKS_FILE, LinkSpec, _prepare, _q, judge, load_links, validate
from .model import Comparison, FieldModel, comparator, level_distribution, threshold_for
from .roles import dataset_roles, role_table

CONTROL_SHIFT_DAYS = 400
RANDOM_PAIRS = 200_000


@dataclass(frozen=True, slots=True)
class ProbabilisticSpec:
    compare: tuple[Comparison, ...]
    blocks: tuple[tuple[tuple[str, str], ...], ...]
    target_fdr: float = 0.01
    control_role: str = ""


def load_probabilistic(name: str) -> ProbabilisticSpec:
    body = (read_yaml(LINKS_FILE).get("links") or {})[name].get("probabilistic")
    if not body:
        raise KeyError(f"link spec {name!r} declares no probabilistic block")
    spec = load_links()[name]
    left_roles = dataset_roles(spec.left.dataset).roles
    compare = tuple(
        Comparison(str(a), "..".join(b), "interval") if isinstance(b, list)
        else Comparison(str(a), str(b), left_roles[str(a)].type)
        for a, b in body["compare"]
    )
    blocks = tuple(
        tuple((str(a), "..".join(b) if isinstance(b, list) else str(b)) for a, b in block) for block in body["blocks"]
    )
    return ProbabilisticSpec(compare, blocks, float(body.get("target_fdr", 0.01)),
                             str(body.get("control_role") or spec.control_role))


@dataclass
class ProbabilisticResult:
    spec: str
    left_records: int
    right_records: int
    pairs: pa.Table
    models: list[FieldModel] = field(default_factory=list)
    candidates: int = 0
    control_candidates: int = 0
    threshold_bits: float | None = None
    estimated_fdr_percent: float | None = None
    validations: dict[str, Any] = field(default_factory=dict)
    verdict: str = "not viable"

    def summary(self) -> dict[str, Any]:
        return {
            "spec": self.spec, "method": "probabilistic", "left_records": self.left_records,
            "right_records": self.right_records, "candidates": self.candidates,
            "control_candidates": self.control_candidates, "threshold_bits": self.threshold_bits,
            "pairs": self.pairs.num_rows,
            "linked_share": round(self.pairs.num_rows / self.left_records, 4) if self.left_records else 0.0,
            "estimated_fdr_percent": self.estimated_fdr_percent, "validations": self.validations,
            "verdict": self.verdict, "models": [m.as_dict() for m in self.models],
        }


def _shifted_left(con: duckdb.DuckDBPyConnection, role: str, days: int) -> None:
    con.execute(f"""CREATE OR REPLACE TEMP VIEW LS AS
        SELECT * REPLACE (CAST({_q(role)} + INTERVAL {days} DAY AS DATE) AS {_q(role)}) FROM L""")


def _condition(a: str, b: str) -> str:
    if ".." in b:
        start, end = b.split("..")
        return f"l.{_q(a)} BETWEEN r.{_q(start)} AND r.{_q(end)}"
    return f"l.{_q(a)} = r.{_q(b)}"


def _right_cols(compare) -> str:
    return ", ".join(
        f"struct_pack(s := r.{_q(c.right_roles[0])}, e := r.{_q(c.right_roles[1])})" if c.kind == "interval"
        else f"r.{_q(c.right)}" for c in compare
    )


def _candidates(con: duckdb.DuckDBPyConnection, left_view: str, blocks) -> str:
    parts = []
    for block in blocks:
        cond = " AND ".join(_condition(a, b) for a, b in block)
        notnull = " AND ".join(f"l.{_q(a)} IS NOT NULL" for a, _ in block)
        parts.append(f"SELECT DISTINCT l._id AS l, r._id AS r FROM {left_view} l JOIN R r ON {cond} WHERE {notnull}")
    return " UNION ".join(parts)


def _values(con, left_view: str, pairs_sql: str, compare) -> list[tuple]:
    lcols = ", ".join(f"l.{_q(c.left)}" for c in compare)
    rcols = _right_cols(compare)
    return _as_values(con.execute(f"""
        SELECT p.l, p.r, {lcols}, {rcols}
        FROM ({pairs_sql}) p
        JOIN (SELECT DISTINCT ON (_id) * FROM {left_view}) l ON l._id = p.l
        JOIN (SELECT DISTINCT ON (_id) * FROM R) r ON r._id = p.r""").fetchall())


def _as_values(rows: list[tuple]) -> list[tuple]:
    """Interval structs arrive as dicts; the comparator takes (start, end)."""
    return [tuple((v["s"], v["e"]) if isinstance(v, dict) else v for v in row) for row in rows]


def _score_rows(rows: list[tuple], models: list[FieldModel]) -> list[tuple[str, str, float]]:
    k = len(models)
    cmps = [comparator(m.comparison.kind) for m in models]
    out = []
    for row in rows:
        total = 0.0
        for i, fm in enumerate(models):
            total += fm.bits(cmps[i](row[2 + i], row[2 + k + i]))
        out.append((row[0], row[1], total))
    return out


def _one_to_one(scored: list[tuple[str, str, float]], threshold: float) -> list[tuple[str, str, float]]:
    used_l: set[str] = set()
    used_r: set[str] = set()
    kept = []
    for l_id, r_id, s in sorted(scored, key=lambda x: -x[2]):
        if s < threshold:
            break
        if l_id in used_l or r_id in used_r:
            continue
        used_l.add(l_id)
        used_r.add(r_id)
        kept.append((l_id, r_id, s))
    return kept


def _anchors(con, comp: Comparison, others: list[Comparison], control_role: str) -> tuple[list[tuple], int, int]:
    """Pairs linked 1:1 on every other comparison; their control; the left-out field's values.

    A pair is kept when each of its records has exactly one partner under the
    join, which is the 1:1 rule of the deterministic engine and also works for
    an interval (a birth day BETWEEN an admission's start and end).
    """
    date_keys = [c for c in others if c.kind in ("date", "interval")]
    shift_role = control_role if any(c.left == control_role for c in others) else (date_keys[0].left if date_keys else None)

    def join_sql(shift: bool) -> str:
        left = "L"
        if shift and shift_role:
            left = f"(SELECT * REPLACE (CAST({_q(shift_role)} + INTERVAL 7 DAY AS DATE) AS {_q(shift_role)}) FROM L)"
        cond = " AND ".join(_condition(c.left, c.right) for c in others)
        notnull = " AND ".join(f"l.{_q(c.left)} IS NOT NULL" for c in others)
        return f"""WITH j AS (SELECT DISTINCT l._id AS l, r._id AS r FROM {left} l
                             JOIN (SELECT DISTINCT ON (_id) * FROM R) r ON {cond} WHERE {notnull})
                   SELECT l, r FROM j
                   QUALIFY count(*) OVER (PARTITION BY l) = 1 AND count(*) OVER (PARTITION BY r) = 1"""

    real_sql = join_sql(False)
    n_real = con.execute(f"SELECT count(*) FROM ({real_sql})").fetchone()[0]
    n_control = con.execute(f"SELECT count(*) FROM ({join_sql(True)})").fetchone()[0] if shift_role else 0
    rows = _as_values(con.execute(f"""
        SELECT l.{_q(comp.left)}, {_right_cols([comp])} FROM ({real_sql}) p
        JOIN (SELECT DISTINCT ON (_id) * FROM L) l ON l._id = p.l
        JOIN (SELECT DISTINCT ON (_id) * FROM R) r ON r._id = p.r""").fetchall())
    return rows, n_real, n_control


def run_probabilistic(spec: LinkSpec, prob: ProbabilisticSpec, left: pa.Table, right: pa.Table) -> ProbabilisticResult:
    from dataclasses import replace as _replace

    con = duckdb.connect()
    # An interval is compared as an interval here: the deterministic engine's
    # one-row-per-day explosion is its way of making "inside" an equality.
    n_left = _prepare(con, "L", left, _replace(spec.left, explode_days=None))
    n_right = _prepare(con, "R", right, _replace(spec.right, explode_days=None))
    # u: random pairs.
    lcols = ", ".join(_q(c.left) for c in prob.compare)
    rsel = ", ".join(dict.fromkeys(_q(role) for c in prob.compare for role in c.right_roles))
    random_rows = _as_values(con.execute(f"""
        SELECT {", ".join("l." + _q(c.left) for c in prob.compare)}, {_right_cols(prob.compare)}
        FROM (SELECT {lcols} FROM L USING SAMPLE 2000 ROWS) l
        CROSS JOIN (SELECT {rsel} FROM R USING SAMPLE 100 ROWS) r""").fetchall())
    k = len(prob.compare)
    models: list[FieldModel] = []
    for i, comp in enumerate(prob.compare):
        cmp = comparator(comp.kind)
        u, n_u = level_distribution([(row[i], row[k + i]) for row in random_rows], cmp)
        others = [c for c in prob.compare if c is not comp]
        anchor_rows, n_anchor, n_anchor_control = _anchors(con, comp, others, prob.control_role)
        m, n_m = level_distribution(anchor_rows, cmp)
        fm = FieldModel(comp, m, u, anchors=n_m, controls=n_u)
        fm.m_source = {"anchors": n_anchor, "anchor_control": n_anchor_control}  # type: ignore[attr-defined]
        models.append(fm)
    # Candidates, real and control.
    real_rows = _values(con, "L", _candidates(con, "L", prob.blocks), prob.compare)
    _shifted_left(con, prob.control_role, CONTROL_SHIFT_DAYS)
    control_rows = _values(con, "LS", _candidates(con, "LS", prob.blocks), prob.compare)
    real = _score_rows(real_rows, models)
    control = _score_rows(control_rows, models)
    # Threshold on 1:1-resolved scores, so real and control are counted alike.
    real_best = _one_to_one(real, float("-inf"))
    control_best = _one_to_one(control, float("-inf"))
    t, fdr = threshold_for([s for *_x, s in real_best], [s for *_x, s in control_best], prob.target_fdr)
    kept = _one_to_one(real, t) if t is not None else []
    pairs = pa.table({"l": [x[0] for x in kept], "r": [x[1] for x in kept],
                      "bits": pa.array([round(x[2], 3) for x in kept], pa.float64())})
    con.execute("CREATE OR REPLACE TEMP TABLE linked AS SELECT l, r FROM pairs")
    validations = validate(con, spec)
    fdr_percent = round(100.0 * fdr, 2) if fdr is not None else None
    verdict = judge(len(kept), fdr_percent, validations)
    return ProbabilisticResult(spec.name, n_left, n_right, pairs, models, len(real), len(control),
                               round(t, 2) if t is not None else None, fdr_percent, validations, verdict)


def link_probabilistic(name: str, *, period: object, geography: object, right_period: object = None,
                       **query_kwargs: Any) -> ProbabilisticResult:
    """Link under ``name``'s probabilistic block, reading both sides through ``query``."""
    from .engine import _roles_needed

    spec = load_links()[name]
    prob = load_probabilistic(name)
    left_roles = sorted(set(_roles_needed(spec, "left")) | {c.left for c in prob.compare})
    right_roles = sorted(set(_roles_needed(spec, "right")) | {r for c in prob.compare for r in c.right_roles})
    left = role_table(spec.left.dataset, period=period, geography=geography, roles=left_roles, **query_kwargs)
    right = role_table(spec.right.dataset, period=right_period or period, geography=geography,
                       roles=right_roles, **query_kwargs)
    return run_probabilistic(spec, prob, left, right)


__all__ = ["ProbabilisticResult", "ProbabilisticSpec", "link_probabilistic", "load_probabilistic", "run_probabilistic"]
