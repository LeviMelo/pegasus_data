## ADR-0042: Labels are not borrowed across systems by default, and a historical fallback is recorded, not narrated

**Date:** 2026-08-23. **Status:** active.

**Context.** Labelling involves substitutions that are defensible one at a time
and misleading in aggregate if nobody is told: a code labelled from another
system's table because the requested system ships none; a 1995 request
answered from the current vintage because the pack has no window that old; a
codelist that decodes only part of a column
(`docs/history/pegasus_data_ARCHITECTURE.md` §8.1). A blanket refusal of
historical labels was tried and took a fresh-install SINASC 2022 fetch from 15
labelled columns to 0, because the pack then carried no windows. The second
external review found cross-system labels "optimistic"
(`docs/history/DEFECTS.md`, second review closure). The historical-label
policy was made explicit in `9b45d4b` (2026-08-22); borrowing became opt-in in
`1578b40` (2026-08-23).

**Decision.**
- **System independence is positive evidence** (`docs/history/FINDINGS.md`
  §3l). A `system = NULL` pack row means every observed system agrees and is
  usable everywhere; the absence of one system's table does not make a
  neighbour's safe. A foreign-system table is used only under
  `allow_borrowed_labels=True`, and is recorded in `RenderReport.borrowed`.
- `historical_labels="current"` (default) answers a historical request from
  today's table and records the substitution; `"refuse"` returns raw codes.
  The default was chosen by the measurement above.
- Substitutions are collected in a `ContextVar` for the render and returned as
  machine-readable fields (`borrowed`, `fallback_vintage`,
  `partial_codelist_match`, `rollup_used`, `constant`), so a strict pipeline
  can refuse them by threshold rather than by regex over English.

**Alternatives.** Borrowing by default, and refusing historical labels by
default. Both rejected above.

**What would reverse it.** Nothing foreseen. In the query path, an unknown
vintage now resolves to null rather than current (ADR-0048).
