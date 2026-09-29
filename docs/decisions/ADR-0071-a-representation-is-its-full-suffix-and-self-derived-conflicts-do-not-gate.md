## ADR-0071: A representation is known by its full suffix; a conflict the selector derived itself is re-evaluated, not stored as a gate

**Date:** 2026-09-28. **Status:** active. **Amends:** ADR-0047, ADR-0068.

**Context.** `fetch("SINAN-TUBE", years=2022)` refused with
`RepresentationConflictError` (evaluation 2026-09-28, age units).
- The publication `SINAN|TUBE|BR|22` exists as `.dbc` (PRELIM) and, in Dados
  Abertos, as `.csv.zip`, `.json.zip` and `.xml.zip`.
- The chooser compared container formats, so the three archives were all
  `zip`, with three different sizes and one date. It read them as competing
  editions of one format, found the dates tied, refused, and wrote an `open`
  row to `representation_conflicts`.
- That stored row then gated every later read, including after the rule was
  fixed. Stored conflicts were consulted before any evaluation.

**Decision.**
- Candidates are compared by their full representation suffix (`csv.zip`,
  `json.zip`, `dbc`, from `strip_container_suffixes`). Decode cost is still
  ranked by container.
- A stored open conflict gates selection only when its evidence cannot be
  recomputed at selection time (row counts or schemas measured at decode).
  Conflicts the selector itself derives from sizes and dates ("multiple
  objects of the same format") are re-evaluated on every call. Their rows
  remain as the audit trail.

**Measured after:** `fetch("SINAN-DENG", years=2022)` and SINAN-TUBE 2022
select one representation (the `.dbc`) and read.

**What would reverse it.** A same-format conflict that can only be decided by
a person. That belongs in the adjudication queue with evidence the selector
cannot recompute, which still gates.
