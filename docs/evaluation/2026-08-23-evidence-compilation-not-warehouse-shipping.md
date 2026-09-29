## 2026-08-23 — The next architecture is evidence compilation, not warehouse shipping

*Split from docs/history/FINDINGS.md §3m on 2026-09-28; text unchanged.*

## 3m. The next architecture is evidence compilation, not warehouse shipping (2026-08-23)

Three read-only audits settled the design before implementation:

1. `scripts/storage_report.py` measured the recovered 15.0 GB catalog with
   SQLite `dbstat`. There were no free pages. `code_tables`, `dictionary` and
   four repeated B-tree indexes explain nearly all of the file. SQLite is not
   intrinsically the cost; expanded maintainer evidence and duplicated lookup
   paths are. Runtime resources should remain compiled Parquet projections.
2. `scripts/audit_representations.py` found 4,422 logical publications with
   alternatives: 14,446 physical files, of which 10,024 can be avoided by a
   deterministic decode-cost preference. The grouping key must retain archive
   member identity; suffix similarity alone is not proof of equivalence.
3. `scripts/audit_crosswalk.py` measured the rebuilt CNES↔CNPJ pack. Temporal
   ambiguity and reverse one-to-many relations are real, not corner cases. A
   dictionary overwrite or a default join would silently select an identifier
   or multiply fact rows. Exact-window grouping understated both: 951 source
   ambiguities become **1,816 pairwise-overlapping relation pairs**, and 12,619
   reverse multi-source windows become **13,923 pairwise-overlapping relation
   pairs**. These are pair counts, not canonical disjoint ambiguity segments.

The implementation follows those measurements:

- `query()`/`plan()` separate source-publication intent from physical lake/fetch
  mechanics, expose requested versus effective time, and preserve structural
  absence as report data and Arrow metadata.
- Annual files answer a subannual source request by retrieving the enclosing
  annual publication with a warning, or refusing under a strict policy. Event
  dates never manufacture a row-level month in the source API.
- `label_of`, `rollup_to`, `attribute_of` and `crosswalk_to` are distinct typed
  relations. Only the first may become an automatic `*_label`; the middle two
  require a dimension request.
- CNES↔CNPJ is additive and temporal. It preserves observed identifiers,
  returns safe nulls for conflicts/ambiguity, and changes row count only through
  explicit `explode=True`.
- The resource manifest carries schema/content versions, build identity,
  checksums, sizes and budgets. Compact semantics ship; CNES history and names
  are optional local resources whose requirement and estimated cost appear in
  the plan before retrieval begins.
- Semantic uncertainty above a cost cap creates a stable adjudication item.
  Evidence can be exported and a reviewed typed relation applied; truncation is
  never allowed to become truth.

`HANDOFF.md` was rechecked during this pass. Its durable novel lessons had
already been consolidated in §3l; the remaining text is operational history or
duplicates the architecture, so no second copy was introduced.
