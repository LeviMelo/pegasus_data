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
  normalize/
    engine.py types.py geo.py time.py
  persist/
    lake.py               Parquet layout and partitioning
    reference.py          system- and vintage-scoped code tables
    duck.py               DuckDB view registration
  sources/
    demas_api.py ibge.py sigtap.py community.py
  view.py                 read-time labelling and render profiles
  retrieve.py             fetch(): one call, DATASUS to a table
  bundle.py               portable semantic bundle
  docsgen.py              docs/dictionary/*.md
  progress.py             watchdog, heartbeat, per-item deadlines
  verify.py               15 regression assertions
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

**System identity comes from the filename, not the path.** `stratum_id` and
`family_id` are hashes of `(system, series, …)`, so a directory rename would
silently re-derive every identifier and restart 35 years of continuity under new
keys with no error anywhere. The prefix→system map is *learned* from a healthy
crawl, held against later moves, and a disagreement between name and path is
recorded in `system_disagreements` as a finding — never resolved silently, and
settled by a person through `prefix-adjudicate`.

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

## 14. Public API

```python
from pegasus_data import fetch, load, describe, export, pack, unpack

fetch("SIH-RD", uf="AL", years=2023, report=True)
load("SIHSUS", "RD", uf="AL", years=range(2015, 2025),
     columns=[...], profile="analysis", render={"SEXO": "both"})
describe("SIHSUS", "RD", field="DIAG_PRINC")
export("SIHSUS", "RD", uf="AL", format="xlsx")
```

Names resolve lazily: `import pegasus_data` should not pay for pyarrow and
duckdb when the caller wanted `Settings`.

`describe()` is the module's user-facing face — the answer to *what is this
variable and what do its values mean*, which DATASUS does not publish anywhere.
It returns the ledger entry, dictionary coverage, top values **with labels**,
the reference table and its vintages, how the binding was established, the
schema generations the field appears in, and the open questions against it.

---

## 14b. The generated dictionary

`pegasus-data dictionary` writes `docs/dictionary/` — **3,036 pages** — from the
catalog. Never hand-written, so it cannot drift; the corollary is that a gap in
the docs is a gap in the catalog and must be fixed there. Writing prose into the
Markdown would hide the gap, which is the opposite of the point.

Per system, three artifacts, because they answer three different questions:

- **`<system>.md`** — every column: what it is, how confident, from what source.
  It opens with the columns that produce a wrong answer if used naively.
- **`<system>/schemas.md`** — every generation of the record and exactly which
  columns each added or dropped. *Does this year have `DIAG_SECUN`* becomes a
  glance instead of a diff.
- **`<system>/codelists/`** — **the values**, one page per code table, with the
  vintage each label belongs to. 3,008 of these. A relabelled code shows both
  readings, because a row filed in 2005 means what the 2005 table said.

Plus `columns.md`, indexing all distinct column names against the systems that
carry them — with the warning that a shared name is not a shared meaning.

Three constraints the generator enforces, each from a way the output failed:

- **No page exceeds 600 KB.** GitHub refuses to render a Markdown file much
  above 1 MB, and SINAN's 2,250 columns came to 1,043 KB — the most exhaustive
  page in the set was the one nobody could open. Oversized pages are split into
  linked parts that repeat their header.
- **No dead links.** A codelist can be *bound* and still have no rows in that
  system, because the dictionary entry lives under a neighbour that shipped the
  same kit. Linking anyway put 49 dead links on the site; the renderer now only
  links pages that were written, and a test walks every link on a generated
  site.
- **Only bound codelists get pages**, and large ones are truncated with a
  pointer to `load_reference()`. Nobody reads three thousand hospital names in
  Markdown; at the original cap the establishment registries alone were 8.8 MB
  per system.

The whole build is **one pass over the dictionary**, not one per system. Asking
per system was sixteen scans of 19.9M rows and ran at roughly a page a second;
hoisted, it is 54 seconds for all 3,036.

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

`verify` runs 15 assertions. They are checks, not opinions:

`check_blob_dedup`, `check_crawl_coverage`, `check_apac_recovered`,
`check_sih_generations`, `check_format_collapse`, `check_dictionary_coverage`,
`check_field_decoding`, `check_detectors`, `check_retired_column_flagged`,
`check_lake`, `check_population`, `check_demas`, `check_describe`,
`check_build_accounted`, `check_stored_labels_agree`.

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
| distinct columns catalogued | 4,354 |
| dictionary rows | 19,905,196 |
| codelists | 10,748 |
| field→codelist bindings | 9,304 |
| systems documented | 18 |
| decodable columns | 2,159 |
| open questions | 1,339 |
| full semantic bundle | 153 MB |
| per-system bundle | ~10 MB |
| generated dictionary pages | 3,036 |
| of which code tables | 3,008 |
| tests | 483 passing |

The headline is the first two rows. The mechanism behind the 82,441-file
difference is stated plainly in `docs/FINDINGS.md` §0.
