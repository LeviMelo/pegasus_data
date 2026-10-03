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

Scope invariance (docs/plans/linkage-theory.md §3.2, step T2):

- **The national partner side.** ``right_geography="BR"`` reads the right
  side nationally, so a partner outside the slice is found and competitors are
  the nation's.
- **National calibration.** A slice decides with the national run's threshold
  and match-probability curve (stored with its channels), not with a threshold
  re-estimated from its own small placebo: that re-estimation was what still
  differed between a slice and the nation (Roraima, 2026-10-03).
- **Pooled error channels.** A run's m is shrunk toward the stored national m
  of the same spec, by ``POOL_PSEUDO_ANCHORS`` pseudo-anchors: a state with
  few anchors leans on the nation, a large one keeps its own. A national run
  stores the reference (``<lake>/links/_params/``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import duckdb
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

from ..semantics.curation import read_yaml
from .engine import LINKS_FILE, LinkSpec, _prepare, _q, judge, load_links, upper95, validate
from .levels import levels
from .model import MISSING, Comparison, FieldModel, threshold_for
from .roles import dataset_roles, role_table

CONTROL_SHIFT_DAYS = 400
RANDOM_PAIRS = 200_000
#: Weight of the national m against a run's own anchors (empirical-Bayes
#: shrinkage with a fixed prior strength; a run with 200 anchors is half its own).
POOL_PSEUDO_ANCHORS = 200


@dataclass(frozen=True, slots=True)
class Inherit:
    """A role a record takes from its partner in another stored link (theory §3.3).

    ``via`` is the stored link, ``role`` the partner's role, ``as_`` the name it
    takes here. The newborn admission's baby inherits the AIH number of its
    mother's delivery admission: evidence no single record carries.
    """

    side: str
    via: str
    role: str
    as_: str


@dataclass(frozen=True, slots=True)
class ProbabilisticSpec:
    compare: tuple[Comparison, ...]
    blocks: tuple[tuple[tuple[str, str], ...], ...]
    target_fdr: float = 0.01
    control_role: str = ""
    inherit: tuple[Inherit, ...] = ()


def load_probabilistic(name: str) -> ProbabilisticSpec:
    body = (read_yaml(LINKS_FILE).get("links") or {})[name].get("probabilistic")
    if not body:
        raise KeyError(f"link spec {name!r} declares no probabilistic block")
    spec = load_links()[name]
    left_roles = dataset_roles(spec.left.dataset).roles
    # A comparison is [left, right] or [left, right, {given: role, side: left|right}]
    # (ADR-0115); the right side is a list [start, end] for an interval.
    compare = tuple(
        Comparison(str(item[0]), "..".join(item[1]), "interval") if isinstance(item[1], list)
        else Comparison(str(item[0]), str(item[1]),
                        str(item[2]["kind"]) if len(item) > 2 and "kind" in item[2]
                        else left_roles[str(item[0])].type,
                        given=str(item[2]["given"]) if len(item) > 2 and "given" in item[2] else None,
                        given_side=str(item[2].get("side", "right")) if len(item) > 2 else "right")
        for item in body["compare"]
    )
    # A block key is [left, right] or [left, right, "typo"]: the typo form also
    # matches the left date through its plausible mistypings (typo_variants).
    blocks = tuple(
        tuple(
            (str(key[0]), "..".join(key[1]) if isinstance(key[1], list) else str(key[1]))
            + (("typo",) if len(key) > 2 and key[2] == "typo" else ())
            for key in block
        )
        for block in body["blocks"]
    )
    inherit = tuple(
        Inherit(side, str(item["via"]), str(item["role"]), str(item["as"]))
        for side in ("left", "right") for item in ((body.get("inherit") or {}).get(side) or [])
    )
    return ProbabilisticSpec(compare, blocks, float(body.get("target_fdr", 0.01)),
                             str(body.get("control_role") or spec.control_role), inherit)


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
    threshold_source: str = "own"
    calibration: dict[str, Any] = field(default_factory=dict)

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
            "verdict": self.verdict, "threshold_source": self.threshold_source,
            "calibration": self.calibration, "models": [m.as_dict() for m in self.models],
        }


def _shifted_left(con: duckdb.DuckDBPyConnection, role: str, days: int) -> None:
    con.execute(f"""CREATE OR REPLACE TEMP VIEW LS AS
        SELECT * REPLACE (CAST({_q(role)} + INTERVAL {days} DAY AS DATE) AS {_q(role)}) FROM L""")


def _condition(a: str, b: str) -> str:
    if ".." in b:
        start, end = b.split("..")
        return f"l.{_q(a)} BETWEEN r.{_q(start)} AND r.{_q(end)}"
    return f"l.{_q(a)} = r.{_q(b)}"


def typo_variants(dates: pa.Array) -> tuple[np.ndarray, pa.Array]:
    """Plausible mistypings of each date, as (row index, variant date).

    From the error channel measured on SIA's encrypted CNS (EVALUATION
    2026-09-30, national linkage measurements): one digit replaced by a key
    adjacent to it on the numeric keypad or top row (60% of one-digit errors),
    two neighbouring digits swapped, and day and month exchanged. A variant
    that is not a calendar date is dropped, and so is the original.
    """
    from .levels import _ADJ, _digits

    digits = _digits(dates)
    valid = digits[:, 0] >= 0
    rows_all, texts = [], []
    base = np.nonzero(valid)[0]
    d = digits[base]
    for pos in range(8):
        for new in range(10):
            hit = _ADJ[d[:, pos].clip(0), new] & (d[:, pos] != new)
            if hit.any():
                v = d[hit].copy()
                v[:, pos] = new
                rows_all.append(base[hit])
                texts.append(v)
    for pos in range(7):
        differ = d[:, pos] != d[:, pos + 1]
        if differ.any():
            v = d[differ].copy()
            v[:, [pos, pos + 1]] = v[:, [pos + 1, pos]]
            rows_all.append(base[differ])
            texts.append(v)
    swap = (d[:, 0:2] != d[:, 2:4]).any(axis=1)
    if swap.any():
        v = d[swap].copy()
        v[:, 0:4] = np.concatenate([v[:, 2:4], v[:, 0:2]], axis=1)
        rows_all.append(base[swap])
        texts.append(v)
    if not rows_all:
        return np.zeros(0, dtype=np.int64), pa.array([], pa.date32())
    rows = np.concatenate(rows_all)
    grid = np.concatenate(texts)
    strings = ["".join(map(str, r)) for r in grid]
    parsed = pc.cast(pc.strptime(pa.array(strings), format="%d%m%Y", unit="s", error_is_null=True), pa.date32())
    keep = pc.is_valid(parsed).to_numpy(zero_copy_only=False)
    return rows[keep], parsed.filter(pa.array(keep))


def _typo_view(con: duckdb.DuckDBPyConnection, left_view: str, role: str) -> str:
    """A temp table of (_id, variant) for one date role of one left view."""
    name = f"typo_{left_view}_{abs(hash(role)) % 10**8}"
    exists = con.execute(f"SELECT count(*) FROM information_schema.tables WHERE table_name = '{name}'").fetchone()[0]
    if not exists:
        base = con.execute(f"SELECT DISTINCT _id, {_q(role)} AS d FROM {left_view} WHERE {_q(role)} IS NOT NULL").fetch_arrow_table()
        idx, variants = typo_variants(base.column("d").combine_chunks())
        table = pa.table({"_id": base.column("_id").take(pa.array(idx)), "v": variants})
        con.register(f"{name}_src", table)
        con.execute(f"CREATE TEMP TABLE {name} AS SELECT * FROM {name}_src")
        con.unregister(f"{name}_src")
    return name


def _candidates(con: duckdb.DuckDBPyConnection, left_view: str, blocks) -> str:
    parts = []
    for block in blocks:
        typo = [k for k in block if len(k) > 2]
        conds, notnull, joins = [], [], ""
        for key in block:
            a, b = key[0], key[1]
            if len(key) > 2:
                view = _typo_view(con, left_view, a)
                joins = f" JOIN {view} tv ON tv._id = l._id"
                conds.append(f"tv.v = r.{_q(b)}")
            else:
                conds.append(_condition(a, b))
                notnull.append(f"l.{_q(a)} IS NOT NULL")
        where = f" WHERE {' AND '.join(notnull)}" if notnull else ""
        del typo
        parts.append(f"SELECT DISTINCT l._id AS l, r._id AS r FROM {left_view} l{joins} JOIN R r ON {' AND '.join(conds)}{where}")
    return " UNION ".join(parts)


def _select_values(left_view: str, pairs_sql: str, compare) -> str:
    """SQL returning l, r and every compared value, one column per role."""
    lcols = [f'l.{_q(c.left)} AS "v{i}_l"' for i, c in enumerate(compare)]
    rcols = []
    for i, c in enumerate(compare):
        for j, role in enumerate(c.right_roles):
            rcols.append(f'r.{_q(role)} AS "v{i}_r{j}"')
        if c.given:
            rcols.append(f'{c.given_side[0]}.{_q(c.given)} AS "v{i}_g"')
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
            out.append(levels(c.kind, a, batch.column(f"v{i}_r0"),
                              batch.column(f"v{i}_g") if c.given else None, c.given_side))
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


def calibration(real: list[float], control: list[float], bin_bits: float = 1.0) -> dict[str, Any]:
    """The local false-match rate by score bin (theory §6, T5).

    At a score s the local false-match rate is the density of placebo pairs over
    the density of real pairs (both resolved 1:1 the same way), per ``bin_bits``
    bin, made non-increasing in the score by pool-adjacent-violators weighted by
    the real count.
    """
    if not real:
        return {"bin_bits": bin_bits, "bins": [], "rate": []}
    r = np.floor(np.asarray(real) / bin_bits).astype(np.int64)
    c = np.floor(np.asarray(control) / bin_bits).astype(np.int64) if control else np.zeros(0, np.int64)
    bins = np.unique(r)[::-1]                       # descending score
    rn = np.array([(r == b).sum() for b in bins], dtype=float)
    cn = np.array([(c == b).sum() for b in bins], dtype=float)
    blocks: list[list[float]] = []                  # [control, real, n_bins]
    for ci, ri in zip(cn, rn, strict=True):
        blocks.append([ci, ri, 1.0])
        while len(blocks) > 1 and blocks[-2][0] / blocks[-2][1] > blocks[-1][0] / blocks[-1][1]:
            x, y = blocks.pop(), blocks.pop()
            blocks.append([x[0] + y[0], x[1] + y[1], x[2] + y[2]])
    rate = np.concatenate([np.full(int(k), min(1.0, cc / rr)) for cc, rr, k in blocks])
    return {"bin_bits": bin_bits, "bins": bins.tolist(), "rate": [round(float(x), 6) for x in rate]}


def apply_calibration(scores: np.ndarray, curve: dict[str, Any]) -> np.ndarray:
    """P(true match) of each score under a calibration curve: 1 - local false-match rate."""
    if not len(scores) or not curve.get("bins"):
        return np.zeros(len(scores))
    bins = np.asarray(curve["bins"], dtype=np.int64)
    rate = np.asarray(curve["rate"], dtype=float)
    order = np.argsort(bins)
    bins, rate = bins[order], rate[order]
    s_bins = np.floor(np.asarray(scores) / float(curve["bin_bits"])).astype(np.int64)
    # The nearest bin at or above (more conservative inside a gap), clamped to the range.
    pos = np.clip(np.searchsorted(bins, s_bins, side="left"), 0, len(bins) - 1)
    return 1.0 - rate[pos]


def match_probability(scores: np.ndarray, real: list[float], control: list[float],
                      bin_bits: float = 1.0) -> np.ndarray:
    """P(true match) of each score, calibrated on this run's own placebo."""
    return apply_calibration(scores, calibration(real, control, bin_bits))


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


def _pool(fm: FieldModel, national: dict[str, Any] | None) -> FieldModel:
    """Shrink a run's m toward the stored national m (POOL_PSEUDO_ANCHORS)."""
    if not national or national.get("comparison") != fm.comparison.name:
        return fm
    n = fm.anchors
    k = POOL_PSEUDO_ANCHORS
    nat = {lv: float(v["m"]) for lv, v in national.get("levels", {}).items() if float(v.get("m", 0.0)) > 0}
    if not nat:
        return fm
    levels_ = set(fm.m) | set(nat)
    m = {lv: (n * fm.m.get(lv, 0.0) + k * nat.get(lv, 0.0)) / (n + k) for lv in levels_}
    pooled = FieldModel(fm.comparison, m, fm.u, anchors=n + k, controls=fm.controls)
    pooled.m_source = {**getattr(fm, "m_source", {}), "pooled_with_national": k}  # type: ignore[attr-defined]
    return pooled


def run_probabilistic(spec: LinkSpec, prob: ProbabilisticSpec, left: pa.Table, right: pa.Table,
                      national: dict[str, Any] | None = None) -> ProbabilisticResult:
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
        others = [c for c in prob.compare if c is not comp and c.is_key]
        anchor_sql, _ = _anchor_sql(others, prob.control_role, shift=False)
        control_sql, has_control = _anchor_sql(others, prob.control_role, shift=True)
        n_anchor = con.execute(f"SELECT count(*) FROM ({anchor_sql})").fetchone()[0]
        n_anchor_control = con.execute(f"SELECT count(*) FROM ({control_sql})").fetchone()[0] if has_control else 0
        m, n_m = _distribution(_levels_of(con, _select_values("L", anchor_sql, [comp]), [comp])[0])
        fm = FieldModel(comp, m, u, anchors=n_m, controls=n_u)
        fm.m_source = {"anchors": n_anchor, "anchor_control": n_anchor_control}  # type: ignore[attr-defined]
        ref = next((d for d in ((national or {}).get("models") or []) if d.get("comparison") == comp.name), None)
        models.append(_pool(fm, ref))
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
    curve = calibration([s for *_x, s in real_best], [s for *_x, s in control_best])
    threshold_source = "own"
    if national and national.get("threshold_bits") is not None and (national.get("calibration") or {}).get("bins"):
        # A slice decides with the nation's threshold and curve (theory §3.2):
        # its own placebo is too small to place a threshold reproducibly.
        t, curve, threshold_source = float(national["threshold_bits"]), national["calibration"], "national"
        real_at_t = sum(1 for *_x, s in real_best if s >= t)
        fdr = sum(1 for *_x, s in control_best if s >= t) / real_at_t if real_at_t else None
    kept = _one_to_one(rl, rr, rscore, t) if t is not None else []
    kept_scores = np.array([x[2] for x in kept])
    p_match = apply_calibration(kept_scores, curve)
    pairs = pa.table({"l": pa.array([x[0] for x in kept], pa.string()),
                      "r": pa.array([x[1] for x in kept], pa.string()),
                      "bits": pa.array([round(x[2], 3) for x in kept], pa.float64()),
                      "p_match": pa.array(np.round(p_match, 5), pa.float64())})
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
                               validations, verdict, threshold_source, curve)


def _inherited(table: pa.Table, dataset: str, items: list[Inherit], *, period: object, geography: object,
               settings: Any, **query_kwargs: Any) -> pa.Table:
    """Attach roles taken from each record's partner in stored links (``Inherit``).

    The stored link of the same scope is used; a record without a partner there
    gets null, which compares as missing (no evidence either way).
    """
    from . import store

    if not items:
        return table
    ids = pc.binary_join_element_wise(pc.cast(table.column("_blob_sha256"), pa.string()),
                                      pc.cast(table.column("_row"), pa.string()), ":")
    con = duckdb.connect()
    con.register("me", pa.table({"_k": ids, "_pos": pa.array(range(table.num_rows), pa.int64())}))
    for item in items:
        via = load_links()[item.via]
        stored = store.load(settings, store.run_key(item.via, "probabilistic", period, geography))
        if stored is None:
            raise FileNotFoundError(f"inherit: no stored {item.via} link for {geography} {period}; link it first")
        mine, other, partner_ds = (("l", "r", via.right.dataset) if via.left.dataset == dataset
                                   else ("r", "l", via.left.dataset))
        partner = role_table(partner_ds, period=period, geography=geography, roles=[item.role], **query_kwargs)
        pid = pc.binary_join_element_wise(pc.cast(partner.column("_blob_sha256"), pa.string()),
                                          pc.cast(partner.column("_row"), pa.string()), ":")
        con.register("pairs", stored[0].select([mine, other]))
        con.register("partner", pa.table({"_k": pid, "v": partner.column(item.role)}))
        values = con.execute(f"""SELECT p.v FROM me LEFT JOIN pairs ON pairs.{mine} = me._k
                                 LEFT JOIN partner p ON p._k = pairs.{other} ORDER BY me._pos""").fetch_arrow_table()
        table = table.append_column(item.as_, values.column("v").combine_chunks())
    return table


def link_probabilistic(name: str, *, period: object, geography: object, right_period: object = None,
                       right_geography: object = None, **query_kwargs: Any) -> ProbabilisticResult:
    """Link under ``name``'s probabilistic block, reading both sides through ``query``.

    ``right_geography`` reads the right side over another scope: a state's
    records against the nation's (``"BR"``), so a partner outside the state is
    found and chance agreement is weighed nationally (step T2).
    """
    from ..config import load_settings
    from .engine import _roles_needed
    from .store import load_params

    spec = load_links()[name]
    prob = load_probabilistic(name)
    inherited = {i.as_ for i in prob.inherit}
    left_roles = sorted((set(_roles_needed(spec, "left")) | {r for c in prob.compare for r in c.side_roles("left")})
                        - inherited)
    right_roles = sorted((set(_roles_needed(spec, "right")) | {r for c in prob.compare for r in c.side_roles("right")})
                         - inherited)
    settings = query_kwargs.get("settings") or load_settings(root=query_kwargs.get("root"))
    left = role_table(spec.left.dataset, period=period, geography=geography, roles=left_roles, **query_kwargs)
    left = _inherited(left, spec.left.dataset, [i for i in prob.inherit if i.side == "left"],
                      period=period, geography=geography, settings=settings, **query_kwargs)
    right_geo = right_geography or geography
    right = role_table(spec.right.dataset, period=right_period or period,
                       geography=right_geo, roles=right_roles, **query_kwargs)
    right = _inherited(right, spec.right.dataset, [i for i in prob.inherit if i.side == "right"],
                       period=right_period or period, geography=right_geo, settings=settings, **query_kwargs)
    national = None if str(geography).upper() == "BR" and right_geography is None else load_params(settings, name)
    return run_probabilistic(spec, prob, left, right, national)


__all__ = ["ProbabilisticResult", "ProbabilisticSpec", "link_probabilistic", "load_probabilistic", "run_probabilistic"]
