# 2026-11-21: the population account on IBGE's corrected 2022 census (`population-account-8`)

**Regime.** Branch `research-2` (f2c30b4), the core home; `pegasus-data model-build population_account --version
population-account-8` (about 50 minutes beside two other jobs); `data/probes/popsvs/decompose.py population-account-8`
(artifact `decompose_population-account-8.json`); `pegasus-data model-benchmark --json` (artifact
`data/probes/population_research/benchmark_ibge.json`). Decision: ADR-0227.

**What was counted.** The same two things as for `-7`: the distance from POPSVS cell by cell, and the benchmark (each
census forecast from the one before under the other period's fit), now against IBGE's corrected 2022.

| | `-7` (2022 on the PES margins) | `-8` (2022 on IBGE's reconciliation) |
|---|---|---|
| national total 2022, 2025, 2030 (M) | 211.962, 215.225, 219.205 | 210.863, 214.142, 218.227 |
| account / POPSVS, national, 2022 and 2025 | 1.0052, 1.0085 | 1.0000, 1.0034 |
| cells against POPSVS at 2022, RMS | 0.0357 | 0.0167 |
| median municipality against POPSVS, 2022 | 2.1% | 0.7% |
| by size class at 2022 (smallest ... largest) | 0.978 ... 1.033 | 1.007 ... 0.984 |
| cells mid-period (2015), RMS | 0.0405 | 0.0391 |

- 1991, 2000 and 2010 are unchanged (151.116, 174.696, 194.749 M); 219,402,300 rows as before.
- At 2022 what is left against POPSVS is what is left in 2000 and 2010: the spread of a state's people over its
  municipalities (0.0167; one factor per municipality leaves 0.0089). The level, the age-sex and the state terms are
  zero; the size gradient is the 2000 and 2010 one (the largest class 1.6% under POPSVS).
- Between censuses the difference is the timing, as before (0.036-0.041 mid-period).

**Benchmark** (median absolute log error of the municipal total; 80% and 95% coverage):

| | 2000 to 2010 | 2010 to 2022 |
|---|---|---|
| the account | 0.0511 (0.796, 0.938) | 0.0590 (0.828, 0.968) |
| births and deaths alone | 0.0730 | 0.0671 |
| by size, under 5,000 to over 500,000 | 0.059 0.055 0.044 0.033 0.022 | 0.061 0.062 0.058 0.046 0.052 |

Against IBGE's 2022 the previous decade's migration helps less than it did against the PES-raked census (0.0590 for
0.0671; it was 0.0562 for 0.0782): births and deaths alone land nearer IBGE's 2022 than the PES's, and the regression's
gain in municipalities over 500,000 is gone (0.052 against 0.040). The intervals still cover at nominal.

**The signals again, against IBGE's 2022** (`symptomatic_events.py`, `symptomatic_electorate.py` on the new inputs; logs
`*_ibge.log`; the first runs' inputs kept as `inputs_pes.pkl`). 2010 to 2022, coefficients from 2000 to 2010:

| | 2000 to 2010 | 2010 to 2022 |
|---|---|---|
| the account | 0.0511 | 0.0590 |
| + births per accounted woman | 0.0513 | 0.0533 |
| + the electoral roll, all voters | 0.0558 | 0.0521 |
| births and deaths' own symptoms, no lagged migration | 0.0646 | 0.0540 |
| the roll at ages 18-69, 2010 to 2022 / to 2020 (leave one region out) | | 0.0521 / 0.0523 |

The picture of the first runs holds under the new truth: each signal cuts 2010 to 2022 by about a tenth (0.059 to
0.052-0.053) and does not help 2000 to 2010. Against IBGE's 2022 the events' own symptoms do better than the previous
decade's migration (0.0540 against 0.0590).
