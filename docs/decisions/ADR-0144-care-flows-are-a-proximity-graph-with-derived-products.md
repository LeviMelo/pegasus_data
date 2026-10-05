## ADR-0144: Care flows are a proximity graph kind; their products are derived on request

**Date:** 2026-10-05. **Status:** active. **Request:** PegaSUS phase 2 (health regions from where people actually seek care).

**Context.**
- `proximity.py` already holds the municipality graphs as `(from, to, weight, kind, vintage)` edge lists, and a first `care_flows` that counted residence -> place of care, but by period, with 6-digit codes and no share.
- The questions asked of it (is a city self-sufficient, who depends on whom, do official health regions match real flows) are all functions of that one table.

**Decision.**
1. **`care_flows` is the one flow mechanism** (`proximity.care_flows`, CLI `pegasus-data graph SIH-RD --period Y`). One edge per (origin, destination, year[, `by`]): `weight` admissions, `share` the part of the origin's admissions of that year (and group) that went to `to`, IBGE 7-digit codes, `kind` `care_flow:<dataset>`. SIH-RD origin is `MUNIC_RES_municipio` (residence), destination `MUNIC_MOV`; `--to establishment` ends at the CNES (`kind` `...:establishment`). `--by` takes any classifier (`COMPLEX`, `DIAG_PRINC --level chapter`).
2. **Every event is accounted for.** Table metadata carries `events`, `unplaced` (blank origin or destination), `unresolved` (a code that is no municipality) and the codes per year; the edges sum to `events - unplaced - unresolved`. An unresolved code is never mapped to a neighbour.
3. **Products are derived from that table, not stored** (`careflow.py`, `--derive`): `profile` (self-sufficiency, import share, treated, per municipality), `catchments` (nodal regions: each municipality follows its dominant destination until it reaches a hub, one whose own largest destination is itself), `communities` (Leiden on the directed weighted graph, RBConfiguration null model, `--resolution` is the only knob and is reported, not hidden), `regions` (the communities against a membership-pack classification: ARI, NMI and the share of admissions treated away from home that stay inside the region). Nothing persists: computed on request, the consumer caches.
4. **Dependencies:** `igraph`, `leidenalg` and `scikit-learn` are the `network` extra (and in `all`); the products need them, graph and profile do not.
5. **Geography selects publications only.** SIH files are by hospital state, so `geography="PR"` gives flows into Paraná hospitals, not out of its residents; national runs use `BR`.

**Limits (to state, not hide).**
- Communities depend on the resolution; none is the "true" regionalisation. The comparison is reported at matched counts, not at one resolution.
- Admissions are SIH (SUS-paid) only; the private sector and ambulatory care are absent.
- Residence is as declared on the AIH.

**Evidence.** EVALUATION 2026-10-05 "Care-flow graph".

**What would overturn it.** A use that needs the flows persisted and versioned (then a stored object with a vintage), or a published official flow matrix that supersedes counting from records.
