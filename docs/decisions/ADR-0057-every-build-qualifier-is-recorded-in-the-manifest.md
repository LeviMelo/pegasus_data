## ADR-0057: Every qualifier a build applies to its input is recorded in the artifact's manifest

**Date:** 2026-08-29. **Status:** active.

**Context.** Found by a user looking at a map: the frontend ranked Rio Branco,
AC first for hospital admissions in Brazil (`docs/history/FINDINGS.md` §3r).
The data was correct. `build_aggregate(..., uf="AC")` had been run, so the
artifact held 49,547 admissions from Acre's SIH files only, 2,417 cells over
118 municipalities. `build_aggregate` took `uf` and did not record it: the
manifest carried years, support, partial periods and warnings, every qualifier
about time and dimensions and none about space. From inside the cells, 118
municipalities with data looks exactly like a national build of something rare.
Fixed with `declared_ufs` in `100830f` (2026-08-29).

**Decision.**
- **Every qualifier a build applies to its input is part of what the output
  means, and belongs in the manifest.** `AggregateReport.uf` is recorded at
  build time and carried back on read as a warning.
- `capabilities()` projects `spatial.coverage`: `declared_ufs` (what the build
  fetched; authoritative), `observed_ufs` (prefixes present in the cells; a
  measurement, not a substitute), and `municipalities`. Artifacts built before
  the change report `kind: "unknown"`.
- A record-date build names the periods it cannot have filled
  (`partial_periods`), because a December admission is billed in January: the
  SIH file published under 2022 for Acre holds 3,687 admissions (7.44%) from
  2021 (FINDINGS §3p, second). It does not silently widen the fetch.

**Alternatives.** Inferring scope from the cells. Rejected: a national build
of a rare condition also touches few states.

**What would reverse it.** Nothing. Any future build predicate must be
recorded the same way.
