## ADR-0037: A windowed label pack ships in `resources/`, and codelist roles are declared, not inferred

**Date:** 2026-08-22. **Status:** active.

**Context.** `fetch("SIM-DO", uf="AC", years=2022)` on a clean machine
returned 4,159 rows and labelled nothing. The labels lived only in a 14 GB
catalog produced by an hour-long `semantics` run that no user has reason to
perform (`docs/history/pegasus_data_ARCHITECTURE.md` §14.9). Sorting codelists
by size to decide what to ship is wrong: a 50,000-row cap keeps 450 municipal
roll-ups and drops CID10. Structure cannot separate them either, since CID10
and an establishment directory both have one label per code. The first pack
cost 1,309 MB of RAM (DEFECTS R-1) and carried no validity windows. Shipped in
`8f56655` (2026-08-22); roles and prose retired in `41a613f`; windows restored
in `70f4abf` and on the recovered full catalog at the second review closure
(`1578b40`, 2026-08-23).

**Decision.**
- The semantic layer ships distilled as `resources/labels.parquet`: runs, not
  enumerations; one cross-system copy only where every system carrying the
  codelist agrees; packed facts split. The current artifact holds 3,654,320
  versioned runs across 2,238 codelists (29.97 MB in ARCH §14a).
- `system = NULL` means every system carrying the codelist reads the code this
  way. SIH codes sex 1/3 and SINASC 1/2, so "the systems that have this code
  agree" is a different and unsafe claim.
- Roles are declared in `curation/codelists.yml`: `enumeration`,
  `classification` (kept whole), `geography`, `registry` (held back: CADGERBR is
  687,789 establishments, a dimension published as `CNES.ST`), `crosswalk`.
- Bindings ship (`resources/bindings.parquet`). A local lake outranks the pack.

**Alternatives.** Shipping the catalog (14 GB), or selecting by size. Both
rejected above.

**What would reverse it.** Independently versioned resource bundles, which
ADR-0046 anticipates; the pack would then update without a code release.
