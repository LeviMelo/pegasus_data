# population-account-3: municipalities, single ages and race — what was measured and what is calibrated

**Scenario.** `data/probes/population_account/v4/` (gitignored): `split_cal.py`, `split_cal2.py`, `births_slope.py` (the split), `race_hold.py` (race hold-outs), `build.py`, `verify_v3.py`. Regime: branch pegasus-core-fixes, core data home 2026-10-05, SIDRA 9606/2093/793, events directory 2000-2023.

**Why 15 municipalities were missing.** Santarém+Mojuí, Laguna+Pescaria Brava, Içara+Balneário Rincão, Bento Gonçalves+Farroupilha+Cotiporã+Pinto Bandeira and the Mato Grosso do Sul group of six were composite entities: a municipality created after 2010 has no 2010 base, so `build_places` joined it to its parents and the label became `a+b+c`. 58 municipalities created 2001-2009 were comparable-area rows before 2010. Both are now split.

## Municipal split (items 1-2)

3,583 pairs of a small (1,000-40,000) and a larger (3-60×) municipality of one micro-region that never changed boundary; 2010 census as anchor; error of the logit share of the small one against the 2007 Contagem (3 years) and the 2000 census (10 years), MAD by class of the small member's size (<2k, <5k, <20k, above):

| estimator | 2000 | 2007 |
|---|---|---|
| constant share | 0.136 0.120 0.115 0.114 | 0.065 0.059 0.058 0.059 |
| births share ratio (SINASC by residence) | 0.246 0.234 0.182 0.128 | 0.227 0.173 0.133 0.108 |
| 0.25 × births ratio | 0.121 0.111 0.105 0.092 | 0.074 0.071 0.063 0.058 |
| **0.5 × the 2010-2022 growth differential** | **0.134 0.105 0.099 0.081** | **0.063 0.057 0.056 0.056** |
| Contagem 2007 as anchor, then the 0.5 differential | 0.100 0.086 0.085 0.081 | |

The births indicator the author suggested (events by residence, coded to a new municipality from its first year: 42 of the 58 in 2001) is worse than no information; the competing explanation (fertility differs between neighbours and drifts) is the likely reason, not tested further. For a creation known only in 2022, births slope added nothing either (weights 0 / 0.25 / 0.5 / 1: MAD 0.205 / 0.214 / 0.279 / 0.477 at 22 years). Error law fitted on the pairs: σ² = σ₀² + k·years; on the 56 real creations with a Contagem 2007 count (2010 anchor, 3 years): median error 0.010, MAD 0.055, coverage 0.82 (80%) and 0.93 (95%) with the quantiles of the pairs' standardized errors (1.48 and 2.76). The five post-2010 creations: σ = 0.0098·years (from the constant-share errors at 12 and 22 years), never validated on a real creation. Mojuí dos Campos 2010 is 19.6k (backcast from 25.4k in 2022): a fast-growing place is probably under-estimated at the earliest years and its interval too narrow.

## Single ages (item 3)

Ages 0-79 are `distribute_residual`'s own single-year path, so bands add to population-account-2 exactly. Within-band share error, the vital account's shape at the end of a period against the closing census (ages 0-79, ten and twelve years): a² 0.0015, b² 0.96 (u = (1−p)/(p·N)); old ages, the state shape interpolated to 2010 between 2000 and 2022 against each municipality's 2010 shares: a² 0.022, b² 0.83. These are the spreads at the largest gap; the product bridges them by κ(1−κ) inside a period. Not calibrated: the interior of a period at single-age resolution has no observation to score against (the censuses are the only single-age data).

## Race (item 4)

Municipal composition scored on the 2010 census at 5-year age bands (cells ≥ 200 people); mean absolute error of the share in percentage points, all races:

| path | method | mean abs. error (pp) |
|---|---|---|
| bridge, ages 10-79, 2010 from 2000 and 2022 | log-linear along the cohort | **2.26** |
| | hold the 2000 shares / hold the 2022 shares | 3.79 / 2.54 |
| forward, ages 10-79, 2010 from 2000 | no reclassification | 3.79 |
| | state drift of the *other* decade (2010→2022) | 3.36 |
| | state drift of the same decade (in-sample) | 3.06 |
| back, ages 0-9, 2010 from 2022 | no reclassification | 3.92 |
| | rate of the other decade (2000→2010) | 3.02 |
| | rate of the same decade (in-sample) | 2.01 |

Reclassification is real and decade-specific: the other decade's rate recovers about half of the gain the same decade's would give, and the Branca share is still biased by +5 pp (back) and +2.8 pp (forward) with it. Spreads (a², b²) fitted on these errors, not centred so a bias is part of the spread: bridge 0.0083, 0.88; back 0.026, 0.22; forward 0.020, 0.56. In the product the bridge path of a 10-12 year gap is scored with the 22-year gap's spread (conservative); the back and forward paths are scored at the ten- and twelve-year horizons used here. 2000 race is the IBGE sample (noisy in small places); the 2010-2022 Asian count falls from 2.1M to 0.85M (rates capped at 0.08 a year).

## Build

(see below)
Built by `data/probes/population_account/v4/build.py` (population_tensor.build_account, one pass of about 25 minutes after a heavy-queue wait): `population-account-3`, 162,020,160 rows (5,570 municipalities × 24 years × 2 sexes × 101 ages × 6 race levels), 3.58 GB. Checked by `verify_v3.py` and a final count: 5,570 municipalities in every year; national totals 174.696 / 194.749 / 211.962 / 213.013 M in 2000 / 2010 / 2022 / 2023, equal to population-account-2's; the municipal band sums of 2010-2023 equal version 2 (2,646,084 cells, largest relative difference 6e-8); the five races add to the total (largest difference 0.017 people); no null or negative cell, no interval out of order; basis counts (municipality-years) census 16,542, intercensal 109,856, backcast 1,712, forecast 5,570. National race counts: 2000 Branca 94.5M, Parda 67.8M; 2010 93.1M, 83.9M; 2022 91.7M, 96.4M (the Parda share 38.8%, 43.1%, 45.5%).

**Calibrated:** the band totals and intervals (ADR-0148); the split error law on pairs and, at three years, on the 56 real creations; the race and single-age spreads at the hold-out horizons. **Not calibrated:** the five post-2010 creations, the interior of a period at single-age resolution and for race (no observation between censuses), 2000 race by single age (sample), the intervals at the census years of the race cells (the cell is a smoothed share, its interval the account's).

## Forecast to 2030 (stage 2, `population-account-4`)

`population_forecast.py`: births and deaths projected from their national trends (log-linear, ten non-COVID years; municipal level from the three reference years, shrunk by 30 deaths and 100 births), the account run forward from the corrected census, the band moved by the migration regression at the horizon. Measured by **pseudo-forecasts with the package code** (`pseudo.py`, output `pseudo_out.txt`; events after the base withheld; coefficients and spreads from the *other* period; interior = the account's own intercensal estimate, truth at the last horizon = reconciled Census 2010 / PES-corrected 2022); median absolute log error of the municipal total, model against the vital account alone, and coverage of the interval (80% / 95%) with the event-projection term of 0.003 per year added:

| horizon (years) | base 2000 (units, 5 years of history) model / vital-only, cov | base 2010 (entities, 10 years of history) model / vital-only, cov |
|---|---|---|
| 1 | 0.0054 / 0.0080, 0.99 / 1.00 | 0.0046 / 0.0077, 1.00 / 1.00 |
| 4 | 0.0235 / 0.0333, 0.92 / 0.98 | 0.0193 / 0.0310, 0.97 / 0.99 |
| 8 | 0.0494 / 0.0705, **0.81 / 0.94** | 0.0393 / 0.0617, **0.89 / 0.98** |
| 10 | 0.0627 / 0.0901 (Census 2010), 0.76 / 0.92 | 0.0498 / 0.0767, 0.86 / 0.97 |
| 12 | | 0.0608 / 0.0863 (PES 2022), **0.83 / 0.96** |

By size at the last horizon (80% coverage): base 2000 <5k 0.73, 5-20k 0.71, 20-100k 0.79, 100-500k 0.80, 500k+ 0.73; base 2010 0.86, 0.83, 0.72, 0.64, 0.84; by region (N, NE, SE, S, CO) 0.63 0.67 0.83 0.76 0.74 and 0.82 0.83 0.77 0.80 0.81. Intermediate horizons are scored against the interior, itself an estimate anchored at the closing census, so their coverage is conservative; the last-horizon rows are against a census. **Calibrated: the municipal total up to eight years (the product's 2030) from both bases, and twelve from base 2010**; not calibrated: the 100-500k class (0.64 at twelve years from 2010), the North and Northeast from base 2000, single ages and race in the forecast (their spreads are the hold-out ones at ten and twelve years, scaled by horizon). The projection of events adds a spread of 0.0047 a year (base 2000, five years of history, a death-rate trend of −2.7% a year fitted on 1996-2000) and 0.0017 (base 2010); the product takes 0.003. National total 2030: 219.2M (213.0M in 2023, trend −1.0% a year in death rates, −1.8% in births per woman); the vital-only error of base 2000 is +2.2% and of base 2010 −2.2% at the end (the opening census is raw 2010: the protocol of ADR-0148).

Built as `population-account-4` (`build.py`, 209,276,040 rows, 4.60 GB, 2000-2030): identical to `-3` for 2000-2023; national total 215.2M in 2025 and 219.2M in 2030 (Parda 100.9M, Branca 89.7M, Preta 26.3M); forecast basis on 44,560 municipality-years (2023-2030); no null or negative cell and no interval out of order.
