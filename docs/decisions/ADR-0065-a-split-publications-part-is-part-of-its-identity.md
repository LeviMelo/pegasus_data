## ADR-0065: A split publication's part is part of its identity; descriptive names may carry a year

**Date:** 2026-09-28. **Status:** active. **Amends:** ADR-0017 (identity from
the filename), ADR-0013 (the date convention per directory).

**Context.** The 2026-09-28 full crawl (208,095 files) and inventory found
three filename forms the grammar did not read:
- SIA splits a large state-month into lettered parts: `PASP2301a.dbc`, `…b`,
  `…c` (727 files, 71 GB: SP, RJ and MG since 2015).
- SIA's BI splits it into numbered parts: `BISP2507_1.dbc`, `_2`, `_3`
  (257 files).
- SISCAN publishes national annual files named `SISCAN_CITO_COLO_2013.csv`
  (130 files).

All three fell through to the "descriptive" grammar, which takes the whole
stem as the series and records no UF and no date. The consequences:
- SIASUS had 1,013 "series" and 1,223 strata.
- A one-state-month request spent 5 minutes censusing them (the `sia_pa`
  live scenario, 339 s).
- A request for SIA in São Paulo, or for SISCAN by year, could not select
  these files at all.

A file's `logical_id` groups representations of *one* publication, and one
representation per publication is kept (ADR-0047). Parts that shared an
identity would therefore have been "deduplicated" down to one.

**Decision.**
- The classic grammar accepts an optional trailing part: a letter, or `_`
  plus one or two digits. `ParsedName.part` records it, and it is appended to
  the `logical_id` (`SIASUS|PA|SP|2301|A`). A part is a different
  publication, never another representation of the same one. Identities of
  unsplit files are unchanged.
- A descriptive name ending in `_19xx`/`_20xx` has that year as an explicit
  `YYYY` date (grammar `descriptive_year`), never read as `YYMM`. Its series
  is the prefix (`SISCAN_CITO_COLO`), which is what `curation/ontology.yml`
  already declares as the observed name.

**Measured after:** the inventory of the full crawl went from 3,156 strata to
2,569, and SIASUS from 1,013 series and 1,223 strata to 16 and 226.

**What would reverse it.** A directory where a trailing letter or `_N` is
not a part: for example, a different dataset distinguished only by that
suffix. Such a file would group with its neighbours under one series, and the
census would show a schema its family does not share.
