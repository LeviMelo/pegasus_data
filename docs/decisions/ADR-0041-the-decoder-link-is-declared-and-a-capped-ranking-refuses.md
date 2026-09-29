## ADR-0041: The variable-to-decoder link is declared in curation; an uncurated candidate set above the cap is refused

**Date:** 2026-08-23. **Status:** superseded (2026-09-28, by ADR-0072). **Amends:** ADR-0012.

**Context.** `CODMUNRES = 120040` is Rio Branco. It came back "Baixo Acre e
Purus", its health region, and had for weeks (`docs/history/FINDINGS.md` §3k).
Four correct mechanisms composed into the wrong answer: `.DEF` binds SINASC's
`CODMUNRES` to 145 codelists at confidence 0.9; `_rank` breaks the tie on name
affinity, then alphabetically; `CIRAC` sorts 3rd and `BR_MUNICIPALFA` 118th;
`_choose_binding` measured only the first 12 candidates. The correct table was
bound, never loaded, never measured. `SIM.CODMUNRES` had 156 candidates, and
`DIAG_PRINC` binds to 114 tables. Fixed in `8d3c404` ("Name the municipality
table, instead of letting ranking guess it") and at the second review closure
(`1578b40`), 2026-08-23.

**Decision.**
- **The variable → decoder link is a static build object**, declared in
  curation, not measured at runtime (`docs/history/HANDOFF.md` §1). 167
  corrections across 36 curation files: 128 columns onto `BR_MUNICIPALFA`, 12
  onto `BR_MUNICGESTOR`.
- **A resource cap cannot decide meaning** (FINDINGS §3l). For an uncurated
  field with more than `_MAX_CANDIDATES` bindings, rendering leaves the raw
  codes unlabelled (or raises in strict mode) and asks for curation; above the
  cap, an adjudication item is opened (ADR-0044).
- A curated codelist that does not ship fails a test
  (`test_every_curated_codelist_actually_exists`), and, since 2026-08-27, a
  municipality-keyed roll-up covering fewer than 20 states fails another
  (FINDINGS §3n, second).
- `RenderReport.codelist_used` names the table that produced each label.

**Alternatives.** Recorded as candidate fixes in HANDOFF §4.1: raise the cap
adaptively when the best candidate is a roll-up; rank by granularity before
alphabetical order. Both keep ranking as the decider for columns that matter.

**What would reverse it.** Nothing foreseen. The uncurated columns this
refuses are open work, not accepted gaps.
