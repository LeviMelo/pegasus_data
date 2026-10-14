# ADR-0165: events are read by one function; a declared duplicate flag must be read; a classifier says what it recodes

**Date:** 2026-10-14. **Status:** accepted. Amends ADR-0159.

**Context.** The review of the semantics layer (2026-10-14) found three ways an event count could be quietly wrong.
- `events_of` skipped the source's duplicate flag (SINAN's `NDUPLIC_N` 2, "do not count") when its column was not in
  the table. 63 event types declare it. `field_overlap` selected only its own columns, so every flagged duplicate was
  counted in both fields and in their overlap (the 0.05 threshold that decides whether two fields are tested as
  independent), and it never applied a weight (SIA-PA, PS, SAD, SIH-SP, SIA-BI count procedures by quantity).
  Reading with the flag, retrying without it, assembling the weight and choosing `select` was done in four places,
  the gateway's among them.
- `group_by` treats null as a key: every row with a blank `N_AIH` or `AP_AUTORIZ` collapsed into one event.
- `Classifier.role == "alternative"` meant two things: a second coding of the primary's attribute (SIM's
  `CAUSABAS_O`, the original underlying cause, in ICD-10 beside `CAUSABAS`: counting by it counts the same deaths
  again) and another attribute of the same events (SIH's procedure beside its diagnosis). A missing `role:` defaulted
  to `alternative`.

**Decision.**
- **One reader.** `event_types.read_events(dataset, event, columns, *, records=None, **query)` selects the columns the
  rule itself reads (status, consolidation key, weight, grid, the source's flag; every column when the duplicates
  rule compares whole rows), reads without the flag when the form or year lacks it, applies `events_of`, and appends
  `__w`, the events a row stands for. `count_events`, `field_overlap` and `proximity.care_flows` read through it.
- **`events_of` raises** when a declared flag column is not in the table, unless the caller passes
  `flag_absent_ok=True`. Only `read_events` does, after its own read found the form without the flag; a table the
  caller supplies (`records=`) must carry it. A forgotten projection fails; it no longer over-counts.
- **A row with no consolidation key** (null or blank in any key column) identifies no event to merge: it is kept as
  an event of its own, counted in the result's `pegasus.unkeyed` metadata, and `count_events` warns.
- **`Classifier.role` is required**, and an alternative may declare `recodes: <primary column>`: a second coding of the
  same property, in the same code structure, validated when the declaration is loaded and returned by
  `event_types()`. It corroborates or compares and is never a further dimension. SIM-DO and SIM-DOFET's `CAUSABAS_O`
  declare it. An alternative without `recodes` is a facet that partitions the events differently.

**Consequences.**
- `pegasus_core.gateway` assembles its own flag/retry (`events_of(table, only)` after reading without the flag): it
  must pass `flag_absent_ok=True` there, or call `read_events`.
- Counts are unchanged where the flag was selected: SIM-DO 2025 1,534,588, SINAN-CHIK 2015 52,338 and SIH-RD 2025
  14,512,292 before and after (SIH-RD has no blank `N_AIH`).
- `field_overlap` now counts a weighted event by its quantity and drops flagged duplicates; its figures change where
  either applies.
