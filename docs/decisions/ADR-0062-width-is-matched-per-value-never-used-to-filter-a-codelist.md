## ADR-0062: Width is matched per value; a codelist is never filtered by a column's curated width

**Date:** 2026-09-28. **Status:** active. **Amends:** ADR-0015 (exact width).

**Context.** `view._render_table._lookup` read each codelist filtered to the
field's curated `token_rule.width`, even for single-valued columns.
- SIH's `DIAG_PRINC` is curated at width 4.
- The column holds 3-character CID-10 categories (I64, J18, I10, F29) beside
  4-character subcategories.
- All 272 distinct 3-character codes, 1,907 of 14,340 admissions (13.3%),
  came back unlabelled, although every one is in SIHSUS's own CID10 table
  (live run 2026-09-28).

The filter existed to keep two classifications of different widths apart.
Exact string matching already does that: a 3-character value can only match
a 3-character code.

**Decision.**
- A single-valued column is labelled by exact string match against the whole
  codelist; its table is never filtered by width.
- `token_rule.width` keeps its one job: splitting packed multi-valued cells.
- The selection weighing (`_select_codelists`) measures coverage the same
  way.

**What would reverse it.** A codelist in which the same code string means two
different things at different widths *and* both appear in one column. Exact
matching cannot separate those, and neither could the filter. It would need a
per-vintage binding (M2).
