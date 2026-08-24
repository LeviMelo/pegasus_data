# pegasus_data

**Brazil's national health data, with its meaning attached.**

DATASUS publishes the administrative record of a health system serving 215
million people — 207,251 files, thirty-five years, twenty information systems —
and publishes almost nothing that explains it. There is no index of what exists,
no machine-readable schema, and no data dictionary a program can consume. The
meaning is real but scattered: in `.CNV` files written for a DOS tabulation
program, in scanned PDFs, in the naming of directories, on a ministry portal that
is not the FTP server.

This turns that tree into a queryable, self-describing, typed data lake — and,
more to the point, makes what the data *means* readable: which classification a
column draws on, which vintage of that classification applies to the year you are
reading, which columns are still emitted but dead, and which of it nobody has
been able to document.

> A number you cannot trace is worth less than no number.

```python
from pegasus_data import info, query

info("SIH.RD")                                  # what is this dataset?
df = query("SIH-RD", period=2023, geography="AL")  # retrieve this publication slice
```

---

## Contents

- [Install](#install) · [Five minutes](#five-minutes)
- [The data model](#the-data-model) — systems, datasets, schema generations,
  column validity, join keys
- [The API](#the-api) — `query` · `plan` · `info` · `explore` · `fetch` · `load` · `availability` ·
  `describe` · `translate` · `search` · `export` · `compendium` · `pack`
- [The command line](#the-command-line)
- [How it works](#how-it-works) — the pipeline, and where things live
- [Why you can trust it](#why-you-can-trust-it) — the rules that are not stylistic
- [Working offline](#working-offline)
- [Where this stands](#where-this-stands) — measured, not estimated
- [Documentation](#documentation) · [Contributing](#contributing)

---

## Install

Python 3.11 or newer.

For a published release:

```bash
pip install pegasus-data          # library and CLI
pip install "pegasus-data[all]"   # + PDF, Excel, RAR and Polars support
```

Maintainers working from a clone use an editable installation instead:

```bash
pip install -e .                  # core
pip install -e ".[all,dev]"       # all readers plus tests and quality tools
```

The wheel includes the reviewed ontology, curation, source map, query
capabilities and compiled semantic packs. It does not include downloaded fact
data, a local catalog, or a data lake. See the
[release procedure](https://github.com/pegasus-sus/pegasus-data/blob/main/docs/RELEASING.md)
for the artifact and clean-install checks run before publication.

### Where the data goes

```bash
pegasus-data where                    # what is in effect, and which layer decided it
pegasus-data config set --root D:/datasus
```

Five layers decide a path, highest first: `--root` on the command, an
environment variable, the nearest `pegasus-data.toml` walking up from where you
are, the per-user config file, then a default that adopts a data home already
in use at or above the working directory. `pegasus-data where` prints the
winner and the reason, because working that out by elimination is miserable.

The cache and the lake do not have to share a disk — the blob store is large,
rebuildable and write-heavy, while the catalog is small and wants to be fast:

```bash
pegasus-data config set --root D:/datasus --blobs E:/cache/blobs --catalog C:/fast/cat
```

`--user` writes the per-user file instead of a project one. Nothing is moved;
setting a path tells future commands where to look, so relocate existing data
yourself first.


---

## Five minutes

### Ask what exists

```python
from pegasus_data import info

info()                    # every system, with file counts
info("SIH")               # the system, and the datasets under it
info("SIH.RD")            # identity, coverage, schema generations, gotchas
```

`info("SIH.RD")` prints something like:

```
dataset: SIH.RD — Reduced AIH
  AIH Reduzida

  One row per approved admission, carrying the fields common to all AIHs.
  This is the dataset almost every SIH analysis actually uses.

  coverage: 18,986 files · 1992–2026 · 20 schema generations
  columns: 126/126 described (100%)

  one row is:
    one billing episode (AIH), NOT one patient
    unit of analysis: admission

  gotchas:
    - One patient readmitted three times is three rows. There is no stable
      patient key.
    - DIAG_SECUN is present and dead from the 113-column generation onward,
      filled with '0000'.
    - VAL_TOT is nominal reais at billing time, never deflated.

  schema generations (20), oldest first:
    1992–1993     35 cols     648 files
    1994          39 cols     323 files
        +4 CEP MUNIC_RES US_RN VAL_RN
    ...
```

Mistype it and it helps rather than sulks:

```python
info("SIH-RDD")     # → Did you mean: SIH.RD, SIH.RJ, SIH.CH?
info("quimio")      # → Did you mean: SIA.AQ?
info("dengue")      # → Did you mean: SINAN.DENG?
```

### Ask for data

```python
from pegasus_data import enrichment, plan, query

request = dict(
    dataset="SIH-RD",
    period=("2022-01", "2023-12"),
    geography="AL",
    select=["CNES", "MUNIC_RES", "DIAG_PRINC"],
    dimensions=["MUNIC_RES.health_region", "DIAG_PRINC.chapter"],
    enrich=[enrichment("CNPJ", from_field="CNES")],
)
print(plan(**request).explain())
df, report = query(**request, return_report=True)
```

`query()` is the primary harmonized source-access interface. It chooses an existing lake or a
bounded direct fetch—or a non-overlapping year-level hybrid—only after checking
that every expected logical source unit (including archive member) is covered. It unions schema generations
with structural nulls, preserves raw codes, admits only explicitly declared
identity labels, and makes dimensions/crosswalks explicit. `period` and
`geography` identify DATASUS publication coordinates; they never filter ordinary
record variables such as `DT_INTER`, `DTOBITO`, `MUNIC_RES` or `MUNIC_MOV`.
When a source is annual, a monthly request retrieves the enclosing annual
publication with `TimeResolutionWarning` and does not remove rows by event date.
For semantic validity that source carries the coarse interval January–December;
a dimension or crosswalk resolves only when one mapping is safe for the entire
year. Pegasus never manufactures a December competence from a bare `year`.
Semantic options append information to the selected observations; use pandas,
Polars or DuckDB when defining an analytical cohort. A query that would acquire
an unbounded history is refused unless `allow_unbounded=True` is explicit.

`fetch()` remains the direct source-shaped interface:

```python
from pegasus_data import fetch

df = fetch("SIH-RD", uf="AL", years=2023)
```

```bash
pegasus-data get SIH-RD --uf AL --years 2023 --out sih_al_2023.csv
```

That downloads what it needs, decodes it, normalises it and labels it. There is
no lake to build first and nothing is written to Parquet. A system the catalog
has not seen triggers a crawl of **that system's directory only**, which is
recorded, so the second call is free.

It never hands back a short table quietly:

```python
df, report = fetch("SIH-RD", uf="AL", years=[2022, 2023], report=True)

report.years_missing      # years DATASUS publishes nothing for
report.undecoded          # files that would not open
report.schema_mismatch    # files whose columns did not fit their family
```

CNES↔CNPJ uses the bundled temporal crosswalk and does not require the full CNES
registry. Larger optional attributes are planned as explicit resources; inspect
their cost before building them:

```bash
pegasus-data resources status --json
pegasus-data resources ensure cnes_names --period 2022-01:2024-12
pegasus-data resources build cnes_names --years 2022-2024
```

`cnes_names` currently compiles a bounded artifact from a maintainer evidence
catalog; it is not yet a fresh-install downloader. Ordinary users install a
compatible precompiled resource. `resources build CNES --years ...` is the
separate bounded acquisition/materialization path for CNES history. Neither runs
implicitly during `query()`. The `--years` scope is also the explicit completeness
claim for a names pack; record validity windows are not treated as proof that a
directory snapshot is complete. Compatible resource packs may carry newer
content than the installed wheel—the schema ABI, manifest identity and checksum,
not an equal content timestamp, determine reader compatibility.

### Ask for it in your own language

`CODMUNRES` is not a column name anyone can read, and the English name was in
the package the whole time with no way to get it onto the table:

```python
df = fetch("SINASC-DN", uf="AC", years=2022, names="described")
# 'Municipality of residence' instead of 'CODMUNRES'
```

A column with no curated name keeps the name DATASUS gave it — inventing one
would make it harder to trace back to the layout, not easier.

### Ask what every column in *this* table means

```python
df, dictionary = fetch("SINASC-DN", uf="AC", years=2022, dictionary=True)

dictionary.write("sinasc_dictionary.md")   # or .csv, .json, .parquet
```

One row per column of the table you actually got: the English name, the
Portuguese official name, the prose, **which reference table decoded it**, and
the evidence rung behind that. The reference table matters more than it sounds —
`labelled: yes` says a column was decoded, and only the table name says whether
it was decoded *correctly*.

```bash
pegasus-data get SINASC-DN --uf AC --years 2022 \
  --out births.parquet --dictionary births_dictionary.md
```

### Provenance is off by default

`_source_path`, `_blob_sha256`, `_ingested_at` and `_schema_signature` are
constant per source file, so carrying them on every row costs width to repeat
what the report says once. Ask when you want byte-level traceability:

```python
df = fetch("SINASC-DN", uf="AC", years=2022, provenance=True)
```

### Ask what a column means

```python
from pegasus_data import describe

describe("SIHSUS", "RD", field="DIAG_PRINC")
```

> CID-10 code for the condition that motivated the admission. Stored without the
> dot: J18.9 is written J189. Older records carry CID-9 instead.

---

## The data model

Four levels, and the distinction between the first two is the one that matters.

```
system        SIH        an information system, as the Ministry runs it
  dataset     SIH.RD     one of its published datasets — the "subfamily"
    schema    113 cols   a generation of that dataset's columns
      variable DIAG_PRINC  a column, with its meaning and codelist
```

### Systems and datasets are *declared*, not derived

"SIH publishes a dataset called AIH Reduzida, known as RD" is a fact about how
the Ministry of Health organises itself. It is true whether or not the FTP server
expresses it, and it survives DATASUS reorganising the tree. That declaration
lives in [`curation/ontology.yml`](src/pegasus_data/curation/ontology.yml) —
**20 systems, 131 datasets** — and the FTP layout is *evidence* for it, never its
definition.

The two demonstrably come apart, which is why the separation is not academic:

| | what the tree shows | what is true |
|---|---|---|
| one file, many datasets | `SIASUS/APAC/2002/acac0201.exe` | seven datasets, as seven DBF members |
| one dataset, many locations | `SIASUS/…AB…` and `Dados_Abertos/APAC_AB` | one dataset, `SIA.AB` |
| one dataset, many names | SINAN `DENG`; open-data `dengue` | one dataset, two representations |

A **binding** layer attaches what the crawler saw to what is declared, and
records *which rule fired* so the mapping is auditable. It has to be more than a
string match: `series` is derived from filenames, so one dataset is spread across
many spellings of itself — SIA's monthly production appears as `PA` but also as
`PASP2509A`, `PAMG2101B` and 700-odd other whole filenames.

**Every one of the 207,030 data files binds to a declared dataset.** That is
regression check 17, not a measurement someone remembers taking. The other 221
files are `.CNV`/`.DEF` codelists, record layouts and legislation PDFs — the
support layer the dictionary is built *from*, counted separately so a real gap
cannot hide among them.

### Schema generations are first class

A dataset is not one schema with exceptions. SIH-RD has **20 measured
generations** spanning 35 to 114 columns and 1992–2026, and `info()` shows what
each one added and dropped:

```
1998   41 cols   +7 CAR_INT DIAG_SECUN GESTAO MARCA_UTI…; -8 DIAG_SEC SEMIPLEN…
1999   52 cols   +11 CID_NOTIF CONTRACEP1 CONTRACEP2 GESTRISCO INSTRU
```

"113 columns, 2014–2025" tells an analyst nothing. "+6, −1 at this boundary" is
what decides whether years either side can be pooled.

### Structural absence is not missingness

`SIH-RD`'s nine secondary-diagnosis columns do not exist before 2014. Ask for
`DIAGSEC4` in 2007 and you get nothing — not because nobody recorded a secondary
diagnosis, but because there was nowhere to put one. Read as clinical
missingness it quietly corrupts anything spanning the boundary.

```python
field_available("SIH-RD", "DIAGSEC4", 2007)   # "absent"  — the column did not exist
field_available("SIH-RD", "DIAGSEC4", 2024)   # "present"
field_available("SIH-RD", "DIAGSEC4", 2017)   # "unknown" — nothing decoded for that year
```

Three states, not two. `absent` is a **positive claim**: a decoded schema for
that year exists and does not carry the column. `unknown` means the catalog is
silent and no claim is being made — which a `valid_from`/`valid_to` interval
cannot express without inventing one.

`availability("SIH-RD").changed_at()` lists every year a column arrived or left:
the boundaries a longitudinal study has to choose around.

### Labels come with the package

`fetch(labels=True)` translates on a fresh `pip install`, with no crawl, no
build and no network beyond the data itself:

```
CAUSABAS   I46.1 Morte subita cardiaca descrita desta forma
CODMUNRES  120017 Capixaba
PARTO      Vaginal
RACACOR    Parda
```

The wheel carries a distilled, versioned label pack — 28.6 MiB and 3.65M runs,
with `valid_from`/`valid_to` retained while code ranges are compacted. A local
`semantics` build always outranks it. Foreign-system codelists are refused by
default; `allow_borrowed_labels=True` is an explicit, reported opt-in.

Two things it deliberately does **not** carry. Entity directories — 687,789
health establishments — are reached with `fetch("CNES-ST")` and the declared
CNES join key instead. And a label broader than the column it decodes is used
but named: where the only bound table for a municipality column is a
health-region rollup, the report says so rather than quietly reporting Rio
Branco as *"Baixo Acre e Purus"*.

### Joins are declared, with their grain

`SIH.RD` calls the admission key `N_AIH`; `SIH.SP` calls it `SP_NAIH`. `SIA.PA`
calls the establishment code `PA_CODUNI`, and it is the CNES code. Knowing that
is the difference between a join and an afternoon.

The trap is not the column name, it is the **grain**. `SIH.RD` is one row per
AIH and `SIH.SP` is many, so joining them and counting rows counts professional
acts while looking like it counts admissions. Every member records which it is.

`CNES` is marked `as_of: competence`: joining a 2015 admission to today's CNES
answers *what is this hospital now*, not *what was it when the patient was
treated*, and it answers silently.

Joins that people want and that have **no key shown to work** are recorded too,
because a join matching the wrong rows produces a cohort rather than an error.
`CO_PACIENTE` exists only in `SISCAN.PACNT` — no exam dataset carries it — so
following a patient across SISCAN exams is not possible from the published
files, and saying so is more useful than a plausible guess.

---

## The API

Every function is importable from the top level: `from pegasus_data import fetch`.

### `info(target=None, *, field_name=None)` — what IS this thing

The ontology, askable. Resolves a system, a dataset, or a variable, and separates
three things that are easy to blur:

- **identity** — what the node IS, from the declaration. Stable.
- **evidence** — which `(system, series)` pairs bind to it, under which rule.
- **coverage** — years, states, schema generations, file counts, how much of the
  column set is described.

```python
info()                                    # overview: every system
info("SIH")                               # a system and its datasets
info("SIH.RD")                            # a dataset in full
info("SIH.RD", field_name="DIAG_PRINC")   # a variable
info("SIH.RD.DIAG_PRINC")                 # the same, one string
info("SIH.RD").as_dict()                  # for programs
```

Aliases resolve throughout — `SIH` and `SIHSUS`, `SIH.RD` / `SIHSUS.RD` /
`SIH/RD` / a bare `RD` — and an ambiguous bare code resolves to nothing rather
than to a guess.

### `explore(target=None, *, series, year, uf, role, source)` — what is out there

The shipped map of the tree, four levels deep: systems → series → coverage →
files. Backed by a 1.04 MB snapshot, so it answers without a network call, and
every result names its source and crawl date.

```python
explore()                          # systems
explore("SIA")                     # its datasets
explore("SIA-PA")                  # coverage: which years, which states
explore("SIA-PA", uf="AC", year=2023)   # the actual files
```

### `fetch(dataset, *, uf, years, months, columns, labels, names, provenance, dictionary, profile, …)` — get data

One call, DATASUS to a table. Three deliberate differences from R's
**microdatasus**, which this borrows its shape from:

- **It does not guess filenames.** Every path comes from a directory listing
  DATASUS actually served.
- **It resolves through the ontology**, so `fetch("SIA-PA")` reaches all 736 of
  that dataset's families rather than the 9 that spell their series `PA`.
- **It says what it could not do** — see `report=True` above.

An unknown *system* fails immediately with suggestions, rather than spending a
crawl on a directory that never existed. An unknown *series* proceeds on purpose:
DATASUS adds datasets, and discovery finding one ahead of the declaration is the
feature working.

Three switches change what the answer *looks like* and never which rows come
back. They compose, and each one you turn on appends to the returned tuple, in
this order:

| switch | default | effect |
|---|---|---|
| `names="described"` | `"original"` | rename columns to their English names |
| `provenance=True` | `False` | keep `_source_path`, `_blob_sha256`, `_ingested_at`, `_schema_signature` |
| `dictionary=True` | `False` | also return a `DataDictionary` for this table |
| `report=True` | `False` | also return a `FetchReport` |

```python
table                        = fetch(...)
table, report                = fetch(..., report=True)
table, dictionary            = fetch(..., dictionary=True)
table, report, dictionary    = fetch(..., report=True, dictionary=True)
```

### `load(system, series, *, uf, years, columns, profile, render, …)` — read the lake

Same rendering as `fetch`, against Parquet you have already built.

```python
table = load("SIHSUS", "RD", uf="AL", years=[2023, 2024])
```

#### Render profiles

| profile | internal codes | external codes | companions | derived | headers |
|---|---|---|---|---|---|
| `analysis` *(default)* | label | code + label | on | on | original |
| `codes` | code | code | off | off | original |
| `audit` | code + label | code + label | on | on | original |
| `report` | label | code + label | on | on | translated |

Override one column with `render={"SEXO": "both"}`. **A label that cannot be
produced is named** — as a warning, or as `LabelUnavailable` under
`strict_labels=True`. It never silently returns unlabelled data.

External codes (CID, CBO, IBGE, CNES) keep the code beside the label, because
those are join keys in their own right.

### `availability(dataset)` — when each column existed

```python
availability("SIH-RD").changed_at()          # {2014: {"added": ["DIAGSEC1", ...]}}
availability("SIH-RD")["DIAGSEC4"].span()    # "2014–2026 — nothing decoded for 2017"
field_available("SIH-RD", "DIAGSEC4", 2007)  # "absent" | "present" | "unknown"
```

Also in the compendium as `field_validity`.

### `describe(system, series=None, *, field=None)` — what a column means

Returns the description, its source, its confidence, and what its values decode
to. `load()` and `describe()` read the same dictionary, so they cannot disagree.

### `translate(data, *, system, ...)` — the dictionary as a service

Decode a table you obtained some other way. `system` is required and never
inferred, because the same code means different things in different systems.

### `search(query, *, kind=None)` — the dictionary is askable

Full-text over variables, code tables and dataset prose, with accents folded.

```bash
pegasus-data search "raça"
pegasus-data search Parda --kind codelist
pegasus-data page SIHSUS DIAG_PRINC
```

### `export(system, series, *, format="csv"|"xlsx", …)` — a file for a colleague

Translated headers, combined values, one call. Shares `load()`'s rendering
implementation, so an option cannot mean one thing in a notebook and another in a
file.

### `compendium(out, *, systems, codes, values, files)` — a portable map

One SQLite file answering *"what does DATASUS have, and can I answer my question
with it?"* — the question asked while writing a protocol, before anything is
downloaded.

```python
from pegasus_data import compendium

compendium("datasus.sqlite")                   # the map            ~5 MB
compendium("datasus.sqlite", codes=True)       # + DATASUS's own codes
compendium("datasus.sqlite", systems=["SIH"])  # scoped
```

```bash
pegasus-data compendium --out datasus.sqlite --codes internal
```

| table | answers |
|---|---|
| `systems`, `datasets` | what exists, and what one row IS |
| `coverage` | which years and states — the feasibility question |
| `schema_generations` | did the columns change under my study period |
| `field_validity` | *when* each column existed — present, absent or unknown |
| `codelist_vintages` | which codelists are versioned, and over what windows |
| `join_keys`, `join_key_members` | how datasets connect, and which side fans out |
| `joins_not_established` | joins people want that have no key — checked, not omitted |
| `variables`, `dataset_variables` | what the columns are and mean |
| `open_questions` | what is *not* known |
| `codes`, `value_frequencies`, `files` | opt-in, and what makes a file large |

The `codes` toggle is the whole design. Measured on SIH: the core is 0.8 MB,
`codes=True` takes it to 4.8 MB, and `codes="bound"` to **425 MB** — because
twelve geography and CID-10 tables are 62% of the codes bound to it. `internal`
keeps DATASUS's own enumerations, which you cannot get anywhere else, and leaves
out the standard classifications you already have — naming which ones in the
report rather than dropping them silently.

### `pack()` / `unpack()` — see [Working offline](#working-offline)

---

## The command line

```
EXPLORE      systems · tree · coverage
UNDERSTAND   info · describe · compendium · dictionary · search · page · gaps
EXTRACT      get · build · export
AUDIT        report · questions · verify · findings · icd-quality
MONITOR      crawl --resume
MAINTENANCE  pack · unpack · prefix-adjudicate · catalog-rebuild
PIPELINE     crawl · inventory · semantics · sigtap · community · curate ·
             reference · schemas · profile · families · ledger · build
```

`pegasus-data --help` groups them by what you are trying to do. Build the whole
lake with one command:

```bash
pegasus-data all      # crawl → … → build, resumable and idempotent
pegasus-data report   # then read what you got
pegasus-data verify   # 20 regression assertions, with their evidence
```

Every stage writes to the catalog before returning, so interrupting `all` and
running it again picks up where it stopped rather than starting over.

---

## How it works

```
crawl       list the tree; every gap becomes a row, not a log line
inventory   filename grammar → (system, series, year) strata → families
schemas     read every stratum's columns from DBF headers — a census, not a sample
semantics   parse .CNV / .DEF / SIGTAP / lookup DBFs into ranked value labels
curate      load curation/*.yml — the part no crawl can produce
reference   materialise the winning code tables, scoped by validity window
profile     measure what the values actually look like
families    group by schema signature; record what each generation changed
ledger      record what is known, what is not, and what would settle it
build       write Parquet, hive-partitioned by system/family/uf/year
```

On disk:

```
_catalog/catalog.sqlite   everything the module knows (45 tables)
blobs/                    content-addressed cache; nothing is fetched twice
lake/                     Parquet, partitioned by system/family/uf/year
lake/reference/           code tables, scoped by validity window
```

The order is not cosmetic: every value source lands before `curate`, so a curated
assertion can override any of them, and `reference` comes after `curate` because
it materialises the winners.

---

## Why you can trust it

**Identity is not location.** A file's identity comes from its *name*
(`SIHSUS|RD|AC|2401`), not its path, so a DATASUS reorganisation moves files
without re-deriving thirty-five years of lineage under new identifiers. Moves and
renames are detected and recorded; a crawl that would withdraw a large share of
the catalog fails loudly instead of passing quietly.

**Labels are joined, never frozen.** Code tables live in `lake/reference/` scoped
by validity window, and a 1995 admission decodes against the 1992–1997 vintage
rather than today's. Materialising labels into the lake would freeze one
vintage's wording forever.

**Widths are matched exactly.** Never padded, never truncated. A 3-character
CBO-1994 code and the first three characters of a CBO-2002 code are different
things, and 452 tables on the tree mix classifications in one file.

**Nothing is dropped for being malformed.** A value that fails to parse is
evidence about the source; deleting it destroys the only record that it happened.
It is preserved and flagged.

**Schemas are a census, not a sample.** A DBF declares its whole schema in a
header of a few hundred bytes, and a `.dbc` keeps that header uncompressed ahead
of its compressed payload — so the columns of every stratum are read with a
ranged fetch: about 17 MB across the tree, where decoding one file per stratum
would be 183 GiB. Validated against 571 full decodes: identical field lists, zero
differences.

**Value labels come from ranked sources.** `.CNV` and `.DEF` first, then SIGTAP,
then lookup DBFs, the DEMAS API, layout PDFs, and — last before a guess —
community transcriptions, which carry the repository and commit they came from
and can never override a first-party table.

**What is not known says so.** `COD_IDADE` decides whether `IDADE=030` means
thirty years or thirty months, and no codelist for it exists anywhere on the
tree. Rather than guess, it is an open question naming exactly what would close
it — and the derived age column is withheld until then. `pegasus-data findings`
lists every such case alongside the ones that were settled.

**Personal identifiers pass through unmodified.** Nothing is masked, hashed or
dropped, and that is a decision rather than an omission: masking in a library
would destroy the evidence that the data was published, and deciding what may be
disclosed about a named person is not a call a data library is entitled to make.
The detector flags them and [`docs/FINDINGS.md` §3j](docs/FINDINGS.md) records
what was measured — including which apparent identifiers turned out, on
check-digit testing, to be obfuscated rather than published.

---

## Working offline

The codelists come from an FTP server that is slow, occasionally unreachable and
not under your control. They do not have to keep coming from there:

```bash
pegasus-data pack --out semantics.pgsb            # everything, ~153 MB
pegasus-data pack --system SIHSUS --out sih.pgsb  # one system, ~10 MB
pegasus-data unpack semantics.pgsb                # elsewhere, no network
```

A bundle carries the dictionary, the bindings, the curated meanings and the
schema catalogue — enough to label and describe data you already have, with
DATASUS unreachable. It carries no files and no rows: it is the means to
interpret data, not the data.

Fetching new files still needs the network. Understanding them does not.

---

## Where this stands

Measured, not estimated. `pegasus-data report` prints the current figures.

| | |
|---|---:|
| files catalogued | 207,251 |
| — what the previous public scan found | 124,810 |
| data files, all bound to a declared dataset | **207,030 (100%)** |
| support files (codelists, layouts, PDFs) | 221 |
| systems declared | 20 |
| datasets declared | 131 |
| families (system × dataset × schema) | 1,633 |
| distinct columns | 4,528 |
| **columns described** | **4,528 (100%)** |
| dictionary rows | 19.9M across 10,748 codelists |
| curated variables · datasets | 4,298 · 85 |
| open questions, recorded not guessed | 1,340 |
| tests | 601, all offline |

The software workflow is complete: crawl, decode, profile, translate, build,
query, and the public API above. Substantive semantic review remains ongoing,
especially for inferred descriptions and genuinely sourceless fields.
Description coverage reached 100% — and the
number to be careful with is that one, because it briefly read *96%* until an
audit found that 1,079 columns were "described" only by a `.DEF` display name.
A name is not a description; those columns were returned to the queue and the
real figure was 72%. The work since closed it for real.

### The strategy, in one paragraph

DATASUS publishes the administrative record of a national health system and
publishes nothing that explains it. The meaning is real but scattered. This
project's bet is that **the meaning is worth assembling once, carefully, with its
provenance attached**, so that nobody has to rediscover it and nobody has to
trust it blindly. Everything the module knows carries a source and a confidence,
and everything it does not know is recorded as a gap rather than filled with a
plausible guess. That constraint is what makes the result usable by a ministry
rather than merely convenient.

---

## Documentation

- **[`CONTRIBUTING.md`](CONTRIBUTING.md)** — how to work on this, and the rules
  that are not stylistic. Start here if you are going to change anything.
- **[`pegasus_data_ARCHITECTURE.md`](pegasus_data_ARCHITECTURE.md)** — how it is
  built and why. §5.4 is the ontology, §11 is `fetch()`, §14 is the public API,
  §19 records every departure from the original brief with its reasoning, §21 is
  the measured state.
- **[`docs/FINDINGS.md`](docs/FINDINGS.md)** — what we learned about DATASUS
  itself. §0 is the headline: why a correct crawl finds 82,441 more files than
  the previous one. §3j is the personal-identifier finding. §3k is the six
  municipality tables DATASUS ships, why they are not interchangeable, and how a
  city came to be labelled with the name of its health region.
- **[`docs/RESUME.md`](docs/RESUME.md)** — operational state: what is left, and
  how to resume an interrupted run.
- **[`docs/HANDOFF.md`](docs/HANDOFF.md)** — for anyone taking the work over:
  every defect found by running it, what is still open, the traps that have bitten
  more than once, and an honest account of how the work went wrong.
- **[`REVIEW.md`](REVIEW.md)** — the second external static audit. Its findings
  are **unverified** — the reviewer could not execute the suite.
- The data dictionary is a **database**, not files. `pegasus-data dictionary`
  builds `docs/dictionary.sqlite`; `search` and `page` read it, or open it with
  anything that speaks SQL:

```sql
-- which columns anywhere draw on CID-10?
SELECT system, field_name FROM variables WHERE codelist LIKE 'CID10%';

-- which generation of SIH-RD added DIAG_SECUN?
SELECT family_id, time_min, added_json FROM families
 WHERE system = 'SIHSUS' AND added_json LIKE '%DIAG_SECUN%';
```

This replaced a tree of 3,036 Markdown files. Everything in it was relational,
and flattening it meant no question anyone would actually ask could be answered,
the large code tables had to be truncated to stay readable, and the biggest
system's page was too large for GitHub to render at all.

---

## Contributing

`curation/*.yml` holds what a variable *means* — the part no crawl can produce.
It is version-controlled because an assertion needs an author and a diff, and it
is loaded by `pegasus-data curate`. Entries carry the rung of evidence behind
them, and the loader refuses to launder one into another: an `inferred` entry
without written-out reasoning does not load.

The tools that make that work tractable:

```bash
python scripts/formsheet.py CATALOG SINAN.VIOL      # one dataset on one screen
python scripts/attach_codelists.py CATALOG FILE.yml # copy bindings from the catalog
python scripts/validate_curation.py CATALOG FILE.yml# does it load? does it contradict?
python scripts/audit_descriptions.py CATALOG        # duplicate or boilerplate prose
python scripts/audit_vagueness.py CATALOG           # well-formed and saying nothing
python scripts/doc_queue.py CATALOG --summary       # what is left, grouped by dataset
```

The unit of work is a **form**, not a column. A SINAN agravo is one notification
form whose columns are a cross-product; describing them one at a time re-derives
the same context for every one. `formsheet.py` exists to put that context on one
screen — including each column's codelist *with its values spelled out*, which is
usually the decisive evidence and usually the thing not looked at.

```bash
pytest                            # 601 tests, all offline
ruff check src tests scripts
pegasus-data verify               # 20 regression assertions
```

See `CONTRIBUTING.md` for the full rules.
