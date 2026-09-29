## ADR-0036: What the project is least sure of is recorded in `docs/CONFIDENCE.md`

**Date:** 2026-08-22. **Status:** superseded.
**Superseded by:** ADR-0040.

**Context.** By 2026-08-21 the project claimed 4,528 of 4,528 columns described
and 100% of files bound to a declared dataset. Several of those claims rested
on thin evidence: most descriptions were inferred and self-audited, and binding
decode rates came from a partial value profile. `f8e08a8` (2026-08-22, "Write
down what we are least sure of") created `docs/CONFIDENCE.md` to hold them,
ranked by the damage a wrong one would do, each with what would settle it.
`52d8690` corrected a wrong entry in it the same day.

**Decision.** Keep a separate document of doubts beside the architecture.

**Alternatives.** None recorded at the time.

**What would reverse it.** Drift between the doubts file and the counts it
qualified. It happened within a day: decode coverage ended up filed there as a
doubt, disagreeing with the counts in ARCH §21, and the file started to hold
project state it was never meant to (`docs/history/pegasus_data_ARCHITECTURE.md`
§22 preamble; `docs/history/HANDOFF.md` §0). ADR-0040 folded it into the
architecture.
