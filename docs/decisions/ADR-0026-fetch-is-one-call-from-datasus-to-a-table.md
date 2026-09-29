## ADR-0026: `fetch()` is one call from DATASUS to a labelled table, with every path taken from the catalog

**Date:** 2026-08-19. **Status:** active.

**Context.** The package was shaped around a catalog: crawl, learn, build,
query. That suits a data lake and not the question most people arrive with,
"give me SIH admissions for Alagoas in 2023". R's microdatasus answers that in
one line, which is why most Brazilian health researchers reach DATASUS through
it (`docs/history/pegasus_data_ARCHITECTURE.md` §11). Added in `586cade`
(2026-08-19).

**Decision.** `fetch("SIH-RD", uf="AL", years=2023)` downloads what it needs,
decodes, normalises, labels and returns a table; no lake is built. It differs
from microdatasus deliberately (ARCH §11):

- **It does not guess filenames.** Every path comes from the catalog. A system
  the catalog has never seen triggers a bounded crawl of that system's
  directory only, recorded so the second call is free. The header census
  (ADR-0024) makes discovery affordable.
- **It resolves the dataset through the ontology**, not by string match
  (since 2026-08-21, ADR-0033). The string match had found 9 of SIA-PA's 736 families and none
  of SIA-AC's 7, and `fetch("SIA-AC")` returned nothing while reporting
  success.
- **It labels through the same render path as `load()`** (ADR-0014).
- **It says what it could not do.** Every file that failed to decode, every
  schema that did not fit its family, and every requested year DATASUS never
  published is named in the `FetchReport`.

**Alternatives.** Template-built FTP paths, as microdatasus does. Rejected:
they break when DATASUS moves something.

**What would reverse it.** It was not reversed; it was layered.
`query()`/`plan()` became the front door for analysis-ready slices, and
`fetch()` remains the source-shaped mechanic beneath it (ADR-0043).
