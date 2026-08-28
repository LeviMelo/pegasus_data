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
    schema.sql            49 tables (§4)
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
    base.py               DecodedTable/DecodeOutcome, the shape every reader returns
    dbc.py dbf.py text_.py duckdb_.py archives.py lha.py
    header.py             schema from a file prefix
    service.py            shared projection and killable-decode policy for every stage
    isolation.py          a pool of KILLABLE decoder processes (§12.1)
    _worker.py            the other side of that boundary; `python -m` entry point
  profile/
    accumulators.py detectors.py drift.py runner.py
  semantics/
    cnv_parser.py def_parser.py tabkit.py
    dictionary.py         merge, source authority, confidence, provenance
    reference.py icd.py gaps.py ledger.py pdf_harvest.py
    bindings.py           field → codelist, and measuring whether one decodes
    defnames.py           display names off a .DEF, kept apart from descriptions
    curation.py           curation/*.yml → variable_docs; fingerprint refresh (§9.1)
    relations.py          typed relations and reviewable adjudication (§9.3)
  curation/
    ontology.yml          the DECLARED ontology: systems and datasets (§5.4)
    datasets.yml          what one row IS, per dataset
    datasets_sinan.yml    one entry per SINAN agravo
    systems.yml           prefix → system overrides
    codelists.yml         what KIND of thing a codelist is (§14.9)
    joins.yml             declared join keys and their grain (§14.8)
    sources.yml           what every [TOKEN] in a source_ref refers to (§9.2)
    variables/*.yml       per-dataset variable documentation
  normalize/
    engine.py types.py geo.py time.py
  persist/
    lake.py               Parquet layout and partitioning
    reference.py          system- and vintage-scoped code tables
    staging.py            write-then-swap durability for files and trees (§7.5)
    decisions.py          the decision collector: borrowed labels, vintage fallbacks (§8.1)
    duck.py               DuckDB view registration
  sources/
    demas_api.py ibge.py sigtap.py community.py
  ontology.py             declared systems/datasets; binds observations to them (§5.4)
  representations.py      one shared logical-publication selector (§5.3)
  locate.py               five-layer placement resolution (§15)
  labelpack.py            the shipped label pack and bindings (§14.9)
  crosswalk.py            temporal, cardinality-safe identifier enrichment (§14.13)
  geography.py            supramunicipal memberships, compiled (§14.14)
  measures.py             the aggregation algebra and its refusals (§14.15)
  _aggregate.py           aggregate(): persistent analytical cells (§14.15)
  _vintage.py             exact/coarse/unknown source-vintage intervals (§14.13)
  providers.py            resource requirement/provider contracts (§14.13)
  _resources.py           versioned bundled and optional-resource lifecycle (§14.13)
  _query.py               compatibility facade for query internals (§14.13)
  _query_engine/
    model.py              immutable intent, plans, reports and input parsing
    capabilities.py       compiled/local source-publication capabilities
    planner.py            source intent → retrieval/resource plan
    executor.py           lake/fetch/hybrid execution and report assembly
    filters.py            immutable publication competence and source-period selection
    semantics.py          label policy, vintage dimensions and enrichments
    core.py               compatibility exports for the split engine (§14.13)
  render_groups.py        ONE vintage-scoped render path, shared by fetch and load (§8.2)
  _availability.py        present / absent / unknown, per column per year (§14.7)
  textenc.py              encoding detection for the text readers
  _info.py                info(): what a system, dataset or variable IS (§14.5)
  _compendium.py          compendium(): a portable map of DATASUS (§14.6)
  _explore.py             explore(): the shipped map of the tree (§14.1)
  _unknowns.py            gaps(), questions(): what the module cannot tell you (§14.11)
  _dictionary.py          the dictionary for one fetched table (§14.12)
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

One SQLite database, 49 tables, shipped alongside the lake. It is the module's
memory: everything discovered, decided, or left open lives here. Grouped by what
they hold:

- **Discovery** — `files`, `directories`, `file_moves`, `coverage_gaps`,
  `crawl_runs`, `prefix_systems`, `system_disagreements`
- **Identity** — `file_facts`, `strata`, `stratum_members`, `schemas`,
  `families`, `family_files`, `representations`, `representation_conflicts`
- **Acquisition** — `blobs`, `fetches`, `decode_attempts`, `archive_members`
- **Evidence** — `variable_profiles`, `value_frequencies`, `schema_presence`,
  `schema_header_facts`, `schema_drift`, `field_renames`
- **Meaning** — `dictionary`, `field_codelists`, `dictionary_rules`,
  `dictionary_conflicts`, `code_tables`, `tab_kits`, `def_variables`,
  `def_datasets`, `field_documentation`, `ledger`, `semantic_relations`
- **Judgement** — `variable_docs`, `dataset_docs`, `open_questions`,
  `adjudication_items`
- **Output** — `build_outcomes`, `lake_partitions`, `lake_datasets`,
  `population_series`, `api_endpoints`, `api_ingests`
- **Meta** — `schema_version`, `events`, `curation_state`

`curation_state` holds a fingerprint of the shipped `curation/` files. It exists
because curation used to be loaded only into an EMPTY catalog, so every later
correction to the YAML — a new column, a codelist fixed — reached nobody who had
run the package once. See §9.1.

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

**Representation selection is a physical decision, shared by every consumer.**
`representations.py` groups candidates globally by logical publication and
archive member before family execution, then chooses the cheapest directly
readable form (Parquet/DuckDB/CSV before compressed or archive decoding).
Archive members remain separate datasets. If cheap metadata contradicts
equivalence, the selector records a `representation_conflicts` row and normal
runtime/build execution refuses; `on_conflict="all"` is an explicit diagnostic
escape hatch. Both `fetch()` and the lake builder use the global result, so two
schema families cannot each contribute one representation of the same logical
publication.

Measured on the recovered full catalog: **4,422** logical publications have
alternative physical forms, covering 14,446 files. Preference avoids 10,024
redundant physical reads. This is an inventory result, not a deduplication ratio
assumed from suffixes.

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
manual(0) → cnv(1) → layout_doc(1) → def(2) → sigtap(3) → dbf_lookup(4)
          → demas_api(5) → pdf(6) → community(7) → semantic_match(7)
          → inferred(8)
```

`layout_doc` sits beside `cnv`: a published record layout is a primary statement
by the publisher, the same standing as a `.CNV` and above anything extracted.

`semantic_match` is the weakest rung that still points at real evidence, and it
is deliberately a CANDIDATE rather than a claim. It says "this column looks like
it holds the thing that table decodes" — a municipality column against the
municipality table, `SP_COMPLEX` against the complexity table its unprefixed
sibling uses — and it ships at confidence ≤0.6 with `decodes_observed` NULL so
the renderer weighs it against the column's real values and discards it if it
explains nothing (§8). A wrong `semantic_match` therefore costs a measurement,
not a wrong label. One was caught that way: `NATURALMAE` was bound to the country
table on the strength of its description and decoded none of the observed 8xx
values, which are Brazil's UF encoding, so the binding was refused and removed.

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

### 6.6 Projection is pushed into the reader `[D]`

Decompressing a DBC's row stream is unavoidable. Building Arrow arrays for 208
columns when three were asked for is not, and projection used to happen after
the whole table had been constructed. Measured on a real CNES-ST payload, column
construction was **74% of the decode**, and pushing the projection down made a
narrow read **4.1x faster**.

The header still reports EVERY field either way. It is what the family's schema
signature is matched against, so narrowing it would make a projected read look
like a different generation and drop the file.

A projection naming nothing that exists reads everything rather than returning
an empty batch — otherwise a typo becomes a silent empty result.

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

### 7.5 Durability: replace only with something that exists `[D]`

`persist/staging.py`

Every stage that re-derives clears its own output first (§4), and that rule has
a failure mode: between the clear and the write there is a window in which the
artifact does not exist. Disk full, an interrupt or an Arrow raise inside it
leaves nothing where the data was — and for a partition that took a full build
to produce, that is not a retryable inconvenience.

So a replacement is staged beside the target under a unique transaction token
(`{pid}-{uuid}`), written in full, and only then swapped in. The swap is a
rename, which is atomic on both filesystems this runs on, and the previous
artifact is renamed aside rather than unlinked so a failure mid-swap can be
rolled back rather than mourned.

Trees are staged the same way, with `merge_depth` controlling how much of the
existing tree survives the swap. That parameter is load-bearing: the reference
warehouse is laid out `<codelist>/system=<sys>/window=<w>`, and merging at the
wrong depth deleted SIBLING SYSTEMS' tables while replacing one system's. The
test that missed it compared only top-level names.

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

### 8.1 Decisions the renderer makes are collected, not narrated `[D]`

`persist/decisions.py`

Labelling is full of substitutions that are defensible individually and
misleading in aggregate if nobody is told: a code labelled from another system's
table because the requested system ships none; a 1995 request answered from the
current vintage because the pack carries no window that old; a codelist that
decodes only part of the column.

Each of those is recorded in a `ContextVar` collector for the duration of a
render and returned on the report — `borrowed`, `fallback_vintage`,
`partial_codelist_match`, `rollup_used`, `constant` — as machine-readable values
rather than only as prose in `warnings`, so a strict pipeline can refuse them
with a threshold instead of a regex over English.

Cross-system borrowing is **off by default**. A null-system row in the shipped
pack is explicitly system-independent and remains usable everywhere; an actual
foreign-system table is used only under `allow_borrowed_labels=True`, and that
choice is recorded in `RenderReport.borrowed`.

`historical_labels` is the policy attached to the same problem: `"current"`
(default) answers a historical request from today's table and records the
substitution; `"refuse"` returns the raw codes instead. The default is not
neutral and was chosen by measurement — a blanket refusal was tried and took a
fresh-install SINASC 2022 fetch from 15 labelled columns to 0, because the
older shipped pack carried no validity windows. The current pack carries the
windows recovered from the full catalog; fallback still applies where no window
covers the requested period.

### 8.2 One render path, and why it is a module `[D]`

`render_groups.py`

`fetch()` and `load()` both render, and they rendered separately. That is how the
vintage bug in §D-P0-2 could be fixed on one path and remain on the other, and
how an option came to mean one thing in a notebook and another in a file.

The shared unit is a GROUP — `(rows, family, year, competência)` — because
rendering correctly is per-vintage-per-family, not per-result: a request spanning
1995 to 2025 must render each generation against the codelist of its own era, and
a single call cannot. `fetch` and `load` differ only in how they SPLIT their rows
into groups: the lake has a `year` partition column plus internal
`_competencia` provenance for month-exact boundaries, and a fetch has provenance
in `_source_path`. Everything after the split is one implementation.

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

### 9.1 A corrected meaning has to reach an existing catalog `[D]`

Curation was loaded when `variable_docs` was EMPTY, which is true exactly once in
a catalog's life. Everything the shipped YAML gained or corrected afterwards was
therefore invisible to anyone who had run the package before — the wheel carried
the right answer and the catalog kept serving the old one, with nothing saying so.

The catalog now records a content fingerprint of `curation/` in `curation_state`
and compares it on each use: reload when the meaning changed, stay quiet when it
did not. Content, not mtime, because the YAML ships inside a wheel and its
timestamps say when it was unpacked.

The same shape of bug existed for the shipped bindings, which were skipped
whenever the catalog held ANY binding of its own — and curation writes ~900, so a
catalog curated before it was seeded could never receive the other ~8,500. Both
now merge: `field_codelists` is keyed on `(system, family_id, field_name,
codelist)` and the insert is `OR IGNORE`, so a local `semantics` run still
outranks the wheel without costing the rest of it.

### 9.2 A citation has to resolve `[D]`

`curation/sources.yml`

Curated entries cite their evidence as `[ESTRUTURA-SIM] "..."`. Nothing in the
repository said what those tokens meant, so 396 citations across 41 tokens could
not be checked against the documents they came from — and an unverifiable
citation decays into decoration.

`sources.yml` maps every token to a title, publisher, evidence rung and, where one
is vendored, a local path. The documents themselves live in `sources/`, which is
deliberately NOT committed: it is over a gigabyte of Ministry record layouts,
TabWin `.DEF`/`.CNV` packs and extracted evidence, all re-downloadable. The
manifest is committed in their place, so the trail survives in version control
even when the bytes do not.

### 9.3 Relations are typed, and uncertainty becomes work `[D]`

One field can participate in several true relations. `MUNIC_RES` has an
identity label, rolls up to a health region and has an attribute saying whether
the municipality is a capital. These are not interchangeable mappings.
`semantics/relations.py` therefore models `label_of`, `rollup_to`,
`attribute_of` and `crosswalk_to` explicitly, seeded from `curation/joins.yml`
and persisted in `semantic_relations`.

Each persisted row is a temporal assertion with a stable `relation_id`; its
validity window is part of that identity. Adjacent historical decisions can
therefore coexist, while overlapping assertions in the same authority and
semantic slot are rejected. A lossless schema migration preserves legacy rows,
classifying only rows matched by resolved `adjudication_items` decision JSON as
local; other legacy rows are curated compiler output. Reseeding transactionally
replaces the complete curated snapshot and never mutates local assertions.
Schema v4 also repairs catalogs already opened by the faulty v3 all-local
migration using the same evidence rule.

The renderer and query layer only put an identity-level `*_label` beside a raw
code. Roll-ups and attributes require an explicit dimension request. An
overlarge unresolved candidate set creates a stable `adjudication_items` key;
`pegasus-data adjudicate show|export|apply` packages its evidence and records a
reviewed decision. This converts semantic uncertainty into a reproducible queue
instead of a truncated ranking or a silent guess.

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

### 12.1 A timeout has to end the work, not just stop waiting `[D]`

`decode/isolation.py` · `decode/_worker.py`

The per-item deadline above was never cancellation. `run_with_timeout` starts a
daemon thread and joins it with a deadline; on expiry it stops WAITING, which is
all Python can do, because a thread cannot be killed and DBC inflation runs
inside a native extension that never yields. So a file recorded as "abandoned
after 1200s" went on holding a core, an inflated DBF and temporary disk while the
API moved on — and several of those accumulate.

A process can be killed. Decoding runs in a small pool of persistent worker
processes; on expiry the parent kills the worker and starts a fresh one, so
"abandoned" means the work stopped.

Three decisions worth stating:

- **The unit of work is one PHYSICAL SOURCE, not one logical member**, so an
  archive holding seven selected members is opened and inflated once. Killability
  did not cost the optimisation that made archives affordable.
- **Workers are persistent.** Interpreter startup is the one real cost of the
  design, and paying it per file would swamp the decode it protects.
- **Batches are framed individually** across the pipe, so neither side ever holds
  a whole decoded table — the streaming property the in-process path has.

Measured cost of the boundary on a real 208-column payload: Arrow IPC serialise
plus deserialise is **1% of decode**. It runs as `python -m
pegasus_data.decode._worker` rather than through `multiprocessing`, because a
library imported from a notebook, a REPL or a frozen application cannot rely on
the caller having a guarded `__main__`.

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
| Give me an analysis-ready slice. | `query()` · `plan()` | intent planner → lake or fetch → semantics |
| Give me source-shaped rows. | `fetch()` · `load()` | direct retrieval mechanics |
| What does this column mean? | `describe()` · `search()` | ledger, dictionary, curation |
| I already have data — decode it. | `translate()` | the 19.9M-row dictionary |
| What can't you tell me? | `gaps()` · `questions()` | `open_questions`, `coverage_gaps` |
| Per capita? | `load_population()` | IBGE series |
| It will not fit in memory. | `scan()` · `export(stream=True)` | the lake, batch by batch (§14.10) |

The intent-driven `query()` is the front door. `fetch()`, `load()` and
`export()` remain public lower-level mechanics for callers that deliberately
want source-shaped behavior.

Beside them are the entry points that support those verbs rather than answering a
question of their own, and they are public because a caller reaching them through
a private name is a caller the next refactor breaks:

| | |
|---|---|
| `load_settings()` · `Settings` | where things live, resolved through §15 |
| `load_reference()` | one codelist as a table, system- and vintage-scoped |
| `field_coverage()` | which columns a family carries, and in which years |
| `open_lake()` | a DuckDB session with the lake registered |
| `read_manifest()` · `unpack()` | the semantic bundle (§10) |
| `resource_manager()` · `enrichment()` | resource lifecycle and explicit crosswalk requests (§14.13) |

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

**A note on module names.** `explore`, `translate`, `info`, `availability` and
`compendium` are functions whose implementation modules are private —
`_explore.py`, `_translate.py`, `_info.py`, `_availability.py`,
`_compendium.py`. A module named `explore.py` exporting a function named
`explore` collide as attributes of the package: importing the submodule binds it
over the function, and `from pegasus_data import explore` then returns a module,
so calling it raises `'module' object is not callable`. The underscore removes
the ambiguity rather than arbitrating it.

`availability.py` and `compendium.py` were left un-prefixed and had the defect,
which is worse than it sounds because it is ORDER-DEPENDENT and therefore does
not fail for whoever wrote the code. Touching any sibling name — `field_available`
lives in the same module — imports the submodule and shadows the function, so

    pg.field_available(...)   # fine, and imports .availability
    pg.availability(...)      # TypeError: 'module' object is not callable

is a program that breaks because of the order its lines are in.

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

The pack is that layer distilled to **28.6 MB**, carried inside the wheel:

| reduction | effect |
|---|---|
| runs, not enumerations | a `.CNV` says *this range is Brasília*; the ingest wrote out all 10,000 integers |
| one copy across systems | stored once **only** when every system carrying the codelist agrees |
| packed facts split | `CADGERBR` labels are a CNPJ *and* an establishment name in one string |
| registries held back | 90 entity directories |

The current artifact contains 3,654,320 versioned runs across 2,238 codelists;
1,840,269 rows carry an explicit historical boundary. Runs compact 9.1M bound
input rows by 59.8%, without collapsing distinct validity windows.

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
across systems that key on tax identity rather than CNES. The rebuilt temporal
artifact carries 1,774,993 evidence rows in 10.3 MB, shipped separately because
throwing it out with the prose would have been the expensive half of the
decision. Its cardinality audit is in §14.13.

Bindings ship too (9,380 rows, 35 KB). Knowing `I219` is a heart attack is no
help if nothing says `DIAG_PRINC` is coded in CID10.

Rebuilt by `pegasus-data labelpack` after `semantics`. `read_reference_table`
prefers a local lake and falls back to the pack, so a real build always outranks
what shipped.

### 14.10 `scan()` — when the answer does not fit in memory `[D]`

`load()` builds the whole table before returning it, which is right for the
question most callers ask and wrong for the one that ends the session: an
unfiltered national multi-year extract does not fit in memory, and finding that
out costs the whole read.

`scan()` returns a `LakeScan` — a projected schema and an iterator of record
batches — so an export can be written batch by batch. Measured on a real
multi-generation read: **+4.6 MB peak against +27.9 MB** for the eager path.

Two constraints, both deliberate:

- **It does not render.** Choosing a codelist weighs it against the values a
  column actually holds (§8), which is a whole-column question; answering it per
  batch would let two batches of one column disagree. `stream=True` is therefore
  available only with `profile="codes"`, and says so rather than silently
  rendering the first batch's choice across the rest.
- **One file has one header**, so generations that do not share a schema are
  unified up front — first-seen column order, each generation null-filled for what
  it lacks — rather than discovered mid-write. Building the writer from the first
  batch's schema is what made a second generation fail halfway through a file that
  already looked successful.



### 14.11 `gaps()` and `questions()` — what the module cannot tell you `[D]`

`_unknowns.py`

Both were listed in §14's table and reachable only from the CLI. §14's own
organising rule is that every capability the module has internally should be
reachable as a service or it does not really exist, and these were the last two
that were not: a caller in a notebook could read a coverage percentage but not
the list of what was missing from it, which is the half that decides whether an
analysis is possible at all.

`gaps()` ranks undecoded columns by observed ROW MASS rather than by count,
because a column absent from every file matters less than one present in every
row of SIH, and an alphabetical list hides that. `questions()` returns the
recorded `[V]` list — and an empty answer means the catalog recorded none, not
that nothing is uncertain.

### 14.12 `fetch()`'s three shape switches `[D]`

`_dictionary.py`

Three parameters that change what the answer LOOKS like and never which rows
come back. Each existed as a capability the module already had and could not
deliver onto the table it was about.

**`provenance: bool = False`.** `_source_path`, `_blob_sha256`, `_ingested_at`
and `_schema_signature` were attached to every row of every result. They are
constant per source file, so they paid width in every row to repeat what the
report states once, and the default is now off. They are dropped FIRST in the
return path — before the dictionary is built and before renaming — so they can
never be renamed or described as data. `split_by_source()` still needs
`_source_path` and still has it: the drop happens after rendering.

**`names: "original" | "described"`.** `CODMUNRES` becomes `Municipality of
residence`. A column with no curated English name keeps the name DATASUS gave
it, because inventing one makes a column harder to trace back to the layout, not
easier. Collisions are real — two SINAN columns genuinely are both "Municipality
of residence", one current and one historical — so the original name is appended
in parentheses rather than allowing two identically-named columns, which Arrow
permits and no caller wants.

**`dictionary: bool = False`.** One row per column: the English name, the
Portuguese official name, the prose, the reference table that decoded it, and
the evidence rung behind that (§6.3). It reads curation in ONE query rather than
calling `describe()` per column, which at 74 columns is 74 round trips to answer
one question. Label companions and derived columns (`_codes`, `_unmatched`,
`_ibge7`, …) get rows too: a column absent from the dictionary reads as a column
nobody has documented, which is the complaint the dictionary answers.

The switches compose, and the return is a tuple in a fixed order — `(table)`,
`(table, report)`, `(table, dictionary)`, `(table, report, dictionary)`. Order
in the RETURN PATH is load-bearing and is the reverse of what reads naturally:
provenance is dropped, then the dictionary is built against the ORIGINAL names,
then renaming uses that dictionary. Built the other way round, the dictionary
would describe columns under names it had itself invented and lose the only
mapping back.

`RenderReport.codelist_used` was added for this. `labelled` says THAT a column
was decoded; only the table name says whether it was decoded *correctly*, and
`CODMUNRES` sat in `labelled` for the entire period it was being named with
health regions (§22.7). A caller could not see the defect because nothing
reported which table produced the label.

`RenderReport.renamed_headers` was added for the same reason and closes a defect
of its own. The `report` profile translates headers *during* rendering and is
the CLI's default, so the dictionary — built from the rendered table — was
looking up "Mother's age" in a curation layer keyed on `IDADEMAE`, finding
nothing, and emitting a heading with no prose under it. The map is `rendered ->
DATASUS`, and `original_column` on every dictionary row is always the DATASUS
name however many times the column was renamed on the way out.

**Both were found by reading a produced CSV, not by a test.** So was the
`_combine` defect below, and that is the recurring lesson: the suite asserted on
columns and reports and never on the rendered STRING a person opens.

#### A combined value must not repeat a code the label already carries

`--profile report` joins `code – label`, and many DATASUS `.CNV` tables write
the code into the label itself: `BR_MUNICIPALFA` maps `120001` to
`'120001 Acrelândia, AC'`. Combining blindly produced

    120001 – 120001 Acrelândia, AC

in every municipality cell of every report-profile export. `_combine` now skips
the prefix when the label already opens with the code AND the next character is
a boundary — the boundary check is what stops code `12` being swallowed by label
`'120001 Acrelândia'`, where the match is a coincidence of digits.

### 14.13 `query()` and `plan()` — source intent before source mechanics `[D]`

`query()` is a harmonized source-access and semantic-serving facade, not an
epidemiological cohort engine. It accepts a dataset, source `Period`, source
`Geography`, selected fields, identity labels, typed dimensions, explicit
enrichments, provenance and publication-resolution policy. `period` and
`geography` identify DATASUS publication coordinates. Ordinary fact variables
such as `DT_INTER`, `DTOBITO`, `MUNIC_RES` and `MUNIC_MOV` never decide which
observations the core API returns. Their meanings remain in `describe()` and the
semantic ontology for researchers and analytical tools.

Only the implemented `resource_policy="local"` is exposed; resource acquisition
is an explicit operation. `plan()` accepts the same
arguments and returns an immutable `QuerySpec`/`QueryPlan` without executing it;
`explain()` names physical publication resolution, lake-vs-fetch strategy,
hidden dependencies, adaptations and required resources with local status and
estimated source bytes.

```python
from pegasus_data import enrichment, plan, query

kwargs = dict(
    dataset="SIH-RD",
    period=("2022-01", "2024-12"),
    geography="AL",
    select=["CNES", "MUNIC_RES", "DIAG_PRINC"],
    dimensions=["MUNIC_RES.health_region", "DIAG_PRINC.chapter"],
    enrich=[enrichment("CNPJ", from_field="CNES")],
)
print(plan(**kwargs).explain())
table, report = query(**kwargs, return_report=True)
```

`QueryReport` records requested/effective source time, source strategy,
structural absence, semantic relations, crosswalk counts and warnings. The
planner owns these safety rules:

- A monthly request over annual files widens to the enclosing year under
  `time_policy="adapt"` and raises `TimeResolutionWarning`; `"strict"` refuses.
  It never inspects an event-date field to manufacture a monthly subset.
- A UF is applied only when it is a declared and observed physical publication
  axis. Municipality requests, or UFs for nationally published datasets, refuse
  rather than becoming predicates on residence, occurrence or facility fields.
- A fresh-install request that would acquire an unbounded source history refuses
  before retrieval. `allow_unbounded=True` is the explicit expert opt-in; an
  already-complete unbounded local read remains possible.
- Coverage is compiled per selected logical publication and year. A lake year
  is usable only when its recorded `(family, logical publication, archive
  member)` identities cover every expected source unit. New provenance stores
  canonical `path!member` identifiers; legacy path-only provenance proves loose
  files but cannot falsely prove a multi-member archive complete. Complete and
  incomplete years may form a `hybrid` plan, but one
  partially-built year is never split between lake and fetch. Annual/monthly
  resolution is retained per year rather than collapsed with `any(monthly)`.
- Representation reconciliation runs once across all selected families at
  logical-publication scope. An existing conflict blocks even a singleton
  family call; cheap schema/format evidence can open a conflict without scanning
  fact contents.
- Schema evolution is always a union. A selected field absent from one schema
  generation is null-filled and listed in both `QueryReport.structural_absence`
  and Arrow schema metadata; `StructuralSchemaWarning` makes partial structural
  absence visible.
- Raw codes survive. A high-level label is admitted only by an effective
  `label_of` relation; reviewed catalog decisions override shipped curation and
  explicit legacy `variable_docs.codelist` entries are a migration bridge.
  `rollup_to` and `attribute_of` are only produced by `dimensions=`, using
  immutable source-vintage intervals for semantic validity. An exact monthly
  publication supplies `[YYYYMM, YYYYMM]`; an annual publication supplies
  `[YYYY01, YYYY12]`; genuinely unknown provenance remains unknown. A coarse
  interval is resolved only when one effective relation and mapping remains
  valid throughout it. Relation-level
  `valid_from`/`valid_to` windows select historical artifacts with deterministic
  local-over-shipped-over-legacy and dataset/system specificity. If a temporal
  mapping needs a vintage that provenance cannot supply, its derived value is
  null unless the mapping is explicitly time-invariant; “current” is not a
  silent fallback.

`_competencia` is immutable source/publication provenance in this path. It may
select a monthly lake publication and a historical semantic relation, but is
never replaced with an admission, discharge, death or registration date.
`_source_resolution` distinguishes a deliberate annual enclosure from missing
monthly provenance. Mixed-resolution plans retain month pushdown per year.

The execution boundary is explicit:

- runtime planning may read catalog, inventory, schema, publication and resource
  metadata, but not fact rows;
- requested-slice ETL may decode/project/normalize the selected sources, union
  schemas, label, derive requested dimensions and perform explicit enrichment;
- optional resource builds may scan the bounded reference slice the user asked
  to build;
- maintainer build/audit/profiling may perform broad evidence scans.

**Crosswalks are not labels or translations.** `crosswalk.py` implements the
temporal CNES↔CNPJ relation through `EnrichmentRequest`/`enrichment()`. Raw CNPJ
is never overwritten. Placeholder/invalid raw values may produce a unique
`CNPJ_resolved`; agreeing observed values are confirmed; disagreement and
multiple applicable targets become null with explicit status and
`CrosswalkAmbiguityWarning`. Row count cannot change unless `explode=True` is
requested. A direct primitive supplied only `year=2020` evaluates the complete
`[202001, 202012]` interval; it never substitutes January or December. Reverse
CNPJ→CNES uses the same rule and is explicitly one-to-many.

The rebuilt artifact is **10,339,656 bytes and 1,774,993 evidence rows**, with
273,514 CNES and 265,418 CNPJ identifiers. The audit found 951 ambiguous source
windows but **1,816 pairwise-overlapping source relation pairs**, 1,218 CNES
identifiers changing target over time, 12,619 reverse multi-source windows and
**13,923 pairwise-overlapping reverse relation pairs**. These pair counts are
not claimed to be canonical disjoint ambiguity segments. Runtime lookup is a predicate-pushed
Parquet slice over requested identifiers and validity bounds, not a process-wide
Python dictionary. Those are modeled cardinalities, not rows silently won by
sort order.

**Resources have identity and lifecycle.** `resources/manifest.json` records a
resource schema version, content version, build/source identity, checksum, size,
tier and growth budget for every shipped runtime artifact, including compiled
query capabilities.
`resource_manager().status()`, `.ensure()` and `.build()` expose that state;
`pegasus-data resources status|ensure|build` is the CLI equivalent. Tier A is
bootstrap metadata, Tier B is the compact runtime semantic layer, and Tier D is
an optional local registry. `providers.py` gives the planner one
availability/authority/period/estimated-bytes contract. CNES→CNPJ needs only
the bundled compact pack. CNES history (`CNES.ST`) and establishment names are
separate optional resources, with the latter explicitly compiled as
`cnes_registry.parquet` from a maintainer evidence catalog. That compiler is not
presented as fresh-install acquisition and refuses when documentary registry
evidence is absent. Its local manifest records schema ABI, independently
updatable content identity, checksum and explicitly asserted covered years from
verified complete source snapshots; record validity windows never manufacture a
completeness claim. All runtime opens pass through the resource-resolution
interface, `ResourceManager.ensure()`. Lake-backed resources such as CNES history
delegate integrity and completeness to lake catalogs/fingerprints rather than to
the static-pack validator. CNES registry enrichment is driven by the CNES codes
and relevant validity period in selected rows, never restricted by the fact
publication's UF. A query reports a missing requirement before touching the fact
dataset and never starts an unbounded build implicitly.

`ResourceManager`, `ResourceStatus`, `QuerySpec`, `QueryPlan`, `QueryReport`,
`Period`, `Geography`, `EnrichmentRequest` and the warning classes are public so
callers can type, persist and test plans/reports without reaching into private
modules.

### 14.14 `memberships()` — which region a municipality is in `[M]`

`geography.py`

`normalize/geo.py` canonicalises a municipality — six digits to seven, the check
digit, the UF prefix — and stops there. "Which health region is this in" had no
answer, and it is the question nearly every roll-up asks.

It needed no new acquisition. DATASUS publishes each supramunicipal
classification as an ordinary `.CNV` codelist keyed on the six-digit
municipality code, and 139 national ones already ship in the label pack.
`CIRBRN` maps 5,680 municipalities to 478 health regions — and `CIRAC`, the
24-row Acre table that labelled Rio Branco "Baixo Acre e Purus" (§22.7), is one
state's slice of it. So this **compiles**, and the compile is 98,584 rows in
140 KB.

`curation/geography.yml` carries the only irreducible fact — which codelist is
which classification — with the measurement behind each entry. Nine are
compiled: health region, IBGE meso/microregion, colegiado de gestão,
metropolitan region, PNDR region, citizenship territory, agglomeration, capital.

**The compile is deterministic only when scoped by publishing system.** Grouped
by municipality alone, `CIRBRN` looks self-contradictory on 295 municipalities
and `RSAUDBR` on 2,612; adding the validity window changes nothing and adding
the *system* takes every one of them to zero. That is §3e's lesson again — most
of the contradiction was manufactured by the comparison.

What survives is real and splits in two. On `CIRBRN` only **46** of the 295 have
a differently-*named* region; the rest are the same region at a different code
width (`420005 → SIM:42008 | SINASC:4208`, both "SC Meio Oeste"). On `RSAUDBR`
1,944 are genuine, and they are not a disagreement about geography but **two
regionalisations published under one codelist name** — CIH and SINASC on the
older DIRES scheme, SIA and SIH on the named-region scheme.

Three consequences, all of which the API states rather than hides:

* **A roll-up is not system-neutral.** The pack is keyed
  `(municipality, classification, system, window)`. An aggregate over SIH must
  roll up through SIH's regionalisation or its totals will not reconcile with
  DATASUS's own TabNet output. `MembershipSet.conflicts` names any
  classification whose systems disagree instead of averaging them away.
* **Health macroregion is not shipped.** `BR_MACSAUD` conflicts on 66% of
  municipalities and `MSAUDBR` on 4%; neither is usable, and the exclusion is
  recorded with its measurement. Picking one system's answer for two-thirds of
  Brazil would be worse than the gap.
* **Sentinels are members.** `999999 → Ignorado/Exterior`,
  `120000 → Município ignorado - AC`. Folding them into a real municipality is
  the §22.7 error; dropping them biases every count that uses the geography.

This is the first piece of the aggregate layer (`docs/AGGREGATE_DESIGN.md`),
because a safe geographic roll-up is what the frontend contract rests on.

### 14.15 `aggregate()` — analytical cells, built once `[M]`

`measures.py`, `_aggregate.py`, `curation/aggregates/*.yml`

The dominant PegaSUS workload is geography × time → measures, and answering it
from microdata is not viable at request time. Measured: `fetch("SIH-RD",
uf="AC", years=2022)` takes **130 s** for 49,547 admissions; the same rows at
municipality × month × sex × race are **2,417 cells**. Acre is 0.4% of national
SIH volume.

So the artifact is built once and served cheaply. Two surfaces, kept apart:
`build_aggregate()` is a maintainer step whose **only** source of rows is the
ordinary retrieval path; `aggregate()` is filter → pushforward → merge →
finalize over the built cells and touches no microdata.

**What is stored is accumulator state, never a number.** `los_n` and `los_sum`,
not a mean. Writing down a mean destroys the state, and the state is the only
thing that can be merged. `docs/AGGREGATE_ALGEBRA.md` derives this; the short
form is that roll-up is *pushforward along a map of key spaces*, valid exactly
when the measure is a commutative monoid and the map is a total single-valued
function. Every refusal below is one of those two failing.

**Marginalising an axis is not a special case.** "Total" is the pushforward to a
one-point space — the same operation as municipality → health region with a
smaller target. An axis the caller does not name is totalled, which is what makes
the SIDRA-shaped output fall out rather than needing to be built.

**One base cuboid.** Every view derives from the single materialised finest
table. Computing "sex = Total" independently would let it disagree with the sum
over sex — different retrieval moments, different vintages — and a table whose
total is not the sum of its parts discredits everything else on it. Verified on
live data: Total = 49,547 = the sum of its sex categories exactly.

**It consumes what already exists.** `semantic_axes` supplies the geography and
time bindings — a spec names `residence`, not `MUNIC_RES`, because which
municipality column a dataset means is a question about the analysis and curation
already answers it (§3l kept those axes for exactly this). `field_available()`
supplies the support mask. `geography.memberships()` supplies the spatial
pushforward. `_resources.py` supplies the fingerprint pattern.
`persist/staging.py` supplies the atomic swap. Nothing here re-implements any of
them.

**Identity includes semantics.** The fingerprint covers the spec, the source
blob digests, the curation fingerprint, the engine version **and the
`geography.parquet` checksum** — because changing that changes every
health-region roll-up derived from the artifact, and one that does not notice is
stale in a way nobody can see.

The refusals are the product:

| situation | behaviour |
|---|---|
| measure not additive along a requested axis | refused, naming the axis and the reducer that would work |
| `count(entity)` on an entity-period grain | refused, naming both honest alternatives |
| median or percentile | refused — no finite-state associative merge exists |
| partial classification | served, with the unmapped mass **reported** |
| contested municipality, no system named | served, flagged; naming a system clears it |
| multi-valued dimension under a grain count | refused, offering `count(mentions)` |

**It is not event-centric, and that was tested rather than asserted.** CNES.ST
is one row per establishment per month — a stock observed repeatedly, where
SIH.RD is an event stream. Extending to it needed a spec and no code: both
differences were already refusals. `COUNT(*)` there counts establishment-months,
so a measure declaring `unit: establishment` is refused against the grain; and
`QTINST*` is capacity at an instant, declared additive over geography and
dimensions but not over time, so summing rooms across months is refused rather
than returning "room-months".

Correctness was checked against a direct `GROUP BY` on live SIH-RD/AC/2022:
2,417 cells, identical key sets, **zero disagreeing cells**, and totals
reconciling to the microdata row count. Rolling up to `metropolitan_region`
reported 49,477 of 49,547 unmapped rather than returning 70 admissions as if
they were a national figure.

## 14a. What ships, and what does not

A package is not a data lake. The rule is: **ship what makes the module
functional out of the box, and nothing that is derived, large and reproducible.**

**Ships (41,705,449 bytes / 39.8 MiB of Parquet):**

| | size | why it must |
|---|---:|---|
| `resources/tree.parquet` | 1.29 MB | `explore()` on a fresh install, offline. The module's most distinctive asset, and the reason it is worth 1 MB. |
| `resources/families` + `schema_presence` | 0.05 MB | answers "does 2008 have `DIAG_SECUN`" without downloading a byte |
| `resources/labels.parquet` | 29.97 MB | 3,654,320 versioned label runs; offline identity labels |
| `resources/labels_crosswalk.parquet` | 10.34 MB | temporal CNES↔CNPJ evidence, without the full establishment directory |
| `resources/bindings.parquet` | 0.04 MB | declares which codelist can decode each field |
| `resources/query_capabilities.json` | 0.001 MB | compiled source publication resolution/geography capabilities; curation is authoritative |
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
| optional CNES name/history resources | bounded by requested period | `pegasus-data resources build cnes_names` or `... build CNES` |
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
absent rather than half-written.

Placement resolves through five layers, highest first: an explicit `root=` or
`--root`, an environment variable, the nearest project `pegasus-data.toml`, the
per-user config file, then a default that adopts a data home already in use at
or above the working directory rather than following the working directory
blindly. `root`, `blobs`, `lake`, `work`, `catalog` and `curation` are each
separately placeable, because a rebuildable write-heavy cache and a queryable
lake do not want the same disk. Every resolved path records the layer that
decided it (`pegasus-data where`).

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

**This table is the project's bookkeeper.** Every count about what exists lives
here and nowhere else. `docs/RESUME.md` says what to do next, `docs/FINDINGS.md`
what measurement contradicted, §22 what is claimed on thin evidence, `docs/DEFECTS.md` what was broken and is now fixed — none of them
carry counts, because when they did they drifted. §21 read "1,572 described
(34.7%)" beside 538 tests while RESUME read "4,528 (100%)" beside 601, and a
reader had no way to tell which was current. The test count is stated beside the
numbers as the cheapest available clock.

Counted on the shipped artifacts, not estimated. **As of 1,184 tests passing.**

### Storage evidence

`scripts/storage_report.py` uses SQLite `dbstat` and exact row counts; it is
read-only and produces machine-readable JSON. On the recovered full catalog the
14,995,771,392-byte file had no freelist: the size is live expansion and B-tree
duplication, not stale SQLite pages. `code_tables` occupied 6.10 GB for 11.91M
rows (512 bytes/row), `dictionary` 3.98 GB for 21.29M rows (187 bytes/row), and
their primary/lookup indexes another 4.13 GB. The claim that “SQLite costs 15
GB” is therefore rejected; the maintainer warehouse stores expanded evidence
and repeated indexes. Runtime artifacts are compiled projections and total
41,705,449 bytes under the 47,185,920-byte manifest budget.

### The tree

| | |
|---|---:|
| files crawled | 207,251 |
| files the prior scan found | 124,810 |
| data files bound to a declared dataset | 207,030 (100%) |
| systems · datasets declared | 20 · 131 |
| strata · with a known schema | 4,418 · 3,688 |
| distinct schemas | 273 |
| families (system × series × schema) | 1,633 |

### Meaning — what a column IS

| | |
|---|---:|
| distinct columns catalogued | 4,528 |
| **columns described** | **4,528 (100%)** |
| curation entries · files | 4,534 · 108 |
| datasets with `what_one_row_is` | 131 (100%) |

`catalogued` is a MOVING denominator — it is the columns the census knows about,
and the census grows. That is not pedantry: this line read 100% while SIH-RD had
15 of its 117 columns described, because the census had reached families the
description waves never covered. Re-measure rather than trusting the number.

### Meaning — what a VALUE decodes to

| | |
|---|---:|
| label pack | 3,654,320 versioned runs · 2,238 codelists · 30.0 MB |
| CNES↔CNPJ crosswalk | 1,774,993 temporal evidence rows · 10.34 MB |
| field→codelist bindings shipped | 9,796 |
| bindings by rung | def 8,548 · manual 534 · community 315 · semantic_match 298 · layout_doc 101 |
| columns curation declares as code-bearing | 2,157 |
| **… reaching a codelist that ships** | **2,070 (96.0%)** |
| … bound to a registry the pack holds back BY DESIGN | 19 |
| … with no binding at all | 68 |

The 19 are not a gap, and saying so is what `curation/codelists.yml`'s ROLES
are for. They are CNES establishment and team registries — `CADGER*`, `TCNESBR`,
`INE_EQUIPE*`, `HOSFEDRJ` — plus two CNPJ columns that reach CNES through the
shipped crosswalk rather than through a label table. §14.9 holds all of those out
of the pack deliberately; they are reached through `fetch("CNES-ST")` and the key
declared in `joins.yml`. Each is bound to the directory it belongs to anyway,
because naming WHICH registry is the useful half of the answer even when the
table is deliberately absent — and at confidence 0.35, so it can never outrank a
table that does ship.

Reporting these as undecodable was conflating "no table ships" with "no table
should ship", which is the distinction the roles exist to draw.

The 68 that genuinely do not decode are not merely undone; the reasons are in
§22.1b. `semantic_match` bindings are CANDIDATES at
confidence ≤0.6 with `decodes_observed` NULL — the renderer weighs each against
the column's real values and discards what explains nothing, so a wrong one
costs a measurement rather than producing a wrong label.

### Elsewhere

| | |
|---|---:|
| dictionary rows (full catalog, not shipped) | 19,905,196 |
| open questions, recorded not guessed | 1,339 |
| full semantic bundle · per system | 153 MB · ~10 MB |
| dictionary database | 531 MB, 7.47M codes |
| vendored source documents (`sources/`, gitignored) | 11,379 files, incl. 2,563 `.CNV` |

The headline is the first two rows of the tree table. The mechanism behind the
82,441-file difference is stated plainly in `docs/FINDINGS.md` §0.

`docs/FINDINGS.md` records what we measured that contradicted an assumption.
**§22 below records the opposite** — claims this project makes that are NOT
well-evidenced, ranked by how much damage a wrong one would do, each with what
would settle it. A project whose pitch is that it says what it does not know
owes the reader that list, and owes it in the same document as the claims.

---

## 22. What we are least sure of

`docs/FINDINGS.md` records things we measured that contradicted an assumption.
This section records the opposite: **claims this project makes that are not
well-evidenced**, ranked by how much damage a wrong one would do.

It sits in this document rather than beside it because it is not a different
subject. A reader who opens the architecture to learn what the system does
should meet, in the same place, the parts of that description the evidence does
not fully carry. Kept separate, it drifted: decode coverage ended up filed here
as a doubt, disagreeing with the counts in §21, which is exactly the failure §21
now guards against.

Every entry states what would settle it. Delete an entry when it is settled; do
not soften one because it is uncomfortable.

### 22.1 Variable descriptions rest largely on inference, self-audited

**Claim made:** 4,528 columns described, "100% coverage".

**What is actually behind it:** of 4,298 curation entries, **1,799 carry
`source: inferred`** — reasoning from column name, observed values and
neighbouring fields, not a document. The remainder cite a layout document, a
`.DEF`, or the web.

**Why it is the top entry:** a wrong description is worse than a missing one.
A missing description makes an analyst go and look; a confident wrong one does
not. And the audit that cleared these was written by the same author as the
descriptions — an internal vagueness pass flagged 489 entries and then
reclassified 433 of them as acceptable. Nobody independent has reviewed any of
it.

**What would settle it:** a domain reviewer sampling ~100 `inferred` entries
against the paper forms and layout documents, and reporting an error rate.

### 22.1b The columns that still do not decode

**Claim made:** the module decodes DATASUS's codes.

**What is actually behind it:** most of them; the count is in §21. What belongs
here is why the remainder is hard — and, twice now, why it was not.

Two blockers recorded here turned out not to be blockers, and both failed the
same way: the obstacle was asserted rather than tried.

- SINAN was recorded as needing `TAB_SINANNET.zip` parsed per agravo, treated as
  unavailable. It is 44 MB on the same FTP tree this package crawls, carrying 626
  `.CNV` tables and 60 `.DEF` files — and a `.DEF` is exactly the per-agravo
  field-to-table statement said to be missing.
- SISCAN was recorded as needing INCA's forms because `TAB_SISCAN.rar` is RAR5
  and no extractor was available. 7-Zip was already installed on the machine. The
  kit holds 103 `.CNV` tables whose TITLES name the columns outright — "Atipia em
  celulas escamosas", "Celulas atipicas de significado indeterminado-escamosas",
  "Periodo do Preventivo" — so the mapping is DATASUS's own title against
  DATASUS's own column label, not a guess.

A third obstacle was real and internal: the `.DEF` parser matched only
upper-case usage markers while TabWin writes them in either case, discarding 881
of 22,675 variable lines as "unrecognised marker" and with them every binding
they declared.

**What is genuinely left:**

- **RESP** — no laboratory-result table exists anywhere on the tree for it.
- **SINAN** — agravo-specific spaces where one column name means different things
  on different forms. `TIPO_ACID` is `1 típico / 2 trajeto` on the work-accident
  dictionary and `01 administração de medicação endovenosa …` on the
  biological-exposure one; 21 columns were refused outright during the harvest
  for exactly that, because a merged table would label a typical accident as an
  IV administration.
- **SIA** — APAC sub-form columns, and CNES references that are registries.
- **PCE · ESUSNOTIFICA · SINASC** — per-state or non-DATASUS spaces: health
  districts are defined by each state, DRS is a São Paulo structure, Febraban
  bank codes are not DATASUS's to publish.

**What would settle it:** per-agravo (family-scoped) bindings for the SINAN
columns whose meaning genuinely varies — `field_codelists` can already express
that through `family_id` and nothing yet populates it; and for RESP, a source
that does not currently exist.

### 22.2 SINAN wave-1 descriptions were never checked for correctness

**Claim made:** 366 SINAN variable descriptions are documented.

**What is actually behind it:** they were produced in a first pass, then
subjected to a *vagueness* pass — is this sentence specific? — and never to a
*correctness* pass against the SINAN notification forms.

**What would settle it:** compare a sample against the agravo's own
`ficha de notificação`, which DATASUS publishes as PDF.

### 22.3 Binding decode rates are computed on a partial sample

**Claim made, previously stated too strongly:** "35.2% of bindings decode
nothing at all."

**Why that overstates it:** the decode rate is measured against the value
profile, which covers **4 systems** and only the **200 commonest values** per
column. A codelist may decode values we have never observed. The defensible
statement is *"decodes none of the values observed so far"*, and observation is
thin.

**What the evidence does support**, from a real `fetch("SIH-RD", uf="AC",
years=2023)`: `CNES` has **31 codelists bound to it** — `TCNESBR`, one per
state, plus three federal-hospital tables — all from `.DEF` at confidence 0.9,
with nothing ranking them. The renderer picked `HOSFEDRJ` (federal hospitals in
Rio de Janeiro) for Acre data. So the common failure is **over-binding with no
ranking**, not a wrong claim.

**What would settle it:** run `measure_bindings` after widening the value
profile beyond 4 systems and beyond the top 200 values.

### 22.4 Declared join grain is partly unmeasured

**Claim made:** three join keys declared — `AIH`, `CNES`, `APAC`.

**What is actually behind it:** all ten `APAC` members carry
`rows_per_key: unmeasured`. The key was declared without checking whether each
dataset holds one row per APAC or many — which is precisely the fan-out error
the declaration exists to prevent. `AIH` and `CNES` grains come from curation
statements, not from counting.

**What would settle it:** count distinct keys against row counts on a real
sample of each dataset.

### 22.5 Exhaustiveness is true of one crawl

**Claim made:** 207,030 data files, 100% bound to a declared dataset.

**What is actually behind it:** one crawl, at one moment. DATASUS has
reorganised its tree before and will again. The claim is *"nothing on the tree
as we last saw it is unaccounted for"*, which is weaker and is the honest form.

**What would settle it:** nothing permanently — it needs re-checking each crawl,
which verify step 17 does.

### 22.6 The lake has barely been exercised

**Claim made:** the pipeline decodes DATASUS into a queryable lake.

**What is actually behind it:** verify step 14 skips with "no build has been
run against this catalog". Value profiles exist for 4 of 20 systems. Most of
the decode path has been exercised by tests and by single ad-hoc runs, not at
scale.

---

### 22.7 Known-bad, already diagnosed

These are not uncertainties — they are defects with a cause, listed so they are
not rediscovered.

**~~Labels are refused on columns the dictionary can decode.~~** *Wrong, and
worth recording as wrong.* I read a fetch report as "36 of 142 columns
unlabelled, including `DIAG_PRINC`" and blamed the §6.2 width rule. Neither
half held up: `DIAG_PRINC` **is** labelled — the label arrives in a companion
column, `DIAG_PRINC_label` — and most of the rest are empty. `CID_MORTE` holds
`'0000'` in 59,835 of 59,835 rows and `DIAGSEC3` is null throughout, so
"matched none of the observed codes" was correct behaviour reported badly.
Those columns are now named as `constant` rather than filed beside real gaps.

The real defect on that path was different: `_bindings` picked one codelist per
column and the last tie-break was alphabetical, so `CNES` got `HOSFEDRJ` — six
federal hospitals in Rio — while `TCNESBR` sat in the same lake with 7,189 rows
covering every code in the file. Fixed by measuring candidates against the
column. After both changes: 41 labelled, 23 constant, 9 genuine gaps, and the 9
are dates, identifiers and day-counts that `.DEF` should never have bound.

**~~`fetch(labels=True)` cannot work on a fresh install.~~** *Closed.* The wheel
now carries a 28.6 MB windowed label pack and the bindings, and a clean-machine
`fetch("SIM-DO", uf="AC", years=2022)` returns 56 labelled columns. See
ARCHITECTURE §14.9. Along the way this turned up a crash on the same path:
`_discover` unpacked `list_directory`'s `(entries, method)` tuple as a bare
list, so *every* fresh install died before reaching the labelling question at
all — which is what comes of never running the user's own first command.

**~~A label can be broader than the column it decodes.~~** *Closed, and the
diagnosis is worth keeping because every layer behaved as designed while
producing a wrong answer.* `.DEF` binds SINASC's `CODMUNRES` to **145 tables**,
all at confidence 0.9, one of which is `CIRAC` — a 24-row health-region table
containing every municipality code mapped to the region that contains it.

Four correct mechanisms composed into a wrong result:

1. `_rank` breaks a confidence tie on name affinity, then **alphabetically**.
   No table is named `CODMUNRES`, so with 145 candidates tied the tie-break that
   actually decided the answer was alphabetical order.
2. `CIRAC` sorts 3rd. `BR_MUNICIPALFA` sorts **118th**.
3. `_choose_binding` historically measured only the first `_MAX_CANDIDATES`
   (12) candidates — a cost bound, since `.DEF` binds `DIAG_PRINC` to 114 tables.
4. So the correct table was bound, never loaded, never measured. `CIRAC`
   decodes 100% of municipality codes and won.

The runtime now refuses any uncurated candidate set larger than that bound;
the cap can no longer silently become the choice. The granularity tie-break
(§22.7, `CNES → HOSFEDRJ`) was the fix for exactly
this shape and could not fire, because it only ranks candidates that were
*measured*. The rollup guard did fire, and named the problem in a warning —
which is not the same as not doing it. A caller who did not read warnings got a
region where they asked for a city.

**The fix is that the link is stated, not inferred.** The variable → decoder
link is a static build object, so a municipality column names its table in
curation and ranking never decides the answer. 167 corrections across 36
curation files: 128 columns onto `BR_MUNICIPALFA` and 12 onto `BR_MUNICGESTOR`.

Two further defects surfaced in the same sweep, both of which silently produced
an *empty* label column rather than a wrong one:

* **56 curated references named a codelist that does not ship** — `ibge_municipio`
  on 30 columns, and the prose placeholder `'..._MUNICIP (per-UF IBGE
  municipality lists)'` on 6. A curated list bypasses measurement by design
  (§14.12), so a misspelled table does not fall back to a bound one; it decodes
  nothing, with no error.
* **Per-UF lists on national columns.** `SIM.MUNIRES` named `AC_MUNICIP` —
  Acre's 32 municipalities — and `SINASC.MUNI_MAE` named `BR_CAPITAL`, a list of
  capitals. Not rollups; simply the wrong 0.6% of the country.

`BR_MUNICIPALFA` is the municipality table: 5,642 exact keys at 0.992
granularity, accented, and UF-suffixed so the ~250 city names shared across
states stay distinct. `BR_MUNICGESTOR` is the same list plus the "UF0000 —
gestão estadual" sentinels, which is why the `*_GESTAO` columns use it.
`MUNICBR` remains bound as a secondary: 41% of its rows are ranges, but it alone
carries the 62 pre-1988 Goiás codes transferred to Tocantins.

Verified on real data, not on a fixture: `fetch("SINASC-DN", uf="AC",
years=2022)` returns `120040 → 'Rio Branco, AC'` across 5,353 rows, with zero
unlabelled municipality cells and zero rollup warnings.
`tests/test_municipality_never_labels_a_region.py` holds it.

**The catalog is ~200× larger than its information content.** `SIASUS.MUNICBR`
holds 5,728 distinct labels — about Brazil's municipality count — as 280,004
enumerated codes across 4 stored vintages. One `.CNV` rule for "Brasília"
becomes 10,000 rows. This is why a semantics rebuild takes over an hour and
holds a write lock that blocks `curate` and `fetch`.
