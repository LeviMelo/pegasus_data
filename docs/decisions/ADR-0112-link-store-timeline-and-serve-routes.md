## ADR-0112: Link results persist in the lake; a pregnancy is served as a timeline of linked events, behind the microdata switch

**Date:** 2026-09-30. **Status:** active. **Part of:** ADR-0107 (plan phases A5, A6).

**Context.**
- **Recomputing a link is minutes** (national SIH deaths → SIM: 6 minutes
  deterministic), and a person or a frontend asks for the same link many
  times.
- **The plan's product is a timeline**, one pregnancy across systems, which
  pegasus_view can draw. The user named it a good goal.
- **Two more spine links were declared and measured on RR and AC 2022**
  (maternal deaths → admission; neonatal admissions → birth), and one of them
  cannot be identified there.

**Decision.**
- **Persistence.** `linkage/store.py` keeps each run under
  `<lake>/links/<spec>/`: the pairs as Parquet, the report as JSON. A run is
  keyed by spec, method, period, geography and a digest of the spec's
  content, so an edited spec is a different linkage and its old results are
  not served for it. `link()` reuses a stored run unless `refresh=True`;
  `persist=False` keeps nothing. On RR the same link returns in 0.1 s instead
  of 37 s.
- **Timeline.** `linkage/timeline.py` assembles one birth's events from the
  stored spine links:
  - the mother's delivery admission;
  - the baby's admissions in its first 28 days;
  - the baby's death before one year;
  - the mother's obstetric death through the delivery admission.
  
  Twins are grouped into one delivery. Each event carries the record id, the
  hospital (named from the CNES registry), the link, the method and (for the
  probabilistic method) the pair's evidence in bits. A link that is not
  viable at the scope attaches nothing and is named in `not_viable`.
- **HTTP (`serve/`).**
  - `GET /api/v1/links`: specs and stored run reports. Aggregate facts,
    always served.
  - `GET /api/v1/links/timeline`: births with the most linked events.
  - `GET /api/v1/links/timeline/{birth}`: one pregnancy.
  
  The last two are microdata and answer 403 unless the server started with
  `--allow-records`, the switch `/records` already uses.

**Result (fresh home, RR and AC 2022).**
- **SIM maternal deaths → SIH:**
  - RR: 21 obstetric-cause deaths, 11 linked deterministically and 12
    probabilistically, at 0% chance; the admission ended in death for 100% /
    91.7%.
  - AC: 5 deaths, 2 and 3 linked.
  - Only 8–33% of the linked admissions carry an obstetric diagnosis. The
    admission is often recorded under the complication (omnisus found the
    same).
- **SIH neonatal admissions → SINASC: not viable in RR.** 3,484 admissions of
  babies in their first 28 days, 0 pairs. In Boa Vista's single maternity
  hospital about 15 babies of each sex are born on a day, so baby's birth date
  + sex + hospital + residence is not unique. SIH carries nothing else about
  a newborn (no weight, no mother), and the 1:1 rule refuses every pair. The
  method refused a link it cannot make, as designed. The probabilistic spec's
  blocks now all keep the birth date: a block of hospital + residence + sex
  generated tens of millions of candidates without adding identifying
  evidence.
- **A timeline served from AC 2022.** Delivery admission at the Hospital da
  Mulher e da Criança do Juruá (15–16 Jan), a boy born there (3,065 g,
  vaginal, 35 weeks), an infant death the same day (P22.0); the neonatal
  link reported not viable. Without `--allow-records` the route answers 403.
