## ADR-0034: Column availability has three states: present, absent, unknown

**Date:** 2026-08-21. **Status:** active.

**Context.** `SIH.RD` has 20 schema generations across 34 years, and its
secondary-diagnosis columns `DIAGSEC1`–`DIAGSEC9` do not appear before 2014. A
query for `DIAGSEC4` in 2007 returns nothing, and that nothing is structural:
the column did not exist. Read as clinical missingness, it corrupts any estimate
spanning the boundary (`docs/history/pegasus_data_ARCHITECTURE.md` §14.7).
`DIAGSEC4` is carried by decoded files for 2014–2016 and 2018 onwards, so an
interval `valid_from`/`valid_to` of 2014–2026 would assert something about 2017,
a year nothing had been decoded for. Added in `c4d8995` (2026-08-21).

**Decision.**
- `availability()` and `field_available()` answer per column per year with
  three states: `present` (a decoded schema for that year carries it),
  `absent` (a decoded schema exists and does not carry it, a positive claim),
  `unknown` (nothing decoded for that year; no claim).
- Intervals may bridge undecoded years for the shape of a run, but `state()`
  checks `unknown` first and `span()` names what it bridged.
- What DATASUS published (`file_facts`) and what the catalog decoded
  (`strata`) are kept apart.
- `absent` rests on evidence (`d68dbd3`, 2026-08-22), and an uncensused
  generation is not an empty one (`8a37f17`).
- Exported to the compendium as `field_validity`, which is core, not optional.
- The query layer carries the same distinction as `structural_absence` in its
  report and Arrow metadata (ARCH §14.13).

**Alternatives.** Two states from `valid_from`/`valid_to`. Rejected: one state
short, it turns silence into a claim.

**What would reverse it.** Nothing foreseen.
