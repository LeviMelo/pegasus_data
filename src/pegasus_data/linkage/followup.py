"""A cohort's follow-up through a declared link: each record of a topic's cohort with the date of its partner's event.

A paper on the hospital admissions of one condition needs more than the admissions that ended in death: the 30-day and
1-year mortality of a cohort counts the deaths of those discharged alive, which only a link to the death certificate of
any cause reaches. The link is declared once with its parameters (``curation/links.yml``: ``params``, ``outcome``) and
run for the caller's codes, years and area (``engine.link(codes=...)``, stored per run). This module is the reader:

    fu = linked_deaths("SIH-RD", ["I21", "I22"], years=range(2018, 2023), geography="AL")
    fu.table             # one row per person: record, origin, death_date, days_to_death, death_record, link_pass, p_match
    fu.quality           # verdict, false-match rate at each horizon, validations, the last day of deaths the data hold
    fu.mortality(30)     # {"followed": ..., "died": ..., "rate": ...}, 30-day mortality over those followed that long
    fu.quality["quantities"]   # per horizon: pairs, link-only events, expected chance, false-match shares, sensitivity
    fu.reach(["state", "year"])  # linked share by stratum (``among="known"``: on the events the left records)

The false-match rate of a late death is not that of an early one: a false pair needs a namesake (same birth date, sex and
residence) dying inside the person's window, which a longer window makes likelier. Each horizon has its own rate and
verdict (``quality["horizons"]``), and ``p_match`` of a pair is one minus the rate in the band of days it falls in, so
``link_draws(fu.pairs, report=fu.report)`` and weights read the same pairs as a draw of plausible links. A horizon whose
verdict is "not viable" is refused by ``mortality`` unless asked for.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable
from dataclasses import dataclass, replace
from typing import Any, cast

import pyarrow as pa
import pyarrow.compute as pc

from ..config import UF_CODES, UF_NUMERIC, load_settings
from ..ontology import dataset_key
from . import store
from .engine import (
    LinkNotViable,
    Outcome,
    _prepare,
    _roles_needed,
    _side_table,
    bind,
    dropped_pass_verdicts,
    link,
    load_links,
    padded_period,
    right_geography_for,
    stored_key,
)
from .identity import connect, quote

__all__ = ["Followup", "RunNotStored", "linked_deaths", "linked_outcomes", "quantities"]


class RunNotStored(LookupError):
    """A cohort's run is not in the store and computing it was not asked for (``compute=False``)."""


@dataclass
class Followup:
    """A cohort and the follow-up its link found (`linked_deaths`)."""

    #: one row per person of the cohort: ``record`` (the first admission's identity), ``origin`` (its start), ``death_date``
    #: (the linked death's date, null when none was found inside the window), ``days_to_death``, ``death_record``,
    #: ``link_pass``, ``p_match`` (null when unlinked), then the roles asked for (``roles=``)
    table: pa.Table
    #: the link's quality: ``verdict``, ``horizons`` (the false-match rate and verdict of each follow-up horizon),
    #: ``validations``, ``death_data_end`` (the last day of deaths the data hold), the cohort and linked counts, the run
    quality: dict[str, Any]
    #: the run's pairs (l, r, pass, the event's date and ``p_match``) and its stored report: what `uncertainty.draws` takes
    pairs: pa.Table
    report: dict[str, Any]
    #: the column of days from the origin to the partner's event (``days_to_death`` for a death link, else
    #: ``days_to_event``, `linked_outcomes`)
    days_column: str = "days_to_death"

    @property
    def window(self) -> int:
        return int(self.quality["window_days"])

    @property
    def reach_days(self) -> int:
        """The days after the origin within which the run looks for the event: the window, or less when a pass with too
        many chance matches over the window was kept to a shorter horizon (``passes[].reach_days``)."""
        kept = [p["reach_days"] for p in self.quality.get("passes") or [] if p.get("kept") and p.get("reach_days")]
        return int(min(kept or [self.window]))

    def horizon(self, days: int) -> dict[str, Any]:
        """The quality of the follow-up within ``days``: the first horizon of the run that covers it."""
        for row in self.quality["horizons"]:
            if row["days"] >= days:
                return row
        raise ValueError(f"the run looks for deaths within {self.window} days, not {days}")

    def died_within(self, days: int, *, allow_not_viable: bool = False) -> pa.Array:
        """Whether each person died within ``days`` of the origin: True or False when the person was followed that long,
        null when followed for less (the origin plus ``days`` is past the last day of deaths the data hold, or that day
        is unknown, or ``days`` is past the run's `reach_days`), a death as much as a survival: a death inside a window the data do not cover counted while a
        survivor in the same place dropped, and inflated the mortality of the last origins (ABNc, 2026-11-24). Refused
        (`LinkNotViable`) when the run's verdict at that horizon is "not viable", as pairs of a linkage that fails its
        own verdict look like pairs of one that passes."""
        row = self.horizon(days)
        if row["verdict"] == "not viable" and not allow_not_viable:
            raise LinkNotViable(_Refusal(self.quality["link"], row))
        if days > self.reach_days:
            # the run found no event after its reach: a person alive then is not known to be alive at ``days``, and
            # counting the deaths it found while dropping them would inflate the rate (ABNc t07, 2026-11-24)
            return pa.nulls(len(self.table), pa.bool_())
        died = pc.fill_null(pc.less_equal(self.table.column(self.days_column), days), False)
        # a death link names it death_data_end, an event link (`linked_outcomes`) event_data_end
        end = self.quality.get("death_data_end", self.quality.get("event_data_end"))
        if end is None:
            return pa.nulls(len(self.table), pa.bool_())
        last = (datetime.date.fromisoformat(end) - datetime.date(1970, 1, 1)).days
        followed = pc.fill_null(pc.less_equal(pc.add(pc.cast(self.table.column("origin"), pa.int32()), days), last), False)
        return pc.if_else(followed, died, pa.scalar(None, pa.bool_())).combine_chunks()

    def mortality(self, days: int, *, allow_not_viable: bool = False) -> dict[str, Any]:
        """Deaths within ``days`` over the people followed that long: {"followed", "died", "rate"}, with the horizon's
        false-match rate beside it (``false_match_percent``) and the deaths less the control's coincidences
        (``died_corrected``: the control moves a birth date by a week, so its pairs are all false; it counts the chance
        pairs among persons with no partner of their own as well as those with one, and so overstates them a little)."""
        flags = self.died_within(days, allow_not_viable=allow_not_viable).to_pylist()
        followed = sum(f is not None for f in flags)
        died = sum(bool(f) for f in flags)
        row = self.horizon(days)
        # the control's count is over the whole cohort and one horizon of the run: it corrects a death count only then
        whole = row["days"] == days and followed == len(flags)
        return {"days": days, "followed": followed, "died": died, "rate": died / followed if followed else None,
                "false_match_percent": row["chance_percent"], "verdict": row["verdict"],
                "died_corrected": max(died - row["control_pairs"], 0) if whole else None}


    def quantities(self, among: Any = None, known: Any = None) -> list[dict]:
        """The link's quality as quantities per horizon (`quantities`), on the whole cohort or on the subset
        ``among`` (a boolean mask over `table`'s rows: the persons a claim is about); ``known``: the study's own known
        event, as days from the origin per row (None where none), in place of the spec's."""
        # passes and outcome are the spec's own, whatever codes bound it
        return quantities(self.table, self.report, load_links()[self.quality["link"]], days_column=self.days_column,
                          among=among, known=known)

    def reach(self, by: Iterable[str] | str, *, among: str | None = None) -> pa.Table:
        """The linked share by stratum: persons, linked (within the window) and their share, for ``by`` among
        ``state`` (the residence's first two digits), ``year`` (the origin's), ``age_band`` (ten years at the origin),
        ``sex`` or any column of `table`. ``among="known"``: only the persons whose own record carries the event
        (`quantities`), where linked against unlinked shows whom the link misses (GUILD's linked against unlinked)."""
        import pandas as pd

        by = [by] if isinstance(by, str) else list(by)
        d = self.table.to_pandas()
        if among == "known":
            known = self.quality.get("known_role")
            if not known:
                raise ValueError(f"{self.quality['link']}: the spec declares no event the left records (outcome.known)")
            d = d[d[known[0]].astype(str) == known[1]]
        elif among is not None:
            raise ValueError("among is None or 'known'")
        origin = pd.to_datetime(d["origin"])
        derived = {"state": lambda: d["patient.residence"].astype(str).str[:2], "year": lambda: origin.dt.year,
                   "sex": lambda: d["patient.sex"],
                   "age_band": lambda: ((origin - pd.to_datetime(d["patient.birth_date"])).dt.days // 3652.5 * 10)}
        keys = {b: (derived[b]() if b in derived and b not in d.columns else d[b]) for b in by}
        g = pd.DataFrame({**keys, "linked": d[self.days_column].notna()})
        out = g.groupby(by, dropna=False).linked.agg(persons="size", linked="sum").reset_index()
        out["share"] = out.linked / out.persons
        return pa.Table.from_pandas(out, preserve_index=False)


class _Refusal:
    """A horizon's verdict shaped as the result `LinkNotViable` reads."""

    def __init__(self, spec: str, row: dict[str, Any]) -> None:
        self._summary = {"spec": spec, "chance_percent": row["chance_percent"], "validations": {}, "pairs": row["pairs"],
                         "verdict_reasons": row["verdict_reasons"], "horizon_days": row["days"]}

    def summary(self) -> dict[str, Any]:
        return self._summary


def cohort_link(dataset: str, name: str | None = None, *, event: str | None = None) -> str:
    """The declared cohort link (one with ``params`` and an ``outcome``) that follows ``dataset``'s records; ``event``
    keeps those whose outcome is that role (``death.date`` for `linked_deaths`: SIH-RD is followed to a death, a
    readmission and a radiotherapy course, and a bare call was refused as ambiguous)."""
    specs = load_links()
    cohorts = {n: s for n, s in specs.items() if s.params is not None and s.outcome is not None
               and (event is None or s.outcome.event == event)}
    if name is not None:
        if name not in cohorts:
            raise KeyError(f"{name!r} is not a cohort link; declared: {sorted(cohorts)}")
        return name
    left = dataset_key(dataset)
    found = [n for n, s in cohorts.items() if s.left.dataset == left]
    if len(found) != 1:
        raise KeyError(f"{len(found)} cohort links follow {dataset!r} ({sorted(cohorts)}); name one with link=")
    return found[0]


def _period(years: object) -> object:
    """``years`` (a year, any iterable of years, a pair of years or "2018..2022") as the period a run is keyed by."""
    if isinstance(years, str) and ".." in years:
        years = years.split("..")
    items = [years] if isinstance(years, (int, str)) else list(years)  # type: ignore[call-overload]
    ys = sorted({int(y) for y in items})
    return str(ys[0]) if len(ys) == 1 else (str(ys[0]), str(ys[-1]))


def _geography(area: object) -> object:
    """An area as the scope the lake files are cut at: a state by its sigla or its IBGE number, or "BR"."""
    def one(a: object) -> str:
        text = str(a).strip().upper()
        text = UF_NUMERIC.get(text, text)
        if text not in UF_CODES:   # as query: a place that is not a federal unit raises, never an empty follow-up
            raise ValueError(f"{a!r} is not a federal unit; known: {', '.join(sorted(UF_CODES))}")
        return text

    return [one(a) for a in area] if isinstance(area, (list, tuple, set)) else one(area)


def linked_outcomes(
    dataset: str,
    codes: Iterable[str] | str,
    *,
    years: object,
    geography: object,
    link_name: str | None = None,
    match: str = "principal",
    roles: Iterable[str] = (),
    partner_roles: Iterable[str] = (),
    compute: bool = True,
    refresh: bool = False,
    **query_kwargs: Any,
) -> Followup:
    """`linked_deaths` for any cohort link (``links.yml``: ``params`` and ``outcome``): each person of the cohort with
    the date of the partner's event within the link's window (a radiotherapy course after a tumour's surgery,
    ``sih_admissions_to_radiotherapy``; a readmission; a death). The table's columns are named for an event, not a death:
    ``record``, ``origin``, ``event_date``, ``days_to_event``, ``partner_record``, ``link_pass``, ``p_match``, the
    cohort's ``roles``, then each of ``partner_roles`` (roles of the partner's record: an APAC's pathology date and
    patient token) as ``partner.<role>``. Quality, horizons and refusals are `linked_deaths`'."""
    return _followup(dataset, codes, years=years, geography=geography, link_name=link_name, match=match, roles=roles,
                     partner_roles=partner_roles, compute=compute, refresh=refresh, death_names=False, **query_kwargs)


def linked_deaths(
    dataset: str,
    codes: Iterable[str] | str,
    *,
    years: object,
    geography: object,
    match: str = "principal",
    link_name: str | None = None,
    roles: Iterable[str] = (),
    compute: bool = True,
    refresh: bool = False,
    **query_kwargs: Any,
) -> Followup:
    """The people of ``dataset`` with ``codes`` (ICD-10 prefixes) in ``years`` (a year, a range or a list) in ``geography``
    (a state's sigla or IBGE number, or "BR"), each with the date of the death certificate of any cause found within a
    year of their first admission of the period, or none. Computes the run if it is not stored (``compute=False`` raises
    `RunNotStored` instead); ``refresh`` computes it again.

    ``match`` "principal" takes the codes on the principal diagnosis, "any" on every diagnosis of the admission,
    "procedure" SIGTAP prefixes on the procedure performed (a cohort of decompressive craniectomies). ``roles``
    names further roles of the cohort's records to return (those the link reads come back anyway). The result's quality
    holds the false-match rate and verdict of each horizon; the cohort is the first admission of each person in the
    period (a person is a birth date, sex and residence), so a readmission is not a second person.

    Example::

        fu = linked_deaths("SIH-RD", ["I21", "I22"], years=range(2018, 2023), geography="AL")
        fu.mortality(30)
    """
    return _followup(dataset, codes, years=years, geography=geography, link_name=link_name, match=match, roles=roles,
                     partner_roles=(), compute=compute, refresh=refresh, death_names=True, **query_kwargs)


def _followup(dataset: str, codes: Iterable[str] | str, *, years: object, geography: object, link_name: str | None,
              match: str, roles: Iterable[str], partner_roles: Iterable[str], compute: bool, refresh: bool,
              death_names: bool, **query_kwargs: Any) -> Followup:
    name = cohort_link(dataset, link_name, event="death.date" if death_names and link_name is None else None)
    spec = bind(load_links()[name], codes, match)
    period, area = _period(years), _geography(geography)
    settings = query_kwargs.get("settings") or load_settings(root=query_kwargs.get("root"))
    right_period = padded_period(period, spec.right) if spec.right.pad_years != (0, 0) else None
    right_geo = right_geography_for(spec, area, None)
    key = stored_key(name, "deterministic", period, area, right_period=right_period, right_geography=right_geo,
                     params=spec.bound)
    if not compute and not refresh and store.load(settings, key) is None:
        raise RunNotStored(f"{name} {period} {area} {spec.bound.as_dict() if spec.bound else ''}: no stored run")
    run = link(name, period=period, geography=area, codes=codes, match=match, refresh=refresh, allow_not_viable=True,
               **query_kwargs)
    report = store.report(settings, key) or run.summary()     # the stored one holds the run's seconds and scope
    outcome = spec.outcome
    assert outcome is not None
    table = _table(spec, run.pairs, report, period, area, list(roles), query_kwargs)
    if partner_roles := list(partner_roles):
        table = _with_partner(table, spec, run.pairs, partner_roles, right_period or period, right_geo or area, query_kwargs)
    linked = int(table.column("death_date").drop_null().length())
    # the pairs carry the band's p_match too, so that `uncertainty.draws` and `weights` read the same probabilities
    p_of = dict(zip(table.column("record").to_pylist(), table.column("p_match").to_pylist(), strict=True))
    pairs = run.pairs.append_column("p_match", pa.array([p_of.get(r) for r in run.pairs.column("l").to_pylist()], pa.float64()))
    seconds = report.get("seconds")
    quality = {
        "link": name, "params": spec.bound.as_dict() if spec.bound else {},
        "period": [period] if isinstance(period, str) else list(cast(Iterable[Any], period)), "geography": area,
        "verdict": report.get("verdict"), "verdict_reasons": report.get("verdict_reasons") or [],
        "false_match_percent": report.get("chance_percent"), "false_match_upper95_percent": report.get("chance_upper95_percent"),
        # a stored run made before the dropped-pass rule: its horizons judged again on what its kept passes can see
        "horizons": dropped_pass_verdicts(report.get("horizons") or [], report.get("passes") or [],
                                          _cover_days(table, death_names)), "window_days": _window(spec),
        "passes": report.get("passes") or [], "validations": report.get("validations") or {},
        "cohort": table.num_rows, "linked": linked, "linked_share": round(linked / table.num_rows, 4) if table.num_rows else 0.0,
        "death_data_end": ((report.get("carried") or {}).get(outcome.event) or {}).get("last"),
        "run_seconds": seconds, "run": key.stem,
        # the verdict's measurements: what a study reports on the subset its claim uses (linkage-evidence plan, Q1)
        "quantities": quantities(table, report, spec),
        "known_role": list(spec.outcome.known) if spec.outcome.known else None,
    }
    if death_names:
        return Followup(table, quality, pairs, report)
    names = {"death_date": "event_date", "days_to_death": "days_to_event", "death_record": "partner_record"}
    quality["event"] = outcome.event
    quality["event_data_end"] = quality.pop("death_data_end")
    return Followup(table.rename_columns([names.get(c, c) for c in table.column_names]), quality, pairs, report,
                    days_column="days_to_event")


def _with_partner(table: pa.Table, spec: Any, pairs: pa.Table, roles: list[str], period: object, area: object,
                  query_kwargs: dict[str, Any]) -> pa.Table:
    """``table`` with each of ``roles`` of the partner record (the right side, read as the run read it: its filter,
    group and identity) as ``partner.<role>``, null where the person has no partner."""
    right = _side_table(spec.right, sorted(set(roles) | set(_roles_needed(spec, "right"))), period=period, geography=area,
                        **query_kwargs)
    con = connect()
    _prepare(con, "R", right, replace(spec.right, explode_days=None, explode_values=None))
    con.register("t", table)
    columns = ", ".join(f"r.{quote(role)} AS {quote('partner.' + role)}" for role in roles)
    out = con.execute(f"SELECT t.*, {columns} FROM t LEFT JOIN R r ON r._id = t.death_record ORDER BY t.record"
                      ).to_arrow_table()
    con.close()
    return out


def _cover_days(table: pa.Table, death_names: bool) -> int | None:
    """The last day after the origin any linked event of the run falls on (the kept passes' reach in fact)."""
    col = "days_to_death" if death_names and "days_to_death" in table.column_names else (
        "days_to_event" if "days_to_event" in table.column_names else None)
    if col is None:
        return None
    m = pc.max(table.column(col)).as_py()
    return None if m is None else int(m)


def _window(spec: Any) -> int:
    window = spec.left.explode_days[1] if spec.left.explode_days else None
    if not isinstance(window, int):
        raise ValueError(f"{spec.name}: a cohort link looks for the event within a window of days (explode_days)")
    return window


def _table(spec: Any, pairs: pa.Table, report: dict[str, Any], period: object, area: object, extra: list[str],
           query_kwargs: dict[str, Any]) -> pa.Table:
    """The cohort of the left side as the run saw it (the same filter, group and identity), left-joined to the pairs."""
    outcome: Outcome = spec.outcome
    wanted = sorted(set(_roles_needed(spec, "left")) | set(extra) | {outcome.origin}
                    | ({outcome.known[0], outcome.known[2]} if outcome.known else set()))
    left = _side_table(spec.left, wanted, period=period, geography=area, **query_kwargs)
    con = connect()
    _prepare(con, "L", left, replace(spec.left, explode_days=None, explode_values=None))
    con.register("pairs", pairs)
    p_match = _p_match(report, outcome)
    con.register("band", p_match)
    event, origin = quote(outcome.event), quote(outcome.origin)
    columns = ", ".join(f"c.{quote(r)}" for r in wanted)
    out = con.execute(f"""
        SELECT c._id AS record, c.{origin} AS origin, p.{event} AS death_date,
               CAST(p.{event} - c.{origin} AS INTEGER) AS days_to_death, p.r AS death_record, p.pass AS link_pass,
               b.p AS p_match, {columns}
        FROM L c LEFT JOIN pairs p ON p.l = c._id AND p.{event} >= c.{origin}
                 LEFT JOIN band b ON p.{event} - c.{origin} > b.lo AND p.{event} - c.{origin} <= b.hi
        ORDER BY c._id""").to_arrow_table()
    con.close()
    return out


def _p_match(report: dict[str, Any], outcome: Outcome) -> pa.Table:
    """Probability that a pair is right, by the band of days it falls in: one minus the control's coincidences over the
    pairs found in the band (the difference of two horizons), as the probabilistic method's ``p_match`` is one minus the
    local false-match rate. A run with no horizons (a window of no days) gives its run's rate to every band."""
    rows, lo, prev_pairs, prev_control = [], -1, 0, 0
    for h in report.get("horizons") or []:
        pairs, control = h["pairs"] - prev_pairs, h["control_pairs"] - prev_control
        rows.append({"lo": lo, "hi": h["days"], "p": 1.0 - min(max(control / pairs, 0.0), 1.0) if pairs > 0 else 1.0})
        lo, prev_pairs, prev_control = h["days"], h["pairs"], h["control_pairs"]
    if not rows:
        rows = [{"lo": -1, "hi": 10**6, "p": 1.0 - float(report.get("chance_percent") or 0.0) / 100.0}]
    return pa.table({"lo": [r["lo"] for r in rows], "hi": [r["hi"] for r in rows], "p": [r["p"] for r in rows]})


def _poisson95(n: int) -> tuple[float, float]:
    """The exact (Garwood) 95% interval of a Poisson count."""
    from scipy.stats import chi2

    return (float(chi2.ppf(0.025, 2 * n) / 2) if n > 0 else 0.0, float(chi2.ppf(0.975, 2 * (n + 1)) / 2))


def _binomial95(k: int, n: int) -> tuple[float | None, float | None]:
    """The exact (Clopper-Pearson) 95% interval of k of n."""
    from scipy.stats import beta

    if n <= 0:
        return None, None
    return (float(beta.ppf(0.025, k, n - k + 1)) if k > 0 else 0.0,
            float(beta.ppf(0.975, k + 1, n - k)) if k < n else 1.0)


def quantities(table: pa.Table, report: dict[str, Any], spec: Any, *, days_column: str = "days_to_death",
               among: Any = None, known: Any = None) -> list[dict]:
    """The link's quality as quantities, per horizon of the run (linkage-evidence plan, Q1; GUILD, Gilbert et al. 2018;
    RECORD, Benchimol et al. 2015), where the spec declares the events the left side records itself
    (``outcome.known``: SIH's discharge by death). For each horizon of ``days``:

    - ``pairs``: persons linked to an event within the horizon; ``known_linked`` of them carry the event in their own
      record, ``link_only`` do not (the events only the link finds);
    - ``known``: persons whose own record carries the event within the horizon, linked or not (a study counts them
      without the link);
    - ``expected_chance`` and its exact Poisson interval: the control's pairs (a birth date moved by the control's
      shift, so all false) at the horizon, the run's estimate of its chance pairs;
    - ``false_match_share``: expected chance over all pairs; ``false_match_share_link_only``: over the link-only
      events, an upper bound (it assumes every chance pair falls on a person whose record has no event; the persons
      who do have their own partner, which the one-to-one step prefers);
    - ``sensitivity``: the share of the known events the kept passes that can reach an unrecorded event link (passes
      not ``known_only``), with its exact binomial interval (0 and a ``note`` when none is kept, as on spine surgery
      2019, whose year pass was dropped at 53% chance: ``dropped_passes`` gives its pairs and control pairs); ``sensitivity_any_pass`` with every pass. Taking it for the
      link-only events assumes an unrecorded event is found as often as a recorded one by the same keys: stated, not
      tested (a death after discharge has the same birth date, sex and residence to match, and another hospital or
      none);
    - ``corrected``: known + (link-only − expected chance) / sensitivity, the events within the horizon, with bounds
      from the chance interval and the sensitivity interval taken together (conservative: both ends at once).

    Persons with an event known in their own record but no link count in ``known`` and in the sensitivity's
    denominator. A spec without ``outcome.known`` gives pairs and chance only.

    ``among``: a boolean mask over ``table``'s rows, the subset a claim is about (the paper's analytic cohort). Every
    count is then the subset's, and the control's pairs, counted over the run's whole cohort, are scaled by the
    subset's share of its persons (``expected_chance`` is no longer an integer): this assumes chance pairs fall evenly
    over persons, so a subset of unusual birth dates or towns is not served by it. Dividing the whole cohort's chance
    pairs by a subset's link-only events overstates the share (t03's review: 10-39% at 30 days on the analytic file,
    5-17% on the run's own cohort).

    ``known``: the study's own definition of the events it counts without the link, as days from the origin to the
    event per row of ``table`` (None or NaN where none), in place of the spec's ``outcome.known``: a study that counts
    every death of the chained stay (continuation and transfer AIHs) has more known deaths than the first AIH's
    discharge by death, and the link-only events, their chance share and the sensitivity follow its definition (t07:
    631 of the spec's link-only deaths at 30 days were deaths in the stay)."""
    outcome = spec.outcome
    scale = 1.0
    given: list[int | None] | None = None
    if known is not None:
        vals = known.to_pylist() if isinstance(known, (pa.Array, pa.ChunkedArray)) else list(known)
        if len(vals) != table.num_rows:
            raise ValueError(f"known has {len(vals)} values for {table.num_rows} persons")
        given = [None if v is None or v != v else int(v) for v in vals]     # NaN != NaN
    if among is not None:
        mask = pa.array(among, pa.bool_()) if not isinstance(among, (pa.Array, pa.ChunkedArray)) else among
        if len(mask) != table.num_rows:
            raise ValueError(f"among has {len(mask)} values for {table.num_rows} persons")
        scale = pc.sum(pc.cast(mask, pa.int64())).as_py() / table.num_rows if table.num_rows else 0.0
        table = table.filter(mask)
        if given is not None:
            given = [g for g, m in zip(given, mask.to_pylist(), strict=True) if m]
    rows = table.select([c for c in (days_column, "link_pass", "origin") if c in table.column_names]).to_pydict()
    days = rows[days_column]
    passes = rows["link_pass"]
    ran = {(p.get("name") if isinstance(p, dict) else getattr(p, "name", None)): p for p in report.get("passes") or []}

    def kept(name: str) -> bool:
        p = ran.get(name)
        return True if p is None else bool(p.get("kept") if isinstance(p, dict) else getattr(p, "kept", True))
    reaching = {p.name for p in spec.passes if not p.known_only and kept(p.name)}
    # a pass dropped for its chance share is a quantity too: keeping it and correcting may beat dropping it
    dropped = [{"name": n, "pairs": p.get("pairs"), "control_pairs": p.get("control_pairs"),
                "chance_percent": p.get("chance_percent")}
               for n, p in ran.items() if isinstance(p, dict) and not p.get("kept") and not p.get("skipped")]
    known_days: list[int | None] = [None] * table.num_rows
    has_known = given is not None or outcome.known is not None
    if given is not None:
        known_days = given
    elif outcome.known is not None:
        role, value, date = outcome.known
        flag = [None if v is None else str(v) for v in table.column(role).to_pylist()]
        end, origin = table.column(date).to_pylist(), rows["origin"]
        for i, (f, e, o) in enumerate(zip(flag, end, origin, strict=True)):
            if f == value and e is not None and o is not None:
                known_days[i] = (e - o).days if hasattr(e - o, "days") else int(e - o)
    out = []
    for h in report.get("horizons") or []:
        d = int(h["days"])
        linked = [x is not None and x <= d for x in days]
        known = [k is not None and k <= d for k in known_days]
        pairs = sum(linked)
        raw = int(h.get("control_pairs") or 0)
        lo, hi = (x * scale for x in _poisson95(raw))
        control = raw * scale
        row: dict[str, Any] = {"days": d, "pairs": pairs, "expected_chance": round(control, 2),
                               "expected_chance_95": [round(lo, 2), round(hi, 2)],
                               "false_match_share": round(control / pairs, 4) if pairs else None}
        if has_known:
            n_known = sum(known)
            known_linked = sum(1 for a, b in zip(linked, known, strict=True) if a and b)
            link_only = pairs - known_linked
            reach = sum(1 for k, p in zip(known, passes, strict=True) if k and p in reaching)
            anyp = sum(1 for k, p in zip(known, passes, strict=True) if k and p is not None)
            s_lo, s_hi = _binomial95(reach, n_known)
            sens = reach / n_known if n_known else None
            row.update({
                "known": n_known, "known_linked": known_linked, "link_only": link_only,
                "false_match_share_link_only": round(min(control / link_only, 1.0), 4) if link_only else None,
                "false_match_share_link_only_95": ([round(min(lo / link_only, 1.0), 4), round(min(hi / link_only, 1.0), 4)]
                                                   if link_only else None),
                "sensitivity": round(sens, 4) if sens is not None else None,
                "sensitivity_95": [round(s_lo, 4), round(s_hi, 4)] if sens is not None else None,
                "sensitivity_any_pass": round(anyp / n_known, 4) if n_known else None,
                "sensitivity_passes": sorted(reaching),
            })
            if not reaching:
                row["note"] = ("no kept pass can find an event the left does not record: the link-only events are not "
                               "counted, and the horizon holds the recorded events only")
            if dropped:
                row["dropped_passes"] = dropped
            if sens:
                row["corrected"] = round(n_known + max(link_only - control, 0) / sens, 1)
                row["corrected_bounds"] = [round(n_known + max(link_only - hi, 0) / s_hi, 1),
                                           round(n_known + max(link_only - lo, 0) / s_lo, 1) if s_lo else None]
        out.append(row)
    return out
