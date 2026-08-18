# `pegasus_data` — Architecture and Implementation Brief

**Status:** working specification. Not final. Written to be executed, extended, and corrected by an implementing agent with no prior context.

**Companion document:** `RISCO_DIABETICO_formalizacao_e_plano.md` — the epidemiological research plan that is the first consumer of this module. Read §1 of that document to understand what the module is ultimately for. Neither document depends on the other to be implemented, but the field lists in §12 here are driven by it.

---

## 0. Orientation for an implementer with no prior context

### 0.1 What Brazil's public health data actually is

Brazil's Sistema Único de Saúde (SUS) is the national public health system. Its administrative and epidemiological data are published by **DATASUS**, the Ministry of Health's IT department, on a public FTP server at `ftp.datasus.gov.br`, under `/dissemin/publicos`. There is no authentication. There is no API for it. There is no centralized data dictionary.

The tree contains roughly 125,000 files spanning ~18 information systems and ~35 years. The core systems, and what each one records:

| System | What generates a record | What it contains |
|---|---|---|
| **SIH/SUS** | A hospital bills the SUS for an inpatient stay | Hospital admissions. Diagnosis (ICD-10), procedure, length of stay, cost, in-hospital death, municipality of residence and of occurrence |
| **SIA/SUS** | A service bills the SUS for an outpatient procedure | Outpatient procedure counts. **Public version has no patient, no age, no diagnosis** — it is a billing ledger |
| **SIM** | A physician issues a death certificate | Deaths. Underlying cause plus the full causal chain written on the certificate |
| **SINASC** | A maternity issues a live-birth certificate | Live births |
| **SINAN** | A service fulfils the legal duty to notify a reportable disease | Notifiable disease case reports — dengue, tuberculosis, leptospirosis, ~59 conditions, each with its own form and schema |
| **CNES** | An establishment registers so it can bill | Health facility register: beds, equipment, staff, type |
| **CIHA** | Records of care **not** financed by the SUS | Partial visibility into the private sector |
| **APAC** (within SIA) | High-complexity authorizations | Dialysis, chemotherapy, high-cost medication — the only public data with a patient-anchored longitudinal trail |
| **PNI** | Immunization records | Vaccine doses |
| **IBGE** (mirrored here) | Census and population estimates | Denominators for rates |

**The single most important fact about this data:** none of it was produced to measure population health. It is the administrative residue of billing, registration, and legal-duty acts. Every bias in it is predictable by asking what the person filling the form gained or lost by filling it accurately. Fields that affect payment are filled carefully. Fields that do not are frequently empty.

### 0.2 What this module is

A Python package that turns the DATASUS FTP tree, plus the DEMAS open-data REST API (§11), into a **queryable, self-describing, typed data lake**, where the meaning of every variable and every coded value is recoverable from the package itself.

It is not a downloader with a nice wrapper. The unit of value is the **semantic layer**: the assertion that column `X` of system `Y` in year `Z` means a specific thing, and that value `k` in that column denotes a specific category. Crawling, decoding, Parquet, and concurrency are all machinery in service of producing and defending that assertion.

`pegasus_data` is a component of a larger epidemiological analysis system called PegaSUS. For the purposes of this implementation, PegaSUS is relevant only in that (a) this module is the data-acquisition layer beneath it, and (b) PegaSUS already contains a spatial-adjacency/graph toolkit and a demographic reconstruction module ("demographic tensor" — a municipality × year × sex × age × race population cube reconstructed from censuses plus intercensal totals), both referenced in §10. Neither is required to build this module.

### 0.3 The four problems this module exists to solve

These are the acceptance conditions. Everything in this document serves one of them.

| # | Problem | Acceptance condition |
|---|---|---|
| **P1** | DATASUS publishes **no centralized dictionary**. The meaning of variables and of coded values is scattered across `.DEF`/`.CNV` files, `TAB_*.zip` archives, PDFs, and paper notification forms — or is simply absent. Analysts routinely reconstruct code meanings ad hoc, and get them wrong. | The package ships a **dictionary + metadata ledger covering every system it can reach**, where each entry carries its own provenance and confidence, and where unknown is recorded as unknown rather than guessed. Coverage is reportable as a number. |
| **P2** | Sequential FTP I/O against a slow server dominates wall-clock time; naive implementations take days for what should take hours. | Discovery, acquisition, and decoding are concurrent; the pipeline is resumable and content-addressed, so nothing is fetched twice, ever. |
| **P3** | Raw DATASUS is a storage bomb — `.dbc` inflates several-fold on decode, is row-oriented, and has no post-decode compression. Naive normalization is slower than the download it follows. | Canonical persistence is **Parquet**, partitioned; normalization is parallel and vectorized; raw is retained only under an explicit toggle. |
| **P4** | Coverage gaps hide **whole systems** and **whole schema generations** behind file-format differences. A pipeline that profiles only `.dbc` misses entire information systems and, worse, misses schema variants that live in a different container. | Discovery and profiling are **format-agnostic and schema-first**. A system is never excluded by file extension; a schema variant is never missed because it lives in a different container. |

### 0.4 Marker convention used throughout

- `[M]` **Measured** — verified by query against `datasus_compendium.sqlite` (§1.1). Reproducible.
- `[D]` **Derived** — logical or statistical consequence of something marked `[M]`.
- `[V]` **To verify** — a gap, with the verification procedure attached. **Never promote a `[V]` to a design assumption without running the stated check.** Where a `[V]` is unresolved, the code must record it as an open question in the ledger rather than pick a plausible answer.

This convention is not decoration. The project it feeds is going to a federal ministry, and a claim that cannot state its own provenance is worse than an absent claim.

---

## 1. Input artifacts the implementer will be given

### 1.1 `datasus_compendium.sqlite` — a prior full scan of the FTP tree

An existing artifact produced by a previous, partially-defective scan of `ftp.datasus.gov.br/dissemin/publicos`. **It is evidence, not code.** Every `[M]` marker in this document is a query against it. Use it to plan, to sanity-check the new implementation, and to regression-test: the new pipeline must reproduce everything true in it and fix everything listed in §2.

Headline counts: **124,810 files · 233 inferred families · 12,487 variable profiles · 104,084 value frequencies · 66 warnings.**

Tables and columns:

```
families (233)
  family_id, system_guess, series_prefix, partition_type, date_format,
  time_min, time_max, time_range_display, file_count, member_files,
  source_paths, geo_coverage, format_families, primary_extensions,
  path_types, warnings

inventory_files (124810)
  path, directory, filename, extension, primary_extension, format_family,
  system_guess, series_prefix, geo_code, date_code, date_format,
  normalized_date, path_type, size, modified

variable_profiles (12487)
  family_id, ftp_path, field_name, physical_type, width, decimal_count,
  non_null_count, null_count, missingness_percent, distinct_count,
  distinct_ratio, primitive_type, semantic_guess, semantic_confidence,
  min_value, max_value, mean_value, std_value, p01, p05, p25, p50, p75,
  p95, p99, min_date, max_date, parse_rate_numeric, parse_rate_date,
  ibge_municipality_rate, icd10_rate, warnings

value_frequencies (104084)
  family_id, ftp_path, field_name, value, count, percent, rank

schema_presence (12487)
  family_id, ftp_path, schema_signature, field_name, field_order

schema_drift (233)
  family_id, profiled_file_count, successful_file_count,
  schema_signature_count, schema_signatures, union_field_count,
  always_present_field_count, sometimes_present_field_count,
  always_present_fields, sometimes_present_fields, drift_flag

table_profiles (253)
  family_id, ftp_path, local_path, file_format, file_size,
  row_count_profiled, row_limit_reached, column_count, field_names,
  schema_signature, read_success, warnings

sample_plan (233)      family_id, ftp_path, reason, local_path, size, extension
warnings (66)          stage, path, family_id, message, detail
scan_summary (1)       host, base_path, selected_method, directories_scanned,
                       entries_written, files, directories, started_at,
                       finished_at, warnings
listing_benchmark (6)  directory, method, ok, elapsed_ms, row_count,
                       typed_count, file_count, dir_count, error
```

**Known unreliable columns in this artifact:** `inventory_files.size` and `.modified` are NULL in all 124,810 rows (see D4). `schema_drift.drift_flag` is `False` in all 233 rows but this is an artifact of n=1 sampling, not evidence of stability (see D2). `variable_profiles.icd10_rate` has systematic false positives (see D5).

### 1.2 `source.zip` — the prior scanner implementation

The Python package `datasus_compendium`, ~2,225 LOC, that produced the sqlite above. Modules: `ftp_scan.py` (425), `profiler.py` (445), `inventory.py` (309), `readers.py` (298), `artifacts.py` (213), `main.py` (150), `models.py` (142), `io_utils.py` (102), `sampling.py` (76), `download.py` (62).

**It is the correct skeleton and should be absorbed, not discarded.** Specifically reusable with little change: the FTP protocol benchmarking and per-method dispatch in `ftp_scan.py`; the threaded directory-queue crawler; the per-field streaming accumulator in `profiler.py` (`FieldAccumulator`); the JSONL/CSV/SQLite artifact writer; the DBF/DBC reader wrappers. The seven defects in §2 are what must be redesigned.

Dependencies it declares: `dbfread>=2.0.7`, `datasus-dbc>=0.1.0`, optional `pyarrow`.

---

## 2. The seven measured defects to design out

These are the concrete reasons a rewrite is warranted rather than a patch. Each one is measured, and each one produces a design rule.

### D1 — Whole systems dropped by an extension heuristic `[M]`

`inventory.py::AUX_HINTS` contains the string `"exe"`; `path_type()` returns `"Auxiliary"` for any path matching a hint; `build_families()` keeps only rows where `path_type == "Data"`.

Measured consequence: **1,724 `.exe` files exist in the tree, and 1,723 of them are `/dissemin/publicos/SIASUS/APAC/{2001..2007}`** — 324 + 324 + 297 + 275 + 266 + 129 + 108 files, named like `ACAC0202.EXE`, `ACTO0712.EXE`. These are DATASUS **self-extracting archives**, a common convention on this server. All were classified `Auxiliary`. All were dropped. **The entire APAC series never entered the compendium** — and APAC is the only public data with a patient-anchored longitudinal trail (dialysis, nephrology, high-cost medication).

Also dropped or unhandled by extension: `.rar` (4 files, including `TAB_SISCAN.rar` and `TABWIN_SISCAN.rar` — both dictionary kits), `.duck` (66 loose files plus 12 `.duck.zip` = 78 total `[M]`, including 11 APAC DuckDB databases).

> **Design rule.** Container format must never determine inclusion. Classification is by **probe result**, not by suffix: attempt to open the file; if a tabular payload is recovered, it is data. The extension is a hint that *orders the probe attempts* and nothing more.

### D2 — Schema conclusions drawn from n = 1 `[M]`

`sample_plan` contains exactly **233 rows — one per family**. The `reason` distribution is `earliest` 109, `first_undated` 94, remainder mixed. Therefore `schema_drift.drift_flag = False` across all 233 families is **absence of measurement**, not evidence of stability: with one file per family, drift is undetectable by construction.

Worked case: family `SIHSUS_RD_cc57a5d875` spans **1992-01 → 2026-05 across 12,101 files** and was characterized from `RDAC9201.dbc` — Acre, January 1992, **35 columns**. The 113-column modern schema only surfaced in the compendium because `RDAC2017.zip` happened to fall into a separate two-file family.

> **Design rule.** Sampling is **stratified by schema stratum**, not by family. The stratum key is `(system, series, year)` — schema is a serialization of a national paper form, so it varies with time and system, not with state or month. Profile one file per stratum, then merge strata that share a field signature. Report drift only where n ≥ 2; where n = 1, report `insufficient_evidence`, never `stable`.

### D3 — Families keyed by format, so one dataset becomes many `[M]`

The grouping key in `build_families()` is `(system_guess, series_prefix, date_format, format_family)` — format is inside the key.

Measured consequence in SIHSUS alone: `200801_/Dados` `.dbc` (22,693 files), `DBF/` `.dbf` (2,078), `XML/` `.xml` (2,076), `2008/CSV` `.csv` (324), plus per-year XML directories for 2008–2014. **The same AIH records are published four ways**, landing in four families, inviting silent quadruplication in any downstream aggregation.

> **Design rule.** The family key is `(system, series, schema_signature)`. Format becomes an attribute — a *representation* of the family, ranked by decode cost. Two files with the same logical content in different containers are the same family, with one representation chosen as the preferred read path. This is also what makes P4 structurally satisfied: identical fields collapse into one family, and differing fields cannot.

### D4 — Protocol choice destroyed change detection `[M]`

`scan_summary.selected_method` resolved to NLST — the FTP listing command that returns bare filenames with no metadata. Consequence: `inventory_files.size` is NULL for **124,810 of 124,810** rows, and `modified` likewise. No size, no mtime, therefore no cheap incremental sync — and DATASUS silently republishes old competências, so incremental sync is not optional for a production module.

> **Design rule.** Attempt MLSD → LIST → NLST **per directory with escalation**, not once globally, and persist which method served each directory. Where typed listing is unavailable, fall back to **content addressing** (SHA-256 of the fetched payload) as the change signal.
>
> `[V]` **Probe whether the same tree is reachable over HTTPS.** If it is, prefer it: `HEAD` restores `Content-Length` and `Last-Modified` and eliminates this defect outright, and HTTP keep-alive outperforms FTP's per-transfer data channel.
> *Verification: attempt HTTPS GET/HEAD against the same paths and compare payload SHA-256 to the FTP fetch, for a sample of 20 files across 5 systems.*

### D5 — Semantic detectors are per-value regexes where the discriminator is distributional `[M]`

`profiler.py::ICD10_RE` is `^[A-TV-Z][0-9][0-9AB](?:\.?[0-9A-TV-Z]{0,4})?$`. The regex is correct. The false positives are **genuine encoding collisions**: SINAN's `NU_IDADE` field stores values like `A020`, `A021`, `A022` — DATASUS unit-prefixed age, where the letter is the unit (**A**nos / **M**eses / **D**ias / **H**oras) and the digits are the value, so `A020` = 20 years. And `A02.0` is a valid ICD-10 code (salmonellosis).

Validating against the real 14,197-row ICD-10 table would **not** fix this, because `A020` is a legitimate code. The collision is real and unresolvable per-value.

> **Design rule.** Semantic classification consumes the **whole value distribution**, not values one at a time. For this collision the separating statistics are: entropy of the first character (an age field draws from ~4 symbols; a diagnosis field from ~20), density and contiguity of the numeric tail (age tails are a dense run 0–120; diagnosis tails are sparse), and distinct count (age ≈ 100; a real `DIAG_PRINC` measured at 443 and 693 distinct values by schema generation `[M]`). Every semantic verdict must carry a confidence **and the statistics that produced it**, so a downstream consumer can re-audit the classification without re-reading the raw file.

### D6 — 32 directory listings failed and were never retried `[M]`

`warnings` table, stage `scan`: 32 failures. Including `SINASC/NOV/{DNRES,DOCS,TAB,TABELAS}`, `SINASC/1996_/TABELAS`, `SIHSUS/{Doc, 2009/CSV, 2012/XML}`, `SISCAN/{SISCOLO4,SISMAMA}/DOC`.

Note what those paths are: several of them are **dictionary and documentation directories**. The failures are concentrated precisely on the semantic layer that P1 depends on.

> **Design rule.** Per-directory retry with method escalation and bounded exponential backoff. Directories unresolved after exhaustion persist as first-class `coverage_gap` rows — not warnings — so that coverage becomes a queryable property of the artifact rather than a log line nobody reads.

### D7 — The dictionaries were never opened `[M]`

Measured inventory of the semantic layer in the tree:

- `.def` — 61 files, all under `PNI/AUXILIARES/`
- `.cnv` — 17 files, same directory
- `.pdf` — 46 files
- **`TAB_*.zip` tabulation kits — one per system:**
  `SIHSUS/200801_/Auxiliar/` · `SIHSUS/199201_200712/Auxiliar/TAB_SIH_199201-199712.zip` · `CNES/200508_/Auxiliar/TAB_CNES.zip` · `CIHA/201101_/Auxiliar/TAB_CIHA.zip` · `CIH/200801_201012/Auxiliar/TAB_CIH.zip` · `SINAN/AUXILIAR/TAB_SINANNET.zip` · `SINAN/AUXILIAR/TAB_SINANONLINE.zip` · `CMD/Auxiliar/Tab_CMD.zip` · `PCE/Auxiliar/tab_pce.zip` · `RESP/AUXILIAR/tabresp.zip` · `IBGE/Auxiliar/TAB_POP.zip` · `ESUSNOTIFICA/AUXILIAR/TAB_SINANNOTIFICA.zip` · `painel_oncologia/Auxiliar/PAINEL_ONCOLOGIA.zip` · `SISCAN/TAB_SISCAN.rar` · `CNES/200508_/VersoesAntigas/tabcnes_DEF-CNV_201412.zip`

`[D]` These archives are **TabNet tabulation kits**. TabNet is DATASUS's public tabulation web interface. A kit contains `.DEF` files — which declare, per tabulation, the available line/column/content variables and point at a `.CNV` for each — and `.CNV` files, which map raw codes to the officially published categories, plus auxiliary `.DBF` lookup tables. A prior inspection confirmed that `SIHSUS/199201_200712/Auxiliar/TAB_SIH_199201-199712.zip` contains a DBF with columns `CID10, OPC, CAT, SUBCAT, DESCR, RESTRSEXO` and **14,197 rows** — the complete ICD-10 codebook with Portuguese descriptions, sitting on the same server as the data.

**This is the officially pactuated semantic layer of Brazilian health data.** Twenty-five years of published federal statistics rest on these mappings. It is not absent — it is uncatalogued, inside archives nobody opens.

> **Design rule.** The `Auxiliar` / `AUXILIAR` / `Doc` / `DOCS` trees are a **primary ingestion target with their own parser stack**, not a byproduct. `.DEF` and `.CNV` get real parsers. This is P1's principal supply.

---

## 3. Layered architecture

Each layer has one job, a persisted output, and a stable contract with the next. Layers are independently runnable and resumable; nothing downstream re-derives what an upstream layer persisted.

```
L0  discovery      FTP/HTTPS crawl               → catalog.files, catalog.coverage_gaps
L1  inventory      parse names, infer strata     → catalog.strata, catalog.families
L2  acquisition    concurrent fetch + CAS cache  → blobs/
L3  decode         format-agnostic readers       → in-memory Arrow tables
L4  profile        distributional evidence       → catalog.variable_profiles, value_frequencies
L5  semantics      DEF/CNV/PDF/API + inference   → catalog.dictionary, catalog.ledger
L6  normalize      decode codes, canonicalize    → typed Arrow tables
L7  persist        Parquet lake + DuckDB views   → lake/
L8  denominators   POPSVS/POPTCU/censo           → lake/population/
L9  api_sources    DEMAS open-data API           → lake/demas/
L10 public API     load(), describe(), query()   → user-facing
```

### 3.1 Package layout

```
pegasus_data/
  catalog/
    schema.sql          # see §4
    store.py            # SQLite access, migrations, append-only history
  discovery/
    ftp_client.py       # protocol-adaptive, per-directory method selection  (D4)
    https_client.py     # [V] parallel path if an HTTPS mirror exists        (D4)
    crawler.py          # concurrent, resumable, coverage-gap tracking       (D6)
  inventory/
    naming.py           # filename grammar (§5.2)
    strata.py           # (system, series, year) schema strata               (D2)
    families.py         # schema-signature families, format as attribute     (D3)
  acquire/
    cache.py            # content-addressed store, sha256-keyed
    fetcher.py          # bounded-concurrency fetch, retry, resume
  decode/
    registry.py         # probe-ordered reader dispatch                      (D1)
    dbc.py dbf.py csv_.py json_.py xml_.py parquet_.py xlsx_.py
    archives.py         # zip, gz, rar, and SELF-EXTRACTING .exe             (D1)
    duckdb_.py          # .duck and .duck.zip                                (D1)
  profile/
    accumulators.py     # per-field streaming stats (port FieldAccumulator)
    detectors.py        # distributional semantic detectors                  (D5)
    drift.py            # schema comparison across strata                    (D2)
  semantics/
    def_parser.py       # TabNet .DEF grammar                                (D7)
    cnv_parser.py       # TabNet .CNV grammar                                (D7)
    tabkit.py           # TAB_*.zip / .rar unpack, link members to families  (D7)
    pdf_harvest.py      # dictionary PDFs → candidate field definitions
    dictionary.py       # merge, reconcile, confidence, provenance
    ledger.py           # the metadata ledger (§6.1)
  normalize/
    codecs.py           # code → label application
    types.py            # canonical dtypes
    geo.py              # município 6↔7 digit, validity intervals
    time.py             # competência, epidemiological week, epi year
    engine.py           # parallel, chunked, vectorized
  persist/
    lake.py             # Parquet layout, partitioning, compaction
    duck.py             # DuckDB view registration
  sources/
    datasus_ftp.py
    demas_api.py        # apidadosabertos.saude.gov.br                       (§11)
    ibge.py             # POPSVS / POPTCU / censo                            (§10)
  api.py                # public surface (§9)
  cli.py                # command surface (§8)
```

---

## 4. The catalog

A single SQLite database, versioned, shipped alongside the lake. It is the module's memory: everything discovered, decided, or left open lives here.

Core tables, as DDL sketch (extend freely; these are the required columns):

```sql
CREATE TABLE files (
  path TEXT PRIMARY KEY, directory TEXT, filename TEXT,
  extension TEXT, size INTEGER, modified TEXT,
  listing_method TEXT,             -- which FTP verb served this row  (D4)
  change_signal TEXT,              -- 'mtime' | 'size' | 'content_hash'
  first_seen TEXT, last_seen TEXT
);

CREATE TABLE coverage_gaps (       -- D6: unreachable paths are data, not logs
  path TEXT PRIMARY KEY, attempts INTEGER, methods_tried TEXT,
  last_error TEXT, last_attempt TEXT, resolved INTEGER DEFAULT 0
);

CREATE TABLE strata (              -- D2: unit of schema sampling
  stratum_id TEXT PRIMARY KEY, system TEXT, series TEXT, year INTEGER,
  file_count INTEGER, sampled_path TEXT, schema_signature TEXT
);

CREATE TABLE families (            -- D3: keyed by schema, not format
  family_id TEXT PRIMARY KEY, system TEXT, series TEXT,
  schema_signature TEXT, field_count INTEGER,
  time_min INTEGER, time_max INTEGER, geo_coverage TEXT, file_count INTEGER
);

CREATE TABLE representations (     -- D3: same family, different containers
  family_id TEXT, container_format TEXT, path_glob TEXT,
  file_count INTEGER, decode_cost_rank INTEGER, reader TEXT,
  PRIMARY KEY (family_id, container_format)
);

CREATE TABLE blobs (
  sha256 TEXT PRIMARY KEY, byte_size INTEGER, fetched_at TEXT,
  source_path TEXT, serving_method TEXT
);

CREATE TABLE variable_profiles (   -- superset of the prior artifact's columns
  family_id TEXT, field_name TEXT, schema_signature TEXT,
  physical_type TEXT, width INTEGER, decimals INTEGER,
  non_null INTEGER, nulls INTEGER, distinct_count INTEGER,
  semantic_type TEXT, semantic_confidence REAL, semantic_evidence TEXT,
  stats_json TEXT,
  PRIMARY KEY (family_id, field_name, schema_signature)
);

CREATE TABLE value_frequencies (
  family_id TEXT, field_name TEXT, schema_signature TEXT,
  value TEXT, count INTEGER, percent REAL, rank INTEGER
);

CREATE TABLE dictionary (          -- §6.1
  system TEXT, family_id TEXT, field_name TEXT, schema_signature_scope TEXT,
  value_raw TEXT, value_label TEXT, value_group TEXT,
  source TEXT, source_ref TEXT, confidence REAL,
  valid_from TEXT, valid_to TEXT
);

CREATE TABLE dictionary_conflicts ( -- disagreement is a finding, not an error
  system TEXT, field_name TEXT, value_raw TEXT,
  claim_a TEXT, source_a TEXT, claim_b TEXT, source_b TEXT, noted_at TEXT
);

CREATE TABLE ledger (              -- §6.1
  system TEXT, family_id TEXT, field_name TEXT, schema_signature_scope TEXT,
  semantic_type TEXT, semantic_confidence REAL, semantic_evidence TEXT,
  unit TEXT, aggregation TEXT,     -- 'additive' | 'mean' | 'non_summable'
  first_seen INTEGER, last_seen INTEGER,
  dictionary_coverage REAL,        -- THE headline metric  (§6.2)
  provenance TEXT, open_questions TEXT,
  PRIMARY KEY (system, family_id, field_name, schema_signature_scope)
);

CREATE TABLE open_questions (      -- every [V] the pipeline could not close
  id INTEGER PRIMARY KEY, area TEXT, question TEXT,
  verification_procedure TEXT, blocking TEXT, status TEXT, noted_at TEXT
);
```

---

## 5. L0–L1 — Discovery, naming, strata, families

### 5.1 Crawl

Connection: `ftp.datasus.gov.br`, anonymous login, passive mode, base path `/dissemin/publicos`.

Concurrency model: bounded worker pool, one FTP control connection per worker, shared work queue of directories, deduplicated by normalized path. This is already correct in the prior `ftp_scan.py` and carries over directly. Changes required:

- Per-directory method escalation with persistence of which verb served each directory (D4).
- Failed listings enter a retry queue with bounded exponential backoff; after exhaustion they persist as `coverage_gaps` rows (D6).
- Record `size` and `modified` whenever the serving method provides them; otherwise set `change_signal = 'content_hash'`.
- `[V]` HTTPS probe per D4.

**Operational constraints of this server, observed:** it is slow and it drops connections. Transient failures are normal, not exceptional — the prior scan lost files to them. Therefore: every network operation is retried; the crawl is resumable from the catalog at any point; a worker whose connection dies reconnects rather than aborting; and a sane per-host connection budget (start at 8, tune empirically) avoids being throttled.

### 5.2 Filename grammar

DATASUS's classic convention is `PREFIX + GEO + DATE`, e.g. `RDAL2401.dbc` = SIH reduced file, Alagoas, competência 2024-01. The prior `PATTERNS` list is close and should be carried over. Two hazards must be handled explicitly:

- **Date ambiguity `[M]`.** `DOAL2001` is SIM, year 2001. `RDAL2001` is SIH, competência 2020-01. **Undecidable from the filename alone.** Decidable at directory level: a monthly convention yields ~12 distinct tails sharing a leading pair; an annual convention yields exactly one. **Infer the convention per directory, then apply it to that directory's members.** Never decide per file.
- **Geo token.** The closed set is `BR` plus the 26 state abbreviations plus `DF`. Reject any parse whose geo token is outside it (the prior code does this — keep it).

Extend the grammar beyond the classic convention. Measured: **82 of 233 families are `DADOS_ABERTOS_UNPARSED_*`** `[M]` — the `Dados_Abertos` subtree uses descriptive filenames and needs its own naming module rather than being forced through the classic pattern.

### 5.3 Strata, families, representations

```
stratum        := (system, series, year)                 # unit of schema sampling   (D2)
family         := (system, series, schema_signature)     # unit of logical dataset   (D3)
representation := (family, container_format, path_glob)  # how to physically read it (D3)
```

`schema_signature` = stable hash of the ordered field-name list.

**Crucially, families are discovered *after* profiling one file per stratum, not before.** This inverts the prior order and is what makes schema generations visible.

Regression target the new implementation must reproduce `[M]`: SIH-RD resolves to **three generations — 35 columns (1992), 86 columns (2008–2014, has `DIAG_SECUN`), 113 columns (2017+, has `DIAGSEC1..9` and *no* `DIAG_SECUN`)**. The rename is a silent trap: a query asking for `DIAG_SECUN` against a 2020 file returns empty with no error.

---

## 6. L2–L5 — Acquisition, decoding, and the semantic layer

### 6.1 Content-addressed cache

Every fetched byte-string is stored at `blobs/sha256/<hash>` with a catalog row recording source path, fetch time, and serving method. A logical path maps to one or more blob hashes over time — this **is** the change-detection mechanism when the protocol gives no mtime (D4), and it deduplicates for free across the multi-format republication measured in D3.

### 6.2 Reader dispatch by probe, not by suffix (D1)

```
open(path):
    candidates = readers_ordered_by_suffix_hint(path)
    for reader in candidates:
        try:  return reader(path)     # → (field_metadata[], RecordBatch iterator)
        except: continue
    record as undecodable, with all attempts logged
```

Readers required beyond the prior set:

- **Self-extracting `.exe`.** DATASUS `AC*.EXE` APAC archives. These are a PE stub with a standard archive appended. Strategy, in order: Python `zipfile` directly (`ZipFile` locates the central directory by scanning back from EOF and tolerates a prepended stub), then `rarfile`, then `7z` via subprocess, then a raw signature scan for `PK\x03\x04` and `Rar!\x1a\x07`.
  `[V]` Confirm against `/dissemin/publicos/SIASUS/APAC/2002/ACAC0202.EXE`. Expected payload: one or more `.dbc` or `.dbf`. **This single reader recovers 1,723 files and an entire information system.**
- **`.duck` and `.duck.zip`.** 78 files `[M]`, including 11 APAC DuckDB databases under `Dados_Abertos/APAC_SIA/` (`apac_atd` dialysis, `apac_an` nephrology, `apac_acf` fistula, `apac_am` medication, `apac_ab` bariatric, and others) plus 66 under `Dados_Abertos/BackUp_Ducks_SIASUS_PA/`. Open with `duckdb`, enumerate via `information_schema.tables`, export each table to Arrow.
  `[V]` These may be written by a newer DuckDB storage version than the installed library. Pin and record the version; treat a version error as an open question, not a hard failure.
- **`.rar`.** 4 files, all dictionary kits (D7).
- **Nested archives returning *all* members.** A `TAB_*.zip` contains `.DEF`, `.CNV`, and `.DBF` simultaneously. The prior `choose_archive_member()` picks a single best member and discards the rest — correct for data files, **wrong for dictionary kits**. The archive reader must return every member with its inferred role.

Every reader returns the same contract: `(field_metadata[], RecordBatch iterator)`, Arrow-native. `field_metadata` carries physical type, width, and decimals where the container declares them — DBF does, CSV does not. That declared metadata is real signal for the semantic layer and must not be discarded.

### 6.3 The semantic layer — P1, the core deliverable

Two artifacts.

**Dictionary** — per `(system, family, field, value)`: what a coded value means.

```
system, family_id, field_name, schema_signature_scope,
value_raw            e.g. "1"
value_label          e.g. "Masculino"
value_group          optional roll-up, e.g. the ICSAP group a CID belongs to
source               'cnv' | 'def' | 'dbf_lookup' | 'pdf' | 'demas_api' | 'inferred' | 'manual'
source_ref           exact file path + archive member + line, or URL
confidence           [0,1]
valid_from, valid_to semantics change over time; entries are versioned
```

**Ledger** — per `(system, family, field)`: what the variable *is*. Columns as in §4, with two worth calling out:

- `aggregation` ∈ `additive | mean | non_summable`. This carries the rule that **counts may be summed across cells and rates may not** — the rate of two municipalities combined is not the mean of their rates, it is the summed numerator over the summed denominator. Downstream systems read this field to refuse illegal aggregations.
- `dictionary_coverage` — the fraction of observed values in that field that have a dictionary entry. **This is the headline metric of the whole module**: it turns "DATASUS has no dictionary" from a complaint into a number that goes up as work proceeds, reportable per system and per field.

**Supply chain, highest authority first:**

1. **`.CNV` files** — TabNet's code→category maps. `[V]` Learn the grammar empirically from the 17 uncompressed files under `PNI/AUXILIARES/` (cheapest place to start), then generalize to kit members. Expected shape: a header line giving the category count, then fixed-width records of sequence / label / matched-code expression, where the expression may be a single code, a comma-separated list, or a range. **Ranges and lists must both be expanded** into individual dictionary rows.
2. **`.DEF` files** — declare, per tabulation, which variables exist, their official display names, and which `.CNV` decodes each. This is the only artifact that states *what a column is officially called*. 61 files uncompressed `[M]`, plus kit members.
3. **`.DBF` lookup tables inside kits** — the 14,197-row ICD-10 table, CNES establishment-type tables, procedure tables `[V]`.
4. **Dictionary PDFs** — 46 files `[M]`. Text extraction → candidate field definitions, held at lower confidence, never overriding `.CNV`/`.DEF`.
5. **DEMAS API metadata** (§11) — the OpenAPI document is machine-readable field metadata; fetch and persist it at ingestion.
6. **Inference** (§6.4) — lowest authority, always flagged as `source='inferred'`.

**Conflicts between sources are recorded, never silently resolved** — a `dictionary_conflicts` row with both claims and both provenances. A conflict is a finding.

### 6.4 Inference, done defensibly (D5)

Detectors consume a field's full value distribution and emit `(semantic_type, confidence, evidence)`. Minimum set:

| Detector | Discriminating statistics |
|---|---|
| ICD-10 code | regex match rate **plus** first-character entropy above threshold, sparse numeric tail, distinct count ≫ 120, membership rate in the real 14,197-row CID table |
| DATASUS age | first character ∈ {A,M,D,H} at high rate, dense contiguous numeric tail, distinct ≈ 100–130 |
| Município code | 6 or 7 digits, membership in the IBGE municipality set, leading pair ∈ valid UF numeric range |
| Date | multi-format parse rate, plausible range, sentinel handling (`00000000`, `99999999`) |
| Sex / race / categorical | low cardinality **and** a matching `.CNV`. A low-cardinality field with no dictionary is reported as `categorical_undecoded` — an actionable gap, not a verdict |
| Money | name hint + continuous positive distribution + declared decimals from the DBF header |
| Procedure code | fixed-width numeric, high cardinality, membership in a procedure table `[V]` |

Every verdict stores its evidence in `semantic_evidence`.

---

## 7. L6–L8 — Normalization, storage, denominators

### 7.1 Normalization contract

Default is **normalized persistence**; raw is kept only under an explicit `keep_raw=True`.

Steps, all vectorized over Arrow arrays, never row-by-row:

1. **Type canonicalization.** DBF `C`/`N`/`D`/`L` → Arrow types using declared width and decimals.
2. **Sentinel nulling.** DATASUS missing codes (`9`, `99`, `999…`, `00000000`) are nulled **per field, driven by the ledger** — never globally. A `9` is missing in one field and a valid category in another; a global rule silently corrupts data.
3. **Code decoding.** Apply dictionary entries scoped to the field's schema signature. Emit **both** `field` (raw) and `field_label` (decoded) — nothing is destroyed, and the raw column costs almost nothing after Parquet dictionary encoding.
4. **Geo canonicalization.** IBGE municipality codes are 7 digits (the last is a check digit); DATASUS uses the same codes truncated to 6. A join by equality between the two sources matches nothing. **Primary method is a join against a reference table**; the check-digit algorithm is secondary validation only, because it fails for a known handful of municipalities and cannot resolve extinct or renamed ones. Carry validity intervals — municipalities are created and dissolved across a 35-year series.
5. **Time canonicalization.** Competência (`AAAAMM`); **epidemiological week** (Sunday-to-Saturday; week 1 is the one containing 4 January; a year has 52 **or 53** of them, so `year(date), week(date)` produces a spurious gap or spike every few years) and epidemiological year, computed once into a calendar dimension table rather than per query. Where the source already carries the official epi week (SINAN's `SEM_PRI`, `SEM_NOT`), **use the source's value; do not recompute** — diverging from the official calculation silently desynchronizes from Ministry publications.
6. **Provenance columns.** `_source_path`, `_blob_sha256`, `_ingested_at`, `_schema_signature` on every row group.

### 7.2 Parallelism (P3)

Chunk unit is the Arrow RecordBatch. Process pool for CPU-bound decode/normalize; thread pool for I/O.

**`.dbc` decompression is inherently serial within a file** — it is a stream compression over the whole payload, so a byte range cannot be decoded without inflating everything before it. Therefore parallelize **across files**, not within one. This is also the architectural reason `.dbc` is slow to query and Parquet is not: Parquet's row groups are independently decodable and its footer is a map, so a filtered read touches only the row groups that survive the predicate.

### 7.3 Lake layout

```
lake/
  <system>/<family>/
     schema_signature=<sig>/
        uf=<UF>/
           year=<YYYY>/
              part-<n>.parquet
  population/
  demas/
  _catalog/            # the SQLite catalog, dictionary, and ledger ship with the lake
```

Partition on the columns actually used as predicates — UF and year — so partition pruning eliminates whole files before any bytes are read. Within a file, row-group statistics prune further and column projection avoids reading unrequested columns at all. Compression ZSTD; dictionary encoding on for coded string columns, which is most of them and where the size collapse comes from.

DuckDB registers views over the lake so a consumer writes SQL against `sih_rd` without knowing anything about partitioning.

### 7.4 Denominators (L8)

Measured `[M]`:

| Series | Path | Coverage | Fields | Age standardization |
|---|---|---|---|---|
| **POPSVS** | `IBGE/POPSVS/` (26 files) | 2000–2025 | `COD_MUN, ANO, SEXO, IDADE, POP` | **Yes** |
| POPTCU | `IBGE/POPTCU/` (33 files) | 1992–2025 | `MUNIC_RES, ANO, POPULACAO` | No — no age, no sex |
| POP | `IBGE/POP/` (33 files) | 1980–2012 | legacy | — |
| projpop | `IBGE/projpop/` (71 files) | — | projections | `[V]` unexamined |
| censo | `IBGE/censo/` | 1991, 2000, 2010 | `ALF`, `ESCA`, `ESCB`, `IDOSO`, `RENDA` by município × race × sex × urban/rural | covariates, not denominators |

Ingest all of them into `lake/population/`, each tagged with its authority and its supported stratifications, behind one interface so a consumer can swap series and see the difference. PegaSUS's demographic tensor plugs in as an additional series with the same interface, not as a replacement — validating against Ministry-published rates requires using the Ministry's own denominator.

`[V]` Determine which series the Ministry actually uses to publish its own rates.

---

## 8. Command-line surface

```
pegasus-data crawl        [--host] [--base-path] [--connections N] [--resume]
pegasus-data inventory    # parse names, build strata, no network
pegasus-data sample       # choose one file per stratum
pegasus-data fetch        [--strata|--family|--system] [--concurrency N]
pegasus-data profile      [--family|--system]
pegasus-data semantics    # ingest TAB kits, parse DEF/CNV, build dictionary+ledger
pegasus-data normalize    [--system] [--uf] [--years]
pegasus-data build        [--system] [--uf] [--years]   # normalize + write lake
pegasus-data report       # coverage, dictionary_coverage, open questions
pegasus-data verify       # run the regression assertions in §12
```

Every command is resumable and idempotent. Every command writes to the catalog before returning.

---

## 9. Public API

```python
from pegasus_data import Catalog, load, describe, load_population

cat = Catalog()                              # opens the shipped catalog
cat.systems()                                # what exists
cat.families(system="SIHSUS")
cat.coverage("SIHSUS", "RD")                 # span, UFs, schema generations, gaps

describe("SIHSUS", "RD", field="DIAG_PRINC")
# → ledger entry + dictionary coverage + top values WITH labels + provenance
#   This is the module's user-facing face: the answer to "what is this variable
#   and what do its values mean", which DATASUS does not provide anywhere.

df = load("SIHSUS", "RD",
          uf="AL", years=range(2015, 2025),
          columns=["MUNIC_RES","DIAG_PRINC","IDENT","IDADE","SEXO",
                   "MORTE","DIAS_PERM","VAL_TOT"],
          labels=True)                       # decoded via the dictionary

pop = load_population(series="POPSVS", uf="AL", years=..., by=["idade","sexo"])
```

---

## 10. Environment

- Python ≥ 3.11.
- Core: `pyarrow`, `duckdb`, `dbfread`, `datasus-dbc`, `httpx` (async), `rarfile`, `pypdf` or `pdfplumber`, `polars` optional for normalization throughput.
- System: `7z` available on PATH as an archive fallback.
- No credentials required for any source in this document. All data is public and anonymous-access.

---

## 11. Secondary source — the DEMAS open-data API

Base: `https://apidadosabertos.saude.gov.br`. OpenAPI document at `/static/swagger.json` — **fetch and persist it at ingestion time**; it is machine-readable field metadata and feeds the ledger at higher confidence than PDF harvesting.

This is a REST wrapper maintained by DEMAS (the Ministry department responsible for information dissemination) over bases the FTP tree does not carry. It is not a substitute for the FTP microdata — most endpoints serve pre-aggregated data — but it is the only public access to several domains.

Endpoints that matter, and why:

| Endpoint | Why |
|---|---|
| `/daf/estoque-medicamentos-bnafar-horus` | **Medication stock (BNAFAR/Hórus).** The only face that can see a chronic patient *before* decompensation — insulin, metformin. Nothing equivalent exists on the FTP. `[V]` granularity: municipal? monthly? does it carry medication identity? |
| `/atencao-primaria/cadastro-vinculado-programa-previne-brasil` | Municipal counts of patients **registered** in primary care. Because registration is tied to federal funding, this is the closest thing to a municipal chronic-disease denominator that exists in Brazil. `[V]` does the payload break out by condition? |
| `/atencao-primaria/indicador-desempenho-programa-previne-brasil` | Primary-care performance indicators, including diabetes follow-up. `[V]` the Previne Brasil programme was superseded — confirm which indicator set is current. |
| `/macrorregiao-e-regiao-de-saude/municipio` | Official município → região de saúde crosswalk. **Região de saúde** is the official planning unit above municipality, and is the level at which small-count indicators stop being noise. There is no clean copy of this crosswalk on the FTP. |
| `/assistencia-a-saude/hospitais-e-leitos` | Beds and facility contacts; corroborates CNES. |
| `/sisvan/estado-nutricional` | Nutritional status by municipality — obesity proxy, a covariate for chronic-disease burden. |
| `/vigilancia-e-meio-ambiente/sistema-de-informacao-sobre-mortalidade`, `/…-nascidos-vivos` | SIM/SINASC mirrors — independent check on our own FTP-derived aggregates. |
| `/arboviroses/{dengue,chikungunya,zikavirus}` | Aggregated by year and município. **Not** a substitute for SINAN microdata (no symptom-onset date, so no nowcasting), but a cross-validation target. |
| `/sisagua/*`, `/vacinacao/*`, `/saude-indigena/*`, `/economia-da-saude/*` | Out of immediate scope; ingest opportunistically. |

**Design rule.** The API adapter is a *source*, not a special case: it lands in the same lake, with the same ledger and dictionary treatment. Where the API and the FTP cover the same base, ingest both and produce a reconciliation report — divergence between them is itself a finding worth publishing.

---

## 12. Build order, with regression assertions

Ordered so each step produces something usable and unblocks the next. Each carries a check that must pass before moving on.

| # | Step | Assertion that must pass |
|---|---|---|
| 1 | Catalog schema + content-addressed blob cache | A file fetched twice produces one blob; the catalog records both fetches |
| 2 | Crawler with per-directory method escalation and coverage gaps (D4, D6) | Re-crawl reproduces ≥ 124,810 files; some of the 32 known gaps resolve; every gap that remains is a `coverage_gaps` row |
| 3 | Archive / `.exe` / `.duck` readers (D1) | **`SIASUS/APAC/2001–2007` appears as a family with a real schema.** ≥ 1,700 previously-dropped files enter the inventory |
| 4 | Stratified sampling + schema-signature families (D2, D3) | **SIH-RD resolves to exactly its three known generations (35 / 86 / 113 columns).** The multi-format SIH republication collapses into single families with multiple representations, not four families |
| 5 | `.CNV` / `.DEF` parsers, TAB kit ingestion (D7) | `dictionary_coverage` is reported per system. SIH `DIAG_PRINC` is fully covered by the 14,197-row CID table. `SEXO`, `RACA_COR`, `IDENT` decode from `.CNV` |
| 6 | Distributional detectors (D5) | `NU_IDADE` is **no longer** classified as ICD; `DIAG_PRINC` still **is**; both carry stored evidence |
| 7 | Normalization + Parquet lake (P3) | A full-series SIH-RD for one state is queryable in DuckDB with decoded labels, at a small fraction of the raw footprint |
| 8 | Population ingestion | POPSVS loads with age × sex; POPTCU loads and is flagged as unusable for standardization |
| 9 | DEMAS API adapter | Swagger persisted; at least the crosswalk and one health endpoint land in the lake |
| 10 | Public API + `describe()` | `describe("SIHSUS","RD",field="DIAG_PRINC")` returns labels, coverage, and provenance |

Steps 1–7 are the module. Steps 8–10 make it usable by others without reading the source.

---

## 13. Prohibitions

Things that will silently ruin the artifact and must not be done:

- **Never guess a code's meaning.** An unmapped value is `categorical_undecoded` with a dictionary-coverage penalty. A plausible guess with no provenance is worse than a gap, because it is invisible downstream.
- **Never apply a global sentinel rule.** `9` is missing in some fields and a valid category in others. Sentinel handling is ledger-driven, per field.
- **Never let a missing column pass silently.** A query for `DIAG_SECUN` against a 2017+ file must **raise**, not return empty. The empty result looks legitimate and is the single easiest way to publish a wrong number.
- **Never exclude a file by extension.** See D1: that is how an entire information system disappeared.
- **Never report `stable` where n = 1.** Report `insufficient_evidence`.
- **Never recompute a value the source publishes officially** (epidemiological week being the canonical case).
- **Never discard the raw value when writing a decoded label.** Keep both columns.
- **Never resolve a source conflict silently.** Record both claims.

---

## 14. Consolidated `[V]` list

Each is a concrete check, not an opinion. Record every one in the `open_questions` table with its verification procedure, and close them as they resolve.

1. **HTTPS mirror.** Does `https://` serve the same tree? Compare payload SHA-256 for 20 files across 5 systems. *Payoff: restores size and mtime, eliminates D4.*
2. **Self-extracting `.exe` payload.** Unpack `SIASUS/APAC/2002/ACAC0202.EXE`. *Payoff: recovers 1,723 files and the entire APAC system.*
3. **`.CNV` and `.DEF` grammar.** Learn from the 78 uncompressed files under `PNI/AUXILIARES/`, then generalize to kit members. *Payoff: the entire semantic layer, i.e. P1.*
4. **`TAB_*.zip` contents per system.** Enumerate members of all ~15 kits; catalogue which lookup tables exist in each. *Payoff: procedure tables, establishment tables, ICD tables.*
5. **Procedure code table (SIGTAP).** Determine whether a procedure code table is present inside any kit, or whether SIGTAP must be sourced separately from `sigtap.datasus.gov.br` or elsewhere. **Do not assume either way.** *Blocks the amputation and dialysis signals in the companion research plan.*
6. **`.duck` storage version.** Can the installed DuckDB open `Dados_Abertos/APAC_SIA/apac_atd.duck.zip`? If not, which version wrote it?
7. **`IBGE/projpop/`** — 71 unexamined files. What are they? Do they supersede POPSVS for projected age structures?
8. **Ministry's own denominator.** Which population series backs published federal rates?
9. **DEMAS endpoint granularities** — specifically BNAFAR/Hórus, Previne cadastro, and Previne indicators (§11).
10. **`Dados_Abertos` naming grammar** — 82 families currently `UNPARSED`.
11. **Remaining coverage gaps** — the 32 failed directories, several of which are dictionary directories (D6).
