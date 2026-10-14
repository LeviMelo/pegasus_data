## ADR-0183: The price index is a SIDRA series; deflation is the ratio of two index numbers

**Date:** 2026-10-14. **Status:** active.

**Context.** SIH's `VAL_TOT` and SIA's values are nominal reais of the month billed. SIH-RD Alagoas (AIH type 1) 2014 to 2023: R$ 153.7 to 222.8
million nominal (+45 %), R$ 287.8 to 247.5 million in December 2025 reais (-14 %): the sign of the change differs. The curation said "never
deflated", and nothing in the package could.

**Decision.**
- IBGE's IPCA (SIDRA table 1737, variable 2266, index number, December 1993 = 100, national) is the series `price_index_ipca` in
  `curation/sidra/series.yml`: the existing mechanism (planner, store with provenance, series) and no second one.
- `price_index(root, grain, years, reference)` (`sidra/prices.py`, CLI `price-index`) returns the monthly index or the annual mean (null for a year
  with fewer than twelve months), and with `reference` the `factor` = index(reference) / index: a nominal amount of that month times the factor is
  in reais of the reference month. A month missing between the first and the last raises. The table's metadata carries the series, the base and the
  fetch (time, SHA-256).
- The index is IPCA because it is the Brazilian consumer price index on SIDRA with a monthly index number; no health price index is declared, and a
  caller who needs medical-care prices can declare that series the same way.

**Evidence.** 393 months of 1994-2026 equal IBGE's own historical workbook value for value (all 144 of 2014-2025); SIDRA's query service and table
page agree on the months read (DATA_SOURCES §6.4).

**What would reverse it.** IBGE revising published index numbers (the call stores the body's SHA-256, so a change is visible).
