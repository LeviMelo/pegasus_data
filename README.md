# pegasus_data

**Brazil's national health data, with its meaning attached.**

DATASUS publishes the administrative record of a health system serving 215
million people: 208,095 files and 991 GiB on one FTP server, twenty information
systems, 1992 to now. It publishes almost nothing that explains them. There is
no index of what exists and no machine-readable schema. The meaning of a code
lives in `.CNV` files written for a DOS tabulation program, in PDFs, and in the
names of directories.

pegasus_data reads that tree and hands back tables whose codes carry their
meaning: which classification a column uses, which version of it applies to the
year you read, which columns are dead, and what nobody has been able to
document.

> A number you cannot trace is worth less than no number.

```python
from pegasus_data import query

table = query("SIH.RD", period="2022-01", geography="AL",   # hospital admissions, Alagoas
              select=["MUNIC_RES", "SEXO", "DIAG_PRINC"])
table.to_pandas().head(2)
```

```text
  Município de Residência do Paciente (MUNIC_RES)  Sexo do paciente (SEXO)  Código do diagnóstico principal (DIAG_PRINC)
0                    Delmiro Gouveia, AL (270240)             Feminino (3)             Parto espontaneo cefalico (O800)
1                    Delmiro Gouveia, AL (270240)             Feminino (3)             Parto espontaneo cefalico (O800)
```

---

## Install

Python 3.11 or newer.

```bash
pip install pegasus-data          # library and CLI
pip install "pegasus-data[all]"   # + PDF, Excel, RAR and Polars support
```

From a clone: `pip install -e ".[all,dev]"`.

The wheel carries a **seed catalog** of the whole tree: every file with its
system, series, state, date and schema family, and every curated column
description. It also carries the **label pack** (3.65M code ranges). So a fresh
install answers `info()`, `explore()` and `search()` offline, and its first
`query()` downloads only the files it reads.

**Where the data goes.** `pegasus-data where` prints the data home and which
setting chose it. Set it with `pegasus-data config set --root D:/datasus`, or
with `PEGASUS_DATA_HOME`.

---

## Five minutes

### What exists

```python
from pegasus_data import info, explore, search

info()                    # the twenty systems
info("SIH.RD")            # one dataset: what one row is, coverage, schema generations, gotchas
explore("SIH.RD")         # years, states, files and bytes on the server, offline
explore("SIH.RD", year=2023, uf="SP")   # the files themselves, with sizes
search("raça")            # columns about race: RACACOR, CS_RACA, RACA_COR …
search("Parda", kind="code")            # which codes mean "Parda", in which tables
```

Dataset names are the ontology's codes: `SIH.RD`, `SIM.DO`, `SINASC.DN`,
`SINAN.DENG`, `CNES.ST`, `SIA.PA`. `SIH-RD`, `SIHSUS.RD` and a bare `RD` mean
the same thing everywhere.

### Data

```python
from pegasus_data import query, plan

print(plan("SIM.DO", period=2022, geography="AL").explain())   # what will be read, before reading it
deaths = query("SIM.DO", period=2022, geography="AL")
births = query("SINASC.DN", period=("2020", "2022"), geography=["AL", "SE"])
dengue = query("SINAN.DENG", period=2022, select=["NU_IDADE_N", "CS_SEXO", "ID_MN_RESI"])
```

- **`period`** is `YYYY`, `YYYY-MM` or a `(start, end)` pair.
- **`geography`** is one state or several. Both select **DATASUS
  publications**, the files the Ministry cut by state and month. They never
  filter record variables such as the date of admission or the municipality of
  residence. Ask for a month of an annual dataset and you get the year, with a
  warning.
- **`present`** decides how the result reads (ADR-0084). The default,
  `"readable"`, puts meaning first and keeps the code in parentheses: values
  `Masculino (1)` under headers `Sexo do paciente (SEXO)`. A code no table
  decodes stays visibly undecoded: `9 (?)`. Other presets: `"analysis"` (raw
  codes plus `<column>_label` columns, for code that joins and groups on
  codes), `"labels"` (labels only) and `"codes"` (as filed). Any part is a
  template you can change, per call or as your default in `pegasus-data.toml`:

  ```python
  query("SIH.RD", period="2022-01", geography="AL",
        present={"values": "{code} - {label}", "names": "{name}", "language": "en"})
  ```
- **Derived columns come with it.** `IDADE_anos` is age in fractional years
  (18 months = 1.5), decoded from each system's own age encoding for SIH, SIM
  and SINAN.
- **`return_report=True`** also returns what was read, what was skipped and
  why, which columns could not be labelled and why, and which editions of a
  publication were superseded.
- A request that would download an unbounded history is refused unless
  `allow_unbounded=True` is passed.

`query` reads a lake you have built wherever it covers the request, and the FTP
server otherwise. The table is Apache Arrow: `.to_pandas()`, Polars and DuckDB
read it directly.

### From the command line

```bash
pegasus-data query SIH.RD --period 2023-01 --geo AL,SE --out sih.csv
pegasus-data query SIM.DO --period 2020..2022 --geo AL --present analysis --dictionary sim_dictionary.md --out sim.parquet
pegasus-data query SIM.DO --period 2022 --geo AL --values "{code} - {label}" --language en --out sim.csv
pegasus-data info SIH.RD
pegasus-data search raça
pegasus-data explore SIA.PA
```

`--dictionary` writes one entry per column: its curated name and description,
the table that decoded it, the evidence rung and the source it is documented
in.

### Labels for data you already have

```python
from pegasus_data import translate
labelled = translate("my_sih_extract.csv", system="SIHSUS")
```

### Aggregates

`aggregate()` serves prebuilt municipality × time cells (counts, sums and
means stored as mergeable states) that roll up through health regions, states
and the country without touching microdata. `serve/` exposes them over HTTP to
the companion frontend (`../pegasus_view`).

---

## The data model

```text
system        SIH          an information system, as the Ministry runs it
  dataset     SIH.RD       one of its published datasets
    family    113 columns  a schema generation of that dataset
      column  DIAG_PRINC   with its meaning, its codelist, and when it existed
```

**Systems and datasets are declared, not derived.** "SIH publishes a dataset
called AIH Reduzida, known as RD" is a fact about how the Ministry organises
itself. It lives in `curation/ontology.yml` (20 systems, 131 datasets), and the
FTP layout is evidence for it, never its definition. One archive can hold seven
datasets, one dataset can live in two directories, and one publication can be
split into lettered parts (`PASP2301a`, `b`, `c`). Every data file binds to a
declared dataset.

**Schema generations are first class.** SIH-RD has 20 generations, from 35 to
114 columns. `info("SIH.RD")` shows what each generation added and dropped,
which decides whether years either side of a boundary can be pooled.

**Structural absence is not missingness.** SIH-RD's nine secondary-diagnosis
columns do not exist before 2014. A query spanning the boundary unions the
generations and marks those rows null *structurally*, in the report, rather
than letting the gap read as unrecorded diagnoses. `availability("SIH.RD")`
and `field_available(...)` answer "did this column exist in that year" as
present, absent or unknown.

**One codelist per column per schema generation.** A column is bound to every
TabNet table that mentions it (31 for SIH's `CNES`, 294 for PNI's `MUNIC`).
Which one actually labels it is decided once:
- curation first;
- otherwise measured against real files, with per-state slices of national
  tables set aside;
- a table that only rolls codes up (a municipality to its health region) is
  never a label.

Codelists are keyed by system and by validity window, so a 1995 admission
decodes against the 1995 table. When no table decodes a column, the code stays
raw and the report says why. A guess would be worse than a gap.

**Joins are declared, with their grain.** `SIH.RD` is one row per admission
(`N_AIH`) and `SIH.SP` many, so joining them and counting rows counts
professional acts. `curation/joins.yml` records each key and each side's grain.
Keys that people want but that do not exist are recorded as well: SISCAN exams
cannot be followed across patients.

**Personal identifiers pass through unmodified, and stay flagged.** Masking in
a library would destroy the evidence of what was published, and deciding what
may be disclosed about a person is not a data library's call. Some public
SIASUS files publish real professional CPFs and re-identifiable patient
records, and some SINAN files still carry full birth dates. See `DATA_SOURCES.md`.

---

## How it works, briefly

```text
ftp.datasus.gov.br ─► crawl (the whole tree in ~30 s) ─► catalog: files, strata, schemas, families
                   ─► download on demand ─► decode (DBC/DBF/CSV/XML/archives, in killable workers)
                   ─► normalise ─► label (the seed's bindings + the label pack) ─► your table
                                └─► optionally, a partitioned Parquet lake
```

`HOW_IT_WORKS.md` walks through it, and `ARCHITECTURE.md` maps the code.

---

## Documentation

The project's record follows one model (ADR-0001):

- **[`STATUS.md`](STATUS.md)**: what is true now, and what is being worked on.
- **[`CLAUDE.md`](CLAUDE.md)**: how to work on this repository, and the rules
  that are not stylistic.
- **[`HOW_IT_WORKS.md`](HOW_IT_WORKS.md)** and
  **[`ARCHITECTURE.md`](ARCHITECTURE.md)**: the system in prose, and the map
  of the code.
- **[`DECISIONS.md`](DECISIONS.md)**: every decision, with its evidence and
  what would reverse it.
- **[`EVALUATION.md`](EVALUATION.md)**: every measurement and live run,
  including the August 2026 lab notebook.
- **[`OPEN_QUESTIONS.md`](OPEN_QUESTIONS.md)**: what is not known, and what
  would settle it.
- **[`DATA_SOURCES.md`](DATA_SOURCES.md)**: measured facts about DATASUS,
  IBGE, SIGTAP and the rest.
- **[`RUNBOOK.md`](RUNBOOK.md)**: commands.
- **[`GLOSSARY.md`](GLOSSARY.md)**: the terms.

---

## Contributing

`curation/*.yml` holds what a variable *means*, the part no crawl can produce.
It is version-controlled because an assertion needs an author and a diff. Each
entry carries the rung of evidence behind it (layout document, TabNet `.DEF`,
web source, or inferred with its reasoning). A person's curation outranks
everything the machinery measures.

Changes are verified on the live system: `scripts/live.py` runs the scenarios
in this README against the real server on a fresh data home (CLAUDE.md §5).

MIT licensed.
