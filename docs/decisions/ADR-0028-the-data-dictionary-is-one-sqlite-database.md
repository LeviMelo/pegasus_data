## ADR-0028: The generated data dictionary is one SQLite database, not a tree of Markdown pages

**Date:** 2026-08-19. **Status:** active.

**Context.** `a4488c5` (2026-08-19) generated the dictionary as 3,036 Markdown
pages. Everything in them was relational (systems have variables, variables
have code tables, code tables have codes), and flattening it cost three things
(`docs/history/pegasus_data_ARCHITECTURE.md` §14b):

- No question could be asked. "Which columns draw on CID-10?" was a `grep`
  across 42 MB.
- Values were truncated. The renderer capped tables at 500 rows, so 5,570
  municipalities did not fit.
- The largest page did not render: SINAN's 2,250 columns came to 1,043 KB,
  past what GitHub displays. That produced pagination, then link-integrity
  problems, then a link checker, all serving the container.

Replaced the same day in `634c10e` ("The dictionary is a database, not 3,036
files").

**Decision.** `pegasus-data dictionary` writes one SQLite file (systems,
variables, code tables, every code and label, schema generations, dataset
prose), with a full-text index over names and descriptions. It is generated
from the catalog, never hand-written, and does not ship (531 MB, 7.47M codes);
it rebuilds in about three minutes. Each variable's rendered page is stored as
a column (`pegasus-data page`). Two encoding choices kept it from being larger
than what it replaced (the first schema was 1.1 GB): `codes` references its
codelist by integer, and labels are not indexed into FTS (an index on `label`
serves exact lookup).

**Alternatives.** The Markdown tree, rejected above. Merging it with the
bundle (ADR-0027), rejected: one is a transport format, the other a read
model, and both derive from the catalog.

**What would reverse it.** Nothing foreseen.
