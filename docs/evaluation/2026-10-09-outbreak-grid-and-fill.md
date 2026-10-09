# SINAN-SDTA's ill counted by sex and band; SIM-DO's spans against their fill

**Date and regime.** 2026-10-09; pegasus-core-fixes; the repository's own data home; national reads through the lake.
Scripts: `data/probes/p3_outbreaks/grid_totals.py` and `scripts/audit_role_years.py`, plus one `field_fill` call (SIM-DO,
2012–2023).

## The outbreak grid (ADR-0156)

**What was counted, and why.** SDTA's people live in the 21 grid columns (sex × band) and two totals, so a declaration
that reads a column with the wrong sex or band would count the wrong people without failing. The test is the form's
own arithmetic: each band's male, female and ignorado cells must sum to the band's total column, and each sex's bands
to its total.
- **Grid consistency.** The equations hold in every row that fills the grid. The rows that fill it: 2010, 458 of 498;
  2015, 617 of 673; 2019, 571 of 771; 2023, all 1,162.
- **Partial rows.** 0–3 rows a year (2007–2024) leave a single cell blank. The margin NU_F_TOT solves each, and a
  2017 row's blank solves to 42 males aged 10–19.
- **The grid against NU_TOT.** The grid sums to the ill who were interviewed (field 28), not to NU_TOT:
  - 2010: grid 7,694 against NU_TOT 8,628;
  - 2023: grid 18,313 against 19,671, and above NU_TOT in 10 rows.

**Through PegaSUS** (`gateway.event_counts('SINAN-SDTA', 'case', y)`):

| year | allocated | sex unknown | age unknown | outbreaks never counted |
|---|---|---|---|---|
| 2010 | 6,866 | 1,797 | 72 | 39 |
| 2019 | 8,440 | 1,182 | 23 | 199 |
| 2023 | 16,819 | 2,404 | 608 | 0 |

- **2019's band split:** 136 under 1, 940 aged 1–4, 548 aged 5–9, 1,383 aged 10–19, 4,459 aged 20–49, 974 aged 50+.
- **Assembly.** The 2015–2023 block assembles on the bands the population and the grid share: 6 bands × 2 sexes,
  80,909 cases.
- **Account population.** Under the account population, which has no band edge at 1, the bands are 0, 5, 10, 20 and 50.

## SIM-DO's declared years against fill (OQ-71)

`field_fill` over every year 2012–2023:
- FONTESINF and NUDIASINF fill records in 2014 only: 1,227,039 and 32,223.
- NUDIASOBIN fills 2012–2015 and nothing after.
- DTCONCASO fills 2012–2013 and 2017–2023 and is empty in 2014–2016.

Their spans are corrected to 2014, 2014, 2012–2015 and 2017–2026, each with its fill noted. A span cannot hold
DTCONCASO's gap, so it keeps the years filled without one.
