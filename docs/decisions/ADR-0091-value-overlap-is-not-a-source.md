## ADR-0091: A binding inferred from value overlap is not a source of meaning

**Date:** 2026-09-29. **Status:** active. **Amends:** the `semantic_match` stage
of `semantics/dictionary.py`.

**Context.**
- **What `semantic_match` is.** An earlier stage bound 287 (system, field)
  pairs to code tables because the field's observed values happened to fall
  inside a table's codes. Confidence ran from 0.35 to 0.99, and no document
  says any of it.
- **What it did, measured 2026-09-29.** Among its bindings:
  - SIA's APAC procedure `OPC_PRIPAL` → **municipalities**, at 0.88;
  - `APA_PRIPAL` → the establishment registry;
  - SIH `CEP`, `N_AIH` and `GESTOR_DT`, and SIM `NUMERODO` and `CODBAIRES`
    → the **procedure** table;
  - IBGE `IDADE` → ICD-10.
- **Why it matters.** Measured weighing could pick such a table whenever the
  digits coincided. It would then label a procedure with a city, which is a
  wrong label that looks right: the failure CLAUDE.md §3 ranks first.
- **Scale.** 154 fields had no other binding.

**Decision.**
- **Excluded.** `semantic_match` bindings are no longer label candidates, in
  either loader: `view._bindings` (queries and the compile) and
  `semantics/bindings.py` (normalisation).
- **What still counts.** Documents only: `.DEF` files, layout documents,
  curation and adjudication.
- **What happens to the 154 fields.** Where a guess was right, the field gets
  an explicit curated binding, as the CNES and SIA establishment fields
  already have (ADR-0086). The rest show as visibly undecoded (`code (?)`)
  until a source is found. `pegasus-data meaning` lists them.

**What would reverse it.** Nothing. A statistical match may still **suggest** a
binding to a curator, as `promote_semantic_matches` does when a layout
document confirms it, but it never decodes on its own.
