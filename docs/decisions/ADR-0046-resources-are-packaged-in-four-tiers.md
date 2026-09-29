## ADR-0046: Resources are packaged in four tiers, each runtime artifact with manifest identity and a lifecycle

**Date:** 2026-08-23. **Status:** active.

**Context.** Every derived artifact had been treated as either something that
must ship in the wheel or something every user must rebuild
(`docs/history/PEGASUS_NEXT_ARCHITECTURE_BRIEF.md` §3). The recovered
maintainer catalog was 14,995,771,392 bytes; `scripts/storage_report.py`
measured it with SQLite `dbstat` and found no freelist: `code_tables` 6.10 GB,
`dictionary` 3.98 GB, and indexes another 4.13 GB. The claim that "SQLite costs
15 GB" was rejected; the warehouse stores expanded evidence and repeated
indexes (`docs/history/FINDINGS.md` §3m; ARCH §21). Built in `efbc7c1`;
compatibility rules in `64cb3b5` (2026-08-23).

**Decision.**
- **Tier A** ships: code, ontology and curated decisions, and small bootstrap
  resources. **Tier B** is the compiled runtime semantic layer (label pack,
  crosswalk pack, bindings, query capabilities), compact enough to distribute.
  **Tier C** is maintainer build state (full catalog, source documents,
  profiles, adjudication evidence), never shipped. **Tier D** is user-local
  state (blobs, lake, optional registries such as CNES names and history).
- `resources/manifest.json` records, per runtime artifact, schema version,
  content version, build identity, checksum, size, tier and a growth budget.
  Shipped runtime artifacts totalled 41,705,449 bytes under a 47,185,920-byte
  budget (ARCH §21).
- `resource_manager().status()/.ensure()/.build()` and `pegasus-data
  resources` expose the lifecycle; every runtime open passes through it.
- Schema ABI, manifest identity and checksum are strict; a newer compatible
  content version is accepted without reinstalling (FINDINGS §3p, first).
- A plan names a missing requirement and its estimated cost before touching
  the fact dataset, and never starts an unbounded build implicitly.

**Alternatives.** Ship-it-or-rebuild-it. Rejected by the brief.

**What would reverse it.** Nothing foreseen. Independently updatable resource
bundles (`resources update`) are anticipated, not built.
