## ADR-0016: Derived state is replaced, never accumulated; a catalog that disagrees with its schema is refused

**Date:** 2026-08-18. **Status:** active.

**Context.** Three idempotence bugs, found after the date fix of ADR-0013
(`docs/history/FINDINGS.md` §3b):

- `stratum_members` kept a file in the stratum it used to belong to, so a 2008
  stratum claimed a 2020 file's 113-column schema;
- orphaned strata survived re-inventory, dragging `families.time_min` back to
  1901;
- `family_files` kept stale links, so the 113-column SIH-RD family pointed at
  86-column files and normalised **zero rows** with no error.

A fourth came with the lake: a rebuild numbered its parts after its own stale
output, and `ds.dataset()` read both, returning every row twice (FINDINGS §3d).
Fixed in `89b7acc` (2026-08-18) and `ea0282e` (2026-08-19).

**Decision.**
- Every stage that re-derives clears its own output first; a stale partition
  beside a fresh one is indistinguishable from data
  (`docs/history/pegasus_data_ARCHITECTURE.md` §4).
- A build owns the whole partition it writes and replaces it (ARCH §7.2).
- A family that selects files but produces no rows records why in
  `build_outcomes`.
- **Migration is refused, not attempted.** A table whose columns disagree with
  the shipped schema raises `CatalogSchemaError`, naming `catalog-rebuild`
  (ARCH §4). The clear-then-write window this opens is closed by ADR-0038.

**Alternatives.** Incremental upserts. Rejected: they are how a correction
upstream fails to propagate.

**What would reverse it.** Nothing foreseen.
