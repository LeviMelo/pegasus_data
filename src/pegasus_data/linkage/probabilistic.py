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
import numpy as np
import pyarrow as pa

from ..semantics.curation import read_yaml
from .engine import LINKS_FILE, LinkSpec, _prepare, _q, judge, load_links, upper95, validate
from .levels import levels
from .model import MISSING, Comparison, FieldModel, threshold_for
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
    control_above_threshold: int = 0
    fdr_upper95_percent: float | None = None
    validations: dict[str, Any] = field(default_factory=dict)
    verdict: str = "not viable"

    def summary(self) -> dict[str, Any]:
        return {
            "spec": self.spec, "method": "probabilistic", "left_records": self.left_records,
            "right_records": self.right_records, "candidates": self.candidates,
            "control_candidates": self.control_candidates, "threshold_bits": self.threshold_bits,
            "pairs": self.pairs.num_rows,
            "linked_share": round(self.pairs.num_rows / self.left_records, 4) if self.left_records else 0.0,
            "estimated_fdr_percent": self.estimated_fdr_percent,
            "control_pairs_above_threshold": self.control_above_threshold,
            "fdr_upper95_percent": self.fdr_upper95_percent, "validations": self.validations,
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


def _candidates(con: duckdb.DuckDBPyConnection, left_view: str, blocks) -> str:
    parts = []
    for block in blocks:
        cond = " AND ".join(_condition(a, b) for a, b in block)
        notnull = " AND ".join(f"l.{_q(a)} IS NOT NULL" for a, _ in block)
        parts.append(f"SELECT DISTINCT l._id AS l, r._id AS r FROM {left_view} l JOIN R r ON {cond} WHERE {notnull}")
    return " UNION ".join(parts)


def _select_values(left_view: str, pairs_sql: str, compare) -> str:
    """SQL returning l, r and every compared value, one column per role."""
    lcols = [f'l.{_q(c.left)} AS "v{i}_l"' for i, c in enumerate(compare)]
    rcols = []
    for i, c in enumerate(compare):
        for j, role in enumerate(c.right_roles):
            rcols.append(f'r.{_q(role)} AS "v{i}_r{j}"')
    return f"""SELECT p.l, p.r, {", ".join(lcols + rcols)}
        FROM ({pairs_sql}) p
        JOIN (SELECT DISTINCT ON (_id) * FROM {left_view}) l ON l._id = p.l
        JOIN (SELECT DISTINCT ON (_id) * FROM R) r ON r._id = p.r"""


def _batch_levels(batch: pa.RecordBatch, compare) -> list[np.ndarray]:
    out = []
    for i, c in enumerate(compare):
        a = batch.column(f"v{i}_l")
        if c.kind == "interval":
            out.append(levels(c.kind, a, (batch.column(f"v{i}_r0"), batch.column(f"v{i}_r1"))))
        else:
            out.append(levels(c.kind, a, batch.column(f"v{i}_r0")))
    return out


def _distribution(lv: np.ndarray) -> tuple[dict[str, float], int]:
    usable = lv[lv != MISSING]
    if not len(usable):
        return {}, 0
    names, counts = np.unique(usable.astype(str), return_counts=True)
    return {str(n): c / len(usable) for n, c in zip(names, counts, strict=True)}, int(len(usable))


def _bits_of(fm: FieldModel, lv: np.ndarray) -> np.ndarray:
    names, inverse = np.unique(lv.astype(str), return_inverse=True)
    return np.array([fm.bits(str(n)) for n in names])[inverse]


def _score_stream(con, sql: str, compare, models: list[FieldModel]) -> tuple[list, list, np.ndarray]:
    """Scores of every candidate pair, streamed in batches; only positive scores are kept."""
    ls: list = []
    rs: list = []
    scores: list[np.ndarray] = []
    for batch in con.execute(sql).fetch_record_batch(1_000_000):
        if not batch.num_rows:
            continue
        total = np.zeros(batch.num_rows)
        for fm, lv in zip(models, _batch_levels(batch, compare), strict=True):
            total += _bits_of(fm, lv)
        keep = np.nonzero(total > 0)[0]
        if len(keep):
            ls.extend(pa.array(batch.column("l")).take(pa.array(keep)).to_pylist())
            rs.extend(pa.array(batch.column("r")).take(pa.array(keep)).to_pylist())
            scores.append(total[keep])
    return ls, rs, (np.concatenate(scores) if scores else np.zeros(0))


#: A record is linked only when its best candidate beats the runner-up by
#: this much evidence, on both sides: log2(19) bits, the best at least 95%
#: likely between the two. Without it, a birth date + sex + hospital shared
#: by ~15 newborns a day in one maternity hospital was resolved by picking one
#: of them, and a negative control cannot see that error: the true baby IS
#: among the candidates (RR 2022, 3,294 "viable" pairs; ADR-0113).
AMBIGUITY_MARGIN_BITS = float(np.log2(19))


def _one_to_one(ls: list, rs: list, scores: np.ndarray, threshold: float) -> list[tuple[str, str, float]]:
    """Pairs that are each side's clear best, at or above the threshold.

    A pair is kept when, among its left record's candidates, it scores at
    least AMBIGUITY_MARGIN_BITS above the next, and the same holds among its
    right record's candidates. Candidates below zero never reach here, so a
    lone candidate is compared with nothing and passes.
    """
    if not len(scores):
        return []
    order = np.argsort(-scores, kind="stable")
    best_l: dict[str, tuple[float, int]] = {}
    second_l: dict[str, float] = {}
    best_r: dict[str, tuple[float, int]] = {}
    second_r: dict[str, float] = {}
    for i in order:
        s = float(scores[i])
        for side, best, second in ((ls[i], best_l, second_l), (rs[i], best_r, second_r)):
            if side not in best:
                best[side] = (s, int(i))
            elif side not in second:
                second[side] = s
    kept = []
    for l_id, (s, i) in best_l.items():
        if s < threshold:
            continue
        r_id = rs[i]
        if best_r.get(r_id, (None, -1))[1] != i:
            continue
        if s - second_l.get(l_id, float("-inf")) < AMBIGUITY_MARGIN_BITS:
            continue
        if s - second_r.get(r_id, float("-inf")) < AMBIGUITY_MARGIN_BITS:
            continue
        kept.append((l_id, r_id, s))
    return kept


def _anchor_sql(others: list[Comparison], control_role: str, shift: bool) -> tuple[str, bool]:
    """Pairs linked 1:1 on every other comparison (or their control).

    A pair is kept when each of its records has exactly one partner under the
    join: the 1:1 rule of the deterministic engine, which also works for an
    interval (a birth day BETWEEN an admission's start and end).
    """
    date_keys = [c for c in others if c.kind in ("date", "interval")]
    shift_role = control_role if any(c.left == control_role for c in others) else (date_keys[0].left if date_keys else None)
    left = "L"
    if shift:
        if not shift_role:
            return "", False
        left = f"(SELECT * REPLACE (CAST({_q(shift_role)} + INTERVAL 7 DAY AS DATE) AS {_q(shift_role)}) FROM L)"
    cond = " AND ".join(_condition(c.left, c.right) for c in others)
    notnull = " AND ".join(f"l.{_q(c.left)} IS NOT NULL" for c in others)
    return f"""WITH j AS (SELECT DISTINCT l._id AS l, r._id AS r FROM {left} l
                         JOIN (SELECT DISTINCT ON (_id) * FROM R) r ON {cond} WHERE {notnull})
               SELECT l, r FROM j
               QUALIFY count(*) OVER (PARTITION BY l) = 1 AND count(*) OVER (PARTITION BY r) = 1""", True


def _levels_of(con, sql: str, compare) -> list[np.ndarray]:
    table = con.execute(sql).fetch_arrow_table()
    if not table.num_rows:
        return [np.array([], dtype=object) for _ in compare]
    return _batch_levels(table.combine_chunks().to_batches()[0], compare)


def run_probabilistic(spec: LinkSpec, prob: ProbabilisticSpec, left: pa.Table, right: pa.Table) -> ProbabilisticResult:
    from dataclasses import replace as _replace

    con = duckdb.connect()
    # An interval is compared as an interval here: the deterministic engine's
    # one-row-per-day explosion is its way of making "inside" an equality.
    n_left = _prepare(con, "L", left, _replace(spec.left, explode_days=None))
    n_right = _prepare(con, "R", right, _replace(spec.right, explode_days=None))
    # u: 200,000 random pairs over up to 50,000 distinct records per side,
    # paired by position with a stride: diverse on both sides and repeatable.
    # A 2,000 x 100 rectangle rested u on 100 right records, and one AC run
    # moved from 198 to 173 pairs between two draws (2026-09-30).
    random_pairs = f"""
        WITH l AS (SELECT _id, row_number() OVER () - 1 AS i
                   FROM (SELECT DISTINCT _id FROM L USING SAMPLE reservoir(50000 ROWS) REPEATABLE (107))),
             r AS (SELECT _id, row_number() OVER () - 1 AS i
                   FROM (SELECT DISTINCT _id FROM R USING SAMPLE reservoir(50000 ROWS) REPEATABLE (107))),
             n AS (SELECT (SELECT count(*) FROM l) AS nl, (SELECT count(*) FROM r) AS nr),
             g AS (SELECT k % n.nl AS li, (k * 7919) % n.nr AS ri FROM range({RANDOM_PAIRS}) t(k), n)
        SELECT l._id AS l, r._id AS r FROM g JOIN l ON l.i = g.li JOIN r ON r.i = g.ri"""
    random_levels = _levels_of(con, _select_values("L", random_pairs, prob.compare), prob.compare)
    models: list[FieldModel] = []
    for i, comp in enumerate(prob.compare):
        u, n_u = _distribution(random_levels[i])
        others = [c for c in prob.compare if c is not comp]
        anchor_sql, _ = _anchor_sql(others, prob.control_role, shift=False)
        control_sql, has_control = _anchor_sql(others, prob.control_role, shift=True)
        n_anchor = con.execute(f"SELECT count(*) FROM ({anchor_sql})").fetchone()[0]
        n_anchor_control = con.execute(f"SELECT count(*) FROM ({control_sql})").fetchone()[0] if has_control else 0
        m, n_m = _distribution(_levels_of(con, _select_values("L", anchor_sql, [comp]), [comp])[0])
        fm = FieldModel(comp, m, u, anchors=n_m, controls=n_u)
        fm.m_source = {"anchors": n_anchor, "anchor_control": n_anchor_control}  # type: ignore[attr-defined]
        models.append(fm)
    # Candidates, real and control, scored as they stream.
    rl, rr, rscore = _score_stream(con, _select_values("L", _candidates(con, "L", prob.blocks), prob.compare),
                                   prob.compare, models)
    _shifted_left(con, prob.control_role, CONTROL_SHIFT_DAYS)
    cl, cr, cscore = _score_stream(con, _select_values("LS", _candidates(con, "LS", prob.blocks), prob.compare),
                                   prob.compare, models)
    # Threshold on 1:1-resolved scores, so real and control are counted alike.
    real_best = _one_to_one(rl, rr, rscore, float("-inf"))
    control_best = _one_to_one(cl, cr, cscore, float("-inf"))
    t, fdr = threshold_for([s for *_x, s in real_best], [s for *_x, s in control_best], prob.target_fdr)
    kept = _one_to_one(rl, rr, rscore, t) if t is not None else []
    pairs = pa.table({"l": pa.array([x[0] for x in kept], pa.string()),
                      "r": pa.array([x[1] for x in kept], pa.string()),
                      "bits": pa.array([round(x[2], 3) for x in kept], pa.float64())})
    con.register("pairs_view", pairs)
    con.execute("CREATE OR REPLACE TEMP TABLE linked AS SELECT l, r FROM pairs_view")
    validations = validate(con, spec)
    fdr_percent = round(100.0 * fdr, 2) if fdr is not None else None
    # The estimate rests on few control pairs when the left side is small (a
    # state's infant deaths): say how few, and the 95% upper bound (Poisson on
    # the control count, over the real pairs kept).
    control_kept = sum(1 for *_x, s in control_best if t is not None and s >= t)
    upper = upper95(control_kept, len(kept))
    verdict = judge(len(kept), fdr_percent, validations, upper)
    return ProbabilisticResult(spec.name, n_left, n_right, pairs, models, len(rscore), len(cscore),
                               round(t, 2) if t is not None else None, fdr_percent, control_kept, upper,
                               validations, verdict)


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
