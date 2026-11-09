## ADR-0220: the population account's build writes its own band estimate, `population_account_bands`

**Date:** 2026-11-09. **Status:** active. **Amends** ADR-0151 ("Not decided": `fields.py` and `sus_dependent.py` pinned to
`population-account-2`). **Request:** R1 (STATUS: every modelled product is rebuilt from the repository).

**Context.** The single-age account (ADR-0151) carries an interval per cell. Summed into a five-year band, the point
estimate adds and the interval does not: quantiles are not additive and the cells' errors are correlated (they come
from the band's offset, the split and the age share). Two consumers need a band with its interval: the population
without a private plan (`sus_dependent`, a log-normal draw per band cell) and, until today, `field_rate`. They read
`population-account-2`, which no function of the package built after the move to the tensor.

**Decision.**
1. `population_tensor.build_population_account` writes, beside the account, the product `population_account_bands`
   under the same version number (`population-account-bands-N`): the account before its municipal split and single
   ages (`account_arrays`: comparable areas 2000-2010, municipalities or the area of a post-2010 creation 2010-2022,
   the forecast 2023-2030) by sex and five-year band, with the 80% and 95% intervals the account calibrates on bands.
   Its shape is `population-account-2`'s (`place`, `place_kind`; 2010 is in both blocks, told apart by `place_kind`).
2. A consumer of band intervals reads that product at the version its `inputs:` declares; one needing municipal totals
   alone reads the single-age account through the modelled cube (`field_rate`).
3. Stored versions are not rewritten; PegaSUS's pins (`population-account-2`, `sus-dependent-2`) stay readable.

**Evidence** (evaluation 2026-11-09-principles-audit-defects, rows "population account 7" and "population_account_bands").
`population-account-7` equals `-6` in 2000-2030 to 1e-8 (national and per municipality) and in 1991-1999 within 8e-5
(the 1991-1995 deaths now read through the cube). `population-account-bands-7` equals `population-account-2` at the census
years exactly, with the same 80% widths in every year; interior years differ by a median 0.2-0.8% (max 9.8%), the
migration-schedule timing of ADR-0151 item 7. `sus-dependent-3`, built on it: 2022-2023 populations equal
`sus-dependent-2`'s, 2021 within a median 0.25%, coverage medians equal, and 2024-2025 added.

**Not decided.** An interval for any other aggregate of the tensor (a region, an age group): the general answer is to
store what generates the uncertainty (band-level draws and the split, age and race terms), as the race products store
their draws.
