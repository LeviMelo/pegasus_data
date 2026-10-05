# Population account: a 2010–2022 hold-out against the PES-corrected census, and calibrated intervals

**Question.** Does a cohort-component account of every municipality (`population_account.py`), fitted on 2000→2010 only, predict the 2022 population better than the vital-registration projection alone, and are its 10–90% intervals honest?

**Scenario.** `holdout.py` (train on the raw 2000 and 2010 censuses with SIM/SINASC 2000–2010, forecast 2010→2022 from the raw 2010 census with SIM/SINASC 2010–2022 and no 2022 information) and `score2.py`; artifacts `data/probes/population_account/` (`score_shared.log`, `score_rec.log`, `calib_out.log`). Regime: 2026-10-05, core data home, 5,559 entities (municipalities; five composites of a post-2010 creation and its parents), 100 draws, persistence of the estimated deviations (0, 0.7, 0.45, 0.3) fixed from SIDRA table 200 (1991→2000 against 2000→2010) before scoring.

**Truth.** The PES-corrected 2022 census (enumerated count raked onto the PES net-error margins: age × sex, state, size class; `sources/pes.py`). Never POPSVS, which is IBGE's own reconciliation and rests on the same births and deaths. The corrected cells are an estimate (only margins are published). The raw census and IBGE's reconciliation are sensitivities.

## Point estimates (median absolute error of the municipal total)

| reference | account | vital projection only | 2010 held constant | 2000–10 growth extrapolated |
|---|---|---|---|---|
| PES-corrected | **0.057** | 0.079 | 0.073 | 0.082 |
| raw census | 0.058 | 0.081 | 0.069 | 0.087 |
| IBGE-reconciled | 0.050 | 0.066 | 0.071 | 0.075 |

- By size against PES-corrected, account / vital: under 5k 0.060 / 0.091; 20–100k 0.053 / 0.064; over 500k 0.041 / 0.037 (the account loses on the largest cities).
- Ages 15–29 in places under 5k: 0.139 / 0.263.
- National 2022: PES-corrected 211.96M; account 209.97M (−0.9%); vital 209.08M (−1.4%). The account is low at ages 0–9 by 0.40M boys and 0.76M girls (the vital projection is within 0.15M there).
- Sensitivity, censuses brought to IBGE's reconciled coverage first: 0.066 against 0.088 for the vital projection from the same base; total +1.7%. The cause of its higher median than the raw base is not found.
- Persistence of every deviation at 1 gives 0.063 (0.09 in small places): what carries between periods matters.

## Intervals

The draws of the parameters (estimated hierarchy, redrawn deviations that do not persist, census-quality noise) cover the truth in only 60% of municipalities at the nominal 80%. By size they were equally short (0.59–0.64), so the missing part is shared by all ages of a place: the coverage of the base census differing from 2022's, and migration that did not repeat. The residuals about the draws, on the log scale, had a standard deviation of 7–9% within states in places under 100k (the draws' own: 5.8%) and 5% between states (the truth above the account by 15% in Roraima and 11% in Santa Catarina, below it by 11% in Amapá).

`SHARED_SD` adds one multiplicative factor per place, mean one: national 0.02 (the order of IBGE's reconciled 2010 undercount, 2.2%), state 0.046, municipal 0.058 / 0.053 / 0.042 / 0.030 / 0.020 by size class. State and municipal terms are method-of-moments estimates **from this hold-out's residuals**, so its coverage is in-sample; the out-of-sample check leaves one of the five regions out, estimates on the other four and scores the fifth.

| 10–90% coverage | in-sample | leave one region out |
|---|---|---|
| municipal total, all | 0.794 | 0.806 (pooled) |
| by region N / NE / SE / S / CO | 0.66 / 0.81 / 0.84 / 0.80 / 0.67 | 0.65 / 0.83 / 0.85 / 0.82 / 0.67 |
| entity × sex × band, 0–4 / 5–14 / 15–29 / 30–59 / 60+ | 0.78 / 0.90 / 0.86 / 0.86 / 0.91 | |
| 2.5–97.5% interval (nominal 0.95) | 0.911 | |

Median half-width of the 10–90% interval is 11.7% of the municipal total. What it takes: a 1.5 to 2 times wider interval than the parameter draws give, because errors of 2022 coverage and of migration are shared across ages. The tails are fatter than normal (0.91 at 95%), and the North and Center-West are under-covered at 0.66.

## The product

`population-account-1` (modelled tier, ADR-0145; `build_smoke.py`, 800 sweeps, 100 draws, core data home, 4,503,606 rows, 11,031 places). It holds no row after 2022: the intervals were validated for a forecast twelve years ahead; a one-year extension was not, and a row of it was dropped. The interior of an anchored intercensal period is narrower than the hold-out's by construction and is not separately validated.

## Assumptions not estimated

- The share of deaths not registered is fixed at 10% for 2000–2010 (not identifiable from cohorts: it is collinear with old-age migration), closing afterwards.
- Coverage enters the product as IBGE's published corrections, not as a fitted latent term: 2022 by the PES margins raked onto cells, 2000 and 2010 by IBGE's reconciliation (made with the 2022 PES, so a sensitivity).

## Build check (population-account-1)

- Yearly totals meet the anchors: 174.70M (2000), 194.75M (2010), 211.96M (2022, the PES-corrected census); no nulls; `lo <= population <= hi` in every row.
- Between two censuses the draws are closed onto both and their spread multiplied by sin(πk): the median half-width of a municipal total is 0 at the censuses, 3.1% a year after 2010, 12.1% in 2016 (the hold-out's 11.7%) and 3.2% a year before 2022. The tapered interior is **not** validated; only its middle matches the hold-out's width.
- A first build (v1, without the shared factor, with a 2023 row, no anchor at the opening census) was deleted: its intervals were the 60% ones.
- `registration_completeness` (SINASC by state and half-period) runs 0.85 to 1.10, median 0.995; above 1 means the census counted fewer children than were registered, not registration.
