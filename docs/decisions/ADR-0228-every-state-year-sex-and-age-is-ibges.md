## ADR-0228: every state's people of a year, sex and age are IBGE's; the account decides the spread below

**Date:** 2026-11-21. **Status:** active. **Extends** ADR-0227. **Request:** the author, 2026-11-21: the most defensible
figures, using the data POPSVS uses; IBGE's corrected population is the truth to model on.

**Context.** With ADR-0227 the account met IBGE at the three census years and nowhere else: between censuses its
states followed registered births and deaths (ages 0-4 up to 3% from IBGE's), and after 2022 its own forecast (0.34%
over IBGE's by 2025). IBGE's *Projeções, Revisão 2024* give every state by sex and single age for 2000-2070 (held as
`projpop`); what IBGE does not publish is the municipality and the race. Two estimates of one state-year by different
methods are a disagreement a reader cannot settle; the account has nothing IBGE lacks at that level, and its measured
skill is in the spread of a state's people over its municipalities.

**Decision.**
1. The account's last stage (`population_tensor.constrained_to_ibge`) multiplies every cell of 2000-2030 by its
   state's factor: IBGE's population of that state, year, sex and age (90 and over together) over the account's own.
   The intervals take the factor. 1991-1999 are not constrained (no IBGE series by state and age).
2. The product is `population-account-9`; `-7` and `-8` stay stored. `population_account_bands` is not constrained (its
   rows are comparable areas; consumers of band intervals read it as before).
3. A state's total and anything above it carry no interval of the account: they are IBGE's. Inside a state, a group of
   municipalities takes `population_benchmark.group_log_sd` (errors correlate 0.45-0.50 inside a micro-region).

**Evidence** (evaluation 2026-11-21-account-on-ibge-census). `-9`: the 4,914 state x sex x age cells of 2005, 2015, 2025
and 2030 equal IBGE's to 4e-8; totals 185,518,369, 202,403,642, 213,421,037 and 216,973,093; factors 0.846, 1.001,
1.160 (1%, median, 99% of cells); the five races add to the total (largest difference 0.014 people). Against POPSVS
every national, age-group and state ratio is 1.000 in every year; what is left is the spread inside a state: median
municipality 0.7-1.0%, cells 0.017-0.027 RMS at census years and 0.034-0.038 between.

**Not decided.** The same for the band product; 1991-1999; intervals of age groups and race inside a state.
