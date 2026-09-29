## ADR-0040: Counts live only in ARCHITECTURE §21, and doubts in §22 beside them

**Date:** 2026-08-23. **Status:** retired (ADR-0001, 2026-09-28: the
documentation model was replaced and the architecture document frozen under
`docs/history/`). **Supersedes:** ADR-0036.

**Context.** The same count was stated in several documents and they
disagreed: §21 read "1,572 described (34.7%)" beside 538 tests while `RESUME.md`
read "4,528 (100%)" beside 601, and a reader could not tell which was current
(`docs/history/pegasus_data_ARCHITECTURE.md` §21). RESUME's own state table
disagreed with §21 by a factor of three (`docs/history/RESUME.md`, State).
`docs/CONFIDENCE.md` (ADR-0036) drifted from the counts it qualified within a
day. `7aa4b77` (2026-08-22, "Make ARCHITECTURE §21 the only place a count
lives") and `bf62316` (2026-08-23, "fold CONFIDENCE.md into the architecture").

**Decision.**
- Every count about what exists lives in ARCH §21 and nowhere else, with the
  test count stated beside it as the cheapest available clock.
- Claims the project makes on thin evidence live in ARCH §22, ranked by the
  damage a wrong one would do, each with what would settle it. An entry is
  deleted when settled, never softened.
- `RESUME.md`, `FINDINGS.md`, `DEFECTS.md` carry no counts.

**Alternatives.** A separate doubts file (ADR-0036), superseded here.

**What would reverse it.** It was reversed. After 2026-08-27 all work was
tracked only in FINDINGS §3r–§3y and commit messages, although `HANDOFF` and
`RESUME` both named ARCH §21 as the only place for state (ADR-0001). The rule
that a count lives in one place survives in the new model: measurements are
dated evaluation entries, and `STATUS.md` holds current state.
