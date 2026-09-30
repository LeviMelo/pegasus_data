# Plan: record linkage (branch `linkage`)

Written 2026-09-30, when `redesign` was merged into `master` and this branch
opened. It is the working plan for the branch: phases, what each delivers, the
decisions and evaluations each must record, and how each is accepted. It
changes as the work teaches us; every change to it is committed with the work
that caused it. Decisions live in ADRs, measurements in evaluation entries
(CLAUDE.md §7): this file points at them and never replaces them.

---

## 1. What linkage is, in this project

pegasus_data attaches meaning to records. It already connects:

| rung | what is connected | mechanism today |
|---|---|---|
| 1 | a code → its meaning | labels, validity windows (ADR-0079…0106) |
| 2 | a code → an entity or a newer classification | registries, crosswalk, bridges (ADR-0100…0104) |
| 3 | a record → a record through a published key | `curation/joins.yml` (declared, not measured: OQ-20) |
| 4 | a record → a record about the same person, with no shared key | **this branch** |

Rung 4 is what epidemiology calls record linkage. The public files carry no
common person identifier across systems (SIH has no patient CNS; SIA's
encrypted CNS matches only within SIA). A person is identified by attributes
plus shared events, and every link must carry its measured error, as every
label carries its source: a wrong link is worse than no link.

The goal is not a notebook study but a capability of the library: general,
learned from the data, measured, reproducible, and exposed through the same
API, CLI and HTTP surfaces as everything else.

## 2. Principles (to be fixed in ADR-0107)

1. **A link is a query.** `link(spec, period, geography)` is planned, fetched
   and persisted through the existing planner, fetch path and lake. "National"
   is a geography, not a separate build.
2. **Candidates come from intrinsic properties; geography is evidence.** No
   hard geographic blocking: patients cross state lines for care. Blocking keys
   are intrinsic (birth date, sex, mother's birth date, birth weight) and
   typo-tolerant; residence and facility enter the score through learned
   travel flows.
3. **Evidence is measured in bits.** Every comparison contributes
   log2(P(observation | same person) / P(observation | different people)).
   Field weights, dependence between fields, and constraints share that one
   currency. A linkage's feasibility is computed before it runs: bits
   available after errors against bits needed to single out one record.
4. **Numbers are learned, meaning is declared.** People declare which column
   states which property of whom (roles) and which facts are impossible. Error
   channels, travel flows, frequency weights, blocking keys and thresholds are
   learned from the data and measured.
5. **Self-supervision.** True pairs come from exact identifiers inside systems
   (SIA's encrypted CNS, AIH numbers, SIM's subset copies). False pairs come
   from negative controls (a key deliberately shifted). Models are trained on
   both by minimising cross-entropy and judged on fresh controls.
6. **Every linkage reports its error.** Per pass and overall: pairs, estimated
   chance pairs (negative control over the same remaining records), agreement
   on held-out variables, and a verdict under thresholds fixed before the
   numbers (viable / caution / not viable). A non-viable linkage raises.
7. **People, not pairs.** Final resolution enforces cardinality (born once,
   dies once, one delivery per pregnancy) and temporal order (no care after
   death).
8. **Everything is recorded.** Each measurement is an evaluation entry; each
   choice an ADR; each unresolved question an OPEN_QUESTIONS row.

## 3. Workstreams and phases

Phases run in order within a workstream; workstreams B and C run alongside A.

### Workstream A: linkage

**A0. Architecture decision.** ADR-0107 fixes §2 and the vocabulary (GLOSSARY:
link, pass, negative control, chance rate, verdict, role, entity, event,
channel, bits of identity). Done when ADR-0107 and GLOSSARY entries exist.

**A1. Foundations.**
- *Record identity.* Every decoded row carries `_row` (its ordinal in its
  source member). `(_blob_sha256, member, _row)` is a permanent record id: the
  blob store is content-addressed, so the id survives re-downloads. Accepted
  when a live query shows the id and two queries of the same file give the same
  ids.
- *Roles.* A curated layer (`curation/roles.yml`) says which column states
  which property of which entity in each dataset: `SIM.DTNASC →
  Person[deceased].birth_date`, `SINASC.DTNASCMAE → Person[mother].birth_date`,
  `SINASC.PESO → Birth.weight`. Values are compared through their meaning
  (decoded sex, parsed dates, 7-digit municipality), never raw codes. Accepted
  when the spine's datasets (SINASC, SIM-DO, SIH-RD, CIHA) have roles for every
  linkage-relevant field and `roles()` resolves them live.
- *Measured same-key joins (OQ-20).* Rows per key, measured for every
  `joins.yml` entry the spine uses (SIH-RD↔SP by `N_AIH`, SIH-RD↔RJ, SIA CNS
  across SIA families). Evaluation entry.

**A2. Measurements that make the engine general.** Each is an evaluation
entry with its artifact under `data/probes/linkage/`.
- *Bits of identity.* For each spine field: entropy, joint entropy with the
  other keys, mutual information between pairs (residence↔facility), per state
  and year; and the bits needed to single out one record per link scope.
  National, 2022–2023 (downloads ~1.8 GB/year for SINASC, SIM, SIH-RD, CIHA).
- *Error channels.* From true pairs (SIA-PS/AQ/AD/AM encrypted CNS; SIH
  RD↔SP; SIM subsets vs DO), per field and system: how values disagree
  (adjacent key, transposition, day/month swap, dropped digit, century), with
  counts. National for the small SIA families.
- *Travel flows.* Origin–destination matrices (residence municipality → care
  municipality) by care type (delivery, oncology, infection, all), from SIH-RD
  and CIHA; their mutual information.
- *Coverage of admissions.* SIH ∪ CIHA: CIHA's hospital vs outpatient
  records, payer mix, overlap with SIH (`FONTE` 04/05), CIH → CIHA eras.

**A3. Deterministic baseline.** Reproduce omnisus's RR 2022 study
(`evidence/2026-09-23-*`) on our stack, with the same passes, controls
(birth date +7 days; neighbouring identifier for exact keys), validations and
verdict thresholds. Compare every number; each difference is traced to a
decoding or label defect on one side. Evaluation entry; defects fixed or
recorded.

**A4. The engine (`src/pegasus_data/linkage/`).**
- `spec`: link specs in `curation/links.yml` (sides, roles, passes, control
  shift, validations, cardinality). A spec is data, reviewed like curation.
- `candidates`: blocking on intrinsic roles with typo-tolerant variants drawn
  from the measured error channels; several keys combined; key choice
  measured by recall on true pairs per comparison budget.
- `evidence`: comparison functions per role type (date, category, number,
  municipality, facility) returning bits, from learned channels, frequency
  weights and flows.
- `model`: Fellegi–Sunter with learned m/u, frequency-based u, dependence
  handled by conditioning (facility given residence) rather than independence.
  Trained on anchor pairs and control pairs (cross-entropy); EM where no
  anchors exist, initialised from anchors elsewhere.
- `controls`: negative controls per pass over the same remaining records;
  chance rates; held-out validation; verdicts.
- `resolve`: 1:1 assignment and cardinality/temporal constraints.
- `store`: link tables in the lake (`lake/links/<spec>/…parquet`) with
  provenance (source blobs, spec version, model version, rates).
Accepted when the deterministic passes reproduce A3's numbers inside the
engine, and the probabilistic model beats them on held-out anchors with an
equal or lower measured chance rate.

**A5. The pregnancy spine (flagship).**
Links, in order of key strength:
1. SINASC birth ↔ SIH-RD / CIHA delivery admission (mother's birth date +
   facility + birth day inside the admission).
2. SIM infant death ↔ SINASC birth (birth date + sex + residence + weight).
3. SIM maternal death ↔ SIH-RD / CIHA admission (mother's birth date + death
   date = discharge date + facility).
4. SIM fetal death (DOFET) ↔ delivery admission.
5. SIH neonatal admissions (baby as patient) ↔ SINASC birth.
Each: live run on a small state (RR/AC) and a large one (SP), then national
for one year; evaluation entry per link; verdict recorded.

**A6. Surfaces.**
- API: `link(...)` returning links + report; `query(..., linked=...)` adding
  the other side's columns; linked cohorts in `aggregate`.
- CLI: `pegasus-data link …`.
- HTTP (`serve/`): `/links` and the person-timeline routes. The frontend
  (`../pegasus_view`) is a separate project and out of scope here (user,
  2026-09-30); a linkage module was drafted there on its own `linkage` branch
  before that instruction and is left for the user to keep or discard.
- `scripts/live.py`: linkage scenarios.

**A7. Beyond the spine (later, same engine).** Deaths after discharge
(SIH→SIM, 30-day mortality); oncology (APAC→SIM); SINAN→SIM where bits allow;
professional linkage (CNES professionals across establishments, CNPJ
networks) as the administrative sibling.

### Workstream B: what omnisus teaches (evaluation 2026-09-30)

Each item is checked against our data before adoption; each adoption is an
ADR or a curation change with its measurement.
- **Facts to verify and record in DATA_SOURCES:**
  - SIM DOINF/DOMAT/DOEXT are copies of DO rows;
  - SIH-SP ⊂ SIH-RD by AIH;
  - SINAN FINAIS/PRELIM split per agravo, with no overlap;
  - SINAN-TB's file year follows `DT_DIAG`;
  - `id_agravo` truncated (`A16.`);
  - AIDABR24 half-empty records;
  - `LERBR19`/`LERDBR19` same size;
  - CADMUN coordinates (0,0) and missing post-2011 municipalities;
  - countries table with duplicate codes;
  - `classi_fin` in hanseníase set by the system;
  - SIM age-unit documentation conflict;
  - SINASC `CODESTAB`/`CODANOMAL` width drift;
  - CNES `turno_at` `'  -99'`;
  - `ESPEC` 17, `FINANC` 00, `HOMONIMO` 2, `CO_ERRO` codes outside `MOTERRO`, `FINALID` 7, `TPIDADEPAC` and `AP_COIDADE` bare codes;
  - incomplete months (RR June 2022);
  - impossible dates;
  - `TIPPRE  ` column name with spaces;
  - ER `ANO`/`MES` equal to the file's period;
  - no public dispensation-event source.
- **Mechanisms to evaluate:**
  - catch-all CNV ranges (`00-99` → "Ignorado") that mask undocumented codes, against "an unmapped code is undecoded, visibly";
  - SIH `IDENT` (and any other CNV grouping category such as "Outras/ignorado") labelled from the layout instead of the TabWin grouping;
  - a per-table `check_columns()` for a person in Python (empty share, distinct, unlabelled codes present in this table, date range and impossible dates), composed from existing coverage primitives;
  - per-label claim status (verified / measured / conflicting / unreviewed) with document locator, and a SHA-256 registry of `sources/`;
  - `cite()` from blob hashes;
  - IBGE `/v3/agregados` population editions (202, 4714, 6579) against OQ-12;
  - FTP: two clocks (listing year vs filename year), skip counts as a returned field, pre-flight byte reservation for split months.
- **Checked and not needed:** DBC truncation (our decompression is complete
  and byte-identical to `datasus_dbc` on RDAC2401 and PAAC2401); SIGTAP and
  DEMAS sources (already have); per-code CNES name API (the kit's registry is
  bulk and offline).

### Workstream C: continuous health

- OQ-61 values, by measurement against other columns, as ADR-0105/0106 did.
- Live scenarios (`scripts/live.py --all --fresh`) after each phase; defects
  found there fixed and the scenario re-run.
- `scripts/codehealth.py` for dead code after each refactor.
- STATUS updated at each phase boundary.

## 4. Records this branch must produce

| kind | where | when |
|---|---|---|
| architecture and each method choice | `docs/decisions/ADR-NNNN-*.md` + DECISIONS row | A0, A1 roles, A4 model, thresholds, each adoption |
| every measurement and live run | `docs/evaluation/YYYY-MM-DD-*.md` + EVALUATION row | A1–A5, each B item checked, each live pass |
| vocabulary | GLOSSARY.md | A0 |
| module boundaries | ARCHITECTURE.md | A1, A4 |
| commands | RUNBOOK.md | A4, A6 |
| facts about the sources | DATA_SOURCES.md | A2, B |
| open questions | OPEN_QUESTIONS.md | as they arise |
| state of work | STATUS.md | each phase boundary |

## 5. Constraints

- Disk: ~177 GB free. The spine is ~1.8 GB/year compressed nationally; SIA
  PA/BI (~46 GB/year) is reduced to persons before any linkage and deferred.
- Memory: 32 GB. The engine never holds a nation: it streams blocks from the
  blob store and lake; DuckDB (in the environment) spills joins to disk.
- The FTP server is one connection's bandwidth: plan() before every national
  pull; national pulls detached, logged.
- No unit tests; verification is live, on a fresh home, reading the output.

## 6. Progress

| phase | state | record |
|---|---|---|
| A0 | done | ADR-0107, GLOSSARY "Record linkage" |
| A1 | done: record identity, roles; join grains measured except AN, AB, MT (OQ-20) | ADR-0109, EVALUATION national measurements |
| A2 | done: bits (4 datasets), channels, flows, coverage, national 2022 | EVALUATION 2026-09-30 national linkage measurements |
| A3 | done: omnisus RR 2022 reproduced to the pair | EVALUATION 2026-09-30 |
| A4 | deterministic and probabilistic done (vectorised, clear-best margin, upper-bound verdicts); travel-flow evidence and typo-variant blocks next (OQ-63) | ADR-0110, ADR-0111, ADR-0113 |
| A5 | five spine links plus two private-sector (CIHA) links declared; three spine links viable on AC/RR; newborn admissions viable in SE with ICD-10 P07 evidence, caution in RR/AC (ADR-0117); maternal not certifiable per state (ADR-0113); residence scored given the place of care (ADR-0115); CIHA deaths and deliveries viable in SE; national 2022: all seven links viable, probabilistic (SIH deaths 90.0% at upper 0.24%, deliveries 59.7% at 0.49%, infant 84.5% at 0.17%, newborn 17.3% at 1.07%, maternal 845 of 1,640 at 1.71%, CIHA deaths 57.0% at 0.25%, births → CIHA 193,335 at 0.95%) | ADR-0110 to ADR-0118, EVALUATION 2026-09-30 (private-sector links, residence given the place of care, newborn P07, national linkage 2022) |
| A6 | done: `link(method=)`, `role_table()`, CLI `link --method`, serve/ `/links` and timeline routes (the timeline includes non-SUS deliveries from CIHA), live scenarios `linkage`, `timeline`; frontend out of scope | README, ADR-0112 |
| B | survey done; IDENT and LOCNASC fixed; catch-all audit run; DBC, DEMAS, SIM subsets, SIH-SP/RD, SINAN FINAIS/PRELIM and TB checked; CIHA residence tested against SINASC; claims audit (SERV_CLA 000000 narrowed); every listed fact measured except the dispensation source (SIM minutes, TABPAIS names, CLASSI_FIN and ORIGEM texts fixed); mechanisms from the survey not yet evaluated | EVALUATION 2026-09-30 (omnisus, catch-all, omnisus facts verified), ADR-0108 |
