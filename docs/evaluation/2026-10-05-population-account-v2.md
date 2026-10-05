# Population account v2: a lagged-migration regression has skill on both intervals; shipped as `population-account-2`

**Question.** `population-account-1` beat the vital-only projection on 2010→2022 (0.057 against 0.079) but not on 2000→2010 (0.077 against 0.076, 80% intervals covering 0.69; [population-account entry](2026-10-05-population-account.md)). Is there a method with skill and calibrated intervals on both, and what limits it?

**Method (probe `data/probes/population_account/v2/`, `pa2_final.py`; core data home, 2026-10-05).** For each period, y = log(truth / vital-only projection of the municipal total). Regressors, all from before the period opens: the previous decade's cohort net-migration rate of the area at ages 10–24 / 25–54 / 55+ (survival-ratio on SIDRA table 200, empirical-Bayes shrunk toward the national mean, as in `persistence.py`), its state mean and micro-region mean, and (v2 full) urban share and log GDP per capita (tables 202, 5938). The same code runs on both periods. **Coefficients and interval spreads for a period come only from the other** (spreads: the other period's leave-one-region-out residuals by size class, a multiplier per region, empirical quantiles, 2% national term); the national total is held at the vital projection's, so nothing about the truth's level enters. Period A (2000→2010) is on IPEA comparable areas (5,472 units: the 58 municipalities created after 2000 sit with their parents, which the v1 check did not do); period B (2010→2022) on the 5,559 entities. Truth: B the PES-corrected census; A the 2010 census at IBGE-reconciled coverage (made with the PES, so a sensitivity), raw census beside it.

## Municipal total, median absolute error

| | A 2000→2010 | B 2010→2022 |
|---|---|---|
| vital only | 0.074 | 0.079 |
| own area's adult rate only | 0.052 | 0.066 |
| + state and micro-region means | 0.053 | 0.062 |
| + young and old rates | 0.053 | 0.060 |
| + urban share, GDP per capita (full v2) | 0.054 | **0.055** |
| `population-account-1` (Gibbs hierarchy) | 0.077 | 0.057 |

- Full v2 against vital by region (N/NE/SE/S/CO): A 0.088/0.063/0.043/0.048/0.079 against 0.099/0.080/0.057/0.082/0.091; B 0.080/0.048/0.053/0.055/0.078 against 0.099/0.088/0.064/0.078/0.097. By size, v2 is better in every class but the largest (500k+: A 0.028 against 0.026, B 0.040 against 0.037; n = 39 and 47).
- Sensitivity truths: A raw 0.057 against 0.072; B raw 0.054 against 0.081, B IBGE-reconciled 0.052 against 0.066. Leave-one-region-out coefficients within a period: A 0.053, B 0.055 (no period shift costs nothing visible).
- The other period's coefficients explain 22% (A) and 27% (B) of the weighted variance of y. Coefficients fitted on A / on B: young rate 0.13 / 0.15, old 0.06 / 0.23, state mean 0.12 / 0.37, micro-region 0.18 / 0.14, urban share 0.05 / 0.08, log GDP 0.04 / 0.03; the own 25–54 rate is slightly negative (−0.04 / −0.05) beside its own state and micro-region means. The state mean and the old-age rate are the least stable.
- Urban share and GDP help B (0.060 → 0.055) and not A (0.053 → 0.054). Municipal totals only need the shrunk own rate and the pooling.

## Intervals (80% and 95%, municipal total)

| | A | B |
|---|---|---|
| 80%, size classes only | 0.811 | 0.805 |
| 80%, + region multiplier | 0.800 | 0.807 |
| 95%, + region multiplier | 0.947 | 0.948 |
| 80% by region N/NE/SE/S/CO | 0.73/0.71/0.88/0.85/0.80 | 0.84/0.83/0.76/0.81/0.83 |
| median half-width of the 80% interval | 12.2% | 13.0% |

Without the multiplier the North and Center-West cover 0.63–0.71 in both periods (the same weakness as v1's 0.66); with it, 0.73–0.84. The multipliers (N 1.6/1.5, CO 1.45/1.4, SE 0.8/1.0) transfer for N and CO and not for the Southeast, which is why the regional rows still range 0.71–0.88.

## Age detail

A single slope per sex-band on the total's deviation recovers part of it. Adding each band's own previous-decade rate (SIDRA, ages 10–79) does more: median entity × sex × band error at 15–29 in places under 5k, vital / total slope / own rate, **B 0.265 / 0.217 / 0.189** (v1: 0.139) and **A 0.247 / 0.136 / 0.098**; the other bands move by a point or two, children not at all. Band-level 80% intervals (same cross-period scheme) cover 0.77 in both periods pooled, but 0–14 in A only 0.60–0.66 and 15–29 in B 0.71 (`pa2_ageband.py`, `pa2_ageband.log`).

## What it means

- Municipal net migration persists enough between decades, once the area's own rate is shrunk and pooled to the state and micro-region, to beat the vital-only projection by about 30% on both intervals, with a 5-parameter regression. The Gibbs hierarchy of `population_account.py` is not needed for that; it is better mainly at ages 15–29 in small places on B.
- A is a transfer test, not a forecast: its coefficients come from the later period; the feature set was chosen looking at both periods' scores (the table is the selection); GDP is of 2002 for A. Treat 0.054 as optimistic by an unknown margin.
- This entry first concluded "not shipped" (the anchored product had no forecast to give the regression to). Superseded: the regression now moves the account after 2022, and it shipped as `population-account-2` (section below, ADR-0148).

## Shipped as `population-account-2` (package code, 2026-10-05)

**What changed from the probe.** The method moved from `data/probes/population_account/v2/` into `population_account.py` (`fit_calibration`, `predict`, `interval`, `assemble`) and v1's Gibbs hierarchy was removed from the code (its product `population-account-1` stays in the lake). The regression is per year (log deviation and lagged rates divided by the horizon and lag length), so it applies to any horizon, and the size class is the start population, not the truth. Probe `data/probes/population_account/v3/validate.py` reproduces the table (core data home, SIDRA 200 fetched into the lake): municipal-total median error A **0.052** against vital 0.074, B **0.056** against 0.079; 80% / 95% coverage A 0.791 / 0.936, B 0.838 / 0.966 (coefficients and spreads from the other period; the probe's 0.054 / 0.055 and 0.80 / 0.81 used each period's spreads at its own length).

**Horizon law (item 3).** The spread of the deviation was equal at 10 years (A, end spread 0.090) and 12 (B, 0.086), which cannot tell a linear law from a √ law. The **2007 Contagem** (SIDRA 793, counted 6.67 years after the 2000 census) can: on the 5,238 comparable areas under 100,000 (larger ones' 2007 figures are IBGE estimates), against the vital account from the raw 2000 census with the raw 2010 deviation as closing, the spread of the regression's error at 6.67 years is **0.81** of that at 10 (√ law 0.82, linear 0.67); the 80% / 95% interval of the √ law covers 0.794 / 0.940, the linear law 0.724 / 0.905. The path wanders from the straight line between the censuses with a variance 0.86 of a Brownian bridge's (size classes 0–2: 0.82, 0.91, 0.73). Shipped: sd² = 0.02² + (0.0012 h)² + s²·h, with the bridge s²·T·κ(1−κ) inside a period (`TIMING_VARIANCE` 1, the measured 0.86 rounded up). Back-cast (`widen_backcast.py`): the A-fit projected from 2010 for k = 1…12 against the account's own interior has median error 0.0046 (k = 1) to 0.057 (12) against 0.0075 to 0.088 vital-only, and the 80% interval covers 0.997 at k = 1 and 0.824 at 12. That check is **not independent**: the interior is the straight-line residual by construction, so its error grows linearly and the √ interval is wide at short horizons; only the Contagem tests the law. Not tested: a horizon of 1–3 years from a census.

**Band intervals (item 2).** 80% coverage of sex × band cells above 20 people, by band group (0–4 / 5–14 / 15–29 / 30–59 / 60+):

| | A | B |
|---|---|---|
| transfer, spreads and coefficients from the other period | 0.63 / 0.66 / 0.79 / 0.80 / 0.75 | 0.89 / 0.84 / 0.79 / 0.79 / 0.84 |
| shipped (larger spread of the two, then widened to nominal in both; in-sample) | 0.80 / 0.83 / 0.83 / 0.84 / 0.81 | 0.92 / 0.87 / 0.82 / 0.83 / 0.85 |

Children and 80+ do not transfer from B to A (0.63, 0.53 and 0.62 for 0–4, 5–9, 80+); 5–9 is over-covered the other way (0.92). The shipped spread of each size × band is the larger of the periods', then each band's is scaled (×1.02 to ×1.22, 80+ ×1.48; listed in the manifest) until both periods' 80% and 95% intervals reach their nominal share. Per band the shipped 80% coverage is 0.80–0.88 (A) and 0.80–0.94 (B); 95% is 0.95–0.98 and 0.95–0.99, so B is conservative where A set the width. The widening is fitted on the two periods it is scored on. Cells under 20 people are not scored. Band point errors, cross-period, median entity × sex × band, 15–29 in places under 5k: A 0.222 vital → 0.098, B 0.245 → 0.149 (v1 0.139).

**Product** (`population-account-2`, 4,692,612 rows, 181 MB; `python data/probes/population_account/v3/build.py`, 234 s). National totals 174.70 M (2000), 194.75 M (2010), 211.96 M (2022) by construction, 213.01 M in 2023 (`basis` = `projection`, +0.5%; 0–4 −3.0%, 75–79 +5.7%). Median 80% half-width of 30–34-year-old municipal cells: 2.7% at 2010, 11.5% in 2016, 3.3% at 2022, 7.0% in 2023. 2023 is the only projected year: SIM and SINASC 2024 are not in the events.
