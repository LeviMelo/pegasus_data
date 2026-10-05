## ADR-0145: the population account is a modelled product whose intervals were measured on a hold-out

**Date:** 2026-10-05. **Status:** active; partly superseded by ADR-0148 (product, method, intervals). **Request:** PegaSUS P8 (population by municipality × sex × age with intervals), ADR-0139 (modelled tier).

**Context.** The Census is a count with its own error: the 2022 Census was 8.3% short by IBGE's post-enumeration survey, 2010 and 2000 about 2 to 3% by IBGE's reconciliation. POPSVS is that reconciliation, not an observation, and rests on the same births and deaths a vital account uses (docs/evaluation/2026-10-05-census-coverage.md in PegaSUS). Municipal population by single age between censuses is observed nowhere.

**Decision.**
1. **Product.** `population_account` (municipality × sex × five-year band × year, with `population_lo` and `population_hi`) and `registration_completeness` (SINASC births completeness by state and half-period), written through `modelled.write_modelled` as `population-account-1`. Rows are municipalities 2010–2022 (a `+`-joined group where a post-2010 creation shares an area with its parents) and IPEA comparable areas 2000–2010. Code: `population_account.py`.
2. **Method.** A Lexis cohort-component account from SIM and SINASC; net migration as a smooth age profile (B-splines) per sex with national, state, micro-region and municipal effects, sampled by Gibbs; births shortfall estimated per place; the census's own error as noise of estimated size. Death registration is not estimated: a 10% shortfall to 2010 is assumed, because it cannot be told from old-age migration.
3. **Coverage.** Censuses enter the product corrected: 2022 by the PES margins raked onto cells (`sources/pes.py`), 2000 and 2010 by IBGE's reconciliation (a sensitivity, made with the PES). Coverage is not a fitted latent term.
4. **Validation.** Trained on 2000→2010, forecast 2010→2022 without 2022 information, scored against the **PES-corrected** census, never POPSVS. Median absolute municipal error 0.057 against 0.079 for the vital projection alone.
5. **Intervals.** The parameter draws cover 60% at the nominal 80%. A shared multiplicative place factor (`SHARED_SD`: national 0.02, state 0.046, municipal 0.020–0.058 by size) brings the 10–90% coverage to 0.794 in-sample and 0.806 leaving each of the five regions out in turn. The 95% interval covers 0.91.
6. **Between censuses** the draws are closed onto both censuses and their spread multiplied by sin(πk). **No extrapolation:** there is no row after 2022. The calibration is for a twelve-year forecast without the closing census; a one-year extension was not validated.

**Evidence.** docs/evaluation/2026-10-05-population-account.md (hold-out, sensitivities, coverage by region and band).

**Not decided.**
- Coverage as a latent term per census × age × sex, sampled with the PES as prior.
- The North and Center-West are under-covered (0.66) and the largest cities are not improved by the account (500k+: 0.041 against 0.037).
- The width of intervals inside an anchored intercensal period is not validated.
- The 10% death shortfall is an assumption.
