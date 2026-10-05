## ADR-0148: population-account-2 carries the closing census's residual between censuses and projects by the previous decade's migration

**Date:** 2026-10-05. **Status:** active. **Supersedes** ADR-0145 items 1, 2, 5 and 6 (product, method, intervals, extrapolation); its coverage rule (item 3) and PES-scored validation principle (item 4) stand. **Request:** PegaSUS P8 and a denominator for SIM 2023.

**Context.** `population-account-1` (Gibbs-sampled hierarchical migration) had no skill on 2000→2010 (0.077 against 0.076 vital-only, 80% coverage 0.69), no row after 2022, and band intervals nobody had calibrated. A five-regressor regression of the census's departure from the vital account on the previous decade's cohort net migration beats vital-only on both periods and its intervals transfer between them (docs/evaluation/2026-10-05-population-account-v2.md).

**Decision.** Product `population_account` version `population-account-2` (`population_account.py`), municipality or comparable area × sex × five-year band × year, with 80% and 95% intervals, `basis` (`intercensal` | `projection`) and `years_after_census`.
1. **Between censuses** (2000–2010 on comparable areas, 2010–2022 on municipalities) the vital account (SIM, SINASC) opens on the corrected census and the closing census's departure is carried along each cohort in equal parts (`distribute_residual`). The census gives net migration there, so nothing is modelled.
2. **After the last census** (2023, as far as the events reach) the vital account is moved by exp(h · ŷ), ŷ a per-year regression of log(truth / vital) on the cohort net migration of the previous decade (area, shrunk; state and micro-region means; ages 10–24, 25–54, 55+), urban share and GDP per head, and for bands on each band's own lagged rate; each sex × band keeps the vital account's national total. Coefficients are fitted on both periods.
3. **Intervals.** sd² = 0.02² (completeness of the base census) + (0.0012 h)² + s²·h after a census; inside a period the bridge s²·T·κ(1−κ), κ = k/T. s is the robust spread of leave-one-region-out residuals by size class (total: a region multiplier and empirical quantiles), the larger of the two periods'. Band spreads, per size × band, are then scaled until both periods' 80% and 95% intervals reach nominal; the factors (×1.02 to ×1.48) are in the manifest.
4. **Validation.** Coefficients and spreads from one period scored on the other: total median error 0.052 / 0.056 against 0.074 / 0.079, 80% coverage 0.79 / 0.84. The √h law is checked on the 2007 Contagem at 6.7 years (spread ratio 0.81 against 0.82 for √ and 0.67 for linear; 80% coverage 0.794).
5. `registration_completeness` is not rebuilt: its births shortfall came from the Gibbs model. `registration_completeness/population-account-1` stays, and `completeness.py` reads it. `sus_dependent.py` takes the latest `population_account` version by name, now `-2`.

**Not decided.**
- Coverage as a latent term; the 2022 urban share is the 2010 one (SIDRA 202 has no 2022).
- Horizons of 1–3 years from a census are untested; the back-cast against the account's own interior is circular (the interior is a straight line by construction).
- The band widening is fitted on the periods it is scored on; cells under 20 people are not scored.
- Past 2023 (no SIM or SINASC for 2024), a projection would need assumed births and deaths.
