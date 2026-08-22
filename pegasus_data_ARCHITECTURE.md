# `pegasus_data` — Architecture

**Status: as built.** This document described a system to be built. It now
describes one that exists, and §19 records every place where what was built
departs from what was asked, and why. Where the original brief was factually
wrong about DATASUS, the code follows DATASUS and this document says so.

Measured state of the shipped catalog is in §21. Nothing in this document is a
target; every number in it was counted.

---

## 0. Orientation

### 0.1 What Brazil's public health data actually is

DATASUS publishes the administrative record of Brazil's public health system —
every hospital admission, every outpatient procedure, every death, every live
birth, every notifiable disease — as flat files on an FTP server, in formats
ranging from 1990s compressed dBase to modern CSV, with no machine-readable
schema, no data dictionary that a program can consume, and no stable contract
about where anything lives.

The data itself is extraordinary: 35 years of national-scale individual records.
The distribution is not. A value like `SEXO = 3` means *Feminino* in SIHSUS and
nothing at all in SINASC, and the only statement of that fact is a `.CNV` file
written for a DOS tabulation program called TabNet, sitting in a sibling
directory, occasionally inside a `.zip` inside a self-extracting `.exe`.

### 0.2 What this module is

A Python package that turns that tree into a queryable, self-describing, typed
data lake — and, equally, into a **documented** one: for each variable, what it
is called, what its values mean, where that meaning came from, and how confident
that claim is.

Two ways in, by how much the caller already has:

```python
from pegasus_data import fetch, load, describe

fetch("SIH-RD", uf="AL", years=2023)      # nothing local. Go and get it.
load("SIHSUS", "RD", uf="AL", years=2023)  # read a lake already built
describe("SIHSUS", "RD", field="DIAG_PRINC")
```

### 0.3 The four problems it exists to solve

- **P1 — Meaning.** Codes are meaningless without their codelists, and the
  codelists are in a format nobody parses. This is the core deliverable.
- **P2 — Coverage.** Nothing may be dropped silently. A file that cannot be read
  is a recorded gap, not an absence.
- **P3 — Scale.** 207,251 files, 183 GiB. Everything is resumable, concurrent
  and incremental.
- **P4 — Honesty.** Every claim carries a source and a confidence. A guess with
  no provenance is worse than a gap, because a gap is visible.

### 0.4 Marker convention

`[M]` a measured fact, counted against the live tree. `[V]` an open question with
a stated verification procedure, recorded in `open_questions`. `[D]` a departure
from the original brief, recorded in §19.

---

## 1. Input artifacts (historical)

The build began from `datasus_compendium.sqlite`, a prior full scan, and
`source.zip`, the scanner that produced it. Both were treated as **evidence
about a previous attempt, never as ground truth about DATASUS** — a rule that
paid for itself immediately: the prior scan reported 124,810 files where a
correct crawl finds 207,251 (§21, and `docs/FINDINGS.md` §0 for the mechanism).

Neither artifact is a dependency of the shipped package.

---

## 2. The seven measured defects, and what became of them

These were counted in the prior scan. Each is now either designed out or
explicitly still open.

| | Defect | Resolution |
|---|---|---|
| **D1** | Whole systems dropped by an extension heuristic | **Closed.** Readers dispatch by content probe, not suffix (§6.2). The self-extracting `.exe` archives are unpacked; APAC is recovered. |
| **D2** | Schema conclusions drawn from *n* = 1 | **Closed differently.** The brief asked for better sampling. The header census reads *every* stratum's schema instead (§6.5) `[D]`. |
| **D3** | Families keyed by format, so one dataset became many | **Closed.** `family := (system, series, schema_signature)`; container format is an attribute (§5.3). |
| **D4** | Protocol choice destroyed change detection | **Closed.** Per-directory listing-method selection preserves size and mtime; the method used is recorded per row. |
| **D5** | Semantic detectors were per-value regexes | **Closed.** Detectors are distributional and evidence-bearing (§6.4). |
| **D6** | 32 directory listings failed and were never retried | **Closed.** `coverage_gaps` is a table, retried on `--resume`, and asserted on in `verify`. |
| **D7** | The dictionaries were never opened | **Closed. This was the whole of P1.** `.CNV`, `.DEF` and the `TAB_*.zip` kits are parsed; 19.9M dictionary rows (§6.3). |

---

## 3. Layered architecture

Each layer has one job, a persisted output, and a stable contract with the next.
Every layer is independently runnable, resumable and idempotent; nothing
downstream re-derives what an upstream layer persisted.

```
L0   discovery      FTP crawl, listing-method selection    → files, coverage_gaps
L1   inventory      filename grammar, strata, families     → file_facts, strata, families
L2   acquisition    concurrent fetch, content-addressed    → blobs/
L3   decode         probe-ordered readers                  → in-memory Arrow tables
L3.5 census         schemas from file headers alone        → schema_header_facts   [D]
L4   profile        distributional evidence                → variable_profiles, value_frequencies
L5   semantics      CNV/DEF/kits/SIGTAP/PDF/community      → dictionary, field_codelists, ledger
L5.5 curation       human assertions, outranking all       → variable_docs, dataset_docs  [D]
L6   normalize      typing, sentinels, geography, time     → typed Arrow tables
L7   persist        Parquet lake, reference tables         → lake/
L8   denominators   POPSVS/POPTCU/censo                    → lake/population/
L9   api_sources    DEMAS open-data API                    → lake/demas/
L10  view           read-time labelling, render profiles   → user-facing tables    [D]
L11  public API     fetch(), load(), describe(), export()  → user-facing
```

Three layers are additions to the brief and are marked `[D]`; each is argued in
§19.

### 3.1 Package layout, as built

```
pegasus_data/
  catalog/
    schema.sql            45 tables (§4)
    store.py              SQLite access, migration refusal, event log
  discovery/
    ftp_client.py         per-directory method selection; ranged prefix fetch
    https_client.py       mirror probe
    crawler.py            concurrent, resumable, gap-tracking
    listing.py            MLSD / LIST / NLST dialects, incl. IIS MS-DOS
    reconcile.py          moved vs gone, mass-withdrawal guard
  inventory/
    naming.py             filename grammar, per-directory date convention
    systems.py            prefix→system learned from the crawl, then held
    strata.py             (system, series, year)
    families.py           schema-signature families
    schemas.py            the header census
    build.py              the inventory stage
  acquire/
    cache.py              content-addressed blob store
    fetcher.py            bounded concurrency, retry, deadlock-free drain
  decode/
    registry.py           probe-ordered dispatch
    dbc.py dbf.py text_.py duckdb_.py archives.py lha.py
    header.py             schema from a file prefix
  profile/
    accumulators.py detectors.py drift.py runner.py
  semantics/
    cnv_parser.py def_parser.py tabkit.py
    dictionary.py         merge, source authority, confidence, provenance
    reference.py icd.py gaps.py ledger.py pdf_harvest.py
    curation.py           curation/*.yml → variable_docs
  curation/
    ontology.yml          the DECLARED ontology: systems and datasets (§5.4)
    datasets.yml          what one row IS, per dataset
    datasets_sinan.yml    one entry per SINAN agravo
    systems.yml           prefix → system overrides
    variables/*.yml       per-dataset variable documentation
  normalize/
    engine.py types.py geo.py time.py
  persist/
    lake.py               Parquet layout and partitioning
    reference.py          system- and vintage-scoped code tables
    duck.py               DuckDB view registration
  sources/
    demas_api.py ibge.py sigtap.py community.py
  ontology.py             declared systems/datasets; binds observations to them (§5.4)
  _info.py                info(): what a system, dataset or variable IS (§14.5)
  compendium.py           compendium(): a portable map of DATASUS (§14.6)
  _explore.py             explore(): the shipped map of the tree (§14.1)
  _translate.py           translate(): the dictionary as a service (§14.2)
  view.py                 read-time labelling and render profiles
  retrieve.py             fetch(): one call, DATASUS to a table
  bundle.py               portable semantic bundle
  docsgen.py              docs/dictionary/*.md
  progress.py             watchdog, heartbeat, per-item deadlines
  verify.py               20 regression assertions
  api.py cli.py config.py pipeline.py build.py
```

---

## 4. The catalog

One SQLite database, 45 tables, shipped alongside the lake. It is the module's
memory: everything discovered, decided, or left open lives here. Grouped by what
they hold:

- **Discovery** — `files`, `directories`, `file_moves`, `coverage_gaps`,
  `crawl_runs`, `prefix_systems`, `system_disagreements`
- **Identity** — `file_facts`, `strata`, `stratum_members`, `schemas`,
  `families`, `family_files`, `representations`
- **Acquisition** — `blobs`, `fetches`, `decode_attempts`, `archive_members`
- **Evidence** — `variable_profiles`, `value_frequencies`, `schema_presence`,
  `schema_header_facts`, `schema_drift`, `field_renames`
- **Meaning** — `dictionary`, `field_codelists`, `dictionary_rules`,
  `dictionary_conflicts`, `code_tables`, `tab_kits`, `def_variables`,
  `def_datasets`, `field_documentation`, `ledger`
- **Judgement** — `variable_docs`, `dataset_docs`, `open_questions`
- **Output** — `build_outcomes`, `lake_partitions`, `lake_datasets`,
  `population_series`, `api_endpoints`, `api_ingests`
- **Meta** — `schema_version`, `events`

Two rules the store enforces rather than documents:

- **Migration is refused, not attempted.** A table whose columns disagree with
  the shipped schema raises `CatalogSchemaError` naming `catalog-rebuild` as the
  remedy. Silently adding a column and carrying on is how a catalog starts
  meaning two things at once.
- **Derived state is replaced, not accumulated.** Every stage that re-derives
  clears its own output first. A stale partition sitting beside a fresh one is
  indistinguishable from data.

---

## 5. L0–L1 — Discovery, naming, strata, families

### 5.1 Crawl

Concurrent, resumable, gap-tracking. Listing method is chosen per directory —
MLSD where the server offers it, LIST parsed per dialect otherwise, NLST only as
a last resort — and **recorded per row**, because the method determines whether
size and mtime are available at all, which is the whole of D4.

A crawl that would withdraw a large share of the catalog fails rather than
committing, unless `--accept-mass-gone` is passed. Reconciliation distinguishes
a file that **moved** from one that is **gone** by matching content identity
across directories within the run.

### 5.2 Filename grammar

`RDAL2401.dbc` → prefix `RD`, geography `AL`, date `2401`. Four grammars cover
the tree, including the composite suffixes (`.csv.zip`, `.duck.zip`) that the
prior scanner's suffix-stripper mishandled into 82 `UNPARSED` families.

The date convention is inferred **per directory, never per file**. `SIHSUS/
200801_/Dados` holds 22,807 files; deciding `YYMM` versus `YYYY` from one
filename at a time produces a directory in which some files are 2008 and some
are 2080.

### 5.3 Strata, families, representations

Three keys, and the distinction between them is load-bearing:

- `stratum := (system, series, year)` — the unit of schema evidence.
- `family := (system, series, schema_signature)` — the unit of *data*. One
  family spans every year that shares a column layout, and a schema change
  starts a new family rather than corrupting the old one.
- `representation := (family, container_format)` — the same data published as
  `.dbc` and as `.csv.zip` is one family with two representations, not two
  datasets. This is D3.

**A family needs a schema, not a decode.** `build_families` required
`sample_status = 'ok'` — a file actually decoded — while the header census sets
`'header'` by design, so the census's 2,971 strata across 14 systems were
invisible to it. The effect was that families existed for **4 of 20 systems**,
and since both the build and `fetch()` iterate families, sixteen systems could
not be extracted at all: `fetch("SINASC-DN")` answered "nothing catalogued" for
one of the most-used datasets in Brazilian health research.

The census exists precisely so that a schema costs a few hundred bytes rather
than a decode, and its own tests assert it lands on the *same* `schema_signature`
a full decode produces. A census stratum is therefore legitimate grounds for a
family. What it is *not* is grounds for talking about values, so
`families.schema_source` records which — `profile` when something in the family
has been read, `header` when only its columns are known. 316 → **1,633
families**.

This was the horizontal-scaling ceiling, and it was one clause in one query. The
lesson generalises: **a cheap new way of learning something is worth nothing
until what consumes it stops asking for the expensive one.**

**System identity comes from the filename, not the path.** `stratum_id` and
`family_id` are hashes of `(system, series, …)`, so a directory rename would
silently re-derive every identifier and restart 35 years of continuity under new
keys with no error anywhere. The prefix→system map is *learned* from a healthy
crawl, held against later moves, and a disagreement between name and path is
recorded in `system_disagreements` as a finding — never resolved silently, and
settled by a person through `prefix-adjudicate`.

---

### 5.4 The ontology — declaration, and binding to it `[D]`

Strata and families (§5.3) are derived from what the crawl saw. That is the
right basis for *inventory* and the wrong basis for *identity*, and the API
needs identity: `fetch("SIH-RD")` and `info("SIH.RD")` both name a thing, and
that thing has to mean something stable.

**The ontology is an institutional declaration, not a picture of the FTP tree.**
"SIH publishes a dataset called AIH Reduzida, known as RD" is a fact about how
the Ministry of Health organises its information systems. It is true whether or
not the server expresses it, and it survives DATASUS reorganising the tree. The
declaration lives in `curation/ontology.yml`; the FTP layout is *evidence* for
it, never its definition.

That distinction is not academic. Three measured cases where the two come apart:

| case | what the tree shows | what is true |
|---|---|---|
| one file, many datasets | `SIASUS/APAC/2002/acac0201.exe` | seven datasets, as seven DBF members |
| one dataset, many locations | `SIASUS/…AB…` and `Dados_Abertos/APAC_AB` | one dataset, `SIA.AB` |
| one dataset, many names | SINAN `DENG`; Dados_Abertos `DENG` in Portuguese | one dataset, two representations |

So the module keeps two things apart, deliberately:

- **Declaration** — `SystemNode`, `DatasetNode`. Identity, names, what the thing
  is, status, confidence. Authored. A node may legitimately have **zero files**:
  a dataset known to exist and not found published is a research lead, not a bug.
- **Binding** — `Ontology.bind(system, series) → Binding`. Maps an observed pair
  onto a declared node and records **which rule fired**, so the mapping is
  auditable rather than magic. Derived and disposable.

#### Why binding is not a string match

`series` is derived from filenames, so one dataset is spread across many
spellings of itself. Of 1,505 observed `(system, series)` pairs, only **181** are
clean codes. The rest:

| rule | count | example | means |
|---|---:|---|---|
| `filename` | 976 | `PASP2509A` | whole filename: PA + SP + 2509 + part A |
| `colon-member` | 213 | `RD:RDAC1701` | an archive member leaked into the name |
| `year-suffix` | 130 | `SISCAN_CITO_COLO_2013` | a per-year dataset name |
| `template` | 5 | `EFUFAAMM` | a placeholder filename left in the tree |

Declaration is consulted **before** the pattern rules: a dataset that says it has
been seen as `APAC_AB` wins over anything a regex would infer. The rules are the
fallback for what nobody has declared. An ambiguous bare code — one claimed by
two systems — binds to **neither**, because a wrong bind files rows under a
dataset they do not belong to and nothing downstream would notice.

Current state: **1,505 of 1,505 observed pairs bind, 207,220 files, zero
unbound, zero declared-but-unobserved**, across 20 systems and 131 datasets.

#### The defect this fixed

`retrieve._families()` resolved a dataset with `WHERE series = ?`. Because
`series` carries all the spellings above, that under-collected silently:

| spec | families, exact match | families, bound | files, exact | files, bound |
|---|---:|---:|---:|---:|
| `SIA-PA` | 9 | **736** | 10,076 | **10,803** |
| `SIH-RD` | 20 | **32** | 18,638 | **18,986** |
| `SIA-AC` | 0 | **7** | **0** | **274** |
| `SISCAN-CC` | 3 | **16** | 2,858 | 2,871 |

`fetch("SIA-AC")` returned nothing at all while reporting success — precisely the
failure §11 says the fetch path exists to prevent. `_families` now resolves
through the ontology and falls back to the plain match if the declaration cannot
name the dataset: a narrower answer beats an exception.

`SYSTEM_ALIASES` in `retrieve.py` is now **derived** from the declaration's
`crawled_as` rather than hand-maintained a second time. One fact, one place.

---

---

## 6. L2–L5 — Acquisition, decoding, meaning

### 6.1 Content-addressed cache

Fetches are keyed by SHA-256. Nothing is downloaded twice, and a re-crawl that
finds the same bytes under a new path costs nothing.

### 6.2 Reader dispatch by probe, not by suffix (D1)

Readers are tried in probe order against the file's actual bytes. `.exe` files
under `SIASUS/APAC/` are LHA self-extracting archives and are unpacked — 1,723
files and the entire APAC system, which the prior scan dropped because the
extension was not on a list.

### 6.3 The semantic layer — P1

`.CNV` (last-match-wins semantics), `.DEF` (where `I` marks a summable field),
and the `TAB_*.zip` kits are parsed into `dictionary`, with every row carrying
its source, its source reference, a confidence and a validity window.

Claims are merged by **source authority**, lowest number wins:

```
manual(0) → cnv(1) → def(2) → sigtap(3) → dbf_lookup(4)
          → demas_api(5) → pdf(6) → community(7) → inferred(8)
```

`manual` is 0 because a person who has read the form outranks any extraction.
`community` sits below every primary source but above inference: the R package
**microdatasus** (MIT, rfsaldanha) is *parsed, never executed*, and its recodes
are used only where nothing authoritative exists `[D]`.

**A codelist that maps one code to two labels is not a usable lookup.** That is
a rule, not a fix for one table — and enforcing it exposed that the reference
tables had been keyed on codelist name alone, merging thirteen systems' distinct
`SEXO.CNV` files into one table where `1` meant both Masculino and Feminino.
Scoped by system as well, the number of contradictory `(code, window)` pairs
goes from 311,844 across 264 codelists to **zero** (§7.3).

### 6.4 Inference, done defensibly (D5)

Detectors are distributional, not regex-per-value, and every conclusion carries
its evidence. Two rulings worth stating because both went against the intuitive
answer:

- **Presence in a bound table outranks shape.** A four-character string that
  *looks* like an ICD-10 code but is not in CID-10 is not an ICD-10 code.
- **Exact-width matching, always.** Codes are never padded and never truncated
  to make a join succeed. A codelist that mixes widths warns and labels only
  what matches exactly.

### 6.5 The header census `[D]`

Cataloguing every schema by decoding a file per stratum costs **183 GiB**, and
63% of strata hold a single file, so there is no cheaper member to pick. This is
why the schema catalogue had stayed a sample rather than a census.

It is also unnecessary. A DBF declares its entire schema in a header of a few
hundred bytes, and a `.dbc` stores that header **uncompressed** ahead of the
compressed payload. Measured on `RDAC9201.dbc`: all 35 field names, types and
widths read from the first **1,153 of 91,967 bytes**. Across the tree that is
19.23 MB instead of 183 GiB — about 9,750×.

Delivered by `retrieve_prefix()` on the FTP client (`transfercmd` + `ABOR` + a
drained reply — never `retrbinary`, which owns its socket and applies no read
timeout), a header parser that **refuses rather than guesses** when the prefix is
short, and a `schemas` stage that widens its request once when the file's own
`header_length` says to.

Validated two ways: 571 files parsed from their prefix and decoded in full gave
**identical** field lists, 0 differing; and 100% of headers read had widths
summing to the declared record length.

The census sets `sample_status = 'header'`, never `'ok'`. *We know the columns*
must never be mistaken for *we know what is in them*.

---

## 7. L6–L8 — Normalization, lake, denominators

### 7.1 Normalization contract

Typed per field from the ledger. Sentinels are **per field, never global** — `9`
is missing in some columns and a valid category in others. The raw value is
never discarded when a label is written.

### 7.2 Lake layout

`lake/<system>/<family_id>/uf=<UF>/year=<YYYY>/`, Parquet, zstd. A build owns the
whole partition it writes and replaces it; numbering parts from what is already
there is what once let a rebuild land beside its own stale output.

A family that selects files but produces no rows records **why** in
`build_outcomes` — schema mismatch, undecodable, or genuinely empty. A zero-row
build that reports success is the failure mode this exists to make impossible.

### 7.3 Reference tables — scoped by system *and* by vintage

`lake/reference/<table>/system=<SYS>/window=<valid_from>/`

Both levels are necessary and for different reasons. **System** scoping is
correctness: see §6.3. **Window** scoping is because a code's meaning is a
function of when the row was filed — DATASUS rewords labels and reassigns codes,
and a 2005 admission labelled from the 2023 table is mislabelled.

A read with no year returns the current vintage. A read for a system prefers
that system's own copy and falls back to the union only when the system has
none, which is stated rather than silent.

**Damage assessment.** Because the merge bug predated the fix, partitions built
earlier could have carried wrong labels. 149 stored labels were checked against
their own system-scoped binding: **0 contradicting, 0 unverifiable.** The build
had always used a system-scoped dictionary cache, so the lake was never
poisoned. This is now a standing assertion (`check_stored_labels_agree`), not a
one-off audit.

### 7.4 Denominators

POPSVS / POPTCU / censo under `lake/population/`, with the stratifications each
series actually supports — an unsupported stratification raises rather than
silently aggregating to something else.

---

## 8. L10 — The view layer `[D]`

Labels are produced **at read time**, by joining the vintage-scoped reference
table for the years being read. They are not projected out of Parquet.

That was a real bug, not a preference: `labels=True` used to select `*_label`
columns that had to already exist, so asking for a label after a `--no-labels`
build, or for any field whose codelist was never materialised, returned
unlabelled data **with no error at all**.

Two axes control rendering:

- `code_system` per variable — `internal` (the label replaces the code; nobody
  needs to see `SEXO=3`), `external` (code *and* label; `DIAG_PRINC` is a real
  identifier), `none` (as typed).
- `profile` per call — `analysis` (default), `codes`, `audit`, `report`.

Any single column overrides both: `render={"SEXO": "both"}`.

A label that cannot be produced is **named** — in a warning, or with
`strict_labels=True` in a `LabelUnavailable`. Bindings are ranked
deterministically (family-specific first, then confidence, then name affinity,
then codelist name) because SQLite returning six equally-confident `.DEF`
bindings in arbitrary order once made CNES `NAT_JUR` label differently between
runs.

---

## 9. L5.5 — The curation layer `[D]`

Three times the design created a slot for human judgement and left no way to
write into it: `SOURCE_AUTHORITY['manual']` with nothing emitting a manual
entry; `layout_doc` declared authoritative before anything produced one; and a
prefix contradiction only a person could settle, with no way to record the
settlement.

`curation/*.yml` is that door. YAML under version control, so an assertion has
an author, a date and a diff:

```
curation/
  systems.yml            what each information system is
  datasets.yml           what one row IS, and what will mislead you
  variables/*.yml        per-variable meaning, codelists, dependencies
```

Loaded by `pegasus-data curate`, and `curate --accept` settles an open question
with a required `--note` saying why. A curated claim outranks every extracted
source because manual is authority 0.

`vintage_note` records *when a classification itself changed and how the right
one is selected for a row* — the ICD-9/ICD-10 boundary is per system, read from
the dictionary rather than hardcoded to 1996.

---

## 10. Offline — the semantic bundle `[D]`

Everything the module can *say* about a value is derived from an FTP server that
is frequently slow, occasionally unreachable, and not under anyone's control. A
module that can only translate while DATASUS is up cannot be relied on — and the
data does not change when the server does. A 2019 admission is coded the way it
was coded whether or not `ftp.datasus.gov.br` answers today.

So the semantic layer is packable:

```bash
pegasus-data pack --out semantics.pgsb            # everything
pegasus-data pack --system SIHSUS --out sih.pgsb  # one system
pegasus-data unpack semantics.pgsb                # on a machine with no crawl
```

A bundle carries the dictionary, the field bindings, the curated meanings, the
schema catalogue and the parsed layout documentation. It carries **no** file
inventory, no profiles and no data: it is the means to interpret data someone
already has.

What makes it small enough to be practical, measured on the full catalog:

| | rows | |
|---|---:|---|
| dictionary | 19,905,196 | |
| bound to some field | 9,544,839 | 48.0% of rows, but only 19.5% of codelists |
| after de-duplication | 7,481,170 | the rest were the same label repeated per vintage |

**153 MB** for all sixteen systems; **~10 MB** for one. Only codelists actually
bound to a field are packed — four in five codelists are TabNet tabulation axes
nothing decodes against. Rows are de-duplicated on
`(system, codelist, code, label)` with the validity span carried across, so a
code whose *wording* changed keeps both readings and both spans, and only exact
repeats collapse. `--max-codelist-rows` drops the geographic roll-ups for an
even smaller bundle, and **names in the manifest what it dropped**, so an
unlabelled municipality reads as *not packed* rather than *unknown*.

Two invariants, both silent failures if broken and both under test:

- **Columns are matched by name, never by position.** A bundle that copies
  positionally puts labels in the wrong columns the day the schema gains one,
  and every row count still looks right.
- **Unpacking is additive by default.** A local catalog read the files
  first-hand; a bundle is a copy of someone else's reading. `--replace` is for
  the case where the bundle genuinely is the source of truth.

---

## 11. `fetch()` — one call, DATASUS to a table `[D]`

The rest of the package is shaped around a catalog: crawl, learn, build, query.
That is right for a data lake and wrong for the question most people arrive
with, which is *"give me SIH admissions for Alagoas in 2023"*. R's
**microdatasus** answers that in one line and is, for that reason, how most
Brazilian health researchers touch DATASUS at all.

```python
fetch("SIH-RD", uf="AL", years=2023)
```
```bash
pegasus-data get SIH-RD --uf AL --years 2023 --out sih_al_2023.csv
```

Downloads what it needs, decodes, normalises, labels, returns. No lake is built
and nothing is written to Parquet.

Three deliberate differences from microdatasus:

- **It does not guess filenames.** microdatasus builds the FTP path from a
  template, which works until DATASUS moves something — and DATASUS moves
  things. Every path here comes from the catalog; a system the catalog has never
  seen triggers a **bounded crawl of that system's directory only**, located by
  listing the base directory and matching the name. The result is recorded, so
  the second call is free. Discovery stays observation, never invention.
  The header census (§6.5) is what makes this affordable: families are keyed on
  schema, so discovery must know each stratum's columns, and reading them costs
  a few hundred bytes per stratum instead of a decode.
- **It resolves the dataset through the ontology (§5.4), not by string match.**
  `series` is derived from filenames, so one dataset is spread across many
  spellings of itself. Matching the string found 9 of SIA-PA's 736 families
  and none of SIA-AC's 7 — `fetch("SIA-AC")` returned nothing while
  reporting success. Binding collapses the spellings onto the declared
  dataset.
- **It labels from a vintage-scoped dictionary**, through the same `render_table`
  the lake path uses. One entry point, two callers: a second labelling
  implementation would be a second set of labels to keep true.
- **It says what it could not do.** Every file that failed to decode, every file
  whose schema did not fit its family, every requested year DATASUS never
  published — each is named in the `FetchReport`. Returning a short table quietly
  is the easiest way to publish a wrong number.

On first use with no lake, the Parquet reference tables the render path joins
against are materialised from the catalog — no network involved, since the
codelists were parsed long before. With no codelists at all, it says so rather
than returning bare codes as though they were the answer.

---

## 12. Watchdog, heartbeat, and never hanging silently `[D]`

The exit criterion was not "fix the profile hang". It was **the pipeline can
never hang silently**.

- **Per-item deadline.** Every stage runs its items through `run_with_timeout`.
  An item that exceeds it records a `coverage_gaps` row with `kind='timeout'`
  and the stage **continues**. A slow file is a finding, not a stop.
- **Heartbeat.** A daemon thread names the item currently in flight, on stderr,
  explicitly flushed. Silence for longer than the interval means wedged, and now
  you can tell which of 207,251 files it is wedged on.
- **Stall timeout** bounds the stage as a whole, above the per-item deadline.

Both fetch deadlocks that motivated this are regression-tested: the unbounded
`queue.join()`, and the worker that returned without draining after failing to
connect.

---

## 13. Command surface

Grouped by intent rather than by pipeline order, because the pipeline order is
the implementer's model and not the user's.

- **EXPLORE** — `systems`, `tree`, `coverage`
- **UNDERSTAND** — `describe`, `dictionary`, `gaps`
- **EXTRACT** — `get`, `load`/`export`, `build`, `normalize`
- **AUDIT** — `report`, `questions`, `verify`, `findings`, `icd-quality`
- **MONITOR** — `crawl`
- **PIPELINE** — `inventory`, `sample`, `fetch`, `semantics`, `schemas`,
  `profile`, `families`, `ledger`, `reference`, `population`, `demas`,
  `sigtap`, `community`, `curate`, `all`
- **MAINTENANCE** — `pack`, `unpack`, `prefix-adjudicate`, `catalog-rebuild`

`pegasus-data all` runs: crawl → inventory → semantics → sigtap → community →
curate → reference → schemas → profile → families → ledger → build. Optional
stages degrade to a recorded note rather than failing the run.

---

## 14. The public API — capabilities as services

The API was organised by **implementation stage**: `load` read the lake, `fetch`
downloaded, `describe` read the ledger. That is the pipeline's model of itself,
and it is the wrong model for the person calling it. Nobody arrives wanting to
"read the lake"; they arrive with a question, and the questions come in a fixed
order:

| The question | The verb | What backs it |
|---|---|---|
| What is even there? | `explore()` | the shipped map of 207,251 files |
| Give me some. | `fetch()` | crawl → decode → normalise → label |
| What does this column mean? | `describe()` · `search()` | ledger, dictionary, curation |
| I already have data — decode it. | `translate()` | the 19.9M-row dictionary |
| What can't you tell me? | `gaps()` · `questions()` | `open_questions`, `coverage_gaps` |
| Per capita? | `load_population()` | IBGE series |

Five verbs, one question each. `load()` and `export()` remain for the lake path,
but they are no longer the front door.

**The organising rule: every capability the module has internally should be
reachable as a service, or it does not really exist.** Three were not, and each
was a capability the module genuinely had and nobody could use.

### 14.1 `explore()` — the map is the product

DATASUS publishes no index. There is no manifest and no API that enumerates the
tree; there is an FTP server with thirty-five years of files in directories that
have been reorganised more than once. Finding out what exists has meant clicking
through it — which is why most people who use this data use one system, for the
years someone told them about.

This module crawled all of it. That knowledge — every file resolved to a system,
series, year, state, size and schema — **compresses to 1.04 MB**, so it ships in
the wheel. The consequence is not a minor convenience:

```python
explore()                      # 20 systems, 990 GiB, 1979–2026
explore("SIHSUS")              # 7 series
explore("SIH-RD")              # coverage by year, chronologically
explore("SIH-RD", year=2023)   # the files, with sizes
```

On a fresh install, with no crawl and no network, all four answer immediately.

**Where the answer came from is part of the answer.** A local crawl is current
and always wins; the shipped map is a photograph of a server that keeps moving.
Every result names its source and the date of the crawl behind it, because a
two-year-old snapshot presented as the state of the server is worse than no
answer — nobody thinks to doubt it.

### 14.2 `translate()` — the dictionary is a service

A great deal of DATASUS microdata is already on people's disks: exported from
TabNet, pulled with R's **microdatasus**, mailed by a colleague. It is all coded,
and the codelists are in `.CNV` files nobody parses. This module holds 19.9
million rows of them. Requiring someone to re-download data they already have in
order to reach that was an artificial toll.

```python
translate(df, system="SIHSUS", year=2019)
translate("extract.csv", system="SIM")
```

Same `render_table` as `load()` and `fetch()` — one implementation, so a column
labelled one way in a notebook is labelled the same way everywhere.

**`system` is required and is not inferred.** `SEXO=3` is Feminino in SIHSUS and
undefined in SINASC; a function that guessed helpfully here would put wrong
labels on real records with no error anywhere.

### 14.3 `search()` — the dictionary is askable

Backed by `docs/dictionary.sqlite` (§14b). *Which columns anywhere draw on
CID-10? Which code means Parda?* Both are one call, and the second immediately
shows why it matters: **Parda is `03` in SIHSUS.RACACOR, `3` in SIHSUS.RACA_COR,
and `4` in SINASC**. Nothing in the old file tree could surface that.

### 14.4 Return shapes

Data verbs (`fetch`, `load`, `translate`) return `pyarrow.Table`; passing
`report=True` returns `(table, report)` where the report names everything that
could not be done. Knowledge verbs (`explore`, `describe`, `search`) return small
objects with `.rows`, `.table`, `.as_dict()` and a readable `__repr__` — usable
in a notebook and serialisable in a pipeline.

Names resolve lazily: `import pegasus_data` must not pay for pyarrow and duckdb
when the caller wanted `Settings`.

---

### 14.5 `info()` — the ontology is askable `[D]`

**A note on module names.** `explore`, `translate` and `info` are functions
whose implementation modules are private — `_explore.py`, `_translate.py`,
`_info.py`. A module named `explore.py` exporting a function named `explore`
collide as attributes of the package: importing the submodule binds it over the
function, and `from pegasus_data import explore` then returns a module, so
calling it raises `'module' object is not callable`. The underscore removes the
ambiguity rather than arbitrating it.

`explore()` answers *what is out there to fetch*. `describe()` answers *what does
this column mean*. `info()` sits between them and answers **what IS this thing**,
at any level: system, dataset, schema generation, or variable.

```python
info()                              # every system, with file counts
info("SIH")                         # the system, and the datasets under it
info("SIH.RD")                      # identity, coverage, schema generations
info("SIH.RD", field_name="DIAG_PRINC")
info("SIH.RD.DIAG_PRINC")           # same thing, one string
```
```bash
pegasus-data info SIA.AQ
pegasus-data info SIH.RD --json
```

Every answer keeps three things apart, because conflating them is how a
well-documented dataset with no data gets mistaken for a well-covered one:

- `identity` — what the node IS, from the declaration. Stable.
- `evidence` — which `(system, series)` pairs bind to it, under which rule, and
  how many files. Derived.
- `coverage` — years, states, schema generations, file counts, and how much of
  the column set is described.

So `info("SIA.AB")` reports `seen as: AB, APAC_AB`-style evidence that one
dataset is published in two trees, and a dataset declared but never observed
says so in `notes` rather than appearing as an empty success.

**Schema generations are documented, not just listed.** A generation is a
*signature*, not a family: one signature is reached through several spellings of
the series, so listing families showed SIH.RD's 113-column generation twice, as
though the schema had changed and changed back. And a generation only means
something beside its neighbour, so each one carries the columns added and
dropped against the previous:

```
1998   41 cols    324 files
    +7 CAR_INT DIAG_SECUN GESTAO MARCA_UTI NACIONAL; -8 DIAG_SEC SEMIPLEN …
1999   52 cols    323 files
    +11 CID_NOTIF CONTRACEP1 CONTRACEP2 GESTRISCO INSTRU
```

"113 columns, 2014–2025" tells an analyst nothing; "+6, −1 at this boundary" is
what decides whether years either side can be pooled. The columns come from the
header census (§6.5), so a full generation history costs lookups rather than
decodes.

Aliases resolve throughout: `SIH` and `SIHSUS` are the same node, `SIH.RD`,
`SIHSUS.RD`, `SIH/RD` and a bare `RD` all reach the same dataset, and an
ambiguous bare code resolves to nothing rather than to a guess.

---

### 14.6 `compendium()` — the map, as a file `[D]`

`explore()` and `info()` answer from a catalog the caller has. `compendium()`
writes the answer out, so someone with no catalog and no network can open it.
The audience is a researcher deciding whether DATASUS can answer a question at
all, typically while writing a protocol.

The prior art is a 57 MB artefact whose weight was in the wrong place: 124,810
rows of raw file listing and per-column-per-file percentiles (`p01`…`p99`,
`mean`, `std`), with **no descriptions at all** and a `semantic_guess` column
presenting guesses as data — it labelled a CNES establishment code
`municipality_code_candidate`, with nothing to say how much to trust that.

So the core here carries what planning actually needs — `systems`, `datasets`
with what one row IS, `coverage` by year and state, `schema_generations` with
what each changed, `variables` with their meanings, and `open_questions` — and
everything heavy is opt-in.

Two of those answer questions that decide whether an analysis is valid at all,
so they are core rather than optional however tempting the size saving:

- **`field_validity`** (§14.7) — *when* each column existed. Without it a
  structural zero reads as clinical missingness.
- **`codelist_vintages`** — which codelists have more than one vintage, over
  what competence windows, and how many codes. `SIASUS.MUNICBR` has four
  vintages across 280,004 codes; decoding a 1998 extract against today's table
  resolves every code, to the wrong municipality. The full `codes` table is
  optional and runs to 425 MB, so the *hazard* has to be visible without it.

The `codes` toggle is the design decision, and it is sized rather than named:

| mode | SIH | why |
|---|---:|---|
| core | 0.8 MB | the map |
| `internal` | 4.8 MB | DATASUS's own enumerations |
| `bound` | **425 MB** | + CID-10, CBO and geography |

Twelve geography and CID-10 tables are 62% of the codes bound to SIH — `MUNICBR`
alone is 1.2M rows. Those are maintained elsewhere and the reader already has
them. `internal` excludes codelists above `max_codes` and **names them in the
report**, because a size rule that silently drops things is the same failure as
a guess presented as data. Sizing rather than reading a curated `code_system`
was deliberate: that field is thin exactly where curation is thin.

---

### 14.7 `availability()` — when a column existed `[D]`

`src/pegasus_data/availability.py`

`SIH.RD` has 20 schema generations across 34 years, and its nine
secondary-diagnosis columns `DIAGSEC1`–`DIAGSEC9` do not appear before 2014. A
query for `DIAGSEC4` in 2007 returns nothing, and that nothing is **structural**:
the column did not exist. Read as clinical missingness it corrupts any estimate
spanning the boundary. Schema generations (§14.5) already record this, but only
implicitly — the caller has to map signatures to years and reason about gaps.

**Three states, not two.** The obvious model is `valid_from`/`valid_to` per
field. It is one state short, and it fails the way the original problem fails:
`DIAGSEC4` is carried by decoded files for 2014–2016 and 2018 onward, so an
interval reading 2014–2026 quietly asserts something about 2017 — a year nothing
has been decoded for.

| state | meaning |
|---|---|
| `present` | a decoded schema for that year carries the field |
| `absent` | a decoded schema exists and does **not** carry it — a positive claim |
| `unknown` | nothing decoded for that year; no claim is made |

`absent` is the load-bearing answer: it is what separates structural absence from
missingness. `unknown` is what keeps the separation honest when the catalog is
simply silent.

Intervals still **bridge** undecoded years, because splitting `DIAGSEC4` into two
runs would imply the column was removed and reinstated, which nobody has evidence
for. Bridging is an inference about the *shape of a run* and never hardens into a
claim about a year: `state()` checks `unknown` before the intervals, and `span()`
names what it bridged.

```python
availability("SIH-RD").changed_at()            # every year a column arrived or left
field_available("SIH-RD", "DIAGSEC4", 2007)    # "absent"
field_available("SIH-RD", "DIAGSEC4", 2017)    # "unknown"
```

The distinction between what DATASUS **published** (`file_facts`, all years) and
what this catalog has **decoded** (`strata`) is preserved throughout, because
they are different facts and merging them is how a silence becomes a claim.

Exported to the compendium as `field_validity`, one row per contiguous run.

### 14.8 Join keys — how datasets connect `[D]`

`src/pegasus_data/curation/joins.yml`

This knowledge already existed, as prose inside gotchas: *"Joins to SIH.RD on
the AIH number"*, *"Only meaningful joined to CNES.ST on the CNES code and
competência"*. A human reading the docs could find it; nothing else could.

Declared as **keys, not dataset pairs** — pairs explode (the CNES code alone
would be sixty-odd) and what decides whether a join is correct is the key's
identity and each side's grain, not the pair.

Two fields carry the weight:

`rows_per_key`
: `SIH.RD` is one row per AIH; `SIH.SP` is many. Join them, count rows, and you
  have counted professional acts while believing you counted admissions.
  `unmeasured` is used where nobody has checked — a statement about our
  evidence, not about the data.

`as_of`
: `CNES` is versioned by competence. Joining a 2015 admission to today's CNES
  answers *what is this hospital now*, not *what was it when the patient was
  treated* — and it answers silently.

Three keys are declared: **AIH** (4 datasets), **CNES** (18, as-of competence),
**APAC** (10). Every column was measured against `schema_presence`, and verify
check 19 keeps it measured — 32 of 32 present.

**What is not established is recorded too**, under `not_established`. A join
that silently matches the wrong rows produces a cohort, not an error, so
"we checked and there is no key" is the more useful answer:

- A longitudinal patient across SISCAN exams. `CO_PACIENTE` exists **only** in
  `SISCAN.PACNT`; no exam dataset carries it.
- SIH deliveries linked to SINASC births. No shared key exists; any link is
  probabilistic record linkage on quasi-identifiers, which is a
  re-identification method rather than a join, and is out of scope (§18).
- SISPRENATAL to SIH or SIA. Untested, and a CNS-based link would mean handling
  direct personal identifiers.

Exported as `join_keys`, `join_key_members` and `joins_not_established`.

### 14.9 The label pack — meaning, small enough to ship `[D]`

`src/pegasus_data/labelpack.py` · `curation/codelists.yml`

`fetch("SIM-DO", uf="AC", years=2022)` on a clean machine returned 4,159 rows
and labelled **nothing**. The labels lived only in a 14 GB catalog produced by
an hour-long `semantics` run that no user has any reason to perform. Data came
back; meaning did not.

The pack is that layer distilled to **19.8 MB**, carried inside the wheel:

| reduction | effect |
|---|---|
| runs, not enumerations | a `.CNV` says *this range is Brasília*; the ingest wrote out all 10,000 integers |
| one copy across systems | stored once **only** when every system carrying the codelist agrees |
| packed facts split | `CADGERBR` labels are a CNPJ *and* an establishment name in one string |
| registries held back | 90 entity directories |

14.8M dictionary rows → 2.4M runs, a 73% reduction, losing no fact.

**The cross-system rule is narrower than it looks.** `system = NULL` means every
system reads this code this way. That is only safe when every system *carrying
the codelist* has the code — SIH codes sex 1/3 and SINASC codes it 1/2, so
"the systems that happen to have this code agree" is a different and unsafe
claim. Collapsing on it would hand SIH's `3 → Feminino` to a stray `3` in
SINASC.

**Roles are declared, not inferred** (`curation/codelists.yml`). Sorting by size
is the obvious approach and it is wrong: a 50,000-row cap keeps 450 municipal
rollups and throws away **CID10**, the most important codelist in the tree for
clinical work. Structure cannot separate them either — CID10 has one label per
code and so does an establishment directory. What differs is what the code
*refers to*, which is an institutional fact and therefore declared.

- `enumeration` — DATASUS's own closed sets. Irreplaceable; nowhere else.
- `classification` — CID10, CBO, SIGTAP. Kept whole: DATASUS's copy is complete
  for the data DATASUS publishes, and sending someone elsewhere to decode a
  diagnosis defeats the package.
- `geography` — municipalities and regions. Collapse well; essential as joins.
- `registry` — **held back.** `CADGERBR` is 687,789 establishments. That is a
  dimension table, and the project already publishes it as the `CNES.ST`
  dataset with a declared join key (§14.8).
- `crosswalk` — an identifier mapped to another identifier. A category of its
  own, not a label.

**The crosswalk survives the hold-back.** `CADGERBR`'s labels carry each
establishment's CNPJ, and a CNES↔CNPJ mapping is how establishments are matched
across systems that key on tax identity rather than CNES. 546,189 rows, shipped
separately, because throwing it out with the prose would have been the expensive
half of the decision.

Bindings ship too (9,380 rows, 35 KB). Knowing `I219` is a heart attack is no
help if nothing says `DIAG_PRINC` is coded in CID10.

Rebuilt by `pegasus-data labelpack` after `semantics`. `read_reference_table`
prefers a local lake and falls back to the pack, so a real build always outranks
what shipped.

## 14a. What ships, and what does not

A package is not a data lake. The rule is: **ship what makes the module
functional out of the box, and nothing that is derived, large and reproducible.**

**Ships (~1.4 MB):**

| | size | why it must |
|---|---:|---|
| `resources/tree.parquet` | 1.29 MB | `explore()` on a fresh install, offline. The module's most distinctive asset, and the reason it is worth 1 MB. |
| `resources/families` + `schema_presence` | 0.05 MB | answers "does 2008 have `DIAG_SECUN`" without downloading a byte |
| `curation/**/*.yml` | 44 KB | the manual-authority rung. Without it, `SOURCE_AUTHORITY['manual']` is empty and no human judgement can outrank an extraction — the whole point of §9. |
| `catalog/schema.sql` | 40 KB | the catalog cannot be created without it |

`curation/` shipping is a **bug fix**, not an addition: the docstring said it
shipped with the package while the path resolved to the *repository* root, one
level outside it. Every pip install had an empty manual rung.

**Never ships — derived, large, reproducible:**

| | size | how to get it |
|---|---:|---|
| `docs/dictionary.sqlite` | 531 MB | `pegasus-data dictionary` |
| semantic bundle | 153 MB (10 MB per system) | `pegasus-data pack`, or download |
| `lake/`, `blobs/`, `_catalog/` | up to 183 GiB | the pipeline |

The test is whether the artifact is *derived from something else the user can
obtain*. The map is not — it costs a multi-hour crawl and DATASUS will not give
it to you — so it ships. The dictionary database is: it is a projection of the
catalog, and `pegasus-data dictionary` rebuilds it in three minutes.

---

## 14b. The dictionary, as a database

`pegasus-data dictionary` writes **one SQLite file**: systems, variables,
code tables, every code and label, schema generations and dataset prose, with a
full-text index over the names and descriptions. Generated from the catalog,
never hand-written — so a variable with no description here means no source
supplied one, and the fix is `curation/`, not the documentation.

It replaced a tree of **3,036 Markdown files**, and the replacement is worth
recording because the mistake was mine and it was a container mistake, not a
content one. Everything in those files was relational — systems have variables,
variables have code tables, code tables have codes — and flattening it cost
three things at once:

- **No question could be asked.** *Which columns anywhere draw on CID-10? Which
  code means Parda? Which generation added `DIAG_SECUN`?* Every one of those is
  a `SELECT` now and was a `grep` across 42 MB before.
- **The values had to be truncated.** A page listing 5,570 municipalities is not
  a document, so the renderer capped tables at 500 rows. The cap was a property
  of the page; the database keeps all 7.47 million codes.
- **The largest page did not render.** SINAN's 2,250 columns came to 1,043 KB,
  past the size GitHub will display — the most exhaustive page in the set was
  the one nobody could open. That produced pagination machinery, which produced
  link-integrity problems, which produced a link checker. All of it existed to
  serve the container.

The Markdown renderers survive, because the prose is worth having: each
variable's rendered page is stored **as a column**, and `pegasus-data page` prints
it. What is gone is writing them to disk.

Two encoding decisions, because the first schema was 1.1 GB — larger than the
files it replaced, which would have made the change a regression:

- `codes` references its codelist by integer. `system` and `codelist` inline as
  text on 7.5 million rows was most of the file.
- Labels are **not** indexed into FTS. That duplicated the entire codes table
  inside the search store. Full text covers names and descriptions; an exact
  label lookup — which is what people actually do, holding a label and wanting a
  code — is served by an index on `label`.

**A known duplication.** The bundle (§10) and this file overlap: both carry the
codelists. They are kept separate because they are for different things — the
bundle is a *transport* format, restorable into a catalog to make the pipeline
work offline, and this is a *read model*, denormalised and indexed for querying.
Merging them would mean one artifact serving two access patterns badly. Both are
derived from the catalog, so neither can drift from it independently.

---

## 14c. Classifications DATASUS does not own

Researched against the maintainers rather than accepted from whatever `.CNV`
DATASUS ships. The conclusions differ per classification, and two of them are
"keep what we have", which is a finding rather than a shrug.

- **SIGTAP — keep the current source.** `ftp2.datasus.gov.br/public/sistemas/tup`
  *is* the maintainer's channel: for SIGTAP the Ministério da Saúde is the
  maintainer and there is no upstream standards body to escalate to. The
  layout-driven fixed-width reader is not merely acceptable, it is what the data
  demands — the published layout drifts between vintages, so a hardcoded parser
  would be silently wrong today. Do not migrate to the SOAP API; do not adopt a
  third-party mirror.
- **CBO — source externally, highest value.** CBO is the Ministry of Labour's,
  not DATASUS's, and the FTP table mixes ~3,000 three-character CBO-1994 codes
  with ~2,813 six-character CBO-2002 codes **in one file**. Under the exact-width
  rule (§6.4) that is decodable but fragile, and a canonical CBO-2002 table from
  gov.br (`CODIGO;TITULO`, semicolon-delimited) removes the ambiguity. DATASUS's
  copy is retained for the CBO-1994 vintage, because a 1998 record was coded
  against CBO-1994 and that is what it means.
- **CNAE — IBGE's API is authoritative** and verified live, where full-width CNAE
  appears in establishment records.
- **TUSS and ANVISA registries — do not appear** in DATASUS public microdata.
  Nothing to do.
- **CEP, raça/cor, escolaridade — genuine dead ends.** DATASUS's own copy is the
  correct provenance: these are its own codelists, not a standard it borrowed.

**The crux, and it goes against the intuitive answer: canonical does not
automatically outrank DATASUS's copy.** If DATASUS coded a row against its own
stale table, the stale table is what that row *means*. An external source is
authoritative about the classification and not about the encoding, so it ranks
**beside** `cnv`/`def` for vintage selection rather than above them, and is used
where DATASUS's copy is absent, ambiguous, or demonstrably a truncated mirror.

---

## 15. Environment

Python 3.11+. `pyarrow`, `duckdb`, `typer`, `rich`, `httpx`, `pyyaml`;
`openpyxl` optional for Excel export and refused with a clear message when
absent rather than half-written. Data home from `$PEGASUS_DATA_HOME`.

---

## 16. Secondary sources

- **DEMAS** (`apidadosabertos.saude.gov.br`) — endpoint catalogue, ingested to
  `lake/demas/`, with granularities recorded rather than assumed.
- **SIGTAP** (`ftp2.datasus.gov.br/public/sistemas/tup/downloads`) — 224 monthly
  vintages of the procedure table, layout-driven fixed-width parsing. §14 item 5
  asked whether SIGTAP had to be sourced separately. It did.
- **IBGE** — population series.
- **microdatasus** — community codings, parsed never executed, authority 7.

---

## 17. Build order and regression assertions

`verify` runs 20 assertions. They are checks, not opinions:

`check_blob_dedup`, `check_crawl_coverage`, `check_apac_recovered`,
`check_sih_generations`, `check_format_collapse`, `check_dictionary_coverage`,
`check_field_decoding`, `check_detectors`, `check_retired_column_flagged`,
`check_lake`, `check_population`, `check_demas`, `check_describe`,
`check_build_accounted`, `check_stored_labels_agree`, `check_codes_are_codes`,
`check_ontology_exhaustive`, `check_every_dataset_says_what_a_row_is`,
`check_join_keys_exist`,
`check_bound_codelists_decode`.

The last two are the ones the project is judged on, and they are deliberately a
pair. Exhaustiveness without meaning is a file listing; meaning without
exhaustiveness is a sample.

- **16** no codelist stores prose where a code belongs.
- **17** every one of 207,030 data files reaches a declared dataset — 100%,
  with 221 support files (codelists, layouts, PDFs) counted separately rather
  than buried in the same number.
- **18** every one of 131 declared datasets states what one row IS and its unit
  of analysis, across 38 distinct units. Files that are not tables of rows —
  installers, record layouts, the BPA importer — satisfy it by saying so.
  "Not a dataset" is an answer; blank is not.
- **20** no binding measured to decode nothing is still offered to a caller.
  `.DEF` claims a codelist explains a column generously — it cannot tell a
  tabulation axis from a code system, so a date gets bound to a year table and a
  birth weight in grams to weight ranges; 35.2% of checkable bindings decode
  none of their column's observed values. `measure_bindings` records the share,
  `working_bindings` withholds the dead ones, and this asserts the **seam**
  between them, which is where a bug would be invisible: a dead binding that
  still reaches a caller yields a column reported as decodable and labelled by
  nothing. It reads the stored measurement rather than recomputing it.

- **19** every column a declared join key names really exists in that dataset.
  A wrong column here is worse than no column: a join that matches nothing
  reads as "no overlap", and a join on a mistyped-but-real column returns the
  wrong rows. Both look like results. It **skips rather than passes** when
  nothing is decoded, so it cannot pass vacuously.

A check that cannot run on the current catalog **skips with a reason**; it never
passes vacuously.

---

## 18. Prohibitions

Things that silently ruin the artifact:

- **Never guess a code's meaning.** Unmapped is `categorical_undecoded` with a
  coverage penalty. A plausible guess with no provenance is worse than a gap,
  because it is invisible downstream.
- **Never apply a global sentinel rule.** Sentinels are per field.
- **Never let a missing column pass silently.** A query for `DIAG_SECUN` against
  a file that lacks it must **raise**. An empty result looks legitimate.
- **Never exclude a file by extension.** That is D1.
- **Never report `stable` where n = 1.** Report `insufficient_evidence`.
- **Never recompute what the source publishes officially** (epidemiological week
  is the canonical case).
- **Never discard the raw value when writing a decoded label.**
- **Never resolve a source conflict silently.** Record both claims.
- **Never pad or truncate a code to make a join succeed** (§6.4).
- **Never key a codelist without its system** (§6.3).
- **Never modify personal-identifier columns.** They pass through unchanged. The
  detector and its ledger flag stay **on**: that flag is the evidence for
  escalating to the Ministry, and it must not be dropped. No masking, hashing or
  dropping is performed here.

---

## 19. Departures from the brief

Recorded because the brief asked to be corrected where it was wrong, not
followed where it was.

1. **Schema census instead of better sampling (D2).** The brief asked for
   several samples per stratum. Reading headers gives *every* stratum's schema
   for 0.01% of the cost, which is better than a better sample. §6.5.
2. **A view layer the brief did not have.** Labels projected out of Parquet at
   build time cannot answer a question asked after the build. §8.
3. **A curation layer the brief did not have.** The brief's own authority table
   had a `manual` rung with no door into it. §9.
4. **System-scoping of reference tables.** Not in the brief; without it the
   labels are a coin toss. §6.3.
5. **`community` as a source rung.** Not in the brief. Ranked below every
   primary source, above inference.
6. **SIGTAP sourced externally.** The brief left this open and said not to
   assume. It is not in the kits. §16.
7. **`fetch()` and the bundle.** Neither was in the brief. Both follow from what
   the module is *for*: §10, §11.
8. **`IDADE_anos` is not derived.** The brief pushed a `COD_IDADE` binding as
   high-priority twice. No unit codelist exists for it in any source, and
   deriving years from an unknown unit would fabricate ages on real records. The
   raw columns pass through; the gap is a recorded open question. **This is
   settled and is not to be revisited.**
9. **`from pegasus_data import Catalog, load, describe` did not work.** The
   brief's own first example. Fixed by exporting them lazily. §14.

---

## 20. Open questions

`open_questions` holds them with a verification procedure each; `pegasus-data
questions` lists them. Of the brief's original eleven `[V]` items, the ones that
mattered are closed: the HTTPS mirror was probed, the `.exe` payload unpacked
(APAC recovered), the `.CNV`/`.DEF` grammars learned, the kits enumerated,
SIGTAP located externally, the `.duck` files opened, and the `Dados_Abertos`
grammar resolved (the 82 `UNPARSED` families were composite suffixes, not a
missing grammar).

1,339 open questions remain, the great majority of them of one shape: *this
column is bound to no codelist, and here is what is known about it.* That is the
honest state of a tree where DATASUS itself never published a dictionary for
much of what it distributes, and it is the work that continues.

---

## 21. Measured state

Counted on the shipped catalog, not estimated.

| | |
|---|---:|
| files crawled | 207,251 |
| files the prior scan found | 124,810 |
| strata | 4,418 |
| strata with a known schema | 3,688 |
| distinct schemas | 273 |
| families (system x series x schema) | 1,633 |
| distinct columns catalogued | 4,354 |
| columns described | 1,572 (34.7%) |
| dictionary rows | 19,905,196 |
| codelists | 10,748 |
| field→codelist bindings | 9,304 |
| systems documented | 18 |
| columns with a binding that decodes | 2,588 |
| open questions | 1,339 |
| full semantic bundle | 153 MB |
| per-system bundle | ~10 MB |
| dictionary database | 531 MB, 7.47M codes |
| bindings measured to decode nothing | 658 of 1,871 (35.2%) |
| tests | 538 passing |

The headline is the first two rows. The mechanism behind the 82,441-file
difference is stated plainly in `docs/FINDINGS.md` §0.

`docs/FINDINGS.md` records what we measured that contradicted an assumption.
**`docs/CONFIDENCE.md` records the opposite** — claims this project makes that
are NOT well-evidenced, ranked by how much damage a wrong one would do, each
with what would settle it. A project whose pitch is that it says what it does
not know owes the reader that list somewhere they can find it.
