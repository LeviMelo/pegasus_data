## ADR-0043: `query()` and `plan()` express publication-coordinate intent; period and geography never filter record variables

**Date:** 2026-08-23. **Status:** active.

**Context.** The next-architecture brief
(`docs/history/PEGASUS_NEXT_ARCHITECTURE_BRIEF.md` §1) asked for a runtime
that expresses intent, resolves dataset, period and geography, and returns
data with explicit adaptations. The first implementation (`efbc7c1`,
2026-08-23) let `period` and `geography` act as predicates on fact fields
(`time_by`, `geography_by`, `unresolved_time`). The replacement review
narrowed the scope: Pegasus-Data retrieves, decodes, harmonises and serves
DATASUS publications, and the researcher defines the analytical population
afterwards (`docs/history/FINDINGS.md` §3o, first; `docs/history/REVIEW.md`).
Restored in `7bbd076` ("enforce source-oriented query semantics").

**Decision.**
- `period` and `geography` identify DATASUS **publication coordinates**.
  `period="2024-03"` selects the March publication when one exists; it does not
  mean `DT_INTER` or `DTOBITO` fell in March. A publication UF never becomes a
  `MUNIC_RES` predicate.
- A monthly request over annual files widens to the enclosing year under
  `time_policy="adapt"` with `TimeResolutionWarning`; `"strict"` refuses.
- A UF applies only when it is a declared and observed physical publication
  axis; otherwise the request refuses.
- `_competencia` is immutable publication provenance.
- Completeness is per requested year against logical publications
  `(family, logical publication, archive member)`; complete and incomplete
  years may form a non-overlapping hybrid, and one year is never split between
  lake and fetch (FINDINGS §3n, first).
- Planning is metadata-only. A fresh-install unbounded acquisition refuses
  without `allow_unbounded=True`.
- `plan()` returns an immutable `QueryPlan` whose `explain()` names every
  decision; `QueryReport` records requested versus effective time and
  structural absence.

**Alternatives.** Row-level period and geography predicates (the first
implementation), removed.

**What would reverse it.** Nothing foreseen. Analytical helpers over record
fields may be added on top, opt-in, without changing what `period` and
`geography` mean.
