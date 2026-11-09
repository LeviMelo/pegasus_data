"""Crude and directly age-standardised rates over the Ministry's denominator.

A rate is counted events over people, in 5-year age bands: 0-4, ..., 75-79,
80+. POPSVS carries single years of age and closes at 80. Direct
standardisation weights each band's rate by a named standard population:
- ``who2000``: the WHO World Standard Population 2000-2025 (Ahmad et al.,
  WHO GPE Discussion Paper 31, 2001), its bands from 80 on folded into 80+;
- ``brazil2022``: Brazil's own 2022 population from POPSVS.

The variance is the usual sum of ``w_b^2 * d_b / n_b^2`` over bands. The 95%
interval is the gamma interval of Fay and Feuer (1997), which stays valid for
small counts.

Events are counted from a records table the caller already queried (deaths,
admissions); this module only needs each record's age in years and,
optionally, a grouping column such as the residence municipality.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pyarrow as pa

#: Band lower bounds: 0, 5, ..., 80 (80 = 80 and over).
BANDS: tuple[int, ...] = tuple(range(0, 85, 5))

#: WHO World Standard 2000-2025 per 100,000, bands 0-4 ... 75-79, then 80+
#: (80-84 910 + 85-89 440 + 90-94 150 + 95-99 40 + 100+ 5).
WHO_2000: tuple[float, ...] = (8860, 8690, 8600, 8470, 8220, 7930, 7610, 7150, 6590,
                               6040, 5370, 4550, 3720, 2960, 2210, 1520, 1545)

__all__ = ["BANDS", "WHO_2000", "age_standardised_rates"]


def _band(age_years: float | None) -> int | None:
    if age_years is None or age_years != age_years or age_years < 0:
        return None
    return min(int(age_years) // 5 * 5, 80)


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
        for key, value in zip(out, (None, unplaced, None, None, None, None, None, 0, standard, None), strict=True):
            out[key].append(value)
    return pa.table(out)
