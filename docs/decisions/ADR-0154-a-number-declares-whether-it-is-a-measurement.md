# ADR-0154: a number declares whether it is a measurement

**Date:** 2026-10-07. **Status:** accepted.

**Context.** A column of kind `number` is either a quantity, whose sums and logs mean something (length of stay, value,
birth weight, prenatal visits), or a code written in digits (an age packed with its unit, a clock time, a year, an
epidemiological week). Consumers (PegaSUS's mark fields) must tell them apart without naming columns.

**Decision.** `ColumnRole.measure` for every `number`:
- false when its property is in `NOT_MEASURES` (age_coded, year, birth_year, epi_week, onset_week, time);
- false when the column declares `measure: false` (SIH-RD and CIHA `IDADE`, whose property is age but whose value
  packs its unit);
- true otherwise.

**Consequence.** SIH-RD has 39 measurements, SIM-DO 8, SINASC-DN 14, SINAN-DENG 7 and CIHA 4. A newly curated number
is a measurement unless its property or its own declaration says otherwise.

**Addendum (same day): missing codes and domain.** A measurement also declares `missing` (the codes meaning "not
recorded"; `[]` when its layout names none) and, where documented, `domain: [lo, hi]`. A measurement whose `missing`
is undeclared is not to be modelled: its sentinels are unknown. Declared so far from the layouts: SIH-RD's 38
quantities `missing: []` (IT_SIHSUS_1603, numeric, no such code; `TOT_PT_SP` is "Zerado", so not a measurement);
SINASC-DN's Apgar `domain: [0, 10]` (Estrutura_SINASC_2019).
