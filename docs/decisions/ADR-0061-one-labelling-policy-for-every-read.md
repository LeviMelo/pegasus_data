## ADR-0061: One labelling policy for every read; `query()`'s `label_of` gate is removed

**Date:** 2026-09-28. **Status:** active. **Amends:** ADR-0044 (typed
relations and the adjudication queue), ADR-0041 (the declared decoder link).

**Context.** `query()` is the documented primary interface (ADR-0043). On a
fresh home it returned **2** labelled columns for SIH-RD AL 2023-01, 3 for
SIM-DO AL 2022 (not `CAUSABAS`), and 54 of CNES-ST's 113 (evaluation
2026-09-28, the first live runs).
- `fetch()` over the same file labelled 38.
- The difference was `_query_engine/semantics._enforce_identity_labels`.
  After `fetch()` had chosen and applied each codelist, it dropped every label
  whose codelist was not the target of a declared `label_of` relation.
  `curation/joins.yml` declares six such relations.
- The gate wrote one adjudication row per column on every read, emitted one
  `SemanticFallbackWarning` per column (36 to 59 a call), and cost 12 of the
  15 s of a warm `query()`.

Two policies therefore decided what a column means: the renderer's choice
(`view._select_codelists`: curated codelist, then a catalog relation, then
coverage and granularity with a rollup guard; ADR-0012, ADR-0031, ADR-0041),
and the gate's refusal. The gate did not check the renderer's choice for
correctness. It checked only whether a relation file named the choice, and
almost none were named.

**Decision.**
- The renderer's choice is the one policy, applied identically by `query()`,
  `fetch()`, `load()` and `translate()`. `_enforce_identity_labels` is
  deleted.
- What the renderer may choose is governed where it always was: curation
  first, measured coverage and granularity after, with the rollup guard. The
  renderer's own warnings, summarised as one `UserWarning` per call with the
  full list on `RenderReport.warnings`, are what a user sees.
- Declared `label_of` relations stay: `view._select_codelists` still honours
  one as a curated declaration. Compiling one binding per field ahead of time,
  so that the choice is deterministic across files and auditable in review, is
  the next step (STATUS, M2). It will make relations the source of the choice
  rather than a filter applied after it.

**Measured after** (`m1-fixes-2`): SIH-RD 39 labelled, SIM-DO 52, CNES-ST 113,
SINASC 31; a warm `query()` 2.7 s; one warning per call.

**Alternatives.** Writing `label_of` relations for every field, so the gate
passes. That is the compiled-bindings work (M2), and until it exists the gate
only withheld labels the renderer had already vetted.

**What would reverse it.** A field whose renderer-chosen codelist is shown to
be wrong while a declared relation would have been right. The answer to that
is M2's compiled bindings, not the gate.
