"""The population account's benchmark: any method scored on the same truths (docs/plans/population.md, unit P1).

A truth is a count the method did not see. Two are here: the 2010 census forecast from 2000 and the 2022 census
forecast from 2010, each with everything fitted on the *other* period (coefficients, spreads, quantiles), which is how
the shipped account was accepted (ADR-0148). A candidate is the account's regression with more columns: a symptom of
population (births per accounted woman, the electoral roll) enters as one column per period and is scored beside the
shipped rows. The Contagens and the surviving births are the plan's other truths, not yet here.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import numpy as np

from . import population_account as pa

SIZES = ("under 5,000", "5-20,000", "20-100,000", "100-500,000", "over 500,000")
REGIONS = ("North", "Northeast", "Southeast", "South", "Centre-West")
AGE_GROUPS = ((0, 1, "0-4"), (1, 3, "5-14"), (3, 6, "15-29"), (6, 12, "30-59"), (12, 17, "60+"))


def with_columns(period: pa.Period, columns: np.ndarray | None) -> pa.Period:
    """``period`` with more regressors: (rows, k) per-year values, known without the closing census."""
    return period if columns is None else replace(period, X=np.column_stack([period.X, columns]))


def score(period: pa.Period, cal: pa.Calibration) -> dict[str, Any]:
    """One period under a calibration fitted elsewhere: the municipal total's median absolute log error (all, by size,
    by region) beside births and deaths alone, the coverage of its 80% and 95% intervals, and by age group the median
    cell error and the 80% coverage of the cells above 20 people."""
    truth = period.truth
    if truth is None:
        raise ValueError(f"period {period.name} has no closing census to score against")
    _, total, bands = pa.predict(period, cal)
    tt, vt = truth.sum((1, 2)), period.vital.sum((1, 2))

    def err(est: np.ndarray) -> np.ndarray:
        return np.abs(np.log(np.maximum(est, 1e-9) / tt))

    def by(e: np.ndarray, key: np.ndarray, values: range) -> list[float]:
        return [round(float(np.median(e[key == v])), 4) if (key == v).any() else float("nan") for v in values]

    e, ev = err(total), err(vt)
    out: dict[str, Any] = {
        "rows": int(len(tt)), "total": round(float(np.median(e)), 4), "births and deaths alone": round(float(np.median(ev)), 4),
        "by size": dict(zip(SIZES, by(e, period.sizec, range(5)), strict=True)),
        "by region": dict(zip(REGIONS, by(e, period.region, range(1, 6)), strict=True)), "coverage": {}, "age groups": {}}
    for level in pa.LEVELS:
        lo, hi = pa.interval(period, cal, total, period.T, level, total=True)
        inside = (np.log(tt) >= lo) & (np.log(tt) <= hi)
        out["coverage"][str(level)] = round(float(inside.mean()), 3)
    lo, hi = pa.interval(period, cal, bands, period.T, 0.8, total=False)
    logt, ok = np.log(np.maximum(truth, 1e-9)), (period.vital > 20) & (truth > 20)
    inside = (logt >= lo) & (logt <= hi)
    for a, b, name in AGE_GROUPS:
        cell = np.abs(np.log(np.maximum(bands[:, :, a:b].sum(2), 1e-9) / np.maximum(truth[:, :, a:b].sum(2), 1e-9)))
        out["age groups"][name] = {"error": round(float(np.median(cell)), 4),
                                   "coverage 0.8": round(float(inside[:, :, a:b][ok[:, :, a:b]].mean()), 3)}
    return out


def transfer(a: pa.Period, b: pa.Period, columns: dict[str, np.ndarray] | None = None) -> dict[str, Any]:
    """Both forecasts, each under the other period's fit. ``columns`` = {"A": (rows, k), "B": (rows, k)} adds the same
    regressors to both periods (a candidate); a candidate known in one period only cannot be scored here."""
    columns = columns or {}
    pa_, pb = with_columns(a, columns.get("A")), with_columns(b, columns.get("B"))
    return {"2000 to 2010, fitted on 2010 to 2022": score(pa_, pa.fit_calibration([pb])),
            "2010 to 2022, fitted on 2000 to 2010": score(pb, pa.fit_calibration([pa_]))}


def benchmark(settings: Any, log: Any = print) -> dict[str, Any]:
    """``pegasus-data model-benchmark``: the shipped account on the benchmark, from the home."""
    inputs = pa.assemble(settings, log=log)
    return {"method": "the account: births, deaths and the previous decade's migration", **transfer(inputs.A, inputs.B)}


#: Correlation of the forecast errors of two municipalities of one micro-region (0.450 fitted on 2000-2010, 0.500 on
#: 2010-2022; evaluation 2026-11-21-population-symptoms).
MICRO_CORRELATION = 0.47


def group_log_sd(total: np.ndarray, log_sd: np.ndarray, micro: np.ndarray, correlation: float = MICRO_CORRELATION) -> float:
    """The log sd of a sum of municipalities' totals inside one state, from each one's own ``log_sd``.

    Municipal errors are not independent: those of a micro-region move together. With a_i = share_i x sd_i,
    var = (1 - rho) sum a_i^2 + rho sum over micro-regions (sum a_i)^2. Fitted on one intercensal forecast and applied to
    the other, the 80% and 95% intervals of the micro-regions' totals cover 0.83 / 0.94 and 0.91 / 0.97. A state's total
    is not this function's: its error did not transfer between the periods, and from `population-account-9` it is
    IBGE's figure (ADR-0228)."""
    a = np.asarray(total, dtype=float) / float(np.sum(total)) * np.asarray(log_sd, dtype=float)
    together = sum(float(a[micro == m].sum()) ** 2 for m in np.unique(micro))
    return float(np.sqrt((1 - correlation) * float((a**2).sum()) + correlation * together))

