# ADR-0166: a place is `where` or a `mark`, defined once; care flows are derived from the roles

**Date:** 2026-10-14. **Status:** accepted. Amends ADR-0144.

**Context.** A place column states `model: where` or `mark` (or stratum, dimension, link_only, excluded), and
nothing in the code said what the first two mean. The only definition was a docstring in PegaSUS, written after SIM's
death-verification municipality was read as a field and gave 354 answers. The same knowledge was kept three times:
`proximity.FLOWS` (four datasets, residence column to place column, by hand), `FACILITIES`, and PegaSUS's
`declared_flows`. SINAN's notifying unit and infection places were typed differently from SIM's place of death.

**Decision.**
- **Defined where the models are** (`semantics/column_roles.py`, `MODEL_MEANING`). `where`: the place where the event,
  its care, its notification or its infection happened. `mark`: a place the record only names (the registry office, the
  death-verification service, a managing authority, a place of travel or exposure). The residence of the person is a
  stratum; where they were born or work, a dimension. A place column's model is one of
  `PLACE_MODELS` and `where` is a place's model only; both are validated.
- **No new attribute and no re-curation.** The notification places stay `where`, as the definition says.
- **Flows are derived.** `proximity.flows()` pairs, per dataset that declares event types, each *residence* stratum
  column with each `where` place column of property `municipality` or `facility_municipality`, within the years both
  exist (one `FlowGeneration` per layout generation). Origin is the residence column, read through the variable's
  declared municipality remap when it has one (SIH's `MUNIC_RES_municipio`, SIA's `AP_MUNPCN_municipio`,
  `PA_MUNPCN_municipio`: Brasilia's 2008-2017 administrative-region codes read as the one municipality). The
  establishment variant ends at the `<entity>.facility` column of the same entity as the place. A dataset whose roles
  give two pairs for the same years has no unique flow and none is derived. `care_flows(event=...)` names the event
  type counted when a dataset declares several and none is the only one of the place role's entity kind.
  `FLOWS` and `FACILITIES` are removed; `care_flows` counts a weighted event by its quantity.

**Consequences.**
- The four flows reproduce byte for byte: SIH-RD and CIHA (AC 2025: 355 and 34 edges, 61,479 and 2,686 events),
  SINASC-DN 2024 (36,498 edges, 2,389,325 events, 56 unresolved) and SIM-DO 2025 (58,366 edges, 1,534,588 events, 1,992
  unresolved), edge lists identical to the hand-written map's. Establishment columns: CNES, CODESTAB as before.
- It adds 82 datasets (72 of the 86 have an establishment column): SINAN's 55 (residence to notifying unit; SINAN-CHIK 2015: 52,338
  events, 17 unplaced, 3 unresolved), SIA's APAC families (10) and PA, the same ten APACs from Dados Abertos, SIH-SP,
  CIH-CR, SIM-DOFET and DOREXT, SINASC-DNEX, e-SUS Notifica DCCR. A new dataset gets a flow by declaring
  its roles; nothing else lists it.
- `pegasus-data graph` accepts any of them; `proximity.flows()` lists them.
