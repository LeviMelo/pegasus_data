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
4. **Control** (`placebo`). The same candidate generation and scoring with every left
   date (birth and event dates) moved by half a year *inside the partner
   side's own period* (`placebo.rotation`). A block whose placebo does not reach the coincidences its real
   candidates must hold (`placebo.block_report`) fails the run.
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
- **Pooled error channels, national chance agreement.** A run's m is shrunk
  toward the stored national m of the same spec, by ``POOL_PSEUDO_ANCHORS``
  pseudo-anchors: a state with few anchors leans on the nation, a large one
  keeps its own. Its u is the nation's: a slice's random pairs are not a
  random sample of Brazil. A national run
  stores the reference (``<lake>/links/_params/``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc

from ..config import load_settings
from ..semantics.curation import read_yaml
from . import placebo
from .engine import (
    LinkSpec,
    Report,
    _prepare,
    _roles_needed,
    _side_table,
    links_file,
    load_links,
    stored_key,
    upper95,
    validate,
    where_roles,
)
from .identity import connect, quote, record_ids
from .levels import Levels, levels
from .model import MISSING, Comparison, FieldModel, threshold_for
from .roles import dataset_roles, role_gaps, role_table, unusable_roles, why_unusable

#: Random pairs for chance agreement (u). 200,000 pairs over 50,000-record
#: reservoirs left "birth date equal" (u about 5e-5, a dozen occurrences) with
#: 0.76 bits of sampling noise between seeds, enough to move thousands of
#: national pairs at the threshold (2026-10-03). Drawn over the whole of both
#: sides, 20 million pairs gave it 0.024 bits across five seeds (50 s); 10
#: million halve the time for about 0.035 bits.
RANDOM_PAIRS = 10_000_000
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
    blocks: tuple[tuple[tuple[str, ...], ...], ...]
    target_fdr: float = 0.01
    control_role: str = ""
    inherit: tuple[Inherit, ...] = ()


def load_probabilistic(name: str) -> ProbabilisticSpec:
    body = (read_yaml(links_file()).get("links") or {})[name].get("probabilistic")
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
    blocks = tuple(
        tuple((str(key[0]), "..".join(key[1]) if isinstance(key[1], list) else str(key[1])) for key in block)
        for block in body["blocks"]
    )
    inherit = tuple(
        Inherit(side, str(item["via"]), str(item["role"]), str(item["as"]))
        for side in ("left", "right") for item in ((body.get("inherit") or {}).get(side) or [])
    )
    return ProbabilisticSpec(compare, blocks, float(body.get("target_fdr", 0.01)),
                             str(body.get("control_role") or spec.control_role), inherit)


@dataclass
class ProbabilisticResult(Report):
    models: list[FieldModel] = field(default_factory=list)
    candidates: int = 0
    control_candidates: int = 0
    threshold_bits: float | None = None
    estimated_fdr_percent: float | None = None
    control_above_threshold: int = 0
    fdr_upper95_percent: float | None = None
    threshold_source: str = "own"
    calibration: dict[str, Any] = field(default_factory=dict)
    #: per block: real and placebo candidate pairs and whether the placebo reaches the block (`placebo.block_report`)
    placebo: list[dict[str, Any]] = field(default_factory=list)
    #: comparisons and blocks left out because a role they read is absent or has no value in the scope, with the reason
    skipped: dict[str, str] = field(default_factory=dict)
    #: where the threshold came from when it is not the nation's: "no national reference for <period>"
    reference: str = ""
    #: The error channels per setting (the state that publishes the left
    #: record), each shrunk toward the national channel (ADR-0123).
    models_by_setting: dict[str, list[FieldModel]] = field(default_factory=dict)

    def summary(self) -> dict[str, Any]:
        return {
            **self._common(), "method": "probabilistic", "candidates": self.candidates,
            "control_candidates": self.control_candidates, "threshold_bits": self.threshold_bits,
            "estimated_fdr_percent": self.estimated_fdr_percent,
            "control_pairs_above_threshold": self.control_above_threshold,
            "fdr_upper95_percent": self.fdr_upper95_percent, "threshold_source": self.threshold_source,
            "calibration": self.calibration, "models": [m.as_dict() for m in self.models],
            "placebo": self.placebo, "skipped": self.skipped, "reference": self.reference,
            "models_by_setting": {key: [{"comparison": m.comparison.name, "anchors": m.anchors,
                                         "m": {k: round(v, 5) for k, v in m.m.items()}} for m in ms]
                                  for key, ms in sorted(self.models_by_setting.items())},
        }


def _placebo_ranges(con: duckdb.DuckDBPyConnection, prob: ProbabilisticSpec, left_dates: list[str]
                    ) -> dict[str, tuple[Any, Any]]:
    """For each left date role, the overlap of its own dates and the partner side's roles it is compared or blocked with
    (an interval's start and end both; `placebo.shared_range`): the period a placebo date has to stay inside to meet a
    partner as often as a real one. A role the
    comparisons and blocks do not pair (the control role alone) is placed inside its own side's period."""
    partners: dict[str, set[str]] = {role: set() for role in left_dates}
    for c in prob.compare:
        if c.left in partners:
            partners[c.left].update(c.right_roles)
    for block in prob.blocks:
        for left, right in block:
            if left in partners:
                partners[left].update(right.split(".."))
    found = {role: placebo.shared_range(con, [role], sorted(rights)) if rights else placebo.partner_range(con, [role], "L")
             for role, rights in partners.items()}
    return {role: within for role, within in found.items() if within is not None}


def _materialise(con: duckdb.DuckDBPyConnection, name: str) -> pa.Array:
    """Replace the view ``name`` by a table whose ``_id`` is 0..n-1; returns
    the record ids, indexed by that integer."""
    con.execute(f"""CREATE TEMP TABLE {name}_t AS
        SELECT * EXCLUDE (_id), _id AS _sid, CAST(row_number() OVER (ORDER BY _id) - 1 AS BIGINT) AS _id
        FROM (SELECT DISTINCT ON (_id) * FROM {name})""")
    con.execute(f"CREATE OR REPLACE TEMP VIEW {name} AS SELECT * FROM {name}_t")
    return con.execute(f"SELECT _sid FROM {name}_t ORDER BY _id").to_arrow_table().column("_sid").combine_chunks()


def _condition(a: str, b: str) -> str:
    if ".." in b:
        start, end = b.split("..")
        return f"l.{quote(a)} BETWEEN r.{quote(start)} AND r.{quote(end)}"
    return f"l.{quote(a)} = r.{quote(b)}"


def _block_sql(left_view: str, blocks: Any) -> list[str]:
    """One SQL per block: the (left, right) pairs agreeing on every key of the block."""
    out = []
    for block in blocks:
        conds = [_condition(a, b) for a, b in block]
        notnull = " AND ".join(f"l.{quote(a)} IS NOT NULL" for a, _b in block)
        out.append(f"SELECT DISTINCT l._id AS l, r._id AS r FROM {left_view} l JOIN R r ON {' AND '.join(conds)}"
                   f" WHERE {notnull}")
    return out


def _build_candidates(con: duckdb.DuckDBPyConnection, left_view: str, name: str, blocks: Any) -> list[tuple[int, int]]:
    """The temp table ``name`` of the candidate pairs of all blocks (each pair once), and per block its pairs and the
    left records among them."""
    counts: list[tuple[int, int]] = []
    sqls = _block_sql(left_view, blocks)
    for i, sql in enumerate(sqls):
        con.execute(f"CREATE TEMP TABLE {name}_{i} AS {sql}")
        n, left = con.execute(f"SELECT count(*), count(DISTINCT l) FROM {name}_{i}").fetchone()  # type: ignore[misc]
        counts.append((int(n), int(left)))
    con.execute(f"CREATE TEMP TABLE {name} AS " + " UNION ".join(f"SELECT l, r FROM {name}_{i}" for i in range(len(sqls))))
    for i in range(len(sqls)):
        con.execute(f"DROP TABLE {name}_{i}")
    return counts


def _select_values(left_view: str, pairs_sql: str, compare, setting: bool = False) -> str:
    """SQL returning l, r and every compared value, one column per role
    (and ``s``, the left record's setting, when asked)."""
    lcols = [f'l.{quote(c.left)} AS "v{i}_l"' for i, c in enumerate(compare)]
    rcols = []
    for i, c in enumerate(compare):
        for j, role in enumerate(c.right_roles):
            rcols.append(f'r.{quote(role)} AS "v{i}_r{j}"')
        if c.given:
            rcols.append(f'{c.given_side[0]}.{quote(c.given)} AS "v{i}_g"')
    if setting:
        lcols.append('l."_setting" AS s')
    return f"""SELECT p.l, p.r, {", ".join(lcols + rcols)}
        FROM ({pairs_sql}) p
        JOIN {left_view} l ON l._id = p.l
        JOIN R r ON r._id = p.r"""


def _batch_levels(batch: pa.RecordBatch, compare) -> list[Levels]:
    out: list[Levels] = []
    for i, c in enumerate(compare):
        a = batch.column(f"v{i}_l")
        if c.kind == "interval":
            out.append(levels(c.kind, a, (batch.column(f"v{i}_r0"), batch.column(f"v{i}_r1"))))
        else:
            out.append(levels(c.kind, a, batch.column(f"v{i}_r0"),
                              batch.column(f"v{i}_g") if c.given else None, c.given_side))
    return out


def _factorize(values: np.ndarray | Levels) -> tuple[np.ndarray, np.ndarray]:
    """Integer codes and the distinct values, in one hash pass (no sort, no
    copy to fixed-width strings: np.unique on object arrays was a fifth of a
    link's time, profile 2026-10-03)."""
    if isinstance(values, Levels):
        return values.codes, np.asarray(values.names, dtype=object)
    codes, names = pd.factorize(values, use_na_sentinel=False)
    return codes, np.asarray(names, dtype=object)


def _counts(lv: np.ndarray | Levels) -> dict[str, int]:
    codes, names = _factorize(lv)
    n = np.bincount(codes, minlength=len(names))
    return {str(k): int(c) for k, c in zip(names, n, strict=True) if c and str(k) != MISSING}


def _distributions_stream(con, sql: str, compare) -> list[tuple[dict[str, float], int]]:
    """Each comparison's level distribution over every row of ``sql``, counted
    batch by batch. The real candidates of the newborn link are tens of
    millions of rows with diagnosis lists; materialising them took the process
    past 40 GB on a 32 GB machine (2026-10-03). Counting is exact and bounded."""
    from collections import Counter

    counts: list[Counter[str]] = [Counter() for _ in compare]
    for batch in con.execute(sql).fetch_record_batch(1_000_000):
        if not batch.num_rows:
            continue
        for k, lv in enumerate(_batch_levels(batch, compare)):
            counts[k].update(_counts(lv))
    out = []
    for c in counts:
        c.pop(MISSING, None)
        total = sum(c.values())
        out.append(({str(k): v / total for k, v in c.items()}, int(total)) if total else ({}, 0))
    return out


def _bits_of(fm: FieldModel, lv: np.ndarray | Levels) -> np.ndarray:
    codes, names = _factorize(lv)
    return np.array([fm.bits(str(n)) for n in names])[codes]


def _score_stream(con, sql: str, compare, models: list[FieldModel],
                  by_setting: dict[str, list[FieldModel]] | None = None
                  ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Scores of every candidate pair, streamed in batches; only positive scores are kept.

    With ``by_setting``, each pair is scored with its left record's setting's
    channels (the ``s`` column); a record without a known setting uses ``models``.
    """
    ls: list[np.ndarray] = []
    rs: list[np.ndarray] = []
    scores: list[np.ndarray] = []
    for batch in con.execute(sql).fetch_record_batch(1_000_000):
        if not batch.num_rows:
            continue
        total = np.zeros(batch.num_rows)
        level_arrays = _batch_levels(batch, compare)
        if by_setting and "s" in batch.schema.names:
            s_codes, s_names = _factorize(np.asarray(
                pc.fill_null(batch.column("s"), "").to_numpy(zero_copy_only=False), dtype=object))
            chosen = [by_setting.get(str(v), models) for v in s_names]
            for k, lv in enumerate(level_arrays):
                codes, names = _factorize(lv)
                matrix = np.array([[ms[k].bits(str(n)) for n in names] for ms in chosen])
                total += matrix[s_codes, codes]
        else:
            for fm, lv in zip(models, level_arrays, strict=True):
                total += _bits_of(fm, lv)
        keep = np.nonzero(total > 0)[0]
        if len(keep):
            ls.append(batch.column("l").to_numpy()[keep])
            rs.append(batch.column("r").to_numpy()[keep])
            scores.append(total[keep])
    if not scores:
        return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0)
    return np.concatenate(ls), np.concatenate(rs), np.concatenate(scores)


#: A record is linked only when its best candidate beats the runner-up by
#: this much evidence, on both sides: log2(19) bits, the best at least 95%
#: likely between the two. Without it, a birth date + sex + hospital shared
#: by ~15 newborns a day in one maternity hospital was resolved by picking one
#: of them, and a negative control cannot see that error: the true baby IS
#: among the candidates (RR 2022, 3,294 "viable" pairs; ADR-0113).
AMBIGUITY_MARGIN_BITS = float(np.log2(19))


def _best_two(key: np.ndarray, rank: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Per candidate: is it its key's best (lowest rank), and the rank of the
    key's runner-up (or -1). ``rank`` orders candidates by descending score,
    ties broken stably."""
    order = np.lexsort((rank, key))
    k = key[order]
    first = np.ones(len(k), bool)
    first[1:] = k[1:] != k[:-1]
    is_best = np.zeros(len(key), bool)
    is_best[order[first]] = True
    second = np.full(len(key), -1, np.int64)
    has_second = np.zeros(len(k), bool)
    has_second[:-1] = first[:-1] & ~first[1:]
    second[order[has_second]] = order[np.nonzero(has_second)[0] + 1]
    return is_best, second


def _one_to_one(ls: np.ndarray, rs: np.ndarray, scores: np.ndarray, threshold: float
                ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pairs that are each side's clear best, at or above the threshold.

    A pair is kept when, among its left record's candidates, it scores at
    least AMBIGUITY_MARGIN_BITS above the next, and the same holds among its
    right record's candidates. Candidates below zero never reach here, so a
    lone candidate is compared with nothing and passes. Vectorised over
    integer ids (the dict loop was 9% of a link, profile 2026-10-03).
    """
    if not len(scores):
        return np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0)
    order = np.argsort(-scores, kind="stable")
    rank = np.empty(len(scores), np.int64)
    rank[order] = np.arange(len(scores))
    best_l, second_l = _best_two(np.asarray(ls), rank)
    best_r, second_r = _best_two(np.asarray(rs), rank)
    gap_l = np.where(second_l >= 0, scores - scores[np.maximum(second_l, 0)], np.inf)
    gap_r = np.where(second_r >= 0, scores - scores[np.maximum(second_r, 0)], np.inf)
    keep = (best_l & best_r & (scores >= threshold)
            & (gap_l >= AMBIGUITY_MARGIN_BITS) & (gap_r >= AMBIGUITY_MARGIN_BITS))
    idx = np.nonzero(keep)[0]
    idx = idx[np.argsort(rank[idx])]
    return np.asarray(ls)[idx], np.asarray(rs)[idx], scores[idx]


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


def _anchor_control(others: list[Comparison], control_role: str, ranges: dict[str, tuple[Any, Any]],
                    days: int) -> str:
    """The left side of the anchors' control: the left records with the key the control moves (the control role when an
    anchor key reads it, else the first date key) moved round the partner's period (`placebo.rotation`, ``days`` as the
    deterministic passes move it); "" when there is no such key."""
    date_keys = [c for c in others if c.kind in ("date", "interval")]
    role = control_role if any(c.left == control_role for c in others) else (date_keys[0].left if date_keys else None)
    sql = placebo.rotation(role, ranges.get(role), days) if role else None
    return f"({placebo.moved_sql('L', {role: sql})})" if role and sql else ""


def _anchor_sql(others: list[Comparison], left: str = "L") -> str:
    """Pairs linked 1:1 on every other comparison, among the records of ``left`` (the left side, or its control
    `_anchor_control`).

    A pair is kept when each of its records has exactly one partner under the
    join: the 1:1 rule of the deterministic engine, which also works for an
    interval (a birth day BETWEEN an admission's start and end).
    """
    if all(".." not in c.right for c in others):
        # Equality keys: a record has exactly one partner exactly when the
        # other side's group of its key has one record. Grouping each side
        # avoids the join of every record to every member of its key group:
        # leaving the birth date out of the newborn link joined each admission
        # to every birth of its sex in its hospital, and held the process at
        # 18 GB (2026-10-03). Same pairs as the join below.
        lk = ", ".join(f"{quote(c.left)} AS k{i}" for i, c in enumerate(others))
        rk = ", ".join(f"{quote(c.right)} AS k{i}" for i, c in enumerate(others))
        lnn = " AND ".join(f"{quote(c.left)} IS NOT NULL" for c in others)
        rnn = " AND ".join(f"{quote(c.right)} IS NOT NULL" for c in others)
        on = " AND ".join(f"lg.k{i} = rg.k{i}" for i in range(len(others)))
        return f"""WITH lg AS (SELECT {lk}, count(*) AS n, min(_id) AS id FROM {left} WHERE {lnn} GROUP BY ALL),
                        rg AS (SELECT {rk}, count(*) AS n, min(_id) AS id FROM R WHERE {rnn} GROUP BY ALL)
                   SELECT lg.id AS l, rg.id AS r FROM lg JOIN rg ON {on} WHERE lg.n = 1 AND rg.n = 1"""
    cond = " AND ".join(_condition(c.left, c.right) for c in others)
    notnull = " AND ".join(f"l.{quote(c.left)} IS NOT NULL" for c in others)
    return f"""WITH j AS (SELECT DISTINCT l._id AS l, r._id AS r FROM {left} l
                         JOIN R r ON {cond} WHERE {notnull})
               SELECT l, r FROM j
               QUALIFY count(*) OVER (PARTITION BY l) = 1 AND count(*) OVER (PARTITION BY r) = 1"""


def _by_setting(comp: Comparison, levels_: np.ndarray, settings: np.ndarray, reference: dict[str, float],
                overall: FieldModel) -> dict[str, FieldModel]:
    """One channel per setting: the setting's anchors shrunk toward
    ``reference`` (the national m) with POOL_PSEUDO_ANCHORS pseudo-anchors.

    The national run shrinks toward its own m and a slice toward the stored
    national m, so a state's channel is the same whichever run estimates it
    (theory §2.3). SP's own anchors gave a different-state residence -7.9
    bits against -6.5 nationally; scored with one national channel, the
    national run and the SP slice disagreed on 578 pairs (2026-10-03).
    """
    k = POOL_PSEUDO_ANCHORS
    usable = levels_ != MISSING
    out: dict[str, FieldModel] = {}
    for value in np.unique(settings[usable]):
        if not value:
            continue
        mine = levels_[usable & (settings == value)]
        names, counts = np.unique(mine.astype(str), return_counts=True)
        own = dict(zip(names.tolist(), counts.tolist(), strict=True))
        n = len(mine)
        m = {lv: (own.get(lv, 0) + k * reference.get(lv, 0.0)) / (n + k) for lv in set(own) | set(reference)}
        fm = FieldModel(comp, m, overall.u, anchors=n + k, controls=overall.controls)
        fm.m_source = {"setting_anchors": n, "pooled_with": k}  # type: ignore[attr-defined]
        out[str(value)] = fm
    return out


#: Kinds whose "equal" level is plain equality of the two values, so its
#: chance rate is countable from each side's value frequencies.
_EXACT_EQUAL_KINDS = frozenset({"exact", "date", "municipality", "integer", "number_distance"})


def _exact_equal(con: duckdb.DuckDBPyConnection, comp, u: dict[str, float]) -> dict[str, float]:
    """u with its "equal" level counted exactly: Σ_v n_L(v) n_R(v) / (n_L n_R).

    Sampled pairs left a rare agreement (a birth date, u about 5e-5) with
    0.024 bits of noise at 10 million pairs; counting removes it (theory §11).
    The other levels keep their sampled shares of the rest. Over non-missing
    pairs, as the sample's distribution is. Not for a comparison conditioned
    on another role (residence given the place of care), whose "equal" is
    split by that role, nor an interval.
    """
    if comp.kind not in _EXACT_EQUAL_KINDS or comp.given or len(comp.right_roles) != 1:
        return u
    left, right = quote(comp.left), quote(comp.right_roles[0])
    try:
        n_l, n_r, agree = con.execute(f"""
            WITH a AS (SELECT {left} AS v, count(*) AS c FROM L WHERE {left} IS NOT NULL GROUP BY 1),
                 b AS (SELECT {right} AS v, count(*) AS c FROM R WHERE {right} IS NOT NULL GROUP BY 1)
            SELECT (SELECT sum(c) FROM a), (SELECT sum(c) FROM b),
                   (SELECT sum(a.c * b.c) FROM a JOIN b ON a.v = b.v)""").fetchone() or (None, None, None)
    except duckdb.Error:
        return u
    if not n_l or not n_r:
        return u
    exact = float(agree or 0) / (float(n_l) * float(n_r))
    sampled = u.get("equal", 0.0)
    rest = (1.0 - exact) / (1.0 - sampled) if sampled < 1.0 else 0.0
    out = {**{lv: p * rest for lv, p in u.items()}, "equal": exact}
    return {lv: p for lv, p in out.items() if p > 0}


def _national_channels(model: dict[str, Any]) -> tuple[dict[str, float], dict[str, float]]:
    """(m, u) of a stored national model: the unrounded values it stores under ``exact`` (`FieldModel.as_dict`), else the
    rounded ``levels`` of a report written before they were."""
    exact = model.get("exact")
    if exact:
        return {k: float(v) for k, v in exact["m"].items()}, {k: float(v) for k, v in exact["u"].items()}
    levels_ = model.get("levels", {})
    return ({lv: float(v["m"]) for lv, v in levels_.items()}, {lv: float(v["u"]) for lv, v in levels_.items()})


def _pool(fm: FieldModel, national: dict[str, Any] | None) -> FieldModel:
    """Shrink a run's m toward the stored national m (POOL_PSEUDO_ANCHORS)."""
    if not national or national.get("comparison") != fm.comparison.name:
        return fm
    n = fm.anchors
    k = POOL_PSEUDO_ANCHORS
    nat_m, nat_u = _national_channels(national)
    nat = {lv: v for lv, v in nat_m.items() if v > 0}
    if not nat:
        return fm
    levels_ = set(fm.m) | set(nat)
    m = {lv: (n * fm.m.get(lv, 0.0) + k * nat.get(lv, 0.0)) / (n + k) for lv in levels_}
    # Chance agreement is the nation's, not the slice's: random pairs of a
    # state's records against the nation share a residence far less often than
    # two random Brazilians (SE: u 0.00067 against 0.0056), which put a slice's
    # scores on another scale than the national threshold (2026-10-03).
    u = {**fm.u, **nat_u} if nat_u else fm.u
    pooled = FieldModel(fm.comparison, m, u, anchors=n + k,
                        controls=max(fm.controls, int(national.get("controls") or 0)))
    pooled.m_source = {**fm.m_source, "pooled_with_national": k}
    return pooled


def _usable(prob: ProbabilisticSpec, left: pa.Table, right: pa.Table) -> tuple[ProbabilisticSpec, dict[str, str]]:
    """The comparisons and blocks the tables can serve, and why the others are left out. A role the scope lacks, or
    no value of which normalised, makes a null column: a key comparison on it left every other comparison without
    anchors, and a block on it generated nothing, with no note (``absent_roles`` had no reader). Raises when no block
    is left."""
    from dataclasses import replace as _replace

    left_names = {r for c in prob.compare for r in c.side_roles("left")} | {k[0] for b in prob.blocks for k in b}
    right_names = ({r for c in prob.compare for r in c.side_roles("right")}
                   | {r for b in prob.blocks for k in b for r in k[1].split("..")})
    left_bad = unusable_roles(left, sorted(left_names))
    right_bad = unusable_roles(right, sorted(right_names))

    def why(lefts: Any, rights: Any) -> str:
        return why_unusable(left_bad, right_bad, lefts, rights)

    skipped: dict[str, str] = {}
    compare = []
    for c in prob.compare:
        reason = why(c.side_roles("left"), c.side_roles("right"))
        if reason:
            skipped[f"comparison {c.name}"] = reason
        else:
            compare.append(c)
    blocks = []
    for b in prob.blocks:
        reason = why([k[0] for k in b], [r for k in b for r in k[1].split("..")])
        if reason:
            skipped["block " + " + ".join(f"{a}~{r}" for a, r in b)] = reason
        else:
            blocks.append(b)
    if not blocks:
        raise ValueError(f"no block can run on these tables ({skipped}); the scope lacks or cannot read a role "
                         "every block keys on")
    return _replace(prob, compare=tuple(compare), blocks=tuple(blocks)), skipped


def _used_roles(spec: LinkSpec, prob: ProbabilisticSpec) -> tuple[set[str], set[str]]:
    """The roles each side contributes to the probabilistic method (comparisons, blocks, side filters): a validation
    reading one agrees by construction (`engine.validate`)."""
    left = {r for c in prob.compare for r in c.side_roles("left")} | {k[0] for b in prob.blocks for k in b}
    right = {r for c in prob.compare for r in c.side_roles("right")} | {r for b in prob.blocks for k in b for r in k[1].split("..")}
    return left | where_roles(spec.left), right | where_roles(spec.right)


def _anchor_channel(con: duckdb.DuckDBPyConnection, comp: Comparison, anchors: pa.Table, anchor_levels: Any,
                    control_sql: str, n_anchor_control: int) -> tuple[dict[str, float], int]:
    """m of a comparison: the level distribution of its anchors less that of the chance pairs among them. The anchors
    are pairs agreeing 1:1 on every other key field; a weakly keyed set (dengue deaths without the death day: sex,
    integer age, residence, facility) holds coincidences, which would flatten the "equal" level. The control join (the
    same over a shifted left key) counts them and their levels, and its counts are subtracted from the anchors'."""
    counts = _counts(anchor_levels) if anchors.num_rows else {}
    if n_anchor_control:
        ctl = con.execute(_select_values("L", control_sql, [comp])).to_arrow_table()
        if ctl.num_rows:
            chance = _counts(_batch_levels(ctl.combine_chunks().to_batches()[0], [comp])[0])
            counts = {k: max(v - chance.get(k, 0), 0) for k, v in counts.items()}
    total = sum(counts.values())
    return ({k: v / total for k, v in counts.items() if v} if total else {}), int(total)


def run_probabilistic(spec: LinkSpec, prob: ProbabilisticSpec, left: pa.Table, right: pa.Table,
                      national: dict[str, Any] | None = None) -> ProbabilisticResult:
    from dataclasses import replace as _replace

    prob, skipped = _usable(prob, left, right)
    con = connect()
    setting_role = dataset_roles(spec.left.dataset).setting
    with_setting = bool(setting_role and setting_role in left.column_names)
    if with_setting:
        left = left.append_column("_setting",
                                  pc.utf8_slice_codeunits(pc.cast(left.column(setting_role), pa.string()), 0, 2))
    # An interval is compared as an interval here: the deterministic engine's
    # one-row-per-day explosion is its way of making "inside" an equality.
    n_left = _prepare(con, "L", left, _replace(spec.left, explode_days=None, explode_values=None), materialise=False)
    n_right = _prepare(con, "R", right, _replace(spec.right, explode_days=None, explode_values=None), materialise=False)
    # Each side once, as a table keyed by an integer: every later query joined
    # 32-character ids and re-deduplicated the whole view (57% of a link's
    # time was SQL, profile 2026-10-03). The record ids come back at the end.
    ids = {name: _materialise(con, name) for name in ("L", "R")}
    # u: RANDOM_PAIRS pairs drawn uniformly over both whole sides by hashing
    # an index into the integer ids (0..n-1, ordered by record id): a function
    # of the record sets alone, not of the order rows were scanned in, and
    # counted batch by batch. It replaces 50,000-record reservoirs paired by a
    # stride, whose draw moved with the row order.
    random_pairs = f"""
        WITH n AS (SELECT (SELECT count(*) FROM L) AS nl, (SELECT count(*) FROM R) AS nr)
        SELECT CAST(hash(k, 1) % n.nl AS BIGINT) AS l, CAST(hash(k, 2) % n.nr AS BIGINT) AS r
        FROM range({RANDOM_PAIRS}) t(k), n"""
    # A slice decides with the nation's u (``_pool``): drawing its own is waste.
    national_u = bool(national and national.get("models"))
    random_u = ([({}, 0)] * len(prob.compare) if national_u
                else _distributions_stream(con, _select_values("L", random_pairs, prob.compare), prob.compare))
    if not national_u:
        random_u = [(_exact_equal(con, c, u), n) if u else (u, n)
                    for c, (u, n) in zip(prob.compare, random_u, strict=True)]
    # An evidence-only comparison (an inherited AIH, a P07 code) learns its
    # chance agreement among the real candidates: the records the blocks put
    # beside a record (same hospital, same day), all but one of them
    # non-matches, so u is slightly overstated (conservative). Random pairs
    # across the country almost never had nearby AIHs ("within 100" earned +15
    # bits), and the placebo's candidates, born 400 days away, never did
    # either: AIH proximity depends on the day the placebo moves (2026-10-03).
    block_roles = {k[0] for block in prob.blocks for k in block}
    left_dates = sorted({c.left for c in prob.compare if c.kind in ("date", "interval")
                         or (c.kind == "order" and pa.types.is_date(left.schema.field(c.left).type))}
                        | {r for r in block_roles if r in left.column_names
                           and pa.types.is_date(left.schema.field(r).type)}
                        | {prob.control_role})
    ranges = _placebo_ranges(con, prob, left_dates)
    con.execute("CREATE OR REPLACE TEMP TABLE LS AS " + placebo.moved_sql("L", {
        role: sql for role, within in ranges.items() if (sql := placebo.rotation(role, within, placebo.placebo_days()))}))
    evidence_only = [c for c in prob.compare if not c.is_key]
    # The candidate pairs, real and placebo, built once each, and counted per block.
    real_counts = _build_candidates(con, "L", "C", prob.blocks)
    control_counts = _build_candidates(con, "LS", "CS", prob.blocks)
    placebo_rows, placebo_failures = placebo.block_report(prob.blocks, real_counts, control_counts)
    candidate_u = (dict(zip([c.name for c in evidence_only],
                            _distributions_stream(con, _select_values("L", "SELECT l, r FROM C", evidence_only),
                                                  evidence_only), strict=True))
                   if evidence_only else {})
    models: list[FieldModel] = []
    per_setting: list[dict[str, FieldModel]] = []
    for i, comp in enumerate(prob.compare):
        u, n_u = candidate_u[comp.name] if comp.name in candidate_u else random_u[i]
        others = [c for c in prob.compare if c is not comp and c.is_key]
        anchor_sql = _anchor_sql(others)
        control_left = _anchor_control(others, prob.control_role, ranges, spec.control_shift_days)
        control_sql = _anchor_sql(others, control_left) if control_left else ""
        n_anchor = con.execute(f"SELECT count(*) FROM ({anchor_sql})").fetchone()[0]  # type: ignore[index]
        n_anchor_control = con.execute(f"SELECT count(*) FROM ({control_sql})").fetchone()[0] if control_sql else 0  # type: ignore[index]
        anchors = con.execute(_select_values("L", anchor_sql, [comp], setting=with_setting)).to_arrow_table()
        anchor_levels: Any = (_batch_levels(anchors.combine_chunks().to_batches()[0], [comp])[0] if anchors.num_rows
                         else np.array([], dtype=object))
        m, n_m = _anchor_channel(con, comp, anchors, anchor_levels, control_sql, int(n_anchor_control))
        fm = FieldModel(comp, m, u, anchors=n_m, controls=n_u)
        fm.m_source = {"anchors": int(n_anchor), "anchor_control": int(n_anchor_control),
                       "chance_share": round(n_anchor_control / n_anchor, 4) if n_anchor else None}
        ref = next((d for d in ((national or {}).get("models") or []) if d.get("comparison") == comp.name), None)
        pooled = _pool(fm, ref)
        models.append(pooled)
        if with_setting and anchors.num_rows:
            reference = _national_channels(ref)[0] if ref else m
            settings_ = np.asarray(pc.fill_null(anchors.column("s"), "").to_numpy(zero_copy_only=False),
                                   dtype=object)
            per_setting.append(_by_setting(comp, anchor_levels.strings(), settings_, reference, pooled))
        else:
            per_setting.append({})
    # Settings with anchors on every comparison get their own channels; the
    # rest score with the overall ones.
    by_setting = ({key: [ps[key] for ps in per_setting]
                   for key in set.intersection(*(set(ps) for ps in per_setting))}
                  if with_setting and per_setting and all(per_setting) else {})
    # Candidates, real and control, scored as they stream.
    rl, rr, rscore = _score_stream(con, _select_values("L", "SELECT l, r FROM C", prob.compare,
                                                       setting=with_setting), prob.compare, models, by_setting)
    cl, cr, cscore = _score_stream(con, _select_values("LS", "SELECT l, r FROM CS", prob.compare,
                                                       setting=with_setting), prob.compare, models, by_setting)
    # Threshold on 1:1-resolved scores, so real and control are counted alike.
    real_scores = _one_to_one(rl, rr, rscore, float("-inf"))[2]
    control_scores = _one_to_one(cl, cr, cscore, float("-inf"))[2]
    t, fdr = threshold_for(real_scores.tolist(), control_scores.tolist(), prob.target_fdr,
                           placebo_candidates=sum(n for n, _l in control_counts))
    curve = calibration(real_scores.tolist(), control_scores.tolist())
    threshold_source = "own"
    if national and national.get("threshold_bits") is not None and (national.get("calibration") or {}).get("bins"):
        # A slice decides with the nation's threshold and curve (theory §3.2):
        # its own placebo is too small to place a threshold reproducibly.
        t, curve, threshold_source = float(national["threshold_bits"]), national["calibration"], "national"
        real_at_t = int((real_scores >= t).sum())
        fdr = int((control_scores >= t).sum()) / real_at_t if real_at_t else None
    kl, kr, kept_scores = (_one_to_one(rl, rr, rscore, t) if t is not None
                           else (np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0)))
    p_match = apply_calibration(kept_scores, curve)
    pairs = pa.table({"l": ids["L"].take(pa.array(kl)), "r": ids["R"].take(pa.array(kr)),
                      "bits": pa.array(np.round(kept_scores, 3), pa.float64()),
                      "p_match": pa.array(np.round(p_match, 5), pa.float64())})
    con.register("linked_ids", pa.table({"l": pa.array(kl, pa.int64()), "r": pa.array(kr, pa.int64())}))
    con.execute("CREATE OR REPLACE TEMP TABLE linked AS SELECT l, r FROM linked_ids")
    validations = validate(con, spec, _used_roles(spec, prob))
    fdr_percent = round(100.0 * fdr, 2) if fdr is not None else None
    # The estimate rests on few control pairs when the left side is small (a
    # state's infant deaths): say how few, and the 95% upper bound (Poisson on
    # the control count, over the real pairs kept).
    control_kept = int((control_scores >= t).sum()) if t is not None else 0
    upper = upper95(control_kept, len(kl))
    result = ProbabilisticResult(
        spec.name, n_left, n_right, pairs, validations, role_gaps={"left": role_gaps(left), "right": role_gaps(right)},
        models=models, candidates=len(rscore), control_candidates=len(cscore),
        threshold_bits=round(t, 2) if t is not None else None, estimated_fdr_percent=fdr_percent,
        control_above_threshold=control_kept, fdr_upper95_percent=upper, threshold_source=threshold_source,
        calibration=curve, placebo=placebo_rows, skipped=skipped, models_by_setting=by_setting)
    result.decide(fdr_percent, upper, placebo_failures=placebo_failures,
                  left_out=[f"{what} left out: {why}" for what, why in skipped.items()])
    return result


def _inherited(table: pa.Table, dataset: str, items: list[Inherit], *, period: object, geography: object,
               settings: Any, run_geography: object = None, optional: frozenset[str] = frozenset(),
               **query_kwargs: Any) -> pa.Table:
    """Attach roles taken from each record's partner in stored links (``Inherit``).

    The stored link of the side's scope is used, else the run's own (a side read nationally, the neonatal link's
    births, still finds the run's state's delivery link: its records are most of the side's partners), else the
    national one (it covers every slice's records); a record without a partner there gets null, which compares as
    missing (no evidence either way).
    """
    from .._query_engine.model import _period
    from . import store

    if not items:
        return table
    ids = record_ids(table)
    con = connect()
    con.register("me", pa.table({"_k": ids, "_pos": pa.array(range(table.num_rows), pa.int64())}))
    for item in items:
        via = load_links()[item.via]
        # One stored link per year of the period (a padded side spans two);
        # each the scope's own, else the national one, which covers every
        # slice's records (theory §3.2). A year with neither leaves its
        # records without the inherited value: missing, not evidence.
        span = _period(period)
        if span is None:
            raise ValueError("an inherited link is read per year: pass a period")
        found, years = [], []
        for year in span.years:
            scopes = list(dict.fromkeys(str(g) for g in (geography, run_geography, "BR") if g is not None))
            run = next((r for g in scopes if (r := store.load(settings, stored_key(item.via, "probabilistic", str(year), g)))),
                       None)
            if run is not None:
                found.append(run[0].select(["l", "r"]))
                years.append(str(year))
        if not found:
            if item.as_ in optional:
                # a role only a validation reads: without its stored link the validation says it is unavailable
                # (`engine.validate`); the run is not refused for want of a test
                continue
            raise FileNotFoundError(f"inherit: no stored {item.via} link for {geography} {period}; link it first")
        stored = (pa.concat_tables(found),)
        # The partner is read only for the years a link exists: reading it over
        # a padded period labelled a whole national year for nothing.
        partner_period: object = years[0] if len(years) == 1 else (years[0], years[-1])
        mine, other, partner_ds = (("l", "r", via.right.dataset) if via.left.dataset == dataset
                                   else ("r", "l", via.left.dataset))
        partner = role_table(partner_ds, period=partner_period, geography=geography, roles=[item.role], **query_kwargs)
        pid = record_ids(partner)
        con.register("pairs", stored[0].select([mine, other]))
        con.register("partner", pa.table({"_k": pid, "v": partner.column(item.role)}))
        values = con.execute(f"""SELECT p.v FROM me LEFT JOIN pairs ON pairs.{mine} = me._k
                                 LEFT JOIN partner p ON p._k = pairs.{other} ORDER BY me._pos""").to_arrow_table()
        table = table.append_column(item.as_, values.column("v").combine_chunks())
    return table


def link_probabilistic(name: str, *, period: object, geography: object, right_period: object = None,
                       right_geography: object = None, spec: LinkSpec | None = None,
                       **query_kwargs: Any) -> ProbabilisticResult:
    """Link under ``name``'s probabilistic block, reading both sides through ``query``.

    ``right_geography`` reads the right side over another scope: a state's
    records against the nation's (``"BR"``), so a partner outside the state is
    found and chance agreement is weighed nationally (step T2). ``spec`` is the
    spec as bound to a caller's codes (`engine.bind`); a cohort has no national
    reference to decide with.
    """
    from .store import load_params

    spec = spec or load_links()[name]
    prob = load_probabilistic(name)
    inherited = {i.as_ for i in prob.inherit}
    setting = dataset_roles(spec.left.dataset).setting
    left_roles = sorted((set(_roles_needed(spec, "left")) | {r for c in prob.compare for r in c.side_roles("left")}
                         | ({setting} if setting else set())) - inherited)
    right_roles = sorted((set(_roles_needed(spec, "right")) | {r for c in prob.compare for r in c.side_roles("right")})
                         - inherited)
    settings = query_kwargs.get("settings") or load_settings(root=query_kwargs.get("root"))
    rest = {k: v for k, v in query_kwargs.items() if k != "settings"}     # `settings` is passed once, resolved
    # each side's own filter is applied where each year is read (`engine._side_table`), as the deterministic engine
    # reads it: a state's maternal deaths read every admission of the country, both sexes, before keeping the women's
    # (12.5 GB for RR 2022, 2026-11-09); `_prepare` applies it again, a no-op on rows it already kept

    left = _side_table(spec.left, left_roles, period=period, geography=geography, **query_kwargs)
    # an inherited role the model compares is required; one only a validation reads is optional
    compared = {r for c in prob.compare for r in (*c.side_roles("left"), *c.side_roles("right"))}
    optional = frozenset(i.as_ for i in prob.inherit if i.as_ not in compared)
    left = _inherited(left, spec.left.dataset, [i for i in prob.inherit if i.side == "left"],
                      period=period, geography=geography, settings=settings, optional=optional, **rest)
    right_geo = right_geography or geography
    right = _side_table(spec.right, right_roles, period=right_period or period, geography=right_geo, **query_kwargs)
    right = _inherited(right, spec.right.dataset, [i for i in prob.inherit if i.side == "right"],
                       period=right_period or period, geography=right_geo, settings=settings, run_geography=geography,
                       optional=optional, **rest)
    national, reference = None, ""
    if not (str(geography).upper() == "BR" and right_geography is None) and spec.bound is None:
        # a slice decides with the national run of ITS period (`store.save_params`: one reference per period)
        key = stored_key(name, "probabilistic", period, "BR", right_period=right_period)
        national = load_params(settings, key)
        if national is None:
            reference = f"no current national reference for {key.period}: decided on the slice's own placebo"
    result = run_probabilistic(spec, prob, left, right, national)
    result.reference = reference
    return result


__all__ = ["ProbabilisticResult", "ProbabilisticSpec", "link_probabilistic", "load_probabilistic", "run_probabilistic"]
