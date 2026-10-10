# ADR-0161: an event's denominator, when it is other events, is declared on its event type

**Date:** 2026-10-10. **Status:** accepted.

**Context.** Some rates are not per resident.
- Gestational and congenital conditions are reported per live birth: the Ministry's syphilis indicators, and the
  studies of SINAN's toxoplasmosis.
- The foetal death rate is per total birth.

A consumer that divides these by the population reads a wrong rate. PegaSUS did so for SINAN-TOXG: per 100,000
residents.

**Decision.**
- **The block.** An event type may declare `exposure:` with:
  - `events`: one or more `DATASET:event`, whose counts by place and year are summed;
  - `per`: the scale the source reports;
  - `evidence`: required, the indicator's definition and who uses it.
  Unknown keys raise. `event_types()` returns the block, or `None` where nothing is declared; it changes no count.
- **Declared for:**
  - SINAN-TOXG and TOXC: live births, per the studies' convention; Nota Técnica 133/2022 states no denominator.
  - SINAN-SIFG and SIFC: live births, the Ministry's syphilis indicators.
  - SIM-DOFET: live births plus foetal deaths, ICD-10's definition.

**Consequences.**
- PegaSUS reads a declared exposure by default (`monolith.default_population`). The rates over 2018–2024:

  | event | denominator | rate |
  |---|---|---|
  | TOXG | 1,000 live births | 2.96 → 6.44 |
  | DOFET | 1,000 total births | 10.1–10.8 |

- An event without the block keeps the resident population.
