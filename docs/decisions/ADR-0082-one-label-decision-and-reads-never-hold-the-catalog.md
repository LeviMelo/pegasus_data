## ADR-0082: One label decision for query and compile; reads never hold the catalog

**Date:** 2026-09-28. **Status:** active. **Amends:** ADR-0072, ADR-0080.

**Context.**
- **Two copies of the label decision.** "Which table labels this column" was
  implemented twice: in `view._select_codelists` at query time and in
  `label_bindings.compile_bindings` at build time. They drifted. The per-form
  rule (ADR-0080) had to be added to both, and the harvested form dictionaries
  reached only the query path, so compiled bindings ignored the best evidence
  there is.
- **Lock contention.** While the per-file census ran, a plain `query()` failed
  with "database is locked", for two reasons:
  - `Catalog.execute` never committed, so any write through it held an
    implicit transaction, and the lock, until some later commit.
  - Constructing a `Pipeline` wrote the seed questions on every open, so a
    read waited on any running stage.

**Decision.**
- **One decision function.** `semantics/label_bindings.decide()` holds the whole
  ladder:
  1. inline `codes:`;
  2. the form's own dictionary, at 95% or more of rows;
  3. a curated `codelist:` (per-form lists become candidates);
  4. a reviewed adjudication;
  5. the stored decision;
  6. measured weighing.

  The renderer and `compile_bindings` both call it. Compile counts rows, not
  only distinct values, because rung 2 is judged on rows.
- **Writes commit themselves.** `Catalog.execute` commits a write made outside a
  `write()` block. Nested `write()` blocks commit once, at the outermost.
- **Reads don't write.** `Pipeline.seed_questions` writes only questions that
  are missing or changed.

**Result, 2026-09-28.** With the census writing concurrently, SIH-RD (40
labelled), SIM-DO (52), SINAN-MENI (47; `CLASSI_FIN` 1 confirmado, 2
descartado), SINAN-BOTU (30), CNES-ST (113) and SIA-PQ all query with no
lock errors.
