## ADR-0048: A source vintage is an interval, and an unknown vintage resolves to null, not to "current"

**Date:** 2026-08-23. **Status:** active.

**Context.** The hardening review found three variants of one false-precision
bug (`docs/history/FINDINGS.md` §3p, first; `docs/history/REVIEW.md`, remaining
issues 2 and 3): an annual publication collapsed to an unknown vintage;
direct crosswalk enrichment given only `year=2020` evaluated December; and a
multi-year dimension lookup applied one current table to every row, silently
rewriting historical categories (FINDINGS §3n, first). Fixed in `64cb3b5`
(2026-08-23, "harden temporal semantics and resources").

**Decision.**
- A source vintage is an interval (`_vintage.py`): a monthly publication is
  `[YYYYMM, YYYYMM]`, an annual one `[YYYY01, YYYY12]`, and missing provenance is
  unknown.
- A coarse interval resolves only when one effective relation and mapping is
  valid throughout it.
- A temporal mapping that needs a vintage the provenance cannot supply yields
  null, unless the mapping is declared time-invariant. "Current" is never a
  silent fallback in the query path.
- A dimension lookup selects the packed relation per row competence or year.
- `_source_resolution` distinguishes a deliberate annual enclosure from missing
  monthly provenance, and month pushdown is kept per year in mixed plans.

**Alternatives.** Treating a year as its last month, or falling back to the
current table. Both rejected above.

**What would reverse it.** Nothing foreseen. The renderer's
`historical_labels="current"` default (ADR-0042) records its substitution
rather than hiding it.
