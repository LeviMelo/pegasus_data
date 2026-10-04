## ADR-0138: proximity graphs are edge lists, care flows are counted events, and aggregates count declared events and roll classifiers up their trees

**Date:** 2026-10-04. **Status:** active. **Request:** PegaSUS handoff §4 and §6 (DESIGN §3.5, §4).

**Decision.**
1. **Proximity is a family of edge lists** `(from, to, weight, kind, vintage)` over 7-digit municipality codes, served by `proximity.py`:
   - **contiguity:** weighted by shared border length (km) from IBGE's 2022 maximum-quality mesh. A point contact is a 0 km edge.
   - **population_distance:** the population-weighted mean distance between two municipalities' people. Census 2022 tracts are aggregated to a 5 km grid, for each municipality's 30 nearest and its neighbours.
   - **regic_network, regic_health_basic, regic_health_high:** REGIC 2018's urban-network links and its links for low/medium- and high-complexity health care, weighted by order (1 strongest).
   - These ship. Areas and every municipality's REGIC city ship beside them.
   - **care_flow:** counted on request from the records (`care_flows`), as events of the dataset's declared type, per year. It can be split by a classifier rolled up its tree.
2. **Aggregation extends `aggregate()`; nothing is built beside it.**
   - **Event types.** A recipe may name an `event_type` (ADR-0137), and the build counts its events.
   - **National files.** A year published as one national file is read from it rather than from 27 state files.
   - **Tree levels.** A classifier with a declared code structure rolls up at query time: `by=["CAUSABAS@category"]`. Codes off the tree are reported as unmapped mass.
   - **Moments.** The `moments` measure (n, sum, sum of squares) is a mark's exact mergeable summary. A histogram is a banded dimension.
   - **Data version.** Results carry the artifact's `data_version`.
3. **Overlap is measured from records.** `field_overlap` is the shared events over the smaller field.

**Evidence** (`docs/evaluation/2026-10-04-roles-and-event-types.md`):
- **Contiguity:**
  - 33,006 directed edges over 5,568 municipalities;
  - 2 without a neighbour, presumably the island municipalities;
  - Marabá 15,166 km² against IBGE's 15,128.
- **REGIC** places all 5,570 municipalities.
- **Care flows sum exactly to their events,** with none unplaced:
  - SIH SE 2022: 107,005, all ICD chapters mapped;
  - SINASC BR 2022: 2,561,922;
  - SIM BR 2022: 1,544,266.
