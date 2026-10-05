# Completeness of SIM and SINASC by UF, and the population without private coverage

**Scenario.** `data/probes/completeness/`: `build_comp.py`, `ro.py`, `val.py`, `val2.py`, `ggb1.py` (completeness); `build_sus.py`, `chk_sus.py` (private coverage); logs beside them. Regime: 2026-10-05, branch pegasus-core-fixes, core data home, `population-account-1`, ANS December 2021 and 2022 (PDA-024). Products: ADR-0146.

## Population without private coverage (`sus-dependent-1`, 378,012 rows, 2021–2022)

- National 2022: population 211.96M, ANS medical-hospital links 50.49M, so 23.8% (2021: 23.3%); 161.5M without. The rate is below ANS's own because the denominator is the PES-corrected population, not IBGE's projection. Dental-only links (28M) are not subtracted.
- By age (2022): 17.5% at 15–19, 29.5% at 35–39, 28% at 80+; women 24.6%, men 23.0%.
- Plausibility: links exceed the population's upper bound in 0.01% of cells (7,558 links); no municipality exceeds 1. Median municipal coverage by size: under 5k 4.5%, 100–500k 23.6%, over 500k 37.2%. Year-to-year change of a municipal rate: SD 0.7–1.0 pp in every size class.
- Unplaced and not subtracted: 38,186 links (2022) with no municipality, 187 with age "Informada Incorreta".
- **Not validated:** how many links are duplicates (no survey by municipality × age exists for 2021–22; PNS 2019 asks medical *or* dental, in another year). The interval holds the account's uncertainty only.

## SIM and SINASC completeness (`system-completeness-1`, 1,296 rows, 27 UFs, 2000–2023)

**Anchor.** IDB 2012 A.17 (births) and A.18 (deaths), UF × year 2000–2011 (tabnet.datasus.gov.br/cgi/idb2012/a17b.htm, a1801b.htm): national SIM 91.0% (2000) to 94.2% (2011), SINASC 92.5% to 95.9%; North and Northeast lowest (Maranhão SIM 55.2% in 2000, 79.1% in 2011). The page states the estimate is the sum of municipal events corrected by the 2008 Busca Ativa factors; the South, Southeast, MS and DF read 100.0 in every year to 2009 (assumed). The Ministry's own 2011 consolidation (SIM-CGIAE, 26 February 2013) gives 96.1% for 2011 against the 94.2% above (a different IBGE projection): a 1.9-point spread, used as `ANCHOR_SD` 0.02.

**Extension model, rolling origin** (origins 2005–2008, horizons 1–3, 19 measured states, drift and spread re-estimated from earlier steps only, inside the first projection base; n = 171, not independent):

| mean abs error at h = 1 / 2 / 3 | chosen model, window inside the first projection base | alternative, first run (horizons may cross the 2009→2010 break) |
|---|---|---|
| SIM | drift 0.7 / 1.2 / 1.2 pp | persistence 0.9 / 1.7 / 2.4 pp |
| SINASC | persistence 0.7 / 1.2 / 1.4 pp | drift 0.8 / 1.2 / 1.4 pp (no better, so the simpler model) |

80% interval coverage at scale 1.0: SIM 0.88, SINASC 0.83 (scales 1.25 and 1.5 gave 0.92 and 0.97 for SIM).

SIM uses the drift, SINASC persistence. By 2023: SIM median 0.954 (Maranhão 0.880 to Rio de Janeiro 0.996), median 80% interval 0.923–0.985. Beyond horizon 3 (after 2014) the interval is an extrapolation.

**Independent checks (weak).**
- Growth balance on our SIM and the raw censuses, 2000–2010: Brazil 0.98 (90% interval 0.88–1.08) against 0.93 modelled; the intervals contain the model in the North, Northeast, Southeast and South; Centre-West 0.81 (0.74–0.85) against 0.93 does not (migration into DF, MT, GO). By UF: correlation with the published mean 0.23, difference SD 0.17, mean +0.03: **useless at UF level**, usable nationally.
- 2010–2022 (deaths from the SIM aggregate): with the raw 2022 census growth balance gives 1.43 for Brazil, impossible; with the PES-corrected 2022 census 1.13 (1.01–1.53): North 1.09, Northeast 1.31, Southeast 1.11, South 1.00, Centre-West 0.87, against 0.89–0.99 modelled. Consistent with high completeness everywhere; cannot tell 0.95 from 1.0.
- SINASC against the population account's census-based estimate (state × half-period): higher than the published ratio by 3.9 points (SD 3.7) over 2000–2011 and by 7.1 (SD 3.0) over 2012–2021; the interval contains it in 78% of state-years before 2012 and 26% after (the upper bound is already raised to it). The published ratio rests on IBGE projections, which the 2022 census did not confirm; which side is right is not decided.
- Ill-defined causes (R00–R99 except R95): 7.0% of deaths in 2010, 4.8% in 2023. Across the 27 UFs it correlates −0.52 with the published SIM coverage in 2010–2011. Shipped as `ill_defined_share`, not as a model term: it could not be tested on the 2000–2009 changes (no cause aggregate before 2010 in hand).

**Not found / not done.** Municipal completeness (the Ministry's municipal factors; SINASC municipal capture–recapture from 2015 per RIPSA DEM.4.01, published at DATASUS, not located); IBGE's sub-registro estimates (civil registration, not SIM/SINASC; www.ibge.gov.br answers 403 to curl with a browser user agent, ftp.ibge.gov.br/Registro_Civil answers); SIM coverage after 2011 by UF (DATASUS links not located); SEG. A collection of SIM causes for 2000–2009 was queued behind other jobs and cancelled.

## Rebuilt on population-account-2 (`system-completeness-2`, `sus-dependent-2`, `registration_completeness/population-account-2`)

`data/probes/completeness/build_reg2.py`, `build_comp2.py`, `build_sus2.py`; 2026-10-05, branch pegasus-core-fixes, core data home. Dependents of v1 found by grep of the code and the manifests: `registration_completeness` (v1's Gibbs births shortfall), `system_completeness` (read it for the SINASC upper bound), `sus_dependent` (manifest input `population-account-1`). The v1 files stay.
- **`registration_completeness`**: v2 has no latent shortfall, so the product is now measured on the cohorts: registered births (survived by registered deaths) in the vital account against the coverage-corrected census, by UF, for the 0-4 and 5-9 cohorts of the 2010 and 2022 censuses (births 2005-09, 2000-04, 2017-21, 2012-16). Median 0.958 / 0.938 / 1.009 / 0.991 (v1, half-periods: 0.982 / 0.962 / 1.030 / 0.999 for 2005-09, 2000-04, 2016-21, 2010-15). Interval sd 0.030 = hypot(0.02 census term, 0.022 spread between the 0-4 and 5-9 cohort of a state). Against the published ratio 2005-09, the 0-4 cohort differs by +0.7 points (SD 2.6), the 5-9 cohort by -1.6 (SD 4.6): the older cohort carries five more years of child migration. A value above 1 is a census undercount, not registration.
- **`system_completeness`**: SIM and the SINASC point estimates and the SIM interval are **identical** (they never used the account); only the SINASC upper bound and the `census_based_estimate` column change: 239 of 648 SINASC rows. The median UF upper bound is 0.955 against 0.967 in 2000, 0.970 against 0.983 in 2008, 1.000 against 0.982 in 2015 and 1.000 against 0.988 in 2021 (v2 against v1). Census-based minus the published/extended completeness: +0.4 points (SD 4.1) for 2000-2011 (v1 +3.9, SD 3.7) and +5.1 (SD 5.2) for 2012-2021 (v1 +7.1, SD 3.0). So the v1 reading that the published ratio sat 4 points below the census before 2011 came from the Gibbs births shortfall; on the cohorts it does not hold for 2000-2011, and the 5-point gap after 2012 remains (the 2022 census counted fewer children than IBGE's projections implied). Which side is right stays undecided. Examples (SINASC upper bound, v1 to v2): Para 2019 1.000 to 0.976, Maranhao 2014 0.962 to 0.991, Bahia 2008 0.985 to 0.959, Sao Paulo and DF unchanged at 1.000. Years 2010-11 and 2022-23 have no cohort and keep the extension's bound.
- **`population_without_private_coverage`**: 2021 and 2022 national totals move by 0.1% in the population (211.08 to 211.22 M in 2021; 2022 identical, the PES-corrected census) and coverage is unchanged to 0.01 points (23.3%, 23.8%); the product gains 2023 (population 213.0 M, ANS links 51.2 M, 24.0%), 567,018 rows (was 378,012). Links exceed the population's upper bound in 0.01% of cells, as before.
- `completeness.py` read the period as `range(start, end)`, dropping the last year of every v1 period; fixed to the inclusive range of birth years.

