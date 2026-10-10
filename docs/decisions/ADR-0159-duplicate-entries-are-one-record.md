# ADR-0159: rows equal on every fact but entry metadata are one record

**Date:** 2026-10-09. **Status:** accepted.

**Context.** SDTA's largest outbreak lead in PegaSUS, Maranhão 2023 (ratio 56 over 217 municipalities), was not a wave.
- **What the rows are.** One notifying unit (CNES 9005064, municipality 210340) filed 32 rows in March 2023, every one
  with 32 ill. 19 of them are identical in every field but entry metadata, and 13 differ in a recorded fact (onset 23
  or 25 March, local type, symptom counts).
- **How common it is.** Across 2007–2024, rows equal but for entry metadata number 0–3 a year, except 21 in 2019
  (none with ill) and 28 in 2023 (771 ill).

**Decision.**
- **The rule.** An event type may declare `duplicates: {except: [...], evidence}`. Rows equal on every column but those
  listed (entry metadata) are one record. The first in file order is kept, before status, consolidation and weight.
- **What it costs to read.** A read of such an event takes every column.
- **SDTA's metadata.** Its notification number, entry, transfer, investigation and closing dates.
- **Near-copies are not merged.** Rows that differ in a fact stay apart, because which copy is right is not known.
  Maranhão keeps 13 such rows from one unit.

**Consequences.**
- SDTA 2023 counts 1,134 outbreaks, from 1,162, and 19,108 ill, from 19,879; the Ministry publishes 19,671.
- PegaSUS's record reader applies the rule too, so a per-outbreak mark (its ill) counts the outbreak once.
