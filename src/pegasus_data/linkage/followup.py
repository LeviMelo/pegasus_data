"""A cohort's follow-up through a declared link: each record of a topic's cohort with the date of its partner's event.

A paper on the hospital admissions of one condition needs more than the admissions that ended in death: the 30-day and
1-year mortality of a cohort counts the deaths of those discharged alive, which only a link to the death certificate of
any cause reaches. The link is declared once with its parameters (``curation/links.yml``: ``params``, ``outcome``) and
run for the caller's codes, years and area (``engine.link(codes=...)``, stored per run). This module is the reader:

    fu = linked_deaths("SIH-RD", ["I21", "I22"], years=range(2018, 2023), geography="AL")
    fu.table             # one row per person: record, origin, death_date, days_to_death, death_record, link_pass, p_match
    fu.quality           # verdict, false-match rate at each horizon, validations, the last day of deaths the data hold
    fu.mortality(30)     # {"followed": ..., "died": ..., "rate": ...}, 30-day mortality over those followed that long

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

from ..ontology import dataset_key
from . import store
from .engine import (
    LinkNotViable,
    Outcome,
    _prepare,
    _roles_needed,
    _side_table,
    bind,
    link,
    load_links,
    padded_period,
    right_geography_for,
    stored_key,
)
from .identity import connect, quote

__all__ = ["Followup", "RunNotStored", "linked_deaths"]


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

    @property
    def window(self) -> int:
        return int(self.quality["window_days"])

    def horizon(self, days: int) -> dict[str, Any]:
        """The quality of the follow-up within ``days``: the first horizon of the run that covers it."""
        for row in self.quality["horizons"]:
            if row["days"] >= days:
                return row
        raise ValueError(f"the run looks for deaths within {self.window} days, not {days}")

    def died_within(self, days: int, *, allow_not_viable: bool = False) -> pa.Array:
        """Whether each person died within ``days`` of the origin: True, False (alive at ``days`` and followed that long)
        or null (followed for less: the origin plus ``days`` is past the last day of deaths the data hold). Refused
        (`LinkNotViable`) when the run's verdict at that horizon is "not viable", as pairs of a linkage that fails its
        own verdict look like pairs of one that passes."""
        row = self.horizon(days)
        if row["verdict"] == "not viable" and not allow_not_viable:
            raise LinkNotViable(_Refusal(self.quality["link"], row))
        died = pc.fill_null(pc.less_equal(self.table.column("days_to_death"), days), False)
        end = self.quality["death_data_end"]
        if end is None:
            return pc.if_else(died, True, pa.scalar(None, pa.bool_())).combine_chunks()
        last = (datetime.date.fromisoformat(end) - datetime.date(1970, 1, 1)).days
        followed = pc.less_equal(pc.add(pc.cast(self.table.column("origin"), pa.int32()), days), last)
        return pc.if_else(died, True, pc.if_else(pc.fill_null(followed, False), False,
                                                 pa.scalar(None, pa.bool_()))).combine_chunks()

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


class _Refusal:
    """A horizon's verdict shaped as the result `LinkNotViable` reads."""

    def __init__(self, spec: str, row: dict[str, Any]) -> None:
        self._summary = {"spec": spec, "chance_percent": row["chance_percent"], "validations": {}, "pairs": row["pairs"],
                         "verdict_reasons": row["verdict_reasons"], "horizon_days": row["days"]}

    def summary(self) -> dict[str, Any]:
        return self._summary


def cohort_link(dataset: str, name: str | None = None) -> str:
    """The declared cohort link (one with ``params`` and an ``outcome``) that follows ``dataset``'s records."""
    specs = load_links()
    cohorts = {n: s for n, s in specs.items() if s.params is not None and s.outcome is not None}
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
    from ..config import UF_NUMERIC

    def one(a: object) -> str:
        text = str(a).strip().upper()
        return UF_NUMERIC.get(text, text)

    return [one(a) for a in area] if isinstance(area, (list, tuple, set)) else one(area)


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

    ``match`` "principal" takes the codes on the principal diagnosis, "any" on every diagnosis of the admission. ``roles``
    names further roles of the cohort's records to return (those the link reads come back anyway). The result's quality
    holds the false-match rate and verdict of each horizon; the cohort is the first admission of each person in the
    period (a person is a birth date, sex and residence), so a readmission is not a second person.

    Example::

        fu = linked_deaths("SIH-RD", ["I21", "I22"], years=range(2018, 2023), geography="AL")
        fu.mortality(30)
    """
    from ..config import load_settings

    name = cohort_link(dataset, link_name)
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
        "horizons": report.get("horizons") or [], "window_days": _window(spec),
        "passes": report.get("passes") or [], "validations": report.get("validations") or {},
        "cohort": table.num_rows, "linked": linked, "linked_share": round(linked / table.num_rows, 4) if table.num_rows else 0.0,
        "death_data_end": ((report.get("carried") or {}).get(outcome.event) or {}).get("last"),
        "run_seconds": seconds, "run": key.stem,
    }
    return Followup(table, quality, pairs, report)


def _window(spec: Any) -> int:
    window = spec.left.explode_days[1] if spec.left.explode_days else None
    if not isinstance(window, int):
        raise ValueError(f"{spec.name}: a cohort link looks for the event within a window of days (explode_days)")
    return window


def _table(spec: Any, pairs: pa.Table, report: dict[str, Any], period: object, area: object, extra: list[str],
           query_kwargs: dict[str, Any]) -> pa.Table:
    """The cohort of the left side as the run saw it (the same filter, group and identity), left-joined to the pairs."""
    outcome: Outcome = spec.outcome
    wanted = sorted(set(_roles_needed(spec, "left")) | set(extra) | {outcome.origin})
    left = _side_table(spec.left, wanted, period=period, geography=area, **query_kwargs)
    con = connect()
    _prepare(con, "L", left, replace(spec.left, explode_days=None))
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
