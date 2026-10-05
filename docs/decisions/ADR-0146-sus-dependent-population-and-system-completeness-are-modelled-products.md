## ADR-0146: the population without private coverage and the completeness of SIM and SINASC are modelled products, anchored on published figures

**Date:** 2026-10-05. **Status:** active. **Request:** PegaSUS ARCHITECTURE §3.1 and §4 (exposure = population variant × completeness), ADR-0139 (modelled tier).

**Context.** SIH and SIA record SUS care, so their exposure is the residents a private plan does not insure; SIM and SINASC are incomplete and the share differs by place and year. Neither is observed. ANS publishes beneficiaries by municipality × sex × age band; the Ministry and IBGE publish registered/estimated events by UF to 2011.

**Decision.**
1. **`population_without_private_coverage`** (`sus_dependent.py`, `sus-dependent-1`): the population account (ADR-0145) minus ANS medical-hospital links (December), per municipality × sex × five-year band, with `private_coverage` and `population_without_private_coverage`, each with an interval. It is **not** the SUS-using population: plan holders use the SUS for part of their care, and links are not persons (someone with two plans counts twice), so the product is a lower bound on the uninsured. The interval is the account's own (independent per cell, so too narrow for sums); the registry's error is not in it, and cells where links exceed the population's upper bound are flagged. **Years: 2021 and 2022 only**: the ANS data held begin in December 2021 and the account has no row after 2022 (ADR-0145 does not extrapolate). The older ANS series (TabNet) was not retrieved.
2. **`system_completeness`** (`completeness.py`, `system-completeness-1`): SIM and SINASC completeness by UF and year, 2000–2023. 2000–2011 is the published ratio (IDB 2012 A.17/A.18, `resources/published_coverage_idb2012.csv`), flagged where the Ministry *assumed* 100% before 2010. From 2012: SIM follows a logit drift, SINASC persists, from the 2011 anchor. The 80% interval adds the published ratio's own spread (0.02 SIM, 0.03 SINASC) to a random-walk term whose scale was calibrated by rolling origin on the published years. For SINASC the upper bound is raised to the population account's census-based estimate where that is higher. Series break: the 2009→2010 step is IBGE's new projection base and is excluded from every estimate.
3. **Not decided here:** municipal completeness. The Ministry's municipal correction factors were not found, and a UF-level association (ill-defined-cause share against coverage, r = −0.52 over 27 UFs in 2010–2011) does not license municipal values; the share is shipped as a column.

**Evidence.** docs/evaluation/2026-10-05-completeness-and-sus-dependent.md.

**Not decided / known weaknesses.**
- Beyond three years from 2011 the intervals are an extrapolation (calibrated to horizon 3); the independent checks are weak: growth balance cannot discriminate 0.95 from 1.0 after 2010, and the census-based SINASC estimate sits 5–8 points above the published ratio, which rests on IBGE projections.
- The published ratio's denominator is itself modelled (2008 Busca Ativa factors); IDB 2012 and the Ministry's 2011 consolidation differ by 1.9 points for SIM nationally.
- Beneficiaries for 2023 to 2025 need a population row after 2022.
