## ADR-0051: A stock measure is refused over time; no time reducer is applied in the core

**Date:** 2026-08-27. **Status:** active.

**Context.** `CNES.ST` is one row per establishment per month: a stock
observed repeatedly, where `SIH.RD` is an event stream
(`docs/history/AGGREGATE_PLAN.md` §7a). `COUNT(*)` there counts
establishment-months, so over a quarter the difference from a count of
establishments is about threefold. `QTINST*` is installed capacity at an
instant, so summing it over months yields "room-months". The request asked to
redesign before broadening if CNES showed the abstraction was event-centric
(`docs/history/REQUEST.md`). It did not: extending to CNES needed a spec and no
code. Landed with the aggregate layer in `bab9cce` (2026-08-27).

**Decision.**
- A measure declares, per axis, whether it is additive. A stock is additive
  over geography and dimensions and not over time.
- `time_reducer` (`mean`, `last`, `max`) is declared, validated and enforced as
  a **refusal**: summing a stock across periods is refused, naming the reducer
  that would work. Applying the reducer is not implemented in the core
  (AGGREGATE_PLAN §9: "the safe half, and the right half to ship first").
- `count` on an entity-period grain declaring `unit: establishment` is refused
  against the grain; the shipped CNES spec names its count
  `establishment_months`.

**Alternatives.** Applying the reducer silently at serve time. Rejected:
"room-months" look like data. The frontend later reduces stocks client-side (a
mean per period, `docs/history/FINDINGS.md` §3y), and the workbook exporter
honours stocks (`e397efa`, 2026-09-03).

**What would reverse it.** A consumer that needs a reduced stock from the
library itself. The reducer would then be implemented, not the refusal
removed.
