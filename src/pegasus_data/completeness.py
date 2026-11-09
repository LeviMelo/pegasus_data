"""Completeness of SIM and SINASC by state and year (modelled tier).

What share of the deaths and births that happened was registered? Three sources, none a truth:

* **Published** (``resources/published_coverage_idb2012.csv``): the Ministry of Health / IBGE ratio of
  registered to estimated events by UF, 2000-2011 (IDB 2012, indicators A.17 and A.18). Estimated events
  are the sum of municipal events corrected by factors from the 2008 *Busca Ativa* survey (Legal Amazon and
  Northeast); where no survey was made (South, Southeast, DF, MS) the ratio is **assumed 100%**, not measured.
* **Growth balance** (Brass / Hill 1987), from our own SIM and the censuses: a demographic estimate of death
  completeness *relative to the census* that does not depend on the Ministry's factors. It assumes a closed
  population and constant census coverage by age, so migration and age misstatement bias it; it is a check
  on the published series and on the extension, not a replacement.
* **The model** (``extend``): from the last published year onward, the logit of completeness follows a random
  walk whose step variance and whose dependence on the ill-defined-cause share are estimated on the published
  years and scored on a held-out tail.

SINASC births are compared with the census instead (``registration_completeness``, from the population account's cohorts).
"""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

UFS = [11, 12, 13, 14, 15, 16, 17, 21, 22, 23, 24, 25, 26, 27, 28, 29, 31, 32, 33, 35, 41, 42, 43, 50, 51, 52, 53]
AGES = 101      # single years 0..99 and an open 100+ (the 2022 census)
RESOURCES = Path(__file__).parent / "resources"


def published() -> dict[tuple[str, int, int], float]:
    """(system, uf, year) -> published registered/estimated ratio, as a fraction (1.0 where assumed complete)."""
    with open(RESOURCES / "published_coverage_idb2012.csv", encoding="utf-8") as f:
        return {(r["system"], int(r["uf"]), int(r["year"])): float(r["ratio"]) for r in csv.DictReader(f)}


# ------------------------------------------------------------------------------------------- inputs

def census_uf(root: str | Path, year: int) -> np.ndarray:
    """The census (raw count) by UF × sex × single age, shape ``[27, 2, AGES]``."""
    import pyarrow.parquet as pq

    t = pq.read_table(Path(root) / "lake" / "population" / "CENSO" / f"censo_{year}.parquet",
                      columns=["municipality", "sex", "age", "population"]).to_pydict()
    out = np.zeros((len(UFS), 2, AGES))
    pos = {u: i for i, u in enumerate(UFS)}
    for m, s, a, p in zip(t["municipality"], t["sex"], t["age"], t["population"], strict=True):
        if p is None or int(s) not in (1, 2) or int(m) // 100000 not in pos:
            continue
        out[pos[int(m) // 100000], int(s) - 1, min(int(a), AGES - 1)] += p
    return out


def events_uf(events_dir: str | Path, year: int, kind: str) -> np.ndarray:
    """Deaths ``[27, 2, AGES]`` or births ``[27]`` of a year by residence UF; unknown sex or age is spread over
    the known cells of the UF in proportion (totals kept). Events with no UF are returned as ``unplaced``."""
    import pyarrow.parquet as pq

    t = pq.read_table(Path(events_dir) / f"{kind}_{year}.parquet").to_pydict()
    pos = {u: i for i, u in enumerate(UFS)}
    codes = t["residence"]
    uf = np.array([pos.get(int(c[:2]), -1) if c and c[:2].isdigit() else -1 for c in codes])
    ev = np.array(t["events"], dtype=float)
    if kind == "births":
        out = np.zeros(len(UFS))
        np.add.at(out, uf[uf >= 0], ev[uf >= 0])
        return out
    from .population_account import SEX_INDEX

    sx = np.array([SEX_INDEX.get(s, -1) for s in t["sex"]])
    ag = np.array([-1 if a is None else min(int(float(a)), AGES - 1) for a in t["age"]])
    out = np.zeros((len(UFS), 2, AGES))
    ok = (uf >= 0) & (sx >= 0) & (ag >= 0)
    np.add.at(out, (uf[ok], sx[ok], ag[ok]), ev[ok])
    rest = (uf >= 0) & ~ok
    extra = np.zeros(len(UFS))
    np.add.at(extra, uf[rest], ev[rest])
    tot = out.sum((1, 2))
    share = np.divide(out, tot[:, None, None], out=np.full_like(out, 1 / (2 * AGES)), where=tot[:, None, None] > 0)
    return out + extra[:, None, None] * share


def interval_events(per_year: dict[int, np.ndarray], y0: int, y1: int) -> np.ndarray:
    """Events between the census dates of 1 August y0 and 1 August y1: 5/12 of y0, whole years, 7/12 of y1."""
    total = 5 / 12 * per_year[y0] + 7 / 12 * per_year[y1]
    for y in range(y0 + 1, y1):
        total = total + per_year[y]
    return total


# ------------------------------------------------------------------------------------ growth balance

def _logmean(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    a, b = np.maximum(a, 1e-9), np.maximum(b, 1e-9)
    d = np.log(b) - np.log(a)
    flat = np.abs(d) < 1e-9
    return np.where(flat, a, (b - a) / np.where(flat, 1.0, d))


def growth_balance(n1: np.ndarray, n2: np.ndarray, deaths: np.ndarray, years: float,
                   ages: range = range(10, 60, 5)) -> dict[str, float]:
    """Hill's growth balance for one population: ``n1``, ``n2`` the two censuses and ``deaths`` the interval's
    deaths, each by single age (1-d, ``AGES`` long). Returns completeness (1 / slope of b(x) - r(x+) on d(x+)),
    its 90% interval (Theil-Sen slope interval), and the intercept (the ratio of the censuses' coverage)."""
    from scipy.stats import theilslopes

    r_, d_, b_ = [], [], []
    for x in ages:
        a1, a2 = n1[x:].sum(), n2[x:].sum()
        py = years * _logmean(np.array(a1), np.array(a2))             # person-years above x over the interval
        g1, g2 = n1[x - 5:x].sum(), n2[x - 5:x].sum()
        r = np.log(a2 / a1) / years
        # reaching age x per year: the age group's mean flow (that of age x - 2.5), brought forward 2.5 years of growth
        entrants = _logmean(np.array(g1), np.array(g2)) / 5 * np.exp(-2.5 * r)
        r_.append(r)
        d_.append(deaths[x:].sum() / py)
        b_.append(entrants * years / py)
    r_, d_, b_ = np.array(r_), np.array(d_), np.array(b_)
    y = b_ - r_
    slope, intercept, lo, hi = theilslopes(y, d_, alpha=0.9)
    return {"completeness": float(1 / slope), "lo": float(1 / hi) if hi > 0 else float("nan"),
            "hi": float(1 / lo) if lo > 0 else float("nan"), "intercept": float(intercept)}


# ------------------------------------------------------------------------------------- the extension

#: IBGE changed its projection base in 2010 (the South/Southeast stop being "100%", the North/Northeast move):
#: the 2009 -> 2010 step is a change of denominator, not of registration, and is left out of every estimate.
BREAK = 2010
#: A series the Ministry did not measure (it set the ratio to 100% in every year to 2009) says nothing about change.
ASSUMED = 0.995
#: Standard deviation (probability scale) of the published ratio itself: SIM, the 94.2% of IDB 2012 against the 96.1%
#: the Ministry's own 2011 consolidation gave for the same year; SINASC, the spread across states of the census-based
#: completeness about the published one (0.025-0.036 by period, population account).
ANCHOR_SD = {"SIM": 0.02, "SINASC": 0.03}
#: SIM follows a drift (the published ratios rose in every uncensored state); SINASC persists (its drift was not better).
MODEL = {"SIM": "drift", "SINASC": "persist"}


def _logit(p):
    p = np.clip(p, 1e-3, 0.999)
    return np.log(p / (1 - p))


def _expit(x):
    return 1 / (1 + np.exp(-x))


def series(system: str) -> dict[int, np.ndarray]:
    """Published logit series 2000-2011 of the states that were measured (not assumed complete before 2010)."""
    pub = published()
    out = {}
    for u in UFS:
        v = np.array([pub[(system, u, y)] for y in range(2000, 2012)])
        if (v[:10] < ASSUMED).all():
            out[u] = _logit(v)
    return out


def steps(logit_series: dict[int, np.ndarray]) -> np.ndarray:
    """Year-to-year changes of the logit across states, without the 2009 -> 2010 break."""
    return np.concatenate([np.delete(np.diff(s), BREAK - 2001) for s in logit_series.values()])


def rolling_origin(system: str, scales=(0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 2.5)) -> dict:
    """Forecast the last published years from earlier ones: origins 2005-2008 (and 2010 for h=1) and horizons
    1-3 within one denominator base, drift and sd re-estimated at each origin from earlier steps only.
    Returns errors on the probability scale, and the smallest scale ``k`` of the interval
    ``logit ± 1.2816·k·sd·sqrt(h)`` whose pooled coverage reaches 80%."""
    S = series(system)
    model = MODEL[system]
    rows = []
    for t0 in (2005, 2006, 2007, 2008):
        k0 = t0 - 2000
        st = np.concatenate([np.diff(s[:k0 + 1]) for s in S.values()])
        delta, sd = (st.mean() if model == "drift" else 0.0), st.std()
        for s in S.values():
            for h in (1, 2, 3):
                if k0 + h > 9:
                    continue                                   # stay inside the first base
                pred = s[k0] + h * delta
                rows.append((h, s[k0 + h] - pred, _expit(s[k0 + h]) - _expit(pred), sd))
    e = np.array(rows)
    cover = {k: float(np.mean(np.abs(e[:, 1]) <= 1.2816 * k * e[:, 3] * np.sqrt(e[:, 0]))) for k in scales}
    k = next((k for k in scales if cover[k] >= 0.8), scales[-1])
    mae = {int(h): float(np.mean(np.abs(e[e[:, 0] == h, 2]))) for h in (1, 2, 3)}
    return {"k": k, "coverage_by_scale": cover, "mae_probability_by_horizon": mae, "n": len(e)}


def ill_defined_shares(cells_path: str | Path) -> dict[tuple[int, int], float]:
    """Share of deaths whose underlying cause is a symptom or sign (ICD-10 R00-R99 without R95, sudden infant death),
    by UF and year, from the stored municipality × year × cause aggregate of SIM. A quality covariate, not a completeness."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    t = pq.read_table(cells_path, columns=["municipality", "competencia", "CAUSABAS", "deaths_n"])
    c3 = pc.utf8_slice_codeunits(pc.utf8_upper(t["CAUSABAS"]), 0, 3)
    ill = pc.and_(pc.starts_with(c3, "R"), pc.not_equal(c3, "R95"))
    g = pa.table({"uf": pc.cast(pc.utf8_slice_codeunits(t["municipality"], 0, 2), pa.int32()),
                  "year": pc.cast(pc.utf8_slice_codeunits(t["competencia"], 0, 4), pa.int32()),
                  "n": t["deaths_n"], "ill": pc.if_else(ill, t["deaths_n"], 0.0)})
    g = g.group_by(["uf", "year"]).aggregate([("n", "sum"), ("ill", "sum")]).to_pydict()
    return {(u, y): i / n for u, y, n, i in zip(g["uf"], g["year"], g["n_sum"], g["ill_sum"], strict=True) if n > 0}


def build_completeness(root: str | Path, ill_cells_path: str | Path, *, version: str, validation: str,
                       last_year: int = 2023, log=print) -> dict:
    """Write the ``system_completeness`` modelled product: SIM deaths and SINASC births, by UF and year."""
    import json
    from types import SimpleNamespace

    import pyarrow as pa
    import pyarrow.parquet as pq

    from .modelled import ModelledManifest, write_modelled

    pub = published()
    ill = ill_defined_shares(ill_cells_path)
    base = Path(root) / "lake" / "modelled" / "registration_completeness"
    acct_dir = base / sorted(p.name for p in base.iterdir())[-1]
    acct = pq.read_table(acct_dir / "estimates.parquet").to_pylist()
    independent = {(r["uf"], y): r["completeness"] for r in acct if r["system"] == "SINASC"
                   for y in range(int(r["period"][:4]), int(r["period"][5:]) + 1)}        # the years the cohort was born in
    rows, calibration = [], {}
    for system in ("SIM", "SINASC"):
        S = series(system)
        st = steps(S)
        delta = float(st.mean()) if MODEL[system] == "drift" else 0.0
        sd = float(st.std())
        ro = rolling_origin(system)
        k = ro["k"]
        calibration[system] = {"drift_logit_per_year": delta, "step_sd_logit": sd, "interval_scale_k": k,
                               "rolling_origin": ro, "model": MODEL[system]}
        for u in UFS:
            measured = u in S
            anchor = pub[(system, u, 2011)]
            for y in range(2000, last_year + 1):
                if y <= 2011:
                    p, sdp, h = pub[(system, u, y)], ANCHOR_SD[system], 0
                    basis = "published" if (measured or y >= BREAK) else "published_assumed_complete"
                    published_ratio = p
                else:
                    h = y - 2011
                    p = float(_expit(_logit(anchor) + h * delta))
                    sdp = float(np.hypot(ANCHOR_SD[system], p * (1 - p) * k * sd * np.sqrt(h)))
                    basis, published_ratio = "extended", None
                p = min(p, 1.0)
                hi = min(p + 1.2816 * sdp, 1.0)
                if system == "SINASC" and independent.get((u, y)) is not None:
                    hi = min(max(hi, independent[(u, y)]), 1.0)        # the census-based estimate where it is higher
                rows.append({"system": system, "uf": u, "year": y, "completeness": p,
                             "completeness_lo": max(p - 1.2816 * sdp, 0.0), "completeness_hi": hi,
                             "basis": basis, "horizon": h, "published_ratio": published_ratio,
                             "ill_defined_share": ill.get((u, y)) if system == "SIM" else None,
                             "census_based_estimate": independent.get((u, y)) if system == "SINASC" else None})
    gap = {name: [r["census_based_estimate"] - r["completeness"] for r in rows if r["system"] == "SINASC"
                  and r["census_based_estimate"] is not None and sel(r["year"])]
           for name, sel in (("2000-2011", lambda y: y <= 2011), ("2012-2021", lambda y: y > 2011))}
    gap_note = "; ".join(f"{k}: {np.mean(v) * 100:+.1f} points (SD {np.std(v) * 100:.1f}, n={len(v)})" for k, v in gap.items() if v)
    table = pa.Table.from_pylist(rows)
    manifest = ModelledManifest(
        product="system_completeness", version=version,
        model="published Ministry/IBGE ratio (IDB 2012 A.17, A.18) to 2011, then a logit drift (SIM) or persistence "
              "(SINASC) with an interval calibrated by rolling-origin on the published years; completeness.py v2",
        estimates={"completeness": ["completeness_lo", "completeness_hi"]},
        inputs={"published ratio": "tabnet.datasus.gov.br/cgi/idb2012/a17b.htm, a1801b.htm (IBGE and MS/SVS)",
                "ill-defined share": "SIM municipality × year × cause aggregate", "census-based SINASC": acct_dir.parent.name + "/" + acct_dir.name},
        validation=validation,
        notes=["Completeness is registered / (registered + unregistered) of events in the UF of residence; 'published' rows are the "
               "Ministry's ratio of registered to estimated events, where the estimate rests on the 2008 Busca Ativa factors "
               "(Legal Amazon, Northeast) and on IBGE's projections; ratio > 1 is capped at 1.",
               "Before 2010 the South, Southeast, MS and DF are assumed 100% by the Ministry, not measured: basis 'published_assumed_complete'.",
               "The interval is 80%. Its calibration holds to a horizon of three years (rolling origin); beyond 2014 it is an extrapolation "
               "checked only against independent estimates (see the evaluation entry).",
               "SINASC: where a census-based estimate exists (the 0-4 and 5-9 cohorts of the 2010 and 2022 censuses, registration_completeness) "
               "the upper bound is raised to it if it is higher; census-based minus the completeness above (published to 2011), mean over state-years: " + gap_note + ".",
               "No municipal completeness: the Ministry's municipal factors were not found, and a state-level association does not carry to municipalities.",
               f"Calibration: {json.dumps(calibration)}"])
    settings = SimpleNamespace(lake_dir=Path(root) / "lake")
    path = write_modelled(table, manifest, settings=settings)
    log(f"written {path} rows={table.num_rows}")
    return {"path": path, "calibration": calibration}
