## ADR-0233: the candidate estimator's error is the model's, with its denominator; what it estimates is the found

**Date:** 2026-11-21. **Status:** active. **Amends** ADR-0229 (its standard errors; settles its "not decided" movers
and twins). **Request:** paper 6 of the race-at-death series (`papers/race_at_death/estimator/`).

**Context.** ADR-0229's errors took each cell of candidates less control as Poisson (candidates plus control) and divided
by the row's sum as if it were known. A proportion's error then ignored its denominator; movers and same-sex twins were
left open.

**Decision.**
1. `modelled_race.candidate_estimates` gives every quantity of the estimator (rows P(k | j), declared mix, share found,
   rate ratios) with four errors from per-municipality pieces: **model** (cells Poisson with variance candidates plus
   control, delta method with the row's sum; the ratio's Poisson error already had its reference row), **chance**
   (only chance agreements vary: twice the control, same delta method), **cluster** (linearised over municipalities),
   and the earlier **counts** error for comparison.
2. The model error is the one reported for tables and ratios of the whole country. The chance error is the yardstick
   against a linkage of the same units. The cluster error treats municipalities as a sample of places; it is several
   times the model error where large cities classify differently, and is not used for national totals.
3. What the estimator estimates is the table of the people who kept the key (birth date, sex, municipality). Movers and
   records whose key differs are its selection, not its error, and are reported as such. Twins only raise the share
   found. Unequal shares found by declared class bias the mix and the rate ratios by their ratio, not the rows.
4. The SQL of the candidates is one function (`_candidates`), used by `candidate_counts` (births register) and by
   `pair_candidate_counts` (any two sides of a stored link recording one event). The control is scaled within birth
   year as well as place, since a register of deaths changes its sex ratio with age.

**Evidence** (evaluation 2026-11-21-candidate-estimator). Infant deaths against the one-to-one link: mean absolute
difference 0.005-0.020 over the 20 cells below 25,600 births a year. Admissions ending in death 2016-2022 against their
certificates linked by day and hospital: 0.001 against the pairs sharing the key, 0.006 against all linked (the 10% of linked
whose certificate does not share it classify differently: certified White, White in hospital 0.50 against 0.63).
Simulation (7 scenarios, 200 replicates, the real 2018 births). With the assumptions holding and the real number of
deaths, the bias is within 0.004 below 6,400 births a year and 0.009 at 6,400-25,599. With a twelfth of the deaths
(`sparse`), the ratio-of-sums bias of small rows reaches 0.020 and 0.134 (the Black row). Coverage: model 92-100%,
counts 86-100% (too wide for common cells, too narrow for rare). Movers bias against all deaths +0.013 (against the
found -0.0003). Moving 22% of White against 30% of Brown children takes the national White to Brown ratio from 0.66
to 0.72. Moving that depends on the class recorded biases the rows by up to 0.038 (coverage of all deaths down to 0%).
Unequal sex ratios (A2 broken) give up to 0.011. `candidate_counts` gives identical cells before and after the refactor.

**Not decided.** A control scaled within age for registers of deaths with many chance candidates.
