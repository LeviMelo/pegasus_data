## ADR-0227: a census year's population is IBGE's corrected one, for 2022 as for 2000 and 2010

**Date:** 2026-11-21. **Status:** active. **Amends** ADR-0145 item 3 (the 2022 census raked to the PES margins).
**Request:** the author, 2026-11-21: the census is the truth to model on, and of the raw count and IBGE's corrected
population, IBGE's corrected.

**Context.** The account took IBGE's reconciliation (the *Projeções, Revisão 2024*, as POPSVS carries it by state, sex
and age) for 2000 and 2010, and for 2022 its own rake of the census onto the three PES margins. The two treatments of
2022 differed by 0.5% nationally, by -2% to +3% over municipality size and by up to 5% for a state, and that was most
of the account's distance from POPSVS at 2022 (evaluation 2026-11-21-account-against-popsvs). What a census missed is a
separate line of work; the account's subject is the years between and after.

**Decision.**
1. Every census enters at IBGE's coverage: the count times POPSVS / count by state, sex and five-year group
   (`reconciled_coverage`), so a census year is IBGE's population of each state, sex and age, spread over the state's
   municipalities as the census counted them. `pes_coverage` is removed; `sources/pes.py` stays for the parked line.
2. `population-account-8` (and `population-account-bands-8`) is built so; `-7` stays stored. A method is scored against
   this truth (`model-benchmark`).

**Evidence** (evaluation 2026-11-21-account-on-ibge-census). `-8` totals 210.863 M in 2022 (POPSVS 210,862,983) with
1991, 2000 and 2010 unchanged; against POPSVS its cells differ by 0.0167 RMS at 2022 (0.0357 before) and the median
municipality by 0.7% (2.1%). Benchmark under this truth: 0.0511 and 0.0590, births and deaths alone 0.0730 and
0.0671; 80% coverage 0.796 and 0.828.

**Not decided.** Constraining the years between and after to IBGE's state totals by sex and age; the within-state
allocation, where the account keeps the census's and POPSVS smooths cohort growth.
