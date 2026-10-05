# Population account v2: a lagged-migration regression has skill on both intervals; the shipped product has no forecast to give it to

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
- **Not shipped as `population-account-2`.** The product is anchored on both censuses of each period and has no row after 2022, so a forecast model changes nothing in its point estimates, and the band-level intervals are not calibrated (0.60 for children in A). What the result supports is a forward projection from 2022 (municipal totals first), whose interval would still need the horizon: both validations are ten and twelve years ahead. Open question added.
