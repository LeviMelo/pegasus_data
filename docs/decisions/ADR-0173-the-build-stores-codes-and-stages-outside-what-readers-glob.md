# ADR-0173: the build stores codes, not labels; a partition is staged where no reader's glob reaches

**Date:** 2026-10-14. **Status:** accepted. **Origin:** the ingest review of 2026-10-14 (findings 7, 9, 10, 20), second round.

**Context.** ADR-0014 joins labels at read time, by validity window, and never freezes them into the lake; `Builder.build`
and `pegasus-data build` still defaulted to `emit_labels=True`. A partition was staged as a hidden sibling
(`uf=AL/.year=2020.__staging__...`) that pyarrow skips and DuckDB's `**/*.parquet` does not: every query on the family
failed ("Hive partition mismatch") while a partition was written and after a killed build. The swap renamed the old
partition outside its `try`: a reader holding it open (Windows) aborted the build and left the written tree behind.

**Decision.**
- Labels are stored only when asked (`emit_labels=False` in `NormalizePlan`, `Builder.build`, `build --labels`).
  `emit_labels` is part of the plan fingerprint; the lakes already built were written with it off, so nothing goes stale:
  all 2,924 partitions of the 3,327 listed in `pegasus_core_data` built by `Builder.build` are current under False and none
  under True (the other 403 were landed by intake and carry no builder fingerprint); none of the 3,327 holds a `_label` column.
- A lake partition is staged under `<lake>/.staging/` (and its old tree moved aside there), outside every family tree.
  `staged_tree(staging_root=)` says where; the default stays a hidden sibling for trees nobody globs.
- A refused rename (`PermissionError`) is retried with backoff (about 6 s in all). If it never succeeds the old tree is
  untouched, the staging tree is removed and the error reaches the build, which records that partition and goes on.
- `_record_key` is hashed only for a caller that keeps provenance (`fetch(provenance=True)`; `query(provenance="all")`).
  Its value is unchanged. The scheme itself (hash of the normalised batch, `'|'`-joined) is left as it is: OQ-78.

**Evidence.** `docs/evaluation/2026-10-14-ingest-review.md`, second round.

**What would overturn it.** A consumer that reads `<field>_label` from the lake without the renderer (none found: the
lake has no such column). A volume that cannot hold `<lake>/.staging/` beside the family trees (the rename would copy).
