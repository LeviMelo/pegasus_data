# pegasus_data

Turns Brazil's DATASUS FTP tree — 207,251 files, thirty-five years, a dozen
information systems — into a queryable, self-describing, typed data lake.

The point is not that the files become readable. It is that what they *mean*
becomes readable: which classification a column draws on, which vintage of that
classification applies to the year you are reading, which columns are still
emitted but dead, and which of it nobody has been able to document. A number you
cannot trace is worth less than no number.

---

## Start here

If you came for data, ask for it:

```bash
pegasus-data get SIH-RD --uf AL --years 2023 --out sih_al_2023.csv
```

```python
from pegasus_data import fetch

df = fetch("SIH-RD", uf="AL", years=2023)
```

That downloads what it needs, decodes it, normalises it and labels it. There is
no lake to build first and nothing is written to Parquet. A system the catalog
has not seen triggers a crawl of **that system's directory only**, which is
recorded, so the second call is free.

Unlike the R package this borrows its shape from, it does not construct FTP
paths from a template — every path comes from a directory listing DATASUS
actually served — and it names every file it could not read instead of handing
back a short table:

```python
df, report = fetch("SIH-RD", uf="AL", years=[2022, 2023], report=True)
report.years_missing      # years DATASUS publishes nothing for
report.undecoded          # files that would not open
report.schema_mismatch    # files whose columns did not fit their family
```

## The whole tree

If you came to build the lake — all 207,251 files, thirty-five years — that is
one command too, and a long one:

```bash
pegasus-data all
```

That runs the whole path — crawl, inventory, semantics, SIGTAP, community
codings, curate, reference, schema census, profile, families, ledger, build —
and each stage writes to the catalog before returning, so it is resumable and
idempotent. Interrupt it and run it again; it picks up
where it stopped rather than starting over or duplicating what it already has.

Then read what you got:

```bash
pegasus-data report
```

To work incrementally instead, every stage is its own command with the same
`--system` and `--root` options. `pegasus-data --help` groups them by what you
are trying to do.

Data lands in `$PEGASUS_DATA_HOME` (default `./pegasus_data_home`):

```
_catalog/catalog.sqlite   everything the module knows
blobs/                    content-addressed cache; nothing is fetched twice
lake/                     Parquet, hive-partitioned by system/family/uf/year
lake/reference/           code tables, scoped by validity window
```

---

## Reading data

```python
from pegasus_data import api

# Labels applied at read time. Internal codes are replaced by their label;
# external codes (ICD, CBO, IBGE, CNES) keep the code beside it, because those
# are join keys in their own right.
table = api.load("SIHSUS", "RD", uf="AL", years=[2023, 2024])

# What a column is, where that came from, and what its values mean.
api.describe("SIHSUS", "RD", field="DIAG_PRINC")

# A file someone opens in Excel: translated headers, combined values.
api.export("SIM", "DO", uf="SP", years=[2024], format="xlsx")
```

`load()` and `export()` share one rendering implementation, so an option cannot
mean one thing in a notebook and another in a file.

### Render profiles

| profile | internal codes | external codes | companions | derived | headers |
|---|---|---|---|---|---|
| `analysis` *(default)* | label | code + label | on | on | original |
| `codes` | code | code | off | off | original |
| `audit` | code + label | code + label | on | on | original |
| `report` | label | code + label | on | on | translated |

Override any single column with `render={"SEXO": "both"}`. **A label that cannot
be produced is named** — in a warning, or as `LabelUnavailable` under
`strict_labels=True`. It never silently returns unlabelled data.

---

## What the commands are for

```
EXPLORE      systems · tree · coverage
UNDERSTAND   describe · dictionary · gaps
EXTRACT      get · build · export
AUDIT        report · questions · verify · findings · icd-quality
MONITOR      crawl --resume
MAINTENANCE  pack · unpack · prefix-adjudicate · catalog-rebuild
PIPELINE     crawl · inventory · semantics · sigtap · community · curate ·
             reference · schemas · profile · families · ledger · build
```

`pegasus-data all` runs the PIPELINE row in that order, and the order is not
cosmetic: every value source lands before `curate`, so a curated assertion can
override any of them, and `reference` comes after `curate`, because it
materialises the winners.

`pegasus-data dictionary` writes `docs/dictionary/`, generated from the catalog
and never hand-written, so it cannot drift from what the catalog holds. Each
system gets three things:

- **`<system>.md`** — every column: what it is, how confident that is, and where
  the claim came from. It leads with the columns that will produce a wrong
  answer if used naively.
- **`<system>/schemas.md`** — every generation of the record, and exactly which
  columns each one added or dropped. The answer to "does this year have
  `DIAG_SECUN`" at a glance instead of by hand.
- **`<system>/codelists/`** — the **values**: one page per code table, every
  code and what it means, with the vintage each label belongs to. A code that
  was relabelled shows both readings, because a row filed in 2005 means what the
  2005 table said it meant.

`docs/dictionary/columns.md` indexes every distinct column name on the tree and
which systems carry it — with the warning that a shared name is not a shared
meaning, since `SEXO` is 1/3 in SIHSUS, 1/2 in SINASC and M/F in SINAN.

---

## Working offline

The codelists come from an FTP server that is slow, occasionally unreachable and
not under your control. They do not have to keep coming from there:

```bash
pegasus-data pack --out semantics.pgsb          # everything, ~153 MB
pegasus-data pack --system SIHSUS --out sih.pgsb # one system, ~10 MB
pegasus-data unpack semantics.pgsb               # elsewhere, no network
```

A bundle carries the dictionary, the bindings, the curated meanings and the
schema catalogue — enough to label and describe data you already have, with
DATASUS unreachable. It carries no files and no rows: it is the means to
interpret data, not the data.

Fetching new files still needs the network. Understanding them does not.

---

## The parts worth knowing about

**Identity is not location.** A file's identity comes from its *name*
(`SIHSUS|RD|AC|2401`), not its path, so a DATASUS reorganisation moves files
without re-deriving thirty-five years of lineage under new identifiers. Moves and
renames are detected and recorded; a crawl that would withdraw a large share of
the catalog fails loudly instead of passing quietly.

**Schema generations are first class.** SIH-RD has **20** measured schema
generations spanning 35 to 114 columns and 1992–2026, not one schema with
exceptions. A column is grouped by the schema it belongs to, so a
query never silently reads a different generation than it thinks.

**Labels are joined, never frozen.** Code tables live in `lake/reference/`
scoped by validity window, and a 1995 admission decodes against the 1992–1997
vintage rather than today's. Materialising labels into the lake would freeze one
vintage's wording forever.

**Widths are matched exactly.** Never padded, never truncated. A 3-character
CBO-1994 code and the first three characters of a CBO-2002 code are different
things, and 452 tables on the tree mix classifications in one file.

**Nothing is dropped for being malformed.** A value that fails to parse is
evidence about the source; deleting it destroys the only record that it happened.
It is preserved and flagged.

**Schemas are a census, not a sample.** A DBF declares its whole schema in a
header of a few hundred bytes, and a `.dbc` keeps that header uncompressed ahead
of its compressed payload — so `pegasus-data schemas` reads the columns of every
stratum with a ranged fetch, about 17 MB across the tree where decoding one file
per stratum would be 183 GiB. Validated against 571 full decodes: identical field
lists, zero differences. Columns known only this way are marked **SCHEMA ONLY**
in the dictionary, because knowing a column exists is not knowing what is in it.

**Value labels come from ranked sources.** `.CNV` and `.DEF` first, then SIGTAP,
then lookup DBFs, the DEMAS API, layout PDFs, and — last before a guess —
community transcriptions, which carry the repository and commit they came from
and can never override a first-party table.

**What is not known says so.** `COD_IDADE` decides whether `IDADE=030` means
thirty years or thirty months, and no codelist for it exists anywhere on the
tree. Rather than guess, it is an open question naming exactly what would close
it — and the derived age column is withheld until then. `pegasus-data findings`
lists every such case alongside the ones that were settled.

---

## Curation

`curation/*.yml` holds what a variable *means* — the part no crawl can produce.
It is version-controlled because an assertion needs an author and a diff, and it
is loaded by `pegasus-data curate`. Entries carry the rung of evidence behind
them, and the loader refuses to launder one into another: an `inferred` entry
without written-out reasoning does not load.

---

## Requirements

Python 3.11+. `pip install -e .` for the core; `.[all]` adds PDF, Excel and RAR
support. Development: `pip install -e .[dev]`, then `pytest` (387 tests) and
`ruff check src tests`.

## Documentation

- `docs/dictionary/` — the generated data dictionary
- `docs/FINDINGS.md` — every measured result that contradicted an assumption
- `pegasus_data_ARCHITECTURE.md` — the design this was built from
