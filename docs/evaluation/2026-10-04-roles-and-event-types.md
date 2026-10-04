# 2026-10-04: a role for every column, and event types (handoff §2–§3)

**Regime.** Branch `linkage`. Linkage home for national 2022 (SIH-RD, SIM-DO, SINASC-DN lakes, stored links); live home for SINAN-DENG 2022. TabNet over HTTP (`sources/tabnet.py`).

**Roles.** `curation/roles/<dataset>.yml`: 1,540 columns of 16 datasets (SIM-DO, SINASC-DN, SIH-RD, CIHA, SINAN DENG CHIK ZIKA TUBE HANS SIFC SIFG SIFA VIOL MENI LEPT IEXO).
- **How they were made.** `scripts/draft_column_roles.py` drafted them from the curation, the semantic axes and the linkage roles; five reviewers then went through them against the entity test.
- **69 stay `draft`.** Each carries its reason. 50 are LEPT's undocumented 2000–2006 block; the others are columns whose curation is only inferred.
- **The validator** (`semantics/column_roles.py`) refuses:
  - a stratum other than age, sex, race or residence;
  - an identifier that is not `link_only`;
  - a column that disagrees with its linkage role.
- **The entity test on linked records** (stored SIH in-hospital deaths → SIM, 2022, 539,879 pairs with p ≥ 0.9). It is measured only on attributes the link did not compare.

| attribute | agreement |
|---|---|
| race (person; "ignored" excluded) | 0.718 |
| principal diagnosis vs underlying cause, 3 characters (event) | 0.237 |
| admission date vs death date (event) | 0.078 |
| discharge date vs death date (used by the link, reference) | 0.956 |

**Event types.** Declared under `event_types:` in `curation/datasets/*.yml` and served by `event_types()`, `count_events()` and `pegasus-data events`. Counts for 2022, by state, against TabNet:

| event type | ours | TabNet | states exact |
|---|---|---|---|
| SIM-DO death (residence; `TIPOBITO` 2) | 1,544,266 | 1,544,266 | 27/27 |
| SINASC-DN birth (mother's residence) | 2,561,922 | 2,561,922 | 27/27 |
| SINAN-DENG probable case (notification state; `CLASSI_FIN` ≠ 5) | 1,405,095 | 1,405,095 | 27/27 |
| SIH-RD hospitalisation (`IDENT` 1, distinct `N_AIH`, hospital's state) | 12,377,318 | 12,377,242 | 12/27 |

**The SIH difference** is 1 to 13 in every month, with no duplicate AIH numbers (OQ-68).

**Declared, not compared with TabNet:**
- CIHA hospitalisation (`MODALIDADE` 02);
- SIM-DOFET foetal death;
- the SINAN notification and confirmed-case types.

**SINAN confirmed cases** are declared only where the form's own classification table names them: DENG, CHIK, LEPT, MENI and IEXO.

Probes: `$TEMP/accept/ours22.py`, `deng.py`; `$TEMP/rolecheck/agree.py`.

**Code structures (handoff §5).** `code_trees.parquet`: ICD10 14,560 nodes (22 chapters, groups, categories, subcategories), SIGTAP 6,217, CBO2002 3,574, CNAE20 2,005; every node below the top level has a parent. `code_lists.parquet`: CID-BR-10 12,075 codes, ICD-10 lists 2 and 4, avoidable causes 0–4 and 5–74 (14,263 each), ICSAP groups 649 and conditions 644; no code sits in two items of one list. Spot check: I219 → I21 → I20-I25 → IX; I219 is CID-BR-10 "068.1 Infarto agudo do miocárdio", J45 is ICSAP "7. Asma". Not served: the morbidity list, GBD, ICD-9 → ICD-10 (OQ-69).

**Proximity graphs (handoff §6).** Built in 75 s from the cached IBGE sources: the 2022 mesh, Census 2022 tracts and localities.
- **Contiguity:** 33,006 directed edges over 5,568 municipalities. 1,022 are 0 km point contacts, and 2 municipalities have no neighbour, presumably the island municipalities.
- **Population distance:** 167,419 edges (30 nearest plus neighbours).
- **REGIC 2018:**
  - edges: network 5,124, basic health 6,293, high-complexity health 6,429;
  - cities: 4,899, covering all 5,570 municipalities.
- **Areas:** Marabá 15,166 km² against IBGE's published 15,128.

**Care flows** (linkage home, 2022) sum exactly to the events, with 0 unplaced:

| dataset | edges | flowed | events |
|---|---|---|---|
| SIH-RD SE, by ICD chapter | 4,536 | 107,005 | 107,005 |
| SINASC-DN BR | 37,417 | 2,561,922 | 2,561,922 |
| SIM-DO BR | 56,244 | 1,544,266 | 1,544,266 |

Every SIH diagnosis maps to a chapter.

Probe: `$TEMP/accept/flows.py`.
