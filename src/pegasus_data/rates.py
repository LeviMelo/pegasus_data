"""Crude, directly and indirectly age-standardised rates over the Ministry's denominator.

A rate is counted events over people, in 5-year age bands: 0-4, ..., 75-79,
80+. POPSVS carries single years of age and closes at 80. Direct
standardisation weights each band's rate by a named standard population:
- ``who2000``: the WHO World Standard Population 2000-2025 (Ahmad et al.,
  WHO GPE Discussion Paper 31, 2001), its bands from 80 on folded into 80+;
- ``brazil2022``: Brazil's own 2022 population from POPSVS.

The variance is the usual sum of ``w_b^2 * d_b / n_b^2`` over bands. The 95%
interval is the gamma interval of Fay and Feuer (1997), which stays valid for
small counts.

Indirect standardisation (`indirect_standardised`) applies reference rates by age band and sex to each place's
person-years and returns observed against expected counts, the standardised ratio and its exact Poisson interval
(Garwood 1936; Breslow and Day 1987, vol. II, 2.3): the input of funnels and of area-risk models (BYM2).

Events are counted from a records table the caller already queried (deaths,
admissions); this module only needs each record's age in years and,
optionally, a grouping column such as the residence municipality.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
import pyarrow as pa

from ._age import bands

#: Band lower bounds: 0, 5, ..., 80 (80 = 80 and over).
BANDS: tuple[int, ...] = tuple(range(0, 85, 5))

#: WHO World Standard 2000-2025 per 100,000, bands 0-4 ... 75-79, then 80+
#: (80-84 910 + 85-89 440 + 90-94 150 + 95-99 40 + 100+ 5).
WHO_2000: tuple[float, ...] = (8860, 8690, 8600, 8470, 8220, 7930, 7610, 7150, 6590,
                               6040, 5370, 4550, 3720, 2960, 2210, 1520, 1545)

__all__ = ["BANDS", "WHO_2000", "age_standardised_rates", "indirect_standardised"]


def _band(age_years: float | None) -> int | None:
    if age_years is None:
        return None
    found = int(bands(np.array([age_years]), BANDS)[0])
    return None if found < 0 else BANDS[found]


def _standard(name: str, settings: Any) -> dict[int, float]:
    if name == "who2000":
        return dict(zip(BANDS, WHO_2000, strict=True))
    if name == "brazil2022":
        from .api import load_population

        table = load_population(series="POPSVS", years=2022, by=("municipality", "year", "sex", "age"),
                                settings=settings)
        weights: dict[int, float] = dict.fromkeys(BANDS, 0.0)
        for age, people in zip(table.column("age").to_pylist(), table.column("population").to_pylist(), strict=True):
            band = _band(age)
            if band is None:
                # Unknown age has no band; a standard is the age-known structure.
                continue
            weights[band] += float(people or 0)
        return weights
    raise ValueError("standard is who2000 or brazil2022")


def age_standardised_rates(
    records: pa.Table,
    *,
    year: int,
    age: str = "IDADE_anos",
    by: str | None = None,
    uf: str | Sequence[str] | None = None,
    area: str | Sequence[str] | None = None,
    standard: str = "who2000",
    per: float = 100_000,
    sex: str | None = None,
    settings: Any = None,
) -> pa.Table:
    """Crude and age-standardised rates of ``records`` per ``per`` people in ``year``.

    ``by`` names a municipality column of ``records`` (6 or 7 digits) to rate
    each municipality, or None for one rate over the whole denominator.
    ``uf`` is the denominator's scope: the states the records cover. It is
    inferred from ``by``'s codes when given, and is the nation otherwise.
    ``area`` is where the numerator is complete: state codes ("27") or municipality codes whose residents' events
    ``records`` hold in full. A dataset published by residence (SIM, SINASC) is complete everywhere; one published by
    the place of care (SIH, CIHA: one state's files) is complete only for the state's own residents, and a municipality
    of another state in its records has the full POPSVS denominator and only the events treated here, a crude rate
    that is a fraction of the residence rate (SIH-RD Alagoas rated by MUNIC_RES gave Sergipe and Bahia municipalities
    rates with no flag). With ``area`` only its groups are returned; without it every group is, and
    ``numerator_complete`` is None: the table does not know.
    ``sex`` restricts the denominator ("1" male, "2" female in POPSVS); the
    records must already be that sex.

    Records without an age are counted in ``unaged`` and left out of every
    rate. With ``by``, records whose code places no municipality (`geography.place_municipalities`; a null, a
    code of another width) are one row of ``group`` None carrying their count in ``events``.
    """
    from scipy.stats import chi2

    from .api import load_population
    from .config import load_settings

    settings = settings or load_settings()
    ages = records.column(age).to_pylist()
    from .geography import place_six

    raw = records.column(by).to_pylist() if by else []
    groups = place_six(raw) if by else ["all"] * records.num_rows
    unplaced = sum(1 for g in groups if g is None)
    cases: dict[tuple[str, int], int] = {}
    unaged: dict[str, int] = {}
    for group, value in zip(groups, ages, strict=True):
        if group is None:
            continue
        band = _band(value)
        if band is None:
            unaged[group] = unaged.get(group, 0) + 1
            continue
        cases[(group, band)] = cases.get((group, band), 0) + 1

    prefixes = tuple(str(a) for a in ([area] if isinstance(area, str) else area or ()))
    states = ([uf] if isinstance(uf, str) else list(uf)) if uf else (
        sorted({a[:2] for a in prefixes}) if prefixes and by else sorted({g[:2] for g, _ in cases}) if by else None)
    population = load_population(series="POPSVS", years=year, uf=states,
                                 by=("municipality", "year", "sex", "age"), settings=settings)
    people: dict[tuple[str, int | None], float] = {}
    distinct = sorted({str(m) for m in population.column("municipality").to_pylist()})
    placed_pop = dict(zip(distinct, place_six(distinct), strict=True)) if by else {}
    for municipality, s, a, n in zip(population.column("municipality").to_pylist(), population.column("sex").to_pylist(),
                                     population.column("age").to_pylist(), population.column("population").to_pylist(),
                                     strict=True):
        if sex is not None and str(s) != str(sex):
            continue
        group = placed_pop[str(municipality)] if by else "all"
        if group is None:
            continue
        key = (group, _band(a))
        people[key] = people.get(key, 0.0) + float(n or 0)

    weights = _standard(standard, settings)
    total_weight = sum(weights.values())
    out: dict[str, list[Any]] = {k: [] for k in ("group", "events", "population", "crude_rate", "standardised_rate",
                                                 "ci95_low", "ci95_high", "unaged", "standard", "numerator_complete")}
    for group in sorted({g for g, _ in people} | {g for g, _ in cases}):
        if prefixes and by and not group.startswith(prefixes):
            continue
        events = sum(cases.get((group, b), 0) for b in BANDS)
        pop = sum(people.get((group, b), 0.0) for b in BANDS)
        rate = variance = 0.0
        empty_band = False
        for b in BANDS:
            n, d, w = people.get((group, b), 0.0), cases.get((group, b), 0), weights[b] / total_weight
            if n <= 0:
                empty_band = empty_band or d > 0
                continue
            rate += w * d / n
            variance += w * w * d / (n * n)
        if pop <= 0 or empty_band:
            asr = low = high = None
        else:
            asr = rate * per
            # Fay & Feuer gamma interval; wm is the largest weight per person.
            wm = max((weights[b] / total_weight) / people[(group, b)] for b in BANDS if people.get((group, b), 0) > 0)
            low = (variance / (2 * rate) * chi2.ppf(0.025, 2 * rate * rate / variance) * per
                   if events and variance else 0.0)
            hv, hr = variance + wm * wm, rate + wm
            high = hv / (2 * hr) * chi2.ppf(0.975, 2 * hr * hr / hv) * per
        out["group"].append(group)
        out["events"].append(events)
        out["population"].append(pop)
        out["crude_rate"].append(events / pop * per if pop > 0 else None)
        out["standardised_rate"].append(asr)
        out["ci95_low"].append(low)
        out["ci95_high"].append(high)
        out["unaged"].append(unaged.get(group, 0))
        out["standard"].append(standard)
        out["numerator_complete"].append(True if prefixes and by else None)
    if unplaced:
        # events of no municipality (a null or a code that places none, `geography.place_municipalities`) belong to no
        # rate: they are one row of group None, so the table's events plus these are the records read
        for column, value in zip(out, (None, unplaced, None, None, None, None, None, 0, standard, None), strict=True):
            out[column].append(value)
    return pa.table(out)


_MALE, _FEMALE = ("masculino", "homem", "male"), ("feminino", "mulher", "female")


def _sex_of(records: pa.Table, sex: str, sex_codes: dict | None) -> list[str | None]:
    """Each record's sex as POPSVS writes it ("1" male, "2" female), None where unknown. Codes differ by source (SIH
    writes female 3, SIM 2, role tables F), so they are mapped from ``sex_codes`` or from the labels a
    ``present="analysis"`` query carries (``<sex>_label``), never assumed."""
    raw = [None if v is None else str(v) for v in records.column(sex).to_pylist()]
    if sex_codes is None:
        label = f"{sex}_label"
        if label not in records.column_names:
            raise ValueError(f"sex codes differ by source: pass sex_codes (e.g. SIH {{'1': '1', '3': '2'}}) or records "
                             f"read with present='analysis', which carry {label!r}")
        sex_codes = {}
        for code, lab in zip(raw, records.column(label).to_pylist(), strict=True):
            low = str(lab or "").strip().lower()
            if code is not None and code not in sex_codes:
                sex_codes[code] = "1" if low.startswith(_MALE) else "2" if low.startswith(_FEMALE) else None
    bad = {v for v in sex_codes.values() if v not in ("1", "2", None)}
    if bad:
        raise ValueError(f"sex_codes map to '1' (male), '2' (female) or None, not {sorted(bad)}")
    return [None if v is None else sex_codes.get(v) for v in raw]


def indirect_standardised(
    records: pa.Table,
    *,
    years: int | Sequence[int],
    by: str,
    age: str = "IDADE_anos",
    sex: str | None = None,
    sex_codes: dict | None = None,
    groups: dict | None = None,
    population: pa.Table | None = None,
    reference: pa.Table | None = None,
    area: str | Sequence[str] | None = None,
    ages: tuple[float, float | None] = (0, None),
    settings: Any = None,
) -> pa.Table:
    """Observed and expected events by place, indirect age-sex standardisation over ``years`` pooled.

    ``records`` holds one row per event of those years (the caller filters the event's own date); ``by`` its
    municipality column (any width, placed by `geography.place_six`). The expected count of a place is the sum over
    5-year age bands (80+) and sex of its person-years times the reference rate. ``reference`` None takes the rates
    of the study population itself (events over person-years of every place in ``area``), so expected and observed
    totals agree; otherwise a table of ``band`` (lower bound), ``sex`` ("1"/"2") and ``rate`` per person-year, such as
    another period's rates.

    - ``population``: None reads POPSVS for each of ``years`` and sums them (person-years); otherwise a table of
      ``municipality``, ``age`` (years) or ``band`` (lower bound), ``sex`` ("1"/"2") and ``population``
      (person-years), e.g. a modelled population without private coverage.
    - ``sex``: the records' sex column, mapped through ``sex_codes`` or its labels (`_sex_of`); None standardises by
      age alone.
    - ``groups``: a map from 6-digit municipality to a larger unit (health region); expected and observed are summed
      to it, and the interval is the group's.
    - ``area``: state prefixes ("27") where the numerator is complete. A dataset published by place of care (SIH)
      read for some states is complete only for their residents; places outside ``area`` are dropped from the
      expected and the reference, and their events are counted in ``outside_area``. None: the nation.
    - ``ages``: the closed range of ages kept, on records and population alike.

    Events with no age, no known sex or no place are left out of every ratio and counted on one row of ``group``
    None (columns ``unaged``, ``unsexed``, ``unplaced``, ``outside_area``), so the observed column plus that row's
    counts are the records given. The ratio's 95% interval is the exact Poisson interval of the observed count over
    the expected.
    """
    import json

    import pandas as pd
    from scipy.stats import chi2

    from .api import load_population
    from .config import load_settings
    from .geography import place_six

    settings = settings or load_settings()
    yrs = [int(years)] if isinstance(years, (int, np.integer)) else [int(y) for y in years]
    lo, hi = float(ages[0]), (float("inf") if ages[1] is None else float(ages[1]))
    prefixes = tuple(str(a) for a in ([area] if isinstance(area, str) else area or ()))

    def banded(values) -> np.ndarray:
        idx = bands(np.asarray(values, dtype=np.float64), BANDS)
        return np.where(idx >= 0, np.asarray(BANDS)[np.clip(idx, 0, None)], -1)

    ev = pd.DataFrame({"mun6": place_six(records.column(by).to_pylist()),
                       "age": pd.to_numeric(pd.Series(records.column(age).to_pylist(), dtype="object"), errors="coerce"),
                       "sex": _sex_of(records, sex, sex_codes) if sex else "all"})
    lost = {"unplaced": int(ev.mun6.isna().sum())}
    ev = ev[ev.mun6.notna()]
    if prefixes:
        inside = ev.mun6.str.startswith(prefixes)
        lost["outside_area"] = int((~inside).sum())
        ev = ev[inside]
    else:
        lost["outside_area"] = 0
    lost["unaged"] = int(ev.age.isna().sum())
    ev = ev[ev.age.notna()]
    ev = ev[(ev.age >= lo) & (ev.age <= hi)]
    lost["unsexed"] = int(ev.sex.isna().sum())
    ev = ev[ev.sex.notna()].copy()
    ev["band"] = banded(ev.age)

    if population is None:
        parts = []
        for y in yrs:
            t = load_population(series="POPSVS", years=y, uf=sorted({a[:2] for a in prefixes}) or None,
                                by=("municipality", "year", "sex", "age"), settings=settings)
            parts.append(t.select(["municipality", "sex", "age", "population"]).to_pandas())
        pop = pd.concat(parts, ignore_index=True)
    else:
        pop = population.to_pandas()
    if "band" not in pop.columns:
        a = pd.to_numeric(pop.age, errors="coerce")
        pop = pop[(a >= lo) & (a <= hi)]
        pop = pop.assign(band=banded(pd.to_numeric(pop.age, errors="coerce")))
    else:
        pop = pop[(pop.band >= np.floor(lo / 5) * 5) & (pop.band <= hi)]
    pop = pop[pop.band >= 0]
    distinct = sorted({str(m) for m in pop.municipality})
    six = dict(zip(distinct, place_six(distinct), strict=True))
    pop = pop.assign(mun6=pop.municipality.astype(str).map(six), sex=pop.sex.astype(str) if sex else "all")
    pop = pop[pop.mun6.notna()]
    if prefixes:
        pop = pop[pop.mun6.str.startswith(prefixes)]
    cell = pop.groupby(["mun6", "band", "sex"], as_index=False).population.sum()

    if reference is None:
        n = ev.groupby(["band", "sex"]).size().rename("n").reset_index()
        ref = cell.groupby(["band", "sex"], as_index=False).population.sum()
        orphan = n.merge(ref[["band", "sex"]], on=["band", "sex"], how="left", indicator=True)
        orphan = int(orphan[orphan["_merge"] == "left_only"].n.sum())
        if orphan:
            raise ValueError(f"{orphan} events fall in age-sex cells with no population: check the age range and "
                             "the sex coding")
        ref = ref.merge(n, on=["band", "sex"], how="left")
        ref["rate"] = ref.n.fillna(0) / ref.population
        ref = ref[["band", "sex", "rate"]]
    else:
        ref = reference.to_pandas()[["band", "sex", "rate"]]
        ref = ref.assign(sex=ref.sex.astype(str) if sex else "all")
    cell = cell.merge(ref, on=["band", "sex"], how="left")
    if cell.rate.isna().any():
        missing = sorted({(int(b), s) for b, s in cell[cell.rate.isna()][["band", "sex"]].itertuples(index=False)})
        raise ValueError(f"the reference has no rate for some age-sex cells of the population: {missing[:5]}")
    cell["expected"] = cell.population * cell.rate

    if groups is not None:
        cell["group"], ev["group"] = cell.mun6.map(groups), ev.mun6.map(groups)
        lost["unplaced"] += int(ev.group.isna().sum())
        ev, cell = ev[ev.group.notna()], cell[cell.group.notna()]
    else:
        cell["group"], ev["group"] = cell.mun6, ev.mun6
    out = (cell.groupby("group").agg(expected=("expected", "sum"), population=("population", "sum"))
           .join(ev.groupby("group").size().rename("observed"), how="outer").reset_index())
    out["observed"] = out.observed.fillna(0)
    obs, exp = out.observed.to_numpy(float), out.expected.to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(exp > 0, obs / exp, np.nan)
        low = np.where(obs > 0, chi2.ppf(0.025, 2 * obs) / 2, 0.0) / exp
        high = chi2.ppf(0.975, 2 * (obs + 1)) / 2 / exp

    def clean(col):
        return [None if v is None or (isinstance(v, float) and not np.isfinite(v)) else v for v in col]

    res = {"group": out.group.astype(str).tolist(), "observed": out.observed.astype(int).tolist(),
           "expected": clean(exp.tolist()), "ratio": clean(ratio.tolist()), "ci95_low": clean(low.tolist()),
           "ci95_high": clean(high.tolist()), "population": out.population.fillna(0).astype(float).tolist()}
    for k in ("unaged", "unsexed", "unplaced", "outside_area"):
        res[k] = [0] * len(res["group"])
    if any(lost.values()):
        for k in res:
            res[k].append(lost[k] if k in lost else (0 if k == "observed" else None))
    meta = {"years": yrs, "reference": "internal" if reference is None else "given", "bands": list(BANDS),
            "ages": [lo, None if hi == float("inf") else hi], "by_sex": bool(sex), "area": list(prefixes) or None,
            "population": "POPSVS" if population is None else "given"}
    return pa.table(res).replace_schema_metadata({b"pegasus.standardisation": json.dumps(meta).encode()})
