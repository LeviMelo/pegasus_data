## ADR-0029: The crawled map of the tree ships in the wheel; what ships is what cannot be derived

**Date:** 2026-08-19. **Status:** superseded (2026-09-28, by ADR-0067).

**Context.** DATASUS publishes no index, manifest or API that enumerates the
tree (`docs/history/pegasus_data_ARCHITECTURE.md` §14.1). The crawl knows
every file's system, series, year, state, size and schema, and that knowledge
compresses to about 1 MB. Added in `b695b19` (2026-08-19: "Capabilities as
services: explore(), translate(), and a 1 MB map that ships").

**Decision.**
- `resources/tree.parquet` ships, so `explore()` answers on a fresh install,
  offline (1.29 MB in the ARCH §14a table).
- A local crawl is current and always wins. Every answer names its source and
  the date of the crawl behind it, because a two-year-old snapshot presented as
  the server's state is worse than no answer.
- The shipping rule (ARCH §14a): **ship what makes the module functional out
  of the box, and nothing that is derived, large and reproducible.** The test
  is whether the artifact can be derived from something the user can obtain.
  The map cannot (it costs a multi-hour crawl), so it ships. The dictionary
  database can (ADR-0028), so it does not. Neither do `lake/`, `blobs/` or the
  catalog.
- Every capability the module has internally is reachable as a service, or it
  does not really exist (ARCH §14).

**Alternatives.** Requiring a crawl before the first question. Rejected.

**What would reverse it.** A published DATASUS index. The resource packaging
was later formalised in tiers (ADR-0046).
