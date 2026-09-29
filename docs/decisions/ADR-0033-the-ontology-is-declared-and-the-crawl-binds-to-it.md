## ADR-0033: Systems and datasets are declared in `curation/ontology.yml`; the crawl is evidence bound to the declaration

**Date:** 2026-08-21. **Status:** active.

**Context.** Strata and families derive from what the crawl saw, which is the
right basis for inventory and the wrong one for identity
(`docs/history/pegasus_data_ARCHITECTURE.md` §5.4). Three measured cases where
the tree and the truth come apart: one file holding seven datasets
(`acac0201.exe`); one dataset in two locations (`SIA.AB` in `SIASUS` and
`Dados_Abertos/APAC_AB`); one dataset under two names (SINAN `DENG`). Of 1,505
observed `(system, series)` pairs only 181 are clean codes; the rest are whole
filenames (976), leaked archive members (213), per-year names (130) and
templates (5). `retrieve._families()` resolved by `WHERE series = ?` and
under-collected: SIA-PA 9 of 736 families, SIA-AC 0 of 7, so `fetch("SIA-AC")`
returned nothing while reporting success. Added in `31c0eaf` (2026-08-21).

**Decision.**
- **Declaration** (`SystemNode`, `DatasetNode`) is authored in
  `curation/ontology.yml`: identity, names, what the thing is, status. A node
  may have zero files; a dataset known to exist and not found published is a
  research lead.
- **Binding** (`Ontology.bind(system, series)`) maps an observed pair onto a
  declared node and records which rule fired. Declaration is consulted before
  the pattern rules.
- An ambiguous bare code, claimed by two systems, binds to **neither**.
  Duplicate aliases raise at ontology construction (DEFECTS, next-architecture
  closure).
- `SYSTEM_ALIASES` is derived from the declaration's `crawled_as`.
- `verify` asserts exhaustiveness (check 17: every data file reaches a
  declared dataset) and that every dataset says what one row is (check 18).

State at the time: 1,505 of 1,505 pairs bind, zero unbound, across 20 systems
and 131 datasets.

**Alternatives.** Identity derived from the FTP layout. Rejected: the layout
is evidence and changes; the institution's organisation of its systems does
not.

**What would reverse it.** Nothing foreseen. Exhaustiveness is true of one
crawl and is re-checked each crawl (ARCH §22.5).
