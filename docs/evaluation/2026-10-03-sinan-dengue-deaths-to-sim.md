# SINAN dengue deaths → SIM (national 2022)

**Date:** 2026-10-03.

**Regime:** spec `sinan_dengue_deaths_to_sim`, probabilistic method, home
`pegasus_linkage`. SINAN is read from its Dados Abertos CSV.

**Left side.** 1,056 notifications with `EVOLUCAO` 2 (death by dengue). They
carry no birth date (post-LGPD), so the comparisons are the death day, sex,
age in whole years, residence and the notifying unit.

**Result.**
- **503 pairs (47.6%):** threshold 29.5 bits, FDR 0.6% (upper 95% 1.74%).
- **Held-out checks:** age agrees within a year in 100%; the certificate's
  cause is dengue (A90–A97) in 82%.

**Fixes made on the way:**
- **The placebo's date shift is now per spec** (`control_shift_days`,
  default 400).
  - At 400 days, every left death date moved out of 2022, so the placebo
    found no candidates.
  - That falsely reported 941 pairs with FDR 0.
  - This link uses 14 days.
- **Integer comparison floors fractional ages.**
- **`geography="BR"` on a nationally published dataset** reads its one
  publication instead of refusing.
- **Dates may be given as `YYYY-MM-DD`** in roles.
