# Race bridge: a confusion matrix between SIM and the declaration at birth, and what it does to infant mortality by race

**Regime.** 2026-10-05, branch pegasus-core-fixes, home `pegasus_core_data`. Module `src/pegasus_data/modelled_race.py`, product `race_confusion_infant` v `race-confusion-infant-1` (`lake/modelled/`, 3,024 rows plus `draws.npz`). Scratch scripts and artifacts: `pegasus_project/data/agent_race/` (`val1.py`, `rates2.py`, `ship.py`, `val1_*.json`, `rates2_*.csv`). First measurement (cross-tabs): `pegasus_project/docs/evaluation/2026-10-04-race-bridge-infant.md`.

**Data.** 52,063 linked SIM × SINASC infant deaths (2021: 26,008 of 31,688 deaths; 2022: 26,055 of 32,081). Link rate by recorded race: 81% for all but SIM-Indígena, 65%; by age, 89% under 28 days and 66% after. Pairs are therefore weighted by 1 / P(linked | state, age band, recorded race), which moves the Indígena row (stays Indígena 82.5% → 85.2%).

**What carries the shift (2021 → 2022 held-out log loss, nats per record).**

| covariates (declared race always in) | log loss |
|---|---|
| none | 0.880 |
| region | 0.820 |
| state | 0.806 |
| state + age band | 0.802 |
| municipal birth composition + size + age band | 0.799 |
| state + composition + age band | 0.789 |

Eight more SIM fields (place of death, certifier, mother's education, birth weight, cause chapter, same municipality, necropsy, sex) lowered it by at most 0.01 together and are not used.

**Model fit.** Prior scales chosen on held-out log loss (state 0.4, region 0.3, composition 0.5 or 0.15, age 0.5). NUTS, 2 chains × 400: R-hat 1.003–1.010, no divergences, ESS ≥ 286, 23–50 leapfrog steps. The first attempt (diagonal mass matrix, scales sampled) needed 511 steps and over an hour per fit; the inverse Hessian at the mode as mass matrix cut it to 5 minutes.

**Out of sample, by state** (fit one year, predict the other's state × recorded-race counts, cells with ≥ 5 expected):

| | fit 2021 → 2022 | fit 2022 → 2021 |
|---|---|---|
| log loss: this model / one national matrix / state-wise empirical | 0.796 / 0.888 / 0.823 | 0.822 / 0.907 / 0.848 |
| absolute error, share of counts: model / national / state-wise / identity | 6.1 / 27.4 / 6.1 / 30.4% | 5.8 / 25.4 / 6.2 / 29.3% |
| 90% interval coverage, state × recorded (simulated) | 76% | 76% |

Mean z-score is 0 (unbiased) but the sd of z is 1.52 and 1.60: the simulated intervals miss year-to-year and weight variation. Widening the sd by 1.5 gives 91% coverage, now `PREDICTIVE_DISPERSION`. The posterior bounds on C itself (`p_lo`, `p_hi`) are not widened.

**Consequence: infant mortality per 1,000 births, 2022, bridged by the 2021 fit** (numerator all 32,081 SIM deaths by recorded race; denominator SINASC births by declared race; truth = linked deaths by SINASC race, inverse-linkage weighted).

| Brazil | raw | bridged (90% interval) | truth |
|---|---|---|---|
| Branca | 14.3 | 10.1 (9.5–10.6) | 9.9 |
| Preta | 5.5 | 15.8 (13.8–18.3) | 15.1 |
| Parda | 11.3 | 13.7 (13.0–14.3) | 13.4 |
| Indígena | 26.1 | 27.8 (25.6–30.6) | 25.5 |

The raw rates say Preta infants die least; the truth says most, after Indígena. By region in 2022 (raw / bridged / truth): North Branca 31.9 / 15.3 / 13.7, Preta 6.5 / 14.2 / 13.2; Northeast Branca 20.6 / 9.7 / 10.7, Preta 5.0 / 14.8 / 16.0; South Branca 11.0 / 9.5 / 9.2, Preta 7.8 / 15.1 / 16.2.
Mean absolute error over the five regions, raw → bridged: 2022 (2021 fit): Branca 70 → 6%, Preta 62 → 11%, Parda 22 → 4%, Indígena 9 → 14%. 2021 (2022 fit): Branca 65 → 9%, Preta 64 → 30%, Parda 21 → 7%, Indígena 9 → 20%. The truth is inside the 90% interval in 85% (2022) and 95% (2021) of the 20 region × race cells. Small cells are noisy (North Preta 2021: bridged 32 against truth 17.5, interval 11–69).
**Indígena is not improved** (raw already within 9%), hence ADR-0143's exclusion.

**Not a transport to adults: the ecological test failed.** Regressing municipal recorded deaths on municipal declared births (no linkage, constant C within a region) should recover C if composition alone identified it. On infants, where the answer is known, it did not: it gave Branca → Branca 91–99% in every region against the linked truth of 37–91%. C depends on local composition, so an ecological estimate on adults is not credible.

**Adults: what would identify it.**
- SIM deaths aged 20+ in 2022 are recorded Branca 61.3% (Southeast) and 84.3% (South) against the Census 2022 population of 49.9% and 72.6%. The gap mixes misclassification, the whiter age structure of the deaths, and true mortality differentials; nothing here separates them.
- The Census 2022 has race × sex × age by municipality (SIDRA 9606, level N6; reachable through `pegasus_data.sidra`). It gives the denominator by declared race. A rate by declared race still needs C for the recorded numerator.
- **Source that identifies C for adults: mothers.** SINASC records the mother's race and birth date; SIM records the woman's. Linking SIM female deaths aged 15–49 to SINASC mothers (key: birth date, municipality of residence, age; lookback over births since 2012) gives a reference declaration for adults, selected on having given birth. That spec does not exist and would be a new link; its size is unmeasured, and the weakness is selection (mothers, 15–49), so it supports a transport assumption, not a full identification.
- **Alternative: assumption-based.** Transport the infant matrix to adults and report rates as a sensitivity band over the transport (state-level C, age-band scale). Each step is explicit; nothing is guessed.
- **SIH × SIM** (`sih_deaths_to_sim`) pairs two recorded systems, with no reference: it measures their disagreement, not their error. SIH `RACA_COR` is also unreliable by hospital (DATA_SOURCES), so it is no anchor.

**Defects found.** Race decoded by hand (codes 1–5, blank): `translate` still returns truncated SIM labels. `query(select=[...])` raises on a column absent from the family's generations (`NUMERODN` in SIM.DO), which is correct but needs a retry loop in a scan over generations.

**Runs.** Each validation fit: about 2 minutes of scale selection and 5 of NUTS (332 s for the 2021 fit); the shipped fit used both years with the average of both directions' held-out loss. Dependencies: the `modelled` extra (`jax`, `numpyro`, `scikit-learn`) in `pyproject.toml`; applying a shipped product needs only numpy.
