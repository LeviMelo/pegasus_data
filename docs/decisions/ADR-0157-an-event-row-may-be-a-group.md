# ADR-0157: an event's row may be a group, not a person

**Date:** 2026-10-09. **Status:** accepted. Extends ADR-0156.

**Context.** SINAN-SDTA's row is one foodborne outbreak, and its ill come in clusters. Counted as people by sex and
band (ADR-0156), they fit in PegaSUS with φ 0.066: a place-year's variance is about 15 μ², so no departure is seen
(PegaSUS OPEN_QUESTIONS 14). The outbreak is the unit their occurrence changes in, and it has no sex or age.

**Decision.**
- An event type may declare `persons: false`. Its row is a group: it has no sex or age, and it is exposed by the whole
  population of its place. A new kind, `outbreak`, is added.
- SDTA declares `outbreak` (one row, one outbreak) beside `case` (its ill, from the grid). Its ill per outbreak
  (NU_TOT, with 0 not recorded) is a measurement on the outbreak.
- A dataset may refuse its file's shared event types with `shared_event_types: false`. SDTA does, because SINAN's
  shared person notification does not hold for an outbreak. Since `case` was declared, SDTA had been inheriting it.

**Consequences.** PegaSUS reads an outbreak's events in one exposed cell, its place's whole population (its decision
0034). Outbreaks fit with φ 1.04, against 0.066 for the same outbreaks' ill.
