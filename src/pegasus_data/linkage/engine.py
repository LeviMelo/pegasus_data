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
3. **Negative control** (`placebo`). The same join over the same remaining records, with
   one left key moved (a birth date by a week, round the partner's period): nobody is the same person as
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
agreed 99.6-100%, and carried "viable" over a held-out 81-87%). A validation compares at least `thresholds.engine.min_compared` pairs, or
it is not evidence. A control that cannot reach its partner's values (a date moved out of the partner's period) is no
control, and the run is not viable: an empty placebo reads as "no false pairs".
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, cast

import duckdb
import numpy as np
import pyarrow as pa

from ..config import curation_root, load_settings
from ..normalize.time import year_of
from ..semantics.curation import read_yaml
from ..semantics.epoch import curated
from . import placebo
from .identity import DUP_SQL, RECORD_ID_SQL, connect, quote
from .roles import dataset_roles, role_gaps, role_table, unusable_roles, why_unusable


def links_file() -> Path:
    return curation_root() / "links.yml"


def chance_drop() -> float:
    """The chance rate (%) from which a pass is dropped, declared in ``links.yml`` (``thresholds.engine``)."""
    return float(raw_links()["thresholds"]["engine"]["chance_drop_pct"])


def min_compared() -> int:
    """Pairs a validation must compare to count (a proportion of fewer says nothing), declared in ``links.yml``."""
    return int(raw_links()["thresholds"]["engine"]["min_compared"])



@dataclass(frozen=True, slots=True)
class Side:
    dataset: str
    where: str = ""
    explode_days: tuple[str, str | int, str] | None = None  # (start role, end role or a count of days, new role)
    group: tuple[str, ...] = ()                       # one record per group (a delivery)
    latest: str = ""                                  # the group's record with the latest value of this role stands for it
    pad_years: tuple[int, int] = (0, 0)               # years read before and after the left period
    earliest: str = ""                                # ... or the one with the earliest value (a cohort's first admission)


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
    among: str | None = None  # the pairs it judges: a condition over (l.*, r.*), e.g. the admissions that ended in death


@dataclass(frozen=True, slots=True)
class CodesParam:
    """A spec's declared parameter: the caller's codes filter, by prefix, the role a ``match`` names on ``side``
    (`bind`). ``roles`` maps each match the spec offers to its role ("principal": the principal diagnosis, "any": every
    diagnosis, "procedure": the procedure performed, or whatever the declaration names); the first is the default.
    ``partner`` maps a match to the other side's role the same codes also filter (a glioma's surgery meets only a glioma's
    radiotherapy, not every cancer's: 606 pairs against 310 by chance before, Sao Paulo 2021); a match it does not name
    filters one side only."""

    side: str
    roles: dict[str, str]
    partner: dict[str, str] = field(default_factory=dict)

    @property
    def role(self) -> str:
        return next(iter(self.roles.values()))


@dataclass(frozen=True, slots=True)
class Codes:
    """The caller's values of a `CodesParam`, as a run was made with them."""

    codes: tuple[str, ...]
    match: str = "principal"

    @property
    def digest(self) -> str:
        return hashlib.sha256(json.dumps([self.codes, self.match]).encode()).hexdigest()[:10]

    def as_dict(self) -> dict[str, Any]:
        return {"codes": list(self.codes), "match": self.match}


@dataclass(frozen=True, slots=True)
class Outcome:
    """What a cohort link follows: ``origin`` a date role of the left side (the zero of the follow-up clock) and ``event``
    the date role of the right side that happens to the person (a death). The event is carried into the run's pairs and
    its range into the report, so a reader needs neither side's table again (`followup`)."""

    origin: str
    event: str
    #: the person's first event, not their only one: a later admission happens many times to one person, and a cohort
    #: whose record pairs with two partners keeps the earliest (a death happens once: two candidates pair with neither)
    first: bool = False
    #: a role both sides carry that must differ in a pair: the index admission is not its own readmission (the AIH)
    differ: str = ""


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
    #: the parameter the caller gives (`params:` in links.yml): a spec that declares it is run per set of codes
    #: (`bind`), never alone, and its runs are keyed by them
    params: CodesParam | None = None
    outcome: Outcome | None = None
    #: the caller's codes this spec was bound to (`bind`); None for a spec as declared
    bound: Codes | None = None


def _side(body: dict[str, Any]) -> Side:
    explode = body.get("explode_days")
    if body.get("latest") and body.get("earliest"):
        raise ValueError("a link side picks its group's record by `latest` or by `earliest`, not both")
    return Side(
        dataset=str(body["dataset"]).upper(),
        where=str(body.get("where") or ""),
        explode_days=tuple(explode) if explode else None,  # type: ignore[arg-type]
        group=tuple(body.get("group") or ()),
        latest=str(body.get("latest") or ""),
        pad_years=tuple(int(x) for x in body.get("pad_years") or (0, 0)),  # type: ignore[arg-type]
        earliest=str(body.get("earliest") or ""),
    )


def stored_key(name: str, method: str, period: object, geography: object, *,
               right_period: object = None, right_geography: object = None, params: Codes | None = None) -> Any:
    """The key a run of ``name`` is stored under: the scope, and the partner's
    scope when it differs, including a side's padded period, and the caller's
    ``params`` of a parameterised spec (two topics' runs of one spec never share
    a file). Every reader of
    stored runs (entities, inheritance) must use it: computing the key from the
    left scope alone missed every padded spec, and entities lost the infant
    deaths and newborns without a word (2026-10-03). The partner's geography is derived here as `link` derives it
    (`right_geography_for`: a state's run reads a side filed by another place nationally): the readers computed the key
    without it and found no stored run of any such link (the newborn link's inherited delivery link, the timeline;
    2026-11-09)."""
    from . import store

    spec = load_links()[name]
    if right_period is None and spec.right.pad_years != (0, 0):
        right_period = padded_period(period, spec.right)
    right_geography = right_geography_for(spec, geography, right_geography)
    return store.run_key(name, method, period if right_period is None else (period, right_period),
                         geography if right_geography is None else (geography, right_geography),
                         params.digest if params else "")


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

    return (str(cast(int, year_of(p.start)) - before), str(cast(int, year_of(p.end)) + after))


@curated
def raw_links() -> dict[str, Any]:
    """`links.yml` as one process read it: the specs a run uses and the digest its store key carries come from this one
    snapshot (a file edited while a run was going stored old specs under the new digest, 2026-10-09)."""
    return read_yaml(links_file())


@curated
def verdict_bands() -> tuple[tuple[float, float], tuple[float, float]]:
    """``(viable, caution)`` as ``(highest chance %, lowest held-out validation %)``: declared once in ``links.yml``
    (``verdict:``), fixed before any result by ADR-0107."""
    declared = raw_links()["verdict"]
    return tuple(tuple(float(x) for x in declared[band]) for band in ("viable", "caution"))  # type: ignore[return-value]


@curated
def load_links() -> dict[str, LinkSpec]:
    data = raw_links()
    out: dict[str, LinkSpec] = {}
    for name, body in (data.get("links") or {}).items():
        passes = tuple(
            Pass(str(p["name"]), tuple((str(k[0]), str(k[1])) for k in p["keys"])) for p in body["passes"]
        )
        control = body["control"]
        validations = tuple(
            Validation(str(v["name"]), v.get("left"), v.get("right"), v.get("tolerance"), v.get("sql"), v.get("among"))
            for v in body.get("validate") or ()
        )
        out[name] = LinkSpec(
            name, str(body.get("description", "")).strip(), _side(body["left"]), _side(body["right"]),
            passes, str(control["role"]), int(control.get("shift_days", 7)), validations,
            bool(body["same_event"]), str(body.get("sensitivity") or ""), _params(name, body), _outcome(body),
        )
    return out


def _params(name: str, body: dict[str, Any]) -> CodesParam | None:
    """The parameters a spec declares. Only ``codes`` exists: the roles of a side the caller's codes filter by prefix,
    by match name (``roles``: {match: role}, the first the default), and the other side's role each match also filters
    (``partner``: {match: role}). The older spelling (``role`` the default, ``any`` beside it) reads as roles
    {principal, any}."""
    declared = body.get("params")
    if not declared:
        return None
    if set(declared) != {"codes"}:
        raise ValueError(f"links.yml: {name}: params can only declare `codes`, not {sorted(declared)}")
    item = declared["codes"]
    side = str(item["side"])
    if side not in ("left", "right"):
        raise ValueError(f"links.yml: {name}: params.codes.side is left or right, not {side!r}")
    roles = {str(k): str(v) for k, v in (item.get("roles") or {}).items()}
    if not roles:
        roles = {"principal": str(item["role"]), **({"any": str(item["any"])} if item.get("any") else {})}
    own = dataset_roles(str(body[side]["dataset"])).roles
    for match, r in roles.items():
        if r not in own or own[r].type not in ("code", "codes"):
            raise ValueError(f"links.yml: {name}: params.codes match {match!r} names {r!r}, which is not a code or codes "
                             f"role of {body[side]['dataset']}")
    partner = {str(k): str(v) for k, v in (item.get("partner") or {}).items()}
    other = "right" if side == "left" else "left"
    theirs = dataset_roles(str(body[other]["dataset"])).roles
    for match, r in partner.items():
        if match not in roles or r not in theirs or theirs[r].type not in ("code", "codes"):
            raise ValueError(f"links.yml: {name}: params.codes.partner {match!r}: {r!r} is not a match of this spec or not "
                             f"a code role of {body[other]['dataset']}")
    return CodesParam(side, roles, partner)


def _outcome(body: dict[str, Any]) -> Outcome | None:
    item = body.get("outcome")
    return Outcome(str(item["origin"]), str(item["event"]), bool(item.get("first")), str(item.get("differ") or ""))         if item else None


#: a code prefix as DATASUS writes codes: letters and digits, up to 15 (ICD-10 I210, SIGTAP 0403070171, CBO 225260)
_CODE = re.compile(r"[0-9A-Z]{1,15}")


def normalise_codes(codes: Iterable[str] | str) -> tuple[str, ...]:
    """The caller's codes as prefixes, upper case, sorted and unique, written with or without their separators
    ("i21.0" is I210, "04.03.07" is 040307). A code that is not one (a range, a word with spaces) is refused: the codes
    become SQL, and a prefix filter that matched nothing would read as a cohort of none."""
    items = [codes] if isinstance(codes, str) else list(codes)
    out = tuple(sorted({str(c).replace(".", "").replace(" ", "").replace("-", "").upper()
                        for c in items if str(c).strip()}))
    bad = [c for c in out if not _CODE.fullmatch(c)]
    if bad or not out:
        raise ValueError(f"codes are prefixes such as I21, I210 or 0403070171 (a range is the caller's list); got "
                         f"{bad or 'none'}")
    return out


def _codes_condition(role: str, kind: str, codes: tuple[str, ...]) -> str:
    """SQL keeping the records whose ``role`` starts with one of ``codes``: a `code` role as it is, a `codes` role (every
    code of the record, space-separated) at the start of any of them."""
    name = f'"{role}"'
    if kind == "codes":
        return "(" + " OR ".join(f"(' ' || {name}) LIKE '% {c}%'" for c in codes) + ")"
    return "(" + " OR ".join(f"{name} LIKE '{c}%'" for c in codes) + ")"


def bind(spec: LinkSpec, codes: Iterable[str] | str | None = None, match: str = "principal") -> LinkSpec:
    """``spec`` with the caller's codes in its filter: a spec that declares `params` needs them, one that does not takes
    none. ``match`` "principal" filters the declared role (the principal diagnosis), "any" the broader one the spec
    declares (every diagnosis). The bound spec is an ordinary spec to every pass, control and validation, to the
    probabilistic method too, and carries ``bound`` so its run is stored under the codes."""
    if spec.params is None:
        if codes is not None:
            raise ValueError(f"{spec.name} declares no params; it takes no codes")
        return spec
    if codes is None:
        raise ValueError(f"{spec.name} is run per set of codes (params.codes: {spec.params.role}); give codes=")
    if match not in spec.params.roles:
        raise ValueError(f"{spec.name} matches codes on {sorted(spec.params.roles)}, not {match!r}")
    role = spec.params.roles[match]
    side = spec.left if spec.params.side == "left" else spec.right
    chosen = normalise_codes(codes)
    cond = _codes_condition(role, dataset_roles(side.dataset).roles[role].type, chosen)
    filtered = replace(side, where=f"({side.where}) AND {cond}" if side.where else cond)
    bound = replace(spec, bound=Codes(chosen, match),
                    **{"left" if spec.params.side == "left" else "right": filtered})  # type: ignore[arg-type]
    partner = spec.params.partner.get(match)
    if partner:
        other_name = "right" if spec.params.side == "left" else "left"
        other = getattr(bound, other_name)
        kind = dataset_roles(other.dataset).roles[partner].type
        pcond = _codes_condition(partner, kind, chosen)
        bound = replace(bound, **{other_name: replace(other, where=f"({other.where}) AND {pcond}" if other.where else pcond)})  # type: ignore[arg-type]
    return bound


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
        names.update(r for r in s.explode_days[:2] if isinstance(r, str))
    names.update(s.group)
    if s.latest:
        names.add(s.latest)
    if s.earliest:
        names.add(s.earliest)
    if spec.outcome:
        names.add(spec.outcome.origin if side == "left" else spec.outcome.event)
        if spec.outcome.differ:
            names.add(spec.outcome.differ)
    declared = dataset_roles(s.dataset).roles
    for text in (s.where, *(t for v in spec.validations for t in (v.sql or "", v.among or ""))):
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
    #: a cohort's pass kept to a shorter follow-up than the window: the longest horizon (days) up to which it is
    #: admissible at every horizon; it contributes its pairs within that many days only (`_pass_reach`)
    reach_days: int | None = None


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
class Report:
    """What either engine says of a run, and the one rule that turns it into a verdict (`decide`): the pairs, the
    held-out and circular validations, the verdict and why."""

    spec: str
    left_records: int
    right_records: int
    pairs: pa.Table
    validations: dict[str, dict[str, Any]] = field(default_factory=dict)
    verdict: str = "not viable"
    #: what failed the verdict, and what the run left out, in words (empty when viable and whole)
    reasons: list[str] = field(default_factory=list)
    #: per year, the roles the scope lacked and the `codes` roles built from fewer columns than declared
    role_gaps: dict[str, Any] = field(default_factory=dict)

    @property
    def linked_share(self) -> float:
        return self.pairs.num_rows / self.left_records if self.left_records else 0.0

    def decide(self, chance_percent: float | None, upper: float | None, *, placebo_failures: Iterable[str] = (),
               left_out: Iterable[str] = ()) -> None:
        """The verdict from the chance rate (``chance_percent``, with its 95% upper bound), the validations and the
        placebo's failures (`judge`); ``left_out`` names what the run could not use, and is kept beside the reasons."""
        self.verdict, self.reasons = judge(self.pairs.num_rows, chance_percent, self.validations, upper,
                                           placebo_failures=list(placebo_failures))
        self.reasons += left_out

    def _common(self) -> dict[str, Any]:
        return {"spec": self.spec, "left_records": self.left_records, "right_records": self.right_records,
                "pairs": self.pairs.num_rows, "linked_share": round(self.linked_share, 4),
                "validations": self.validations, "verdict": self.verdict, "verdict_reasons": self.reasons,
                "role_gaps": self.role_gaps}


@dataclass
class LinkResult(Report):
    passes: list[PassReport] = field(default_factory=list)
    chance_percent: float | None = None
    chance_upper95_percent: float | None = None
    #: the control's reach per key: the share of left records whose moved value finds a partner value, against the same for the real value
    control_reach: dict[str, Any] = field(default_factory=dict)
    #: a cohort spec's event role (`Outcome`) carried into the pairs, with its first and last day on the right side
    carried: dict[str, Any] = field(default_factory=dict)
    #: a cohort run's pairs, coincidences and verdict at each follow-up horizon (`_horizons`)
    horizons: list[dict[str, Any]] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {**self._common(), "passes": [vars(p) for p in self.passes], "chance_percent": self.chance_percent,
                "chance_upper95_percent": self.chance_upper95_percent, "control_reach": self.control_reach,
                **({"carried": self.carried} if self.carried else {}),
                **({"horizons": self.horizons} if self.horizons else {})}


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
        # the smallest id (or the latest by ``side.latest``, the earliest by ``side.earliest``), with the group's size
        # kept for validation.
        # A record missing any key is its own group: null keys partitioned together made every birth of a facility and
        # day without the mother's birth date one "delivery" (SINASC 2010: 2.86 M births, 870 k groups), and its
        # members took one partner (2026-10-08)
        anynull = " OR ".join(f"{quote(g)} IS NULL" for g in side.group)
        keys = f"CASE WHEN {anynull} THEN _id END, " + ", ".join(quote(g) for g in side.group)
        order = (f"{quote(side.latest)} DESC NULLS LAST, _id" if side.latest
                 else f"{quote(side.earliest)} ASC NULLS LAST, _id" if side.earliest else "_id")
        base = (f"SELECT * EXCLUDE (_n), _n AS _group_size FROM (SELECT *, count(*) OVER (PARTITION BY {keys}) AS _n, "
                f"row_number() OVER (PARTITION BY {keys} ORDER BY {order}) AS _k FROM ({base})) WHERE _k = 1")
    if side.explode_days:
        start, end, new = side.explode_days
        if isinstance(end, int):
            # a window of that many days from the start (a cohort's follow-up), not an interval the record carries
            stop, valid = f"CAST({quote(start)} AS TIMESTAMP) + INTERVAL {end} DAY", f"{quote(start)} IS NOT NULL"
        else:
            stop = f"CAST({quote(end)} AS TIMESTAMP)"
            valid = (f"{quote(start)} IS NOT NULL AND {quote(end)} IS NOT NULL AND {quote(end)} >= {quote(start)} "
                     f"AND {quote(end)} - {quote(start)} <= 120")
        base = (f"SELECT *, CAST(unnest(generate_series(CAST({quote(start)} AS TIMESTAMP), {stop}, INTERVAL 1 DAY)) "
                f"AS DATE) AS {quote(new)} FROM ({base}) WHERE {valid}")
    con.execute(f"CREATE OR REPLACE TEMP {'TABLE' if materialise else 'VIEW'} {name} AS {base}")
    return con.execute(f"SELECT count(DISTINCT _id) FROM {name}").fetchone()[0]  # type: ignore[index]


def _join(keys: tuple[tuple[str, str], ...], moved: dict[tuple[str, str], str], one_each: bool = False,
          outcome: Outcome | None = None) -> str:
    """SQL for the 1:1 join of the still-unlinked records on `keys`; a key in ``moved`` joins on its moved left value
    (the control, `placebo.rotation`). With ``one_each`` a record that pairs with two partners pairs with neither: a
    cohort's person dies once, and a namesake who died inside the person's window is another candidate for the one
    death, which no key tells apart (a window explodes a record into one row per day, each unique, so the unique-key
    rule alone let a person take two deaths: 62 of 3,879 admissions, Alagoas I21-I22)."""
    lk = [f"{moved.get(key, quote(key[0]))} AS k_{i}" for i, key in enumerate(keys)]
    rk = [f"{quote(right)} AS k_{i}" for i, (_l, right) in enumerate(keys)]
    kn = ", ".join(f"k_{i}" for i in range(len(keys)))
    notnull = " AND ".join(f"k_{i} IS NOT NULL" for i in range(len(keys)))
    differ = outcome.differ if outcome is not None else ""
    lx = f", {quote(differ)} AS _differ" if differ else ""
    on = " WHERE ua._differ IS DISTINCT FROM ub._differ" if differ else ""
    if one_each and outcome is not None and outcome.first:
        # the earliest of the person's partners (by the right side's event), each partner one person's
        event = next((f"k_{i}" for i, (_l, right) in enumerate(keys) if right == outcome.event), "ub._id")
        each = (f" QUALIFY count(*) OVER (PARTITION BY ub._id) = 1 AND row_number() OVER (PARTITION BY ua._id "
                f"ORDER BY ub.{event}, ub._id) = 1" if event != "ub._id" else
                " QUALIFY count(*) OVER (PARTITION BY ub._id) = 1 AND row_number() OVER (PARTITION BY ua._id ORDER BY ub._id) = 1")
    else:
        each = (" QUALIFY count(*) OVER (PARTITION BY ua._id) = 1 AND count(*) OVER (PARTITION BY ub._id) = 1"
                if one_each else "")
    return f"""
        WITH a AS (SELECT DISTINCT _id, {', '.join(lk)}{lx} FROM L WHERE _id NOT IN (SELECT l FROM linked)),
             b AS (SELECT DISTINCT _id, {', '.join(rk)}{lx} FROM R WHERE _id NOT IN (SELECT r FROM linked)),
             ua AS (SELECT * FROM a WHERE {notnull} QUALIFY count(*) OVER (PARTITION BY {kn}) = 1),
             ub AS (SELECT * FROM b WHERE {notnull} QUALIFY count(*) OVER (PARTITION BY {kn}) = 1)
        SELECT ua._id AS l, ub._id AS r FROM ua JOIN ub USING ({kn}){on}{each}"""


def where_roles(side: Side) -> set[str]:
    """The roles a side's filter reads."""
    return set(re.findall(r'"([^"]+)"', side.where))


def roles_used(spec: LinkSpec) -> tuple[set[str], set[str]]:
    """The roles each side contributes as pass keys or through its filter: a validation reading one of them agrees by
    construction."""
    return ({k[0] for p in spec.passes for k in p.keys} | where_roles(spec.left),
            {k[1] for p in spec.passes for k in p.keys} | where_roles(spec.right))


def run(spec: LinkSpec, left: pa.Table, right: pa.Table) -> LinkResult:
    """Link two role tables under `spec`."""
    left_bad = unusable_roles(left, sorted({k[0] for p in spec.passes for k in p.keys}))
    right_bad = unusable_roles(right, sorted({k[1] for p in spec.passes for k in p.keys}))
    why_skipped = {p.name: why_unusable(left_bad, right_bad, [k[0] for k in p.keys], [k[1] for k in p.keys])
                   for p in spec.passes}
    if all(why_skipped.values()):
        raise ValueError(f"{spec.name}: no pass can run on these tables ({why_skipped}); the scope lacks or cannot "
                         "read a role every pass keys on")
    con = connect()
    n_left = _prepare(con, "L", left, spec.left)
    n_right = _prepare(con, "R", right, spec.right)
    # the control: each key pairing the control role moves round the range both sides hold (`placebo.shared_range`)
    control_keys = sorted({k for p in spec.passes if not why_skipped[p.name] for k in p.keys if k[0] == spec.control_role})
    moved = {key: sql for key in control_keys
             if (sql := placebo.rotation(key[0], placebo.shared_range(con, [key[0]], [key[1]]), spec.control_shift_days))}
    con.execute("CREATE TEMP TABLE linked (l VARCHAR, r VARCHAR, pass VARCHAR)")
    reports: list[PassReport] = []
    kept_controls: list[pa.Table] = []      # a cohort's control pairs, within each pass's reach, by horizon
    horizons = _horizon_days(spec)
    if horizons:
        # one record per id, for the days from origin to event (the views `validate` makes again after the passes)
        con.execute("CREATE OR REPLACE TEMP TABLE _vl AS SELECT DISTINCT ON (_id) * FROM L")
        con.execute("CREATE OR REPLACE TEMP TABLE _vr AS SELECT DISTINCT ON (_id) * FROM R")
    for p in spec.passes:
        if why_skipped[p.name]:
            reports.append(PassReport(p.name, 0, 0, None, False, skipped=why_skipped[p.name]))
            continue
        one = spec.outcome is not None      # a cohort: a person has one event
        real = con.execute(f"SELECT * FROM ({_join(p.keys, {}, one, spec.outcome)})").to_arrow_table()
        if one:
            coincidences = con.execute(_join(p.keys, moved, one, spec.outcome)).to_arrow_table()
            control = coincidences.num_rows
        else:
            control = con.execute(f"SELECT count(*) FROM ({_join(p.keys, moved)})").fetchone()[0]  # type: ignore[index]
        n = real.num_rows
        chance = 100.0 * control / n if n else None
        reach: int | None = None
        if one and horizons:
            # A pass judged on its whole window was dropped when its year held too many coincidences, and its deaths
            # within 30 days went with it: chronic subdural haematoma, Brazil 2019, 1,049 pairs at 34.8% chance within
            # the year, and the run kept the in-hospital deaths alone and called them viable (2026-11-22). Judged horizon
            # by horizon, a pass is kept as far as it is admissible and contributes its pairs within that reach.
            reach = _pass_reach(_offsets(con, spec, real), _offsets(con, spec, coincidences), horizons)
            kept = reach is not None
            if kept and reach is not None and reach < horizons[-1]:
                real = _within(con, spec, real, reach)
                coincidences = _within(con, spec, coincidences, reach)
        else:
            kept = bool(n) and control < n and (chance is None or chance < chance_drop())
        short = reach if reach is not None and reach < horizons[-1] else None
        reports.append(PassReport(p.name, n, int(control), round(chance, 2) if chance is not None else None, kept,
                                  reach_days=short))
        if kept:
            con.register("_new", real)
            con.execute("INSERT INTO linked SELECT l, r, ? FROM _new", [p.name])
            con.unregister("_new")
            if one:
                kept_controls.append(coincidences)
    kept_pairs = int(con.execute("SELECT count(*) FROM linked").fetchone()[0])  # type: ignore[index]
    kept_control = (sum(c.num_rows for c in kept_controls) if horizons
                    else sum(r.control_pairs for r in reports if r.kept))
    chance = round(100.0 * kept_control / kept_pairs, 2) if kept_pairs else None
    validations = validate(con, spec)       # makes _vl and _vr, a record once each, which the cohort's outcome reads
    pairs, carried = _pairs(con, spec)
    worst_pass = max((r.chance_percent or 0.0) for r in reports if r.kept) if any(r.kept for r in reports) else None
    if horizons:
        # a cohort's passes are judged by horizon: the run's own rate is that of the pairs it kept, within their reach
        worst_pass = chance
    upper = upper95(kept_control, kept_pairs)
    reach = {f"{key[0]} ~ {key[1]}": placebo.key_reach(con, *key, moved.get(key, quote(key[0]))) for key in control_keys}

    failures = placebo.key_failures(reach)
    result = LinkResult(spec.name, n_left, n_right, pairs, validations, passes=reports, chance_percent=chance,
                        chance_upper95_percent=upper, control_reach=reach, carried=carried,
                        horizons=_horizons(con, spec, pairs, kept_controls, validations, failures, reports),
                        role_gaps={"left": role_gaps(left), "right": role_gaps(right)})
    result.decide(worst_pass, upper, placebo_failures=failures,
                  left_out=[f"pass {name!r} skipped: {why}" for name, why in why_skipped.items() if why])
    return result


#: the follow-up horizons, in days, a cohort run reports its false-match rate at (those inside the spec's window, and the window)
HORIZONS = (7, 30, 90, 180, 365)


def _horizon_days(spec: LinkSpec) -> list[int]:
    """The follow-up horizons of a cohort spec (those inside its window, and the window), or [] for any other spec."""
    window = spec.left.explode_days[1] if spec.left.explode_days else None
    if spec.outcome is None or not isinstance(window, int):
        return []
    return [h for h in HORIZONS if h < window] + [window]


def _offsets(con: duckdb.DuckDBPyConnection, spec: LinkSpec, table: pa.Table) -> np.ndarray:
    """Days from each pair's origin to its event, in the pairs' order, read through the one-record-per-id views."""
    if not table.num_rows:
        return np.zeros(0, dtype=np.int64)
    assert spec.outcome is not None
    origin, event = quote(spec.outcome.origin), quote(spec.outcome.event)
    con.register("_t", table.select(["l", "r"]).append_column("_k", pa.array(range(table.num_rows), pa.int64())))
    out = con.execute(f"""SELECT CAST(r.{event} - l.{origin} AS INTEGER) AS d FROM _t k JOIN _vl l ON l._id = k.l
                          JOIN _vr r ON r._id = k.r ORDER BY k._k""").fetchnumpy()
    con.unregister("_t")
    return np.asarray(out["d"], dtype=np.int64)


def _pass_reach(real: np.ndarray, control: np.ndarray, horizons: list[int]) -> int | None:
    """The longest horizon up to which a pass is admissible at every horizon (pairs found, fewer coincidences than pairs,
    chance under `chance_drop`), or None when it is admissible at none. A horizon with no pair yet is passed over."""
    reach = None
    for days in horizons:
        n, c = int((real <= days).sum()), int((control <= days).sum())
        if n == 0:
            continue
        if c >= n or 100.0 * c / n >= chance_drop():
            break
        reach = days
    return reach


def _within(con: duckdb.DuckDBPyConnection, spec: LinkSpec, table: pa.Table, days: int) -> pa.Table:
    """The pairs of ``table`` whose event falls within ``days`` of the origin."""
    if not table.num_rows:
        return table
    return table.filter(pa.array(_offsets(con, spec, table) <= days))


def _horizons(con: duckdb.DuckDBPyConnection, spec: LinkSpec, pairs: pa.Table, controls: list[pa.Table],
              validations: dict[str, dict[str, Any]], placebo_failures: list[str],
              reports: list[PassReport] | None = None) -> list[dict[str, Any]]:
    """For a cohort spec whose left side looks for the event within a window (`explode_days` of a count of days), the
    pairs and the control's coincidences found within each horizon, and the verdict that horizon would have by itself.
    The window is a key: a false pair needs a namesake dying inside the person's window, so the false-match rate grows
    with the horizon (Alagoas I21-I22: 2.1% within 30 days, 16% within 365), and one run holds every horizon's. A pass
    kept to a shorter reach (`_pass_reach`) finds no death after it: a horizon past a pass's reach names it
    (``short_passes``) and is at most "use with caution", since deaths only that pass would find are missing there."""
    horizons = _horizon_days(spec)
    if not horizons:
        return []
    real = _offsets(con, spec, pairs)
    control = np.concatenate([_offsets(con, spec, c) for c in controls]) if controls else np.zeros(0, dtype=np.int64)
    short = [(r.name, r.reach_days) for r in reports or [] if r.kept and r.reach_days is not None]
    rows = []
    for days in horizons:
        n, c = int((real <= days).sum()), int((control <= days).sum())
        chance = round(100.0 * c / n, 2) if n else None
        upper = upper95(c, n)
        verdict, reasons = judge(n, chance, validations, upper, placebo_failures=placebo_failures)
        limited = [f"{name} (to {reach} days)" for name, reach in short if reach is not None and reach < days]
        if limited:
            reasons = [*reasons, f"pass {', '.join(limited)} kept only to a shorter horizon: deaths only it finds are "
                                 "missing here"]
            if verdict == "viable":
                verdict = "use with caution"
        rows.append({"days": days, "pairs": n, "control_pairs": c, "chance_percent": chance, "chance_upper95_percent": upper,
                     "verdict": verdict, "verdict_reasons": reasons, **({"short_passes": limited} if limited else {})})
    return rows


def _pairs(con: duckdb.DuckDBPyConnection, spec: LinkSpec) -> tuple[pa.Table, dict[str, Any]]:
    """The pairs of the temp table `linked` and, for a cohort spec (`Outcome`), the right side's event date beside each
    (a column named by the role) with the event's first and last day over everything the right side read: the last day
    of the deaths a follow-up can see. Call after `validate`, which makes the one-record-per-id view `_vr`."""
    if spec.outcome is None:
        return con.execute("SELECT * FROM linked").to_arrow_table(), {}
    event = quote(spec.outcome.event)
    pairs = con.execute(f"""SELECT k.l, k.r, k.pass, CAST(v.{event} AS DATE) AS {event}
                            FROM linked k JOIN _vr v ON v._id = k.r ORDER BY k.l, k.r""").to_arrow_table()
    first, last = con.execute(f"SELECT min({event}), max({event}) FROM _vr").fetchone() or (None, None)
    return pairs, {spec.outcome.event: {"first": str(first) if first else None, "last": str(last) if last else None}}


_QUOTED = re.compile(r'\b([lr])\."([^"]+)"')


def validation_roles(v: Validation) -> tuple[set[str], set[str]]:
    """The left and right roles a validation reads (the pairs it judges included)."""
    found = _QUOTED.findall(f"{v.sql or ''} {v.among or ''}")
    left, right = {name for side, name in found if side == "l"}, {name for side, name in found if side == "r"}
    if not v.sql:
        left, right = left | ({v.left} if v.left else set()), right | ({v.right} if v.right else set())
    return left, right


def validate(con: duckdb.DuckDBPyConnection, spec: LinkSpec,
             used: tuple[set[str], set[str]] | None = None) -> dict[str, dict[str, Any]]:
    """Agreement of each validation over the pairs in the temp table `linked` (l, r). ``used`` (left roles, right
    roles) are the roles the method being judged keys, compares or filters on (`roles_used` for the deterministic
    passes); a validation reading one is ``circular`` and never decides the verdict."""
    used_left, used_right = used if used is not None else roles_used(spec)
    con.execute("CREATE OR REPLACE TEMP TABLE _vl AS SELECT DISTINCT ON (_id) * FROM L")
    con.execute("CREATE OR REPLACE TEMP TABLE _vr AS SELECT DISTINCT ON (_id) * FROM R")
    validations: dict[str, dict[str, Any]] = {}
    held_left = {str(r[0]) for r in con.execute("DESCRIBE _vl").fetchall()}
    held_right = {str(r[0]) for r in con.execute("DESCRIBE _vr").fetchall()}
    for v in spec.validations:
        reads_left, reads_right = validation_roles(v)
        if not (reads_left <= held_left and reads_right <= held_right):
            # a role the sides do not carry here (one a stored link gives the probabilistic engine, `inherit`): the
            # validation is not run, and says so; it never decides by its absence
            missing = sorted((reads_left - held_left) | (reads_right - held_right))
            validations[v.name] = {"pairs_compared": 0, "agreement_percent": None, "circular": False,
                                   "unavailable": f"the sides do not carry {missing}"}
            continue
        if v.sql:
            cond = v.sql
            usable = "TRUE"
        elif v.tolerance is not None:
            cond = f"abs(CAST(l.{quote(v.left or '')} AS DOUBLE) - CAST(r.{quote(v.right or '')} AS DOUBLE)) <= {v.tolerance}"
            usable = f"l.{quote(v.left or '')} IS NOT NULL AND r.{quote(v.right or '')} IS NOT NULL"
        else:
            cond = f"l.{quote(v.left or '')} = r.{quote(v.right or '')}"
            usable = f"l.{quote(v.left or '')} IS NOT NULL AND r.{quote(v.right or '')} IS NOT NULL"
        if v.among:
            usable = f"({usable}) AND ({v.among})"
        row = con.execute(f"""
            SELECT count(*), avg(CASE WHEN {cond} THEN 1.0 ELSE 0 END)
            FROM linked k JOIN _vl l ON l._id = k.l JOIN _vr r ON r._id = k.r
            WHERE {usable}""").fetchone()
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
    `thresholds.engine.min_compared` pairs: a validation on a key or a compared field agrees by construction. A placebo that did not reach
    its blocks (``placebo_failures``) measured no chance at all: not viable."""
    reasons = list(placebo_failures)
    held = [float(v["agreement_percent"]) for v in validations.values()
            if not v.get("circular") and v["agreement_percent"] is not None
            and (v.get("pairs_compared") or 0) >= min_compared()]
    best = max(held) if held else None
    if not pairs:
        reasons.append("no pairs")
    if worst_chance is None:
        reasons.append("no chance estimate: no kept pass or no placebo threshold")
    if best is None:
        reasons.append(f"no held-out validation compares at least {min_compared()} pairs")
    if reasons:
        return "not viable", reasons
    assert best is not None and worst_chance is not None
    if upper is not None:
        worst_chance = max(worst_chance, upper)
    VIABLE, CAUTION = verdict_bands()
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
    codes: Iterable[str] | str | None = None,
    match: str = "principal",
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
    same spec content, method, scope and ``codes``; ``refresh=True``
    recomputes, and ``persist=False`` keeps nothing.

    A spec that declares ``params`` (a cohort of the caller's diagnoses) is run
    per ``codes`` (ICD-10 prefixes) and ``match`` ("principal" diagnosis, or
    "any" of them): two sets of codes are two runs (`bind`).

    Example::

        result = link("sih_deaths_to_sim", period=2022, geography="RR")
        result.summary()["verdict"]     # 'viable'
        result.pairs                    # l, r, pass
        link("sih_admissions_to_sim", period=("2018", "2022"), geography="AL", codes=["I21", "I22"])
    """
    from . import store

    try:
        spec = load_links()[name]
    except KeyError:
        raise KeyError(f"no link spec {name!r}; declared: {sorted(load_links())}") from None
    if method not in ("deterministic", "probabilistic"):
        raise ValueError(f"method must be 'deterministic' or 'probabilistic', not {method!r}")
    spec = bind(spec, codes, match)
    settings = query_kwargs.get("settings") or load_settings(root=query_kwargs.get("root"))
    if right_period is None and spec.right.pad_years != (0, 0):
        right_period = padded_period(period, spec.right)
    right_geography = right_geography_for(spec, geography, right_geography)
    key = stored_key(name, method, period, geography, right_period=right_period, right_geography=right_geography,
                     params=spec.bound)
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
                                    right_geography=right_geography, spec=spec, **query_kwargs)
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
        params = {"params": spec.bound.as_dict()} if spec.bound else {}
        store.save(settings, key, result.pairs,
                   {**result.summary(), **params, "scope": scope, "seconds": round(time.time() - t0, 1)})
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
    needed = sorted({by, *s.group, *([s.latest] if s.latest else []), *([s.earliest] if s.earliest else []),
                     *(r for r in declared if s.where and f'"{r}"' in s.where)})
    scope = period if side == "left" else (right_period or period)
    table = role_table(s.dataset, period=scope, geography="BR", roles=needed, **query_kwargs)
    con = duckdb.connect()
    _prepare(con, "x", table, replace(s, explode_days=None, pad_years=(0, 0)))
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
    return con.execute(f"""SELECT x.{quote(by)} AS unit, CAST(count(DISTINCT x._id) AS INTEGER) AS n,
            CAST(sum(coalesce(m.p, {found})) AS DOUBLE) AS k
        FROM (SELECT DISTINCT _id, {quote(by)} FROM x) x LEFT JOIN (SELECT id, max(p) AS p FROM pm GROUP BY id) m
        ON m.id = x._id {joined} GROUP BY 1 ORDER BY 1""").fetch_arrow_table()


__all__ = ["Codes", "LinkNotViable", "LinkResult", "LinkSpec", "PassReport", "bind", "link", "link_method",
           "load_links", "normalise_codes", "run", "side_counts", "stored_key"]
