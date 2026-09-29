## ADR-0038: Every replacement is staged beside its target and swapped atomically, one reader-visible unit at a time

**Date:** 2026-08-22. **Status:** active.

**Context.** ADR-0016 clears derived output before rewriting it, which opens a
window in which the artifact does not exist. Disk full, an interrupt or an
Arrow exception inside it leaves nothing where a full build's partition was
(defect P0-6, `docs/history/DEFECTS.md`; ARCH §7.5). Two further failures
followed: staging one Parquet file at a time and sweeping siblings later still
exposed mixed generations (`docs/history/FINDINGS.md` §3l); and merging a tree
at the wrong depth deleted sibling systems' reference tables while replacing
one system's. Built in `b686351` ("One staged-artifact abstraction for the lake
and the reference warehouse") and `fddb1f9` ("Give staged replacement real
rollback"), 2026-08-22; cross-process staging names fixed in `c2029a4`.

**Decision.**
- A replacement is written in full beside the target under a unique
  transaction token (`{pid}-{uuid}`), then swapped in by rename, which is
  atomic on both filesystems this runs on (`persist/staging.py`).
- The previous artifact is renamed aside, not unlinked, so a failure mid-swap
  rolls back.
- **The transaction unit is the unit readers observe**: a state-year lake
  partition, a population series and a DEMAS endpoint are directories, and are
  staged and swapped whole (FINDINGS §3l).
- `merge_depth` controls how much of an existing tree survives a swap.
- A multi-file artifact moves atomically: the aggregate manifest is staged and
  renamed like the cells beside it (FINDINGS §3v).

**Alternatives.** Clear-then-write, the P0-6 defect.

**What would reverse it.** Nothing foreseen.
