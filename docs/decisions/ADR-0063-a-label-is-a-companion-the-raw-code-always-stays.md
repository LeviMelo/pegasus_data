## ADR-0063: A label is a companion; the raw code always stays

**Date:** 2026-09-28. **Status:** active. **Amends:** ADR-0010 (the raw value
survives its label).

**Context.** The default render profile (`view.PROFILES["analysis"]`)
replaced internal codes with their labels in place: `MORTE` `0` became
`Sem óbito`. External codes (CID, municipalities) got a `_label` companion.
- The raw value was discarded, against CLAUDE.md §6 and ADR-0010.
- The shape of a column depended on the codelist's role, which the user
  cannot see.
- The live harness (`scripts/live.py`), counting `_label` companions, saw 9
  labelled columns in `fetch()` output that actually carried 38.

**Decision.** The default profile keeps every code and adds `<field>_label`
(`internal="both"`). `query()` already rendered this way (profile `audit`).
The `codes` profile (no labels) and the `report` profile (combined
`code – label`, translated headers) are unchanged and explicit.

**What would reverse it.** Nothing in the analysis case. A reader who wants
labels in place asks for `profile="report"`.
