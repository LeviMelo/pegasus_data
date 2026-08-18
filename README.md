# pegasus_data

A queryable, self-describing, typed data lake over Brazil's DATASUS public health data.

DATASUS publishes roughly 125,000 files across ~18 information systems and ~35 years on a
public FTP server, with **no centralized data dictionary**. The meaning of variables and of
coded values is scattered across `.DEF`/`.CNV` files, `TAB_*.zip` archives, PDFs, and paper
notification forms — or is simply absent. Analysts routinely reconstruct code meanings ad hoc,
and get them wrong.

This package turns that tree into a lake where **the meaning of every variable and every coded
value is recoverable from the package itself**, with provenance attached and unknowns recorded
as unknown rather than guessed.

---

## What it does

```bash
pip install -e .

pegasus-data crawl                 # walk the FTP tree, recording metadata and unreachable paths
pegasus-data inventory             # parse filenames, infer date conventions, build schema strata
pegasus-data semantics             # ingest TAB kits, parse .DEF/.CNV, build the dictionary
pegasus-data profile               # profile one file per stratum, classify every field
pegasus-data families              # group by schema signature; detect drift and renames
pegasus-data ledger                # build the metadata ledger with dictionary_coverage
pegasus-data build --system SIHSUS --uf AL --years 2015-2024
pegasus-data report                # coverage, dictionary_coverage, open questions
pegasus-data verify                # run the regression assertions
```

Then, from Python:

```python
from pegasus_data import Catalog, describe, load, load_population

describe("SIHSUS", "RD", field="DIAG_PRINC")
# → official name, semantic type with the statistics behind it, dictionary coverage,
#   top values WITH labels, which codelists decode it, and which schema generations
#   carry the column at all.

df = load("SIHSUS", "RD",
          uf="AL", years=range(2015, 2025),
          columns=["MUNIC_RES", "DIAG_PRINC", "IDADE", "SEXO", "MORTE", "VAL_TOT"],
          labels=True)

pop = load_population(series="POPSVS", uf="AL", by=["municipality", "year", "sex", "age"])

# Hierarchical classifications are joined, not frozen into a label column:
cid = load_reference("CID10", year=2019)          # the vintage covering 2019
cbo = load_reference("CBO", code_width=6)         # CBO-2002, not CBO-1994
df.join(cid, keys="DIAG_PRINC", right_keys="code")
```

`pegasus-data gaps` ranks every variable that still has no dictionary by observed row mass, so the
remaining work is a list rather than an average.

Every stage is resumable and idempotent, writes to the catalog before returning, and can be
re-run narrowly (`--system`, `--uf`, `--years`, `--prefix`).

---

## The four problems it solves

| | Problem | How it is addressed |
|---|---|---|
| **P1** | No centralized dictionary | Ships a dictionary + ledger where each entry carries provenance and confidence; coverage is a reportable number per system and per field |
| **P2** | Sequential FTP I/O dominates wall-clock | Discovery, acquisition and decoding are concurrent; the pipeline is content-addressed, so nothing is fetched twice |
| **P3** | Raw DATASUS is a storage bomb | Canonical persistence is partitioned Parquet; normalisation is vectorised over Arrow |
| **P4** | Coverage gaps hide whole systems | Discovery and profiling are format-agnostic and schema-first; a system is never excluded by file extension |

---

## What the code found that the specification did not

The architecture brief this package implements marks its measured claims `[M]` and its open
questions `[V]`, and says explicitly that a `[V]` must never be promoted to a design assumption
without running the stated check. Running them produced several corrections. Each is recorded in
the catalog's `open_questions` table with its evidence, readable with `pegasus-data questions`.

**The APAC archives are LHA, not zip.** The brief predicted `SIASUS/APAC/*.EXE` were "a PE stub
with a standard archive appended", to be opened with `zipfile`, then `rarfile`, then `7z`. They
are none of those: the stub identifies itself as `LHA's SFX 2.13S (c) Yoshi, 1991` and the
payload uses method `-lh5-`. Both `zipfile` and `rarfile` reject them. And each archive holds
**seven** DBF members with seven distinct schemas — master record, chemotherapy, radiotherapy,
other procedures, billed procedures, serology, dialysis unit — so one file is seven logical
datasets, not one. `decode/lha.py` implements the decoder in pure Python, byte-exact against
7-Zip on every member.

**The metadata loss (D4) was a listing-dialect bug, not a protocol limitation.** The brief
proposed content addressing as the workaround and an HTTPS mirror as the fix. Measured: the
server is Microsoft IIS FTP on Windows_NT; `MLSD` returns `500 Command not understood`, and
`ftp.datasus.gov.br` accepts nothing on :80 or :443, so there is no mirror. But `LIST` returns
the IIS MS-DOS dialect — `05-29-15  04:10PM  18550 acac0201.exe` — which carries **both size and
mtime**. The prior scanner only had a Unix `ls -l` regex, so every row failed to parse, the
reader raised, and the crawl fell back to `NLST`, which carries no metadata at all. Parsing the
right dialect restores size and mtime for the whole tree.

**SIH-RD has at least nine schema generations, not three.** The brief names 35 / 86 / 113
columns. Measured from January files for Acre: 35 (1992), 41 (1998), 60 (2000), 69 (2005),
75 (2007), 86 (2008–09), 93 (2011–12), 113 (2014–24), 114 (2026). The brief's three are what a
two-file sample could see.

**`DIAG_SECUN` is worse than absent in the 113-column generation.** The brief says it is missing,
so a query would return empty. Measured in `RDAC2001.dbc`: the column is *present*, with 3,784
non-null rows **all equal to `'0000'`**. An empty result at least looks odd; thousands of `0000`
look like data and get counted. A `constant_column` detector flags it.

**`Dados_Abertos` needs no new grammar.** The brief attributes 82 `UNPARSED` families to
descriptive filenames. They are classic `PREFIX+GEO+DATE` (`DENGBR20.csv.zip`); what defeated
the prior parser was the composite suffix `.csv.zip`, which its suffix-stripper handled only for
`.gz`. A genuinely descriptive tail does exist (`apac_atd.duck.zip`) and gets its own grammar.

**A procedure table is in the kits.** `[V]5` asked whether SIGTAP must be sourced separately.
`TPROC.DBF`/`TPROC10.DBF` (7,717 and 7,712 rows) and `EMUSO*.DBF` are inside the SIH kit.
Code→description decoding needs nothing further; anything depending on procedure *attributes*
(validity windows, CBO/CID restrictions, financing) still requires SIGTAP.

**BNAFAR/Hórus carries medication identity.** `[V]9` asked about granularity. The live OpenAPI
parameters are `codigo_municipio`, `codigo_cnes`, `anomes_posicao_estoque`, `codigo_catmat`,
`tipo_produto` — municipality × establishment × month, **with** the medication identified.

**`IBGE/projpop` runs to 2070, not 1970.** Its 71 files are `PROJUF00…PROJUF70` — projections
keyed by projection year. The usual two-digit pivot would read `70` as 1970 and scatter a
contiguous series across a century, so the epoch is inferred per directory from contiguity.

**Codepage detection cannot be "first one that works".** cp850 and latin-1 both map all 256 byte
values, so neither ever raises and the first candidate always wins. `IDENT.CNV` read under cp850
gives `Longa permanÛncia`; the byte is 0xEA, `ê` in latin-1. `textenc.py` scores candidates on
how much the result looks like Portuguese instead.

---

## Design rules the code holds itself to

These come from §13 of the brief and are enforced in code, not just documented:

- **Never guess a code's meaning.** An unmapped value is `categorical_undecoded` with a coverage
  penalty. A plausible guess with no provenance is worse than a gap, because it is invisible
  downstream.
- **Never apply a global sentinel rule.** `9` is missing in one field and a valid category in
  another. Sentinels are per field, derived from the codelist's own "Ignorado" labels.
- **Never let a missing column pass silently.** A query for a column absent from a generation
  raises `MissingColumnError` naming the generations that do carry it.
- **Never exclude a file by extension.** Classification is by probe result; the suffix only
  orders the attempts.
- **Never report `stable` where n = 1.** Drift with one sample is `insufficient_evidence`.
- **Never recompute a value the source publishes.** Where SINAN carries `SEM_PRI`/`SEM_NOT`, the
  source's epidemiological week is used, not a recomputed one.
- **Never discard the raw value when writing a decoded label.** Both columns are emitted.
- **Never freeze a hierarchical classification into a label column.** ICD, procedures, CBO and
  municipality codes are joined from version-scoped reference tables, so the consumer chooses the
  granularity and the vintage instead of inheriting one silently.
- **Never let an inference decide what labels appear on data.** A detector's membership match is a
  candidate; it is used only once a record layout names the same classification.
- **Never resolve a source conflict silently.** Both claims and both provenances are recorded.

---

## Architecture

```
L0  discovery      FTP crawl, per-directory verb escalation → catalog.files, coverage_gaps
L1  inventory      filename grammar, date conventions       → catalog.strata
L2  acquisition    concurrent fetch + content-addressed cache → blobs/
L3  decode         probe-ordered readers                    → Arrow tables
L4  profile        distributional evidence                  → variable_profiles, value_frequencies
L5  semantics      DEF/CNV/kits/PDF/API + inference         → dictionary, ledger
L6  normalize      ledger-driven decoding and typing        → typed Arrow
L7  persist        Parquet lake + DuckDB views              → lake/
L8  denominators   POPSVS / POPTCU / POP / projpop / censo  → lake/population/
L9  api_sources    DEMAS open-data API                      → lake/demas/
L10 public API     load(), describe(), Catalog              → user-facing
```

Three keys carry the design:

```
stratum        := (system, series, year)              # the unit of schema sampling
family         := (system, series, schema_signature)  # the unit of a logical dataset
representation := (family, container_format)          # how to physically read it
```

Families are discovered **after** profiling one file per stratum. That inversion is what makes
schema generations visible, and it is why format is an attribute of a family rather than part of
its key — the same AIH records published as `.dbc`, `.dbf`, `.xml` and `.csv` are one family with
four representations, not four datasets to be double-counted.

Codelists are kept separate from columns. A `.CNV` says `1 → Masculino` without saying which
column uses it, and one codelist serves several columns; the `.DEF` files supply the binding.
Flattening them together would duplicate 5,600 municipality rows per column and report a conflict
every time two unrelated codelists both defined the code `1`.

Dictionary entries are scoped to the period their kit declares. `TAB_SIH_199201-199712.zip` and
the current `TAB_SIH.zip` disagree about thousands of municipality labels because municipalities
were created, merged and renamed in between — both are correct for their window.

---

## Requirements

- Python ≥ 3.11
- Core: `pyarrow`, `duckdb`, `dbfread`, `datasus-dbc`, `httpx`, `typer`, `rich`
- Optional: `pypdf`/`pdfplumber` (PDF harvesting), `openpyxl` (xlsx), `rarfile` (the four `.rar`
  dictionary kits), `polars`
- `7z` on PATH is an archive fallback only; the LHA and zip readers are pure Python

No credentials are required for any source. All data is public and anonymous-access.

## A note on personal data

The 2001–2007 APAC files recovered from the `.exe` archives carry `APA_CPFPCN` — an eleven-digit
patient CPF — in a public download. The profiler flags such columns as
`personal_identifier_cpf` and the ledger raises an open question against them rather than
normalising them into an anonymous-looking "identifier" column. Handle accordingly.

## Licence

MIT.
