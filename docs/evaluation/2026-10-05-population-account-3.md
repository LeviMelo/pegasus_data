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

## Backcast to 1991 (stage 3, `population-account-5`)

**Scenario.** `data/probes/population_account/v5/` (gitignored): `collect_dor.py`, `collect_pre96.py` (events), `prep.py`, `score1-4.py` (hold-out; output `score_final.log`), `build5.py`; code `population_backcast.py`. Regime: branch pegasus-core-fixes, core data home 2026-10-05.

**The HTTP 500 on SIDRA 306, diagnosed.** Table 306 does not exist: the catalog (`/agregados`, 9,336 tables) lists no 306 (the Contagem research CM has 21 tables: 305, 319, 472-484, 552, 553, 579, 580, 793-798), `/306/metadados`, `/periodos` and `/variaveis` answer 500 `Internal server error` with a browser User-Agent (305, 307 and 200 answer 200 from the same host), `/306` answers 404, and the old API (`apisidra.ibge.gov.br/values/t/306`) says "Tabela inválida". The 50,000-value and URL-length limits were not involved (the requests were metadata). Tried: the planner/`sidra show 306`, the three metadata endpoints, the catalog listing, the legacy API. The Contagem 1996 sex × age tables are **475** (17 five-year groups to 70+, sex, situation; 4,974 municipalities, 156,658,740 people in the 15 groups, the official count being 157,070,163 with age ignored) and **472** (single age, declared or presumed; 1,024,644 rows); both fetched through the planner (4 and 28 requests, no refusal).

**Events.** `SIM.DO` starts in 1996; 1991-1995 are `SIM.DOR` (corrected base; `IDADE_anos` exists; no `death` event type is declared, so read with `query`, non-fetal only: all rows are). The city of Rio de Janeiro is coded 3345xxx in SIM and SINASC until 1998 (50,000 deaths a year against 700-1,500 under 330455) and 330455 from 1999 (49,979): without the alias 7.2-8.0% of 1991-1998 deaths were unplaced, with it 1.8% (state-level codes xx0000), like 2000's 0.7% (`LEGACY_CODES`). SINASC 1994-1995 (2.57M and 2.87M births against about 3.5M) is collected and not used: the backward account needs no births.

**Method.** Comparable areas 1991-2010 (4,294 with the five post-2010 parents); the vital account run backward from the coverage-corrected Census 2000 with SIM deaths, settled on the Census 1991 (SIDRA 200 by five-year group, 146,825,475, equal to the universe count) with the departure carried along each cohort (zero at 2000, all at 1991); 1991 coverage is the 2000 census's by state × sex × band carried back (POPSVS starts in 2000). Interval: the cross-period spread of ADR-0148 with the Brownian bridge between the two censuses.

**Hold-out, the Contagem 1996 (4,294 areas, 156.7M people; the area estimate never saw it).** Median |log error| of the area total, after rescaling the national total to the Contagem's ("shape"), all ages / ages 5+ (the forward run has no births):

| estimate at 1996 | all ages | ages 5+ | by size <5k, 5-20k, 20-100k, 100-500k, 500k+ (ages 5+) |
|---|---|---|---|
| **interior** (backward from 2000, settled on 1991: the product) | 0.0296 | 0.0282 | 0.030 0.030 0.026 0.023 0.013 |
| log-linear interpolation of the band counts between the censuses | 0.0293 | 0.0274 | 0.031 0.030 0.024 0.022 0.014 |
| backward from 2000 alone (4 years, vital account) | 0.0563 | 0.0563 | 0.068 0.063 0.046 0.029 0.024 |
| forward from 1991 alone (5 years, deaths only) | | 0.0662 | 0.065 0.072 0.063 0.059 0.032 |

The account does not beat plain interpolation of the totals (it cannot: both ends are anchored); what it adds is the age structure, the deaths and the cohorts. The one-sided runs are what the earlier stages call the vital-only account: no migration regression is applied (the 1980 census by municipality that a lagged signal for 1991 needs was not fetched). **Level:** the interior is 5.0% above the Contagem's count (164.6M against 156.7M); the Contagem 1996 is a raw count, and raw 1991 and 2000 interpolated alone are 1.6% above it (159.2M), the other 3.4% being the coverage correction of the two censuses; with raw 1991 and the corrected 2000 the shape error is 0.0276 (0.0281 carried): the two readings of 1991 are not told apart. The 1996 level is not validated. Coverage of the interior's interval at 1996 on the shape-rescaled count, area totals / sex × band cells (14 bands, > 20 people), 80% / 95%: spread of 2000-2022 as it is 0.785 / 0.927 and 0.740 / 0.917; **times 1.2 (`PRE_SCALE`, one scalar chosen on this hold-out) 0.831 / 0.942 and 0.798 / 0.944**, half-width of an area total 6.7% / 12.0%.

**Municipalities.** 3,601 municipalities that are their own area: median error 0.0295 (the area's). 693 areas (1,969 municipalities) have a municipality created after 1991 and are split. A member's 1996 count is comparable with the estimate only if every member of the area existed in 1996 (265 areas; the others' Contagem counts are on the old boundaries), and then the Contagem anchors the split (member error equal to the area's, 0.0288, by construction). The split from the 2000 anchor alone (the 428 other areas) was scored on those 265 areas with the Contagem withheld (621 members, four years): MAD of the logit share 0.095; the stage-1 law covered 0.68 (80%) and 0.87 (95%); the standardized-error quantiles are 2.16 and 4.58 (stage 1: 1.48, 2.76) and are what the product uses (`PRE_ZQ`).

**Race.** Not estimated before 2000. The 1991 Census has race by municipality only as a total (SIDRA 136, 5,565 municipalities, no age or sex) and by age group × sex only for Brazil, regions and states (SIDRA 140: N1-N3); a municipal race × age cell has no 1991 anchor. **Before 1991** is not built: the 1980 census by municipality and age was not fetched, and SIM 1979-1990 (`SIM.DOR`) would need comparable areas 1980-2010.

**Build.** `population-account-5` (`build5.py`, about 12 minutes unwrapped, the heavy queue being hours long): `-4`'s row groups unchanged (2000-2030) behind 10,126,260 new rows (5,570 municipalities × 1991-1999 × 2 × 101 ages, `race = total`), 219,402,300 rows, 4.89 GB. Checked by `verify5.py`: 5,570 municipalities in every year; national totals 151.12M (1991), 161.86M (1995), 164.55M (1996), 172.25M (1999), then 174.70M (2000) and 194.75M (2010) as in `-4`; no null or negative cell and no interval out of order; basis 1991 `census` 3,601 municipalities, `backcast` 1,969, 1992-1999 `backcast`; the municipalities of an area add to the area's interior to the tenth of a person; the refactor of `tensor_tables` into `age_cells` reproduces `-4` exactly for the Federal District (37,572 rows, largest difference 0).

## Timing of the residual (`population-account-6`)

**Question.** The births-exposure test (pegasus_project `docs/evaluation/2026-10-05-exposure.md`) found the account's women 20-44 running 1-4% above POPSVS after 2019 and its small places 2% lower after the 2022 Census. POPSVS is another estimate, not the truth; so first, what each can say. **Scenario:** `data/probes/population_account/v6/` (gitignored): `check22.py`, `timepath.py`, `sizepath*.py`, `schedule.py`, `explain.py`, `ct96*.py`, `area96.py`, `verify_lib.py`, `build6.py`. Regime: branch pegasus-core-fixes, core data home, 2026-10-05.

**At 2022, against the PES-corrected census** (`check22.py`; the account equals it by construction, so only POPSVS is informative). POPSVS sums to 210.86M against 211.96M (-2.1% for women 20-44); by municipality (single-municipality entities, women 20-44) it is +1.2% in places under 20,000 people (median |log| 0.014), about 0 at 20-100k and -2.3% / -3.6% at 100-500k / 500k+; by region the median is +1.7% in the Northeast, about 0 in the North and Centre-West. The truth is a rake of IBGE's published margins (age-sex, state, size class), modelled, and IBGE's reconciliation used the PES too: this comparison shows that POPSVS and the PES-corrected census distribute the 2022 population differently by place size, not which is right. One partial arbiter: ages 0-4 are all born after 2010, so births less deaths bound them; the PES-corrected count is 1.050 times that in places under 5,000 (POPSVS 1.081), 1.002 at 50-100k (1.021), 0.935 at 500k+ (0.941): in small places the corrected census is nearer the births than POPSVS is (children's migration and registration not removed, and the account uses those births).

**Where the disagreement starts** (`timepath.py`, `sizepath.py`). It is not a post-2019 event. Women 20-44, account/POPSVS nationally: 1.003 (2011), 1.010 (2015), 1.017 (2019), 1.021 (2022). The vital path alone (no migration) runs 16% above POPSVS by 2022 in places under 20,000, so both estimates remove that much through net migration; the account removes it **evenly through the twelve years** and POPSVS does not: the account/POPSVS ratio of those places rises to 1.019 (2016) and falls to 0.990 (2022).

**Competing explanations** (each with the measurement that separates it):

| | measurement | result |
|---|---|---|
| (a) COVID mortality of women under-propagated | SIM women 20-44 deaths 2020-22 over 2019 (`explain.py`) | +6,378, +21,922, +4,189: 0.077% of the 42.45M women, against a 2-4% gap; deaths are the registered ones in the path. **Rejected** |
| (b) migration after 2019 extrapolated from the 2010s | 2020-22 are interior years closed on the census (no regression); the forecast starts in 2023 | **Not it for 2020-22**; the migration is the even timing below |
| (c) the 2022 anchoring and its coverage by age and sex | POPSVS against the corrected census (above) and ages 0-4 against births | level differs by size class (POPSVS +1.2% small, -3% large); at 0-4 the corrected census is nearer the births in small places. Level shifts are absorbed by the births model's place effects. **Not the cause of the test's loss**, and not shown wrong |
| (d) the blend around 2022 | 2022 -> 2023 change of women 20-44, account against POPSVS (`explain.py`) | account / POPSVS: under 5,000 -0.8% / -1.7%, 5-10,000 -0.5% / -1.0%, 20-50,000 -0.2% / -0.2%: no step at the join (the account falls at half POPSVS's rate in the smallest places, in 2020-22 at twice it). **Rejected** |
| (e) **the residual is spread evenly through the years** | cohort residuals by age at the end of 2000-2010 and 2010-2022 (`schedule.py`) | **Supported** (next paragraphs) |

**The residual is an age schedule, not a constant.** The residual of the cohort that ends a period at age *a* is the sum of its yearly net migration (net of coverage change) over the ages it passed; solved for the yearly rates by age with a second-difference penalty (`fit_schedule`), per sex and size class, the rates sit at ages 15-27 and have the same shape in 2000-2010 and 2010-2022 and for both sexes: places under 5,000 lose 3-4% of a cohort a year at 18-22 (women, 2010-22: -3.3% at 20, -2.9% at 22; 2000-10: -3.4%, -1.9%), places over 500,000 gain 1.6-2.1% at 18-20, and the rates are within about one point of zero after 30. A cohort that is 8-12 in 2010 (20-24 in 2022) therefore loses its people in 2018-2022, not 2010-2022.

**Independent check, the Contagem 1996 by age** (SIDRA 475, 3,601 single-member areas; never used by the area estimate; schedule from the 2000-2022 periods, so out of the period; `ct96lib.py`). After rescaling each area and sex to its Contagem total, the mean log bias of the estimate at 1996 by age group, even timing against the schedule, in areas under 5,000: women 15-19 +0.019 / -0.006, 20-24 -0.021 / +0.011, 25-29 -0.022 / +0.010; men 15-19 +0.045 / +0.019, 25-29 -0.025 / +0.009; areas of 5-20,000: women 15-19 +0.025 / +0.004, 20-24 -0.017 / +0.004. Median |error| over ages 15-39, size classes 0-4: 0.0486 / 0.0457, 0.0382 / 0.0358, 0.0290 / 0.0276, 0.0206 / 0.0186, 0.0228 / 0.0179. It is **not** better everywhere: ages 10-19 of the 162 areas over 100,000 worsen by 0.002-0.018. The area totals at 1996 are unchanged (median |error| 0.0294 / 0.0291) and the 2007 Contagem totals of the 5,466 units (period A, in-sample for the schedule) are neutral (0.0250 / 0.0255); the 1996 coverage by age is unknown, so only the contrast between the two timings is read.

**Fix: `population-account-6`** (a version is never overwritten; `-5` stays). `distribute_residual` and the 1991 `settle` give each cohort, each year, the schedule's rate at its age times its size, and spread what the schedule leaves evenly, so the censuses (and every band at 2000, 2010, 2022, and 1991) are unchanged and 2023-2030 is the same forecast. Interior totals differ by up to +0.18% (2004-2005), women 20-44 by +0.04% (2005) and +0.08% (2020), by more in places under 20,000. Account/POPSVS for women 20-44 there (`sizepath2.py`): 1.019 -> 0.996 in 2016, 1.012 -> 0.996 in 2019, 1.006 -> 0.995 in 2020 (the 2022 value, 0.990, is the census anchor), and the yearly change of the log ratio falls from +0.004 ... -0.007 to between -0.003 and +0.0004. **Not recalibrated:** the interval of an interior year (the Brownian-bridge spread around the band's even-timing path) and the intervals' coverage inside the periods, which no census measures.

**Births-exposure test, `-6` against `-3` and POPSVS** (pegasus_project `measure_exposure.py eval births popsvs account-6`, `data/exposure/births_a6.json`, same fits' spans and graph; the full entry is in that repository's `docs/evaluation/2026-10-05-exposure.md`). NLL, block phi: B1 POPSVS 343,524, `-3` 344,937, **`-6` 344,263**; B2 334,658 / 334,773 / **334,277**; held-out BP 99,405 / 99,862 / **99,589** (KS .059 / .096 / .081). The loss to POPSVS at B1 halves (+1,413 to +739) and at BP shrinks from +457 to +184; B2 is now won (-381). It does not beat POPSVS on B1 or BP: 2020-23 still carry +621 of the +739 (places of 50-250 births a year), because the 2022 census still lowers those places' women 15-49 to 0.98 of POPSVS (the census anchor, above); that gap is a disagreement of levels the data here cannot arbitrate.

**Infant fields.** SIM chapter XVI (perinatal conditions, almost all deaths at age 0) against the exposure, same repository's exposure entry: `-6`'s age 0 beats POPSVS's on every tier (B1 NLL 113,432 against 113,645, held-out BP 31,579 against 31,596) and a hybrid of POPSVS with only the account's age 0 matches it, so the gain is age 0 (POPSVS's is about 10% high in the median municipality against births less infant deaths, which the account uses). The age 0 of `-3` to `-5` is the same within the schedule's effect on a newborn cohort.
