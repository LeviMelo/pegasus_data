"""The population account forecast: births and deaths projected from their trends, migration from the account's regression.

``project_vital`` runs the cohort-component account forward from a corrected census with the events SIM and SINASC have
published up to ``last_obs`` and, past it, with *projected* ones:

* **Deaths.** The national death rate of each sex × five-year band follows a log-linear trend over the last ten observed
  years (2020-2022 excluded: the COVID years are not a trend); a single age takes the band's rate times its share in the
  reference years; a municipality's rate is the national one times its own ratio to the national rate in the three reference
  years (the last non-COVID years), shrunk toward 1 by 30 expected deaths.
* **Births.** The national births per woman 15-44 follow a log-linear trend; a municipality's is the national one times its
  own ratio in the reference years (shrunk by 100 births), applied to the women the projected account holds.

``forecast_bands`` then moves each band by the migration regression of ``population_account.predict`` at the horizon. The
same code is run from past bases (``pseudo_forecast``) to measure its error by horizon.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

import numpy as np

from .population_account import (
    BANDS,
    LEVELS,
    W_FIRST,
    W_SECOND,
    A,
    advance,
    interval,
    load_events,
    parameters,
    predict,
    to_bands,
    vital_events,
)

DEATH_PRIOR, BIRTH_PRIOR = 30.0, 100.0
FERTILE = slice(15, 45)


def trend_window() -> tuple[int, tuple[int, ...]]:
    """``(window, excluded years)``: the number of last observed years the national trends are fitted on and the years left out of
    the fit and of the reference years (``parameters: trend`` of ``population_account``, with the reason)."""
    declared = parameters()["trend"]
    return int(declared["window"]), tuple(int(y) for y in declared["excluded_years"])


def national_events(settings: Any, years: list[int]) -> tuple[np.ndarray, np.ndarray]:
    """National deaths (Y, 2, A) by sex and single age and births (Y, 2) by sex; an unknown sex or age is spread over the known."""
    d = np.zeros((len(years), 2, A))
    b = np.zeros((len(years), 2))
    for k, y in enumerate(years):
        t = cast("dict[str, Any]", vital_events(settings, "deaths", y, "country"))
        ok = (t["sex"] >= 0) & (t["age"] >= 0)
        np.add.at(d[k], (t["sex"][ok], np.minimum(np.floor(t["age"][ok]), A - 1).astype(int)), t["events"][ok])
        d[k] *= t["events"].sum() / max(d[k].sum(), 1)
        t = cast("dict[str, Any]", vital_events(settings, "births", y, "country"))
        for x in (0, 1):
            b[k, x] = t["events"][t["sex"] == x].sum()
        b[k] *= t["events"].sum() / max(b[k].sum(), 1)
    return d, b


def _fit(years: np.ndarray, log_rate: np.ndarray, base: int):
    """OLS of log rate on year over the last ``trend: window`` observed years without the excluded (COVID) ones: (slope, rate at year ``base``). ``log_rate`` (Y, …)."""
    window, excluded = trend_window()
    use = (years > base - window) & (years <= base) & ~np.isin(years, excluded)
    x = years[use] - base
    y = log_rate[use]
    if len(x) < 3:
        return np.zeros(y.shape[1:]), y[-1] if len(y) else 0.0
    xm = x.mean()
    slope = ((x - xm)[:, None] * (y - y.mean(0)).reshape(len(x), -1)).sum(0) / ((x - xm) ** 2).sum()
    slope = slope.reshape(y.shape[1:])
    return slope, y.mean(0) - slope * xm


class Trends:
    """National death rates by sex × band and births per woman, their trends and the reference-year shapes."""

    def __init__(self, years, nat_deaths, nat_births, nat_pop, base: int, last_obs: int):
        """``nat_pop`` (Y, 2, A): national population on the 1st of August of each of ``years`` (≥ ``base``-ish)."""
        self.base, self.last_obs = base, last_obs
        years = np.asarray(years)
        k = years <= last_obs
        years = years[k]
        D, B, N = nat_deaths[k], nat_births[k], nat_pop[k]
        bd = np.stack([to_bands(D)[:, x] for x in range(2)], 1)                        # (Y, 2, 17)
        bn = to_bands(N)
        self.rate_slope, self.rate_level = _fit(years, np.log(np.maximum(bd / np.maximum(bn, 1), 1e-9)), last_obs)
        women = N[:, 1, FERTILE].sum(-1)
        self.gfr_slope, self.gfr_level = _fit(years, np.log(B.sum(1) / women), last_obs)
        self.sex_ratio = B[-3:].sum(0) / B[-3:].sum()
        ref = [y for y in years if y <= last_obs and y not in trend_window()[1]][-3:]
        self.ref = ref
        sel = np.isin(years, ref)
        self.nat_rate_ref = D[sel].sum(0) / np.maximum(N[sel].sum(0), 1)               # (2, A) single-age
        self.nat_band_ref = bd[sel].sum(0) / np.maximum(bn[sel].sum(0), 1)             # (2, 17)
        self.nat_gfr_ref = B[sel].sum() / women[sel].sum()
        self.years = years

    def rate(self, t: int) -> np.ndarray:
        """National projected band death rates (2, 17) in year ``t``."""
        return np.exp(self.rate_level + self.rate_slope * (t - self.last_obs))

    def gfr(self, t: int) -> float:
        return float(np.exp(self.gfr_level + self.gfr_slope * (t - self.last_obs)))


def municipal_multipliers(tr: Trends, N0: np.ndarray, dep_ref: np.ndarray, births_ref: np.ndarray):
    """Each area's death-rate multiplier (n, 2, 17) and fertility multiplier (n,) against the national reference.

    ``dep_ref`` (n, 2, A) and ``births_ref`` (n,) are the area's deaths and births summed over the reference years; ``N0`` the
    base census (n, 2, A) as the common denominator of area and nation, so growth cancels. Shrunk toward 1 by the expected counts."""
    nb = to_bands(N0)
    d = to_bands(dep_ref)
    expected = nb * tr.nat_band_ref * len(tr.ref)
    cd = (d + DEATH_PRIOR) / (expected + DEATH_PRIOR)
    women = N0[:, 1, FERTILE].sum(-1)
    eb = women * tr.nat_gfr_ref * len(tr.ref)
    return cd, (births_ref + BIRTH_PRIOR) / (eb + BIRTH_PRIOR)


def project_vital(N0: np.ndarray, tr: Trends, mult, obs_deaths: np.ndarray, obs_births: np.ndarray, steps: int, first_year: int):
    """The vital account ``steps`` years from ``N0`` (n, 2, A), whose census date is August of ``first_year``.

    ``obs_deaths`` (Y, n, 2, A) and ``obs_births`` (Y, n, 2) are the published events of ``first_year``, ``first_year+1``…
    up to ``tr.last_obs``; later years are projected from the population at the step's start. Returns the path (steps+1, n, 2, A)."""
    cd, cb = mult
    shape = tr.nat_rate_ref / np.maximum(tr.nat_band_ref[:, BANDS], 1e-12)             # single age within band, (2, A)
    N = N0.copy()
    path = [N]

    def events(year: int, N):
        k = year - first_year
        if year <= tr.last_obs and k < len(obs_deaths):
            return obs_deaths[k], obs_births[k]
        rate = (tr.rate(year)[:, BANDS] * shape)[None] * cd[:, :, BANDS]
        women = N[:, 1, FERTILE].sum(-1)
        b = tr.gfr(year) * cb * women
        return N * rate, b[:, None] * tr.sex_ratio[None]

    for k in range(steps):
        y = first_year + k
        D1, B1 = events(y, N)
        D2, B2 = events(y + 1, N)
        N = advance(N, W_FIRST * D1 + W_SECOND * D2, W_FIRST * B1 + W_SECOND * B2)
        path.append(N)
    return np.array(path)


def forecast_bands(P, cal, vital_bands: np.ndarray, h: int):
    """``population_account.predict`` at horizon ``h`` with the period's vital account replaced by the projected one."""
    return predict(replace(P, vital=vital_bands), cal, float(h))


#: Spread (log, per year of horizon) the projection of births and deaths adds to a municipality's total. Measured as the
#: robust spread of log(total with projected events / total with the events that happened): 0.0047 a year from base 2000
#: (five years of history), 0.0017 from base 2010 (ten). The product takes 0.003.
EVENT_SD_PER_YEAR = 0.003
Z_LEVEL = {0.8: 1.2816, 0.95: 1.96}


def forecast_account(inp, cal, settings: Any, steps: int = 8) -> dict:
    """The account ``steps`` years after the reconciled 2022 census (2023 is the first, with observed events).

    Returns ``X`` (steps, entities, 2, A) single ages, ``bands`` (steps, entities, 2, 17) and, per level, the log offsets
    ``off[level] = (lower, upper)`` of the band intervals (steps, entities, 2, 17): the account's own interval at the horizon
    in quadrature with ``EVENT_SD_PER_YEAR`` · h."""
    years = list(range(2000, 2024))
    nd, nb = national_events(settings, years)
    npop = np.concatenate([inp.path_a.sum(1)[:11], inp.path_b.sum(1)[1:13], inp.vit22.sum(0)[None]])
    tr = Trends(years, nd, nb, npop, 2022, 2023)
    ev = load_events(settings, list(range(2010, 2024)), inp.places, "entity")
    ref = [y - 2010 for y in tr.ref]
    mult = municipal_multipliers(tr, inp.start22, ev["deaths"][ref].sum(0), ev["births"][ref].sum((0, 2)))
    path = project_vital(inp.start22, tr, mult, ev["deaths"][12:], ev["births"][12:], steps, 2022)
    X, bands = [], []
    off: dict[Any, tuple[list[Any], list[Any]]] = {lv: ([], []) for lv in LEVELS}
    for h in range(1, steps + 1):
        vb = to_bands(path[h])
        centre = forecast_bands(inp.P22, cal, vb, h)[2]
        X.append(np.maximum(path[h] * np.divide(centre, vb, out=np.ones_like(centre), where=vb > 0)[..., BANDS], 0))
        bands.append(centre)
        for lv in LEVELS:
            lo, hi = interval(inp.P22, cal, centre, float(h), lv, total=False)
            c = np.log(np.maximum(centre, 1e-9))
            extra = (Z_LEVEL[lv] * EVENT_SD_PER_YEAR * h) ** 2
            off[lv][0].append(np.sqrt((c - lo) ** 2 + extra))
            off[lv][1].append(np.sqrt((hi - c) ** 2 + extra))
    return {"X": np.array(X), "bands": np.array(bands), "off": {lv: (np.array(a), np.array(b)) for lv, (a, b) in off.items()},
            "trends": tr}
