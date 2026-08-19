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

From an empty directory to a lake, in one command:

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
EXTRACT      build · export
AUDIT        report · questions · verify · findings · icd-quality
MONITOR      crawl --resume
PIPELINE     crawl · inventory · semantics · sigtap · community · curate ·
             reference · schemas · profile · families · ledger · build
```

`pegasus-data all` runs the PIPELINE row in that order, and the order is not
cosmetic: every value source lands before `curate`, so a curated assertion can
override any of them, and `reference` comes after `curate`, because it
materialises the winners.

`pegasus-data dictionary` writes `docs/dictionary/` — one page per system, one
per dataset, generated from the catalog and never hand-written, so it cannot
drift. It leads with the columns that will produce a wrong answer if used
naively.

---

## The parts worth knowing about

**Identity is not location.** A file's identity comes from its *name*
(`SIHSUS|RD|AC|2401`), not its path, so a DATASUS reorganisation moves files
without re-deriving thirty-five years of lineage under new identifiers. Moves and
renames are detected and recorded; a crawl that would withdraw a large share of
the catalog fails loudly instead of passing quietly.

**Schema generations are first class.** SIH-RD has 36 observed generations, not
one schema with exceptions. A column is grouped by the schema it belongs to, so a
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
