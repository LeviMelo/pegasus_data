## 2026-08-23 — Temporal truth has extent, identity and authority

*Split from docs/history/FINDINGS.md §3p (first) on 2026-09-28; text unchanged.*

## 3p. Temporal truth has extent, identity and authority (2026-08-23)

The hardening review exposed three variants of the same false-precision bug.
A source vintage is an interval: a monthly publication is one month, an annual
publication spans January through December, and missing provenance is unknown.
Semantic dimensions and CNES↔CNPJ enrichment may resolve a coarse interval only
when one effective assertion and mapping covers all of it; a bare year is never
silently converted to December.

Catalog relations likewise identify temporal assertions, not only semantic
slots. Stable `relation_id` values include validity boundaries and authority, so
adjacent historical adjudications persist together. Overlaps within one
authority/slot fail explicitly. During legacy migration, a row is local only
when its complete content is recoverable from resolved adjudication decision
JSON; otherwise it is classified as curated. Curated rows are synchronized as a
transactional compiler snapshot on every seed, while local decisions persist.
The v4 migration reapplies this classification to catalogs already opened by
the short-lived v3 all-local migration.

Resource compatibility is separate from resource freshness. The schema/ABI,
manifest identity and checksum are strict, while a newer compatible content
epoch is accepted without reinstalling Pegasus. CNES-name coverage is an
explicit source-snapshot build claim; individual record windows cannot prove a
directory complete. Lake-backed resources use the same resolution interface but
delegate physical completeness to the lake catalog and fingerprints.
