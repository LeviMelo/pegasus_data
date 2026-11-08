# Handoff to pegasus_data: what the PegaSUS design asks of the data module

**2026-10-04.** From the agent working on the PegaSUS design (`pegasus_project/docs/design/DESIGN.md` v0.2), to the agent working on pegasus_data.

**Read first:**
- DESIGN §2 (the boundary);
- DESIGN §3–5 (ontology, space, the modelled tier).

**Every input of PegaSUS comes through pegasus_data**, which will be open source.

**The boundary, in one line** (DESIGN §2): pegasus_data answers *what exists and what it means* (observed tier) and *what was there and how it was recorded* (modelled tier: estimates, typed as modelled, versioned, with uncertainty, never replacing an official series). PegaSUS answers *what is normal, what departs, what relates*.

**pegasus_data's own rules govern all of this:**
- live verification, not new unit tests;
- replace, never build beside;
- an ADR only for a final decision; compact measurements;
- install the library the job needs;
- commit in batches on a branch, and the author merges.

Where an item duplicates something that exists, extend the existing mechanism; the pointers below name it.

**Priority order:** §1 is free and large; §2–§5 unblock PegaSUS phase 1; §6–§7 are phase 2–3.

---

## 1. Storage, operational (no new compression algorithm)

Measured 2026-10-04 on `C:\Users\Galaxy\pegasus_linkage`.

**Where the space is:**

| part | size |
|---|---|
| lake (SIH 2021–2023 is 2.26 GB, about 750 MB per year) | 3.8 GB |
| **raw DBC blobs** | **6.0 GB** |
| **role caches** (SIH-RD alone: six versions, national, by state, superseded) | **3.3 GB** |

**Inside the SIH lake:**

| column | share |
|---|---|
| `_record_key` (32-character hex text) | **30.9%** |
| `N_AIH` | 9.1% |
| `NASC`, `VAL_TOT`, `VAL_SH`, `US_TOT` (stored as text) | about 22% |
| `_row` (int64) | 4.8% |

**The changes, in order of value:**
1. **Evict raw blobs once their lake partition is verified.**
   - Keep the sha256, size and source path in the catalog. Refetch on demand: the fetcher already verifies by size, and falls back to the mirror (ADR-0122).
   - A command (`pegasus-data prune`, or a policy in config) plus an opt-out for those who want the originals.
   - The author has decided to cut blobs.
   - **Caveat to document:** the DBC bytes cannot be regenerated from the lake. A refetch reproduces them, and the lake is the product.
2. **Role-cache policy.**
   - Cache national role tables only, and derive state and region slices by filtering them.
   - Drop superseded keys.
   - Cap total size (least-recently-used).
3. **Record key as 16 raw bytes** (`FIXED_LEN_BYTE_ARRAY`) instead of 32-character hex. Measure the saving.
   - A 64-bit key would save more. Over 300 million records its collision risk is small but not zero, so it would need collision detection on write.
   - **Decide on the measurement.** ADR-0124 is the place to amend.
4. **Typed storage where the text round-trips exactly.**
   - Numbers (values, counts) and dates as numeric and date types, keeping the raw text only for rows that don't round-trip.
   - Codes always stay text (width is meaning).
   - Check column by column against "never discard the raw value".
5. **`_row` with delta encoding** (it is sequential within a file).
6. **Sort rows within each partition** by municipality and date before writing; measure the compression gain.
7. **Build only the national file for systems that publish one** (SIM, SINASC). Per-state builds duplicate it: 22,196 SIM rows were measured in both.

**Acceptance:** sizes before and after per system; `query()` results identical (row counts and checksums of decoded columns) on a fixed set of national queries.

---

## 2. A role for every column (DESIGN §3.2)

**Extend `curation/roles.yml`**, which today covers about 60 columns of 5 datasets for linkage, **to every column of SIM, SINASC, SIH-RD, CIHA and SINAN's main diseases.** Each column gets:
- **role:** `entity.property`, from the test "if the same person had a different event, would the value change?" (person: no; event: yes; institution or place: reached through a reference; identifier);
- **value kind:** category | code tree | number | date | place | institution reference | identifier | text;
- **model role:** stratum | dimension | event type | mark | when | where | institution | link-only | excluded.

**Rules:**
- **A stratum must exist in the population account** (age, sex, race, residence). Everything else categorical about persons is a dimension or a mark.
- **One record can carry several entities:** SINASC has mother, baby, pregnancy and birth.
- **Generate the first draft from existing typing,** then review: VariableDoc codelists → category or code tree; numeric → number; personal-identifier flags and join keys → link-only; semantic axes → where and when.
- **Verify on linked data** that person attributes agree across linked records more than event attributes do (ADR-0120's settings-as-annotators machinery).

**Serve it:** `roles(dataset)` in the API and `pegasus-data roles <dataset>` in the CLI.

---

## 3. Event-type declarations (DESIGN §3.3)

Per dataset, declared in curation and served by the API:

```
grain (exists: "what_one_row_is"), kind, classifier(s) with role (primary / alternatives),
status (which rows count), consolidation (how rows become events)
```

**Concrete needs:**

| system | what to declare |
|---|---|
| **SIH** | the event is the **hospitalisation episode**, not the AIH. Consolidate continuation AIHs (`IDENT`; read the layout, ADR history on `IDENT`) and, where linkage allows, transfers. Classifiers: **principal diagnosis (primary) and procedure performed (alternative)**, since SIH is the source for the epidemiology of procedures and surgeries |
| **SIM** | death and foetal death (`TIPOBITO`); final cause (`CAUSABAS`) primary, original (`CAUSABAS_O`) alternative; certificate lines as multi-valued marks |
| **SINAN** | notification and confirmed case as two event types (`CLASSI_FIN` per disease form; respect ADR-0080 and ADR-0136 on per-form tables) |
| **SINASC** | birth; no classifier; anomalies as a mark |

**Acceptance:** annual counts of each declared event type against an independent figure (TabNet), for 2022, by state.

---

## 4. Aggregation for PegaSUS (extend `aggregate()`, do not build beside it)

PegaSUS phase 1 needs, per event type, **sparse aggregated counts**: only non-empty cells, streamed.
- **Keys:** place lattice (municipality | health region | comparable area) × time grain (year | month) × age band × sex (× race) × classifier at a tree level, with the code role.
- **Mark summaries** as exact accumulator states (n, sum, sum of squares, and a histogram on declared bins), mergeable as the existing monoid states are.
- **Measured overlap** between two fields defined by predicates (shared events / smaller field), computed from records.
- **Output:** Parquet or Arrow streams, with the data version, so PegaSUS caches by content.

**Acceptance:** national SIM 2010–2023 by municipality × year × 18 ages × 2 sexes × ICD three-character: time, memory, row count of non-empty cells, and a total equal to the record count.

---

## 5. Code structures (extend ADR-0092, ADR-0134)

**Serve each structure as data:** nodes, parents, levels, validity windows. A tree is a parent table; a list is a membership table.
- **Trees:** ICD-10 (chapter → block → category → subcategory), SIGTAP (group → subgroup → form → procedure), CBO.
- **Overlapping lists:**
  - the CID-BR mortality list and the morbidity list (ADR-0134 has the TabWin lists);
  - **the GBD cause hierarchy and garbage-code list** (to acquire; licence to check);
  - ICSAP (primary-care-sensitive conditions, Portaria SAS/MS 221/2008);
  - avoidable causes (the Brazilian list of Malta et al.).
- **Crosswalks:** ICD-9 → ICD-10 for SIM before 1996, where a crosswalk exists.

---

## 6. Geography and proximity graphs (new; DESIGN §4)

Built and versioned like other reference tables, as edge lists `(from, to, weight, kind, vintage)`:

| graph | source |
|---|---|
| **contiguity weighted by shared border length**, plus municipality areas | IBGE municipal meshes; install `geopandas` / `shapely` |
| population-weighted distance between municipalities | census tract populations, or the municipal seat as a fallback, stated |
| **care flows:** residence → hospital municipality, per year, per specialty or classifier chapter | **SIH** (`MUNIC_RES` → `MUNIC_MOV`). Also births (SINASC residence → place of birth) and deaths (SIM residence → place of death) |
| urban hierarchy | IBGE REGIC 2018 |
| health regions and comparable areas | exist (ADR-0126, ADR-0129) |
| travel time | road network; later |

**Acceptance:** every municipality present (5,570; state the treatment of new municipalities); flow totals equal the records they come from.

---

## 7. The modelled tier (DESIGN §5): phase 2–3

**Declare a modelled tier first:** where modelled products live, how they are typed (`modelled`, model version, uncertainty, validation evidence), and that no modelled product ever replaces an official series. POPSVS stays as published.

### 7.1 New population sources, acquired as observed data

| source | what | priority |
|---|---|---|
| **INEP school census** | enrolments by municipality × age × sex × race | high |
| **CadÚnico** (CECAD tabulations) | persons by municipality × age × sex × race | high |
| **ANS** | plan holders by municipality × age band × sex: gives the SUS-dependent population | high |
| **TSE electoral roll** | voters by municipality × age band × sex; race (self-declared since 2022; 79% missing in 2026) | medium |
| **RAIS** | formal workers by municipality × age × sex × race | medium |
| census migration questions | origin–destination flows | medium |
| WorldPop / GHSL | gridded population | low |

### 7.2 The population account

- **What it is:** a Bayesian demographic account, after Bryant & Zhang (2018). The cohort-component state `N(u,t,a,s,r)`, observed by every source through its own data model (DESIGN §5.1 lists the equations and sources).
- **Outputs:** N with intervals; net migration; race reclassification; completeness of SINASC and SIM; dated shocks; the SUS-dependent population.
- **Acceptance:** predict the 2022 census by municipality × age × sex from data up to 2021, and beat RIPSA's pre-census estimates (its 2000–2021 series), by municipality size and age. **If it doesn't beat them, it doesn't ship.**

### 7.3 Race measurement

- **What it is:** the structured confusion matrix per setting (DESIGN §5.2): ordinal lightening and darkening propensities with hierarchical, literature-centred priors, on top of ADR-0128's flags.
- **Acceptance:**
  - planted misclassification recovered from real counts;
  - linked pairs' cross-classification predicted by the model.

---

## 8. Scope notes

- **SIA:** PA and BI are not needed by PegaSUS. They are 406 GB of production accounting, so they should not be built by any default path.
  - The APAC families (AQ, AR, ATD, AM) and RAAS PS will be wanted later as care-pathway sources.
  - Their declarations exist (`curation/datasets/declared.yml`, `ontology.yml`).
- **CNES** enters PegaSUS in phase 3 (the institution lattice). ADR-0125 already serves attributes as of the record's month.

## 9. What PegaSUS will measure first, needing §2–§6

- ICD tree pooling against held-out years, chapter by chapter (SIM 2021–2023).
- Which proximity graph best explains between-municipality variation for a few causes.
