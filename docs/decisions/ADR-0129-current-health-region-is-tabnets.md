## ADR-0129: The system-neutral current health region is TabNet's table; per-system tables keep their own claims

**Date:** 2026-10-03. **Status:** active. Resolves OQ-10.

**Context.**
- **OQ-10.** The membership pack's `health_region` comes from each
  publishing system's own `CIRBRN` table. For 46 municipalities SIM and
  SINASC name different codes, so the classification was served flagged
  as contested; naming a system cleared it.
- **What OQ-10 asked for.** A Ministry statement of the current
  regionalisation, which would settle the contested cases.
- **ADR-0126 added that statement.** TabNet's `territorio/br_regsaud.cnv`
  became the `health_region_current` classification (5,606 municipalities,
  446 regions).

**Evidence.** EVALUATION 2026-10-03 "Contested health regions against
TabNet's current table" (`scripts/health_region_conflicts.py`):
- **All 46 are SIM against SINASC:** 44 in Santa Catarina, 2 in Rio Grande
  do Sul.
- **33 are not disagreements.** SINASC's SC table writes a region as UF
  plus two digits (`4214`), where SIM and TabNet write UF plus three
  (`42014`). The region is the same, as the labels confirm (`SC Extremo Sul`
  against `Extremo Sul Catarinense`).
- **13 are real disagreements.** TabNet's current table agrees with SINASC
  in 11 (for example `Vale do Itapocú`, where SIM still says `Nordeste`)
  and with SIM in 2. The pattern is two vintages of the regionalisation,
  not an error in either system.

**Decision.**
1. **A system-neutral current roll-up uses `health_region_current`**
   (authority `tabnet`). It answers "which region is this municipality in
   now", without a contest.
2. **`health_region` stays each system's own claim.** A contest is still
   reported there, because the system tables are what a record of that
   system was tabulated with. Codes are never rewritten across schemes:
   widths are matched exactly (CLAUDE §6). The SC two-digit scheme is
   documented, not normalised.

**Consequences.**
- **The roll-up for an analysis of a given system** remains that system's
  table (`memberships(code, system=...)`).
- **Neither TabNet table carries a vintage** (OQ-11). A historical roll-up
  still has no Ministry source.
