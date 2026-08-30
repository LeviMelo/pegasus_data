# Findings: where measurement disagreed with the specification

`pegasus_data_ARCHITECTURE.md` marks its claims `[M]` (measured), `[D]` (derived) and `[V]` (to
verify), and states the rule that governs this document:

> **Never promote a `[V]` to a design assumption without running the stated check.** Where a `[V]`
> is unresolved, the code must record it as an open question in the ledger rather than pick a
> plausible answer.

Every `[V]` was run. Several `[M]` claims were re-checked and some did not survive. This file
records what was measured, when, and against what — because the project this feeds is going to a
federal ministry, and a claim that cannot state its own provenance is worse than an absent claim.

All measurements below are against `ftp.datasus.gov.br/dissemin/publicos` and
`apidadosabertos.saude.gov.br` on **2026-08-18**, and are reproducible with
`pegasus-data questions`, which prints each resolution with its stored evidence.

---

## 0. The headline

**The previous inventory of DATASUS was missing a third of it, and said nothing.**

A full crawl finds **207,251 files**. The prior scan found 124,810 and reported
success. The 82,441-file difference is not attrition or churn; it is one
mechanism, and it is worth stating exactly:

> FTP's `NLST` command returns **bare names with no type information**. An
> extensionless directory name is therefore indistinguishable from a file. The
> old scan recorded `Dados` as a *file* under `SIASUS/200801_`, and `uploads` as
> a *file* under `/dissemin/publicos`. Because it believed they were files, it
> never listed them, and because nothing failed, it **never warned**.

Behind `Dados` sat **54,199 files** — SIA outpatient production, 2008 to the
present, the largest single dataset on the tree. It was absent from the
inventory under a clean bill of health.

That is the failure this project exists to make impossible, and it shapes
everything else here: an entry that cannot be typed gets a per-file `SIZE`
probe and only a successful probe makes it a file; a directory that cannot be
listed becomes a `coverage_gaps` row rather than a silence; an item that stops
responding is abandoned, recorded, and reported rather than waited on forever.
A gap you can query is a different thing from a gap you cannot see.

---

## 1. The `[V]` list (§14), resolved

### V1 — HTTPS mirror · **resolved: no mirror, and none needed**

`ftp.datasus.gov.br` accepts nothing on :80 or :443; both connections time out. There is no HTTPS
mirror of the tree.

The mirror was wanted because it would restore `Content-Length` and `Last-Modified`, eliminating
defect D4. That turns out to be unnecessary — see §2 below — because the metadata was always
available over FTP and the prior scan simply could not read it.

`FEAT` on the live server reports: `LANG EN*`, `UTF8`, `AUTH TLS;TLS-C;SSL;TLS-P;`, `PBSZ`,
`PROT C;P;`, `HOST`, `SIZE`, `MDTM`, `REST STREAM`. `SIZE` and `MDTM` give per-file metadata on
demand, and `REST STREAM` means interrupted transfers are resumable.

### V2 — self-extracting `.exe` payload · **resolved, and it is not what was predicted**

The brief: *"These are a PE stub with a standard archive appended. Strategy, in order: Python
`zipfile` directly, then `rarfile`, then `7z` via subprocess, then a raw signature scan for
`PK\x03\x04` and `Rar!\x1a\x07`. Expected payload: one or more `.dbc` or `.dbf`."*

Measured on `/dissemin/publicos/SIASUS/APAC/2002/acac0202.exe` (21,354 bytes):

- The stub identifies itself as **`LHA's SFX 2.13S (c) Yoshi, 1991`**.
- The payload is an **LHA archive using method `-lh5-`**, header level 0, beginning at offset 1636.
- `PK\x03\x04` does not appear anywhere in the file. Neither does `Rar!`. `zipfile` raises
  `BadZipFile`; `rarfile` rejects it. The predicted ladder fails at every rung except `7z`.
- The payload is **seven** DBF members, not "one or more":

  | member | bytes | fields | what it is |
  |---|---|---|---|
  | `ACAC0202.DBF` | 75,066 | 19 | APAC master record (`APA_*`) |
  | `COAC0202.DBF` | 55,498 | 14 | billed procedures (`COB_*`) |
  | `OPAC0202.DBF` | 31,715 | 17 | other procedures (`OPC_*`) |
  | `PFAC0202.DBF` | 11,536 | 21 | patient, radiotherapy (`PAF_*`) |
  | `PCAC0202.DBF` | 7,204 | 21 | patient, chemotherapy (`PAC_*`) |
  | `UDAC0202.DBF` | 4,092 | 66 | dialysis unit (`UDI_*`) |
  | `EXAC0202.DBF` | 3,756 | 13 | serology (`EXA_*`) |

**Consequence for the design.** One archive is *seven logical datasets with seven distinct
schemas*, so an archive member has to be a first-class row in the family model. The prior
implementation's `choose_archive_member()` — which selects a single "best" member — would have
discarded six of the seven.

**Implementation.** `decode/lha.py` implements `-lh0-`/`-lhd-`/`-lz4-` (stored) and
`-lh4-`/`-lh5-`/`-lh6-`/`-lh7-` (LZSS + static Huffman) in pure Python, so the package does not
require an external binary. Verified byte-exact against 7-Zip on all seven members. `7z` remains a
fallback for `-lh1-` and friends, and its absence degrades to a recorded decode gap.

**Also worth flagging:** `ACAC0202.DBF` carries `APA_CPFPCN` — an eleven-digit patient CPF — and
`APA_CPFRES`, `APA_CPFDIR` alongside `APA_NOMERE` and `APA_NOMEDI` (names). These are direct
personal identifiers in a public, unauthenticated download. The profiler classifies them as
`personal_identifier_cpf` and the ledger raises an open question against every such column.

### V3 — `.CNV` and `.DEF` grammars · **resolved**

Learned from the 79 uncompressed files under `PNI/AUXILIARES/` and the 177 `.CNV` members of
`TAB_SIH_199201-199712.zip`.

**`.CNV`:**

```
<n_categories> <code_width>
<seq:right-aligned><spaces><label:padded><spaces><match-expression>
```

The match expression is a single code, a comma-separated list, a range, or a mixture. The
expression column is 60 in most files and 64–66 in others, so it is inferred per file rather than
hard-coded.

Two properties a naive reading gets wrong:

- **Last match wins.** `SEXO.CNV` lists `Ignorado → 0-9` *first*, covering the whole domain, then
  overrides it with `Masculino → 1` and `Feminino → 2,3`. First-match-wins would label every
  record "Ignorado". The idiom recurs — `IDADE18.CNV` opens with `Ign → 000-999`.
- **A `.CNV` is a codelist, not a column.** It never says which field uses it, and one codelist
  serves several fields. The binding comes from `.DEF`.

**`.DEF`:**

```
;comment (the first one is the title)
A..\DADOS\RD_AIH_Reduzida\RD*.DBC      the data glob this tabulation reads
?\TAB\RD.HLP                           help file
IValor Total       ,VAL_TOT            Incremento — an additive measure
LRegião int        ,MUNIC_MOV ,1  ,REGIAO.CNV     Linha
CRegião int        ,MUNIC_MOV ,1  ,REGIAOC.CNV    Coluna
SUF - ZI           ,UF_ZI     ,1  ,UFALFA.CNV     Seleção
XCapital int       ,MUNIC_MOV ,1  ,CAPITAL.CNV    all three
LHospital BR (CNES),CNES  ,RAZAO ,TCNESBR.DBF     DBF lookup, label column named
```

`RD.DEF` has 547 lines: 199 `L`, 176 `S`, 73 `X`, 52 `;`, 25 `C`, 20 `I`, 1 `A`, 1 `?`.

The `I` prefix is worth more than it looks: it is **the Ministry's own statement that a variable is
summable**. `IValor Total,VAL_TOT`, `IÓbitos,MORTE`, `IPermanência,DIAS_PERM` — exactly what
`ledger.aggregation` needs, sourced rather than inferred.

The `A` line binds a dictionary to the data files it describes, so a `.DEF` attaches to a family
instead of being guessed at.

### V4 — `TAB_*.zip` contents · **resolved**

`TAB_SIH_199201-199712.zip` (2,926,349 bytes) holds **246 members**: 177 `.CNV`, 62 lookup `.DBF`,
4 `.DEF`, 2 help files, 1 DLL. Notable lookups:

| member | rows | what |
|---|---|---|
| `CID10.DBF` | **14,197** | complete ICD-10 with Portuguese descriptions (`CID10, OPC, CAT, SUBCAT, DESCR, RESTRSEXO`) |
| `TPROC.DBF` / `TPROC10.DBF` | 7,717 / 7,712 | procedure codes and descriptions |
| `EMUSO.DBF` / `EMUSO10.DBF` | 3,206 / 3,184 | procedures flagged for multiple use |
| `TCNESBR.DBF` | 7,543 | establishments by CNES, plus 26 per-UF variants |
| `TCHBR.DBF` | — | establishments by CNPJ, plus per-UF variants |

The 14,197-row count in the brief is confirmed exactly. The modern `TAB_SIH.zip` (6,005,360 bytes,
modified 2026-08-17) carries 794 `.CNV` and 81 lookup tables.

### V5 — procedure table / SIGTAP · **resolved: in the kits, with a caveat**

A procedure code table **is** present inside the kits — `TPROC`, `TPROC10`, `EMUSO`, `EMUSO10`,
each `IP_COD` → `IP_DSCR` with a group code `IP_GP`. Code→description decoding needs nothing
further.

The caveat that matters: these are TabNet's procedure tables *for the kit's own era*, not the full
SIGTAP release. Anything depending on procedure **attributes** — validity windows, CBO and CID
restrictions, financing type, service/classification links — still requires SIGTAP from
`sigtap.datasus.gov.br`. The distinction is recorded in the resolution text rather than being
glossed as "solved".

### V6 — `.duck` storage version · **handled by construction**

DuckDB refuses to open a database written by a newer storage version. `decode/duckdb_.py` reads
the storage version straight from the file header (`DUCK` magic + LE uint64 at offset 8) and
raises a typed `DuckStorageVersionError` carrying it. The pipeline records that as an open
question with the observed version, never as a hard failure and never as a silently skipped file.

### V7 — `IBGE/projpop` · **resolved**

71 files named `PROJUF00.dbf` … `PROJUF70.dbf`, 93,560 bytes each — IBGE population **projections**
keyed by projection year 2000–2070, at UF level.

They do **not** supersede POPSVS: POPSVS is municipal and projpop is not. They complement it for
projected years and for national age structures.

A trap fell out of this. The usual two-digit-year pivot (≤ 40 → 2000s, else 1900s) reads `70` as
1970 and scatters a contiguous series across a century. `naming.infer_two_digit_epoch` chooses the
reading whose expanded years form the tightest contiguous span, per directory — which gives
2000–2070 here and 1996–2023 for SIM.

### V8 — the Ministry's own denominator · **open, with the comparison made cheap**

Not resolvable by reading the tree: it requires reproducing a published federal rate under each
candidate series and seeing which matches. The module ingests POPSVS, POPTCU, POP, projpop and
censo behind one interface precisely so that comparison is a one-line change, and
`load_population` refuses a stratification a series cannot support rather than silently returning
a coarser table. The question stays `open` in `open_questions` with that procedure attached.

### V9 — DEMAS endpoint granularity · **resolved**

Live spec: Swagger 2.0, `DEMAS - API de Dados Abertos`, **version 1.8.32**, **87 paths**. Every
endpoint the brief names still resolves, including both Previne Brasil ones.

`/daf/estoque-medicamentos-bnafar-horus` parameters: `codigo_uf`, `codigo_municipio`,
`codigo_cnes`, `anomes_posicao_estoque`, `data_posicao_estoque`, `codigo_catmat`,
`sigla_programa_saude`, `tipo_produto`, `sigla_sistema_origem`, `limit`, `offset`.

So the answer to the brief's three sub-questions is: **municipal — yes, and finer (per
establishment); monthly — yes (`anomes_posicao_estoque`); medication identity — yes, via
`codigo_catmat`.**

### V10 — `Dados_Abertos` naming grammar · **resolved: there is no new grammar**

The brief attributes 82 `DADOS_ABERTOS_UNPARSED_*` families to descriptive filenames. Measured,
the subtree's filenames are overwhelmingly *classic*: `DENGBR20.csv.zip`, `LEPTBR07.json.zip`,
`CHAGBR15.xml.zip` — prefix, geo, year.

What defeated the prior parser was the **composite suffix**. Its `strip_composite_suffix` handled
`.csv.gz` but not `.csv.zip`, so the stem became `DENGBR20.csv`, which matches no pattern. These
files are therefore not a new naming problem but *more of D3*: the same SINAN series republished
in three containers, which collapse into single families once parsed.

A genuinely descriptive tail does exist — `apac_atd.duck.zip`, `siasus_pa_ac.duck`,
`base_aih1.duck` — and gets its own grammar (`descriptive`, `descriptive_uf`).

### V11 — the 32 failed directories · **resolved**

Re-crawling with per-directory verb escalation resolves them. `SIHSUS/Doc` returns a genuine
`550 The system cannot find the file specified` — the path does not exist, as distinct from being
unreachable — and anything still failing after backoff persists as a `coverage_gaps` row rather
than a log line.

---

## 2. `[M]` claims that did not survive re-measurement

### D4's root cause is a listing-dialect bug, not a protocol limitation

The brief's design rule proposes escalating `MLSD → LIST → NLST` per directory and falling back to
content addressing where typed listing is unavailable. Both are good rules and both are
implemented. But the diagnosis was incomplete.

Measured: the server is **Microsoft FTP Service on Windows_NT**. `MLSD` returns
`500 Command not understood`. `LIST` works and returns the **IIS MS-DOS dialect**:

```
05-29-15  04:10PM                18550 acac0201.exe
02-24-18  07:38AM       <DIR>          199201_200712
08-17-26  10:07PM              6005360 TAB_SIH.zip
```

which carries **both size and mtime for every entry**.

The prior implementation's `_LIST_UNIX` regex matches only `ls -l` output. Every MS-DOS row failed
it; `_parse_list` then raised `"LIST returned rows but parser did not understand them"`; the
fallback chain ran to `NLST`, which carries no metadata at all. That is why
`inventory_files.size` and `.modified` are NULL for 124,810 of 124,810 rows.

So D4 is not "the protocol gave us nothing". It is "we asked correctly and could not read the
answer". `discovery/listing.py` parses both dialects and — importantly — treats a non-empty
listing it cannot parse as a **hard error**, never as an empty directory. Conflating those two is
how a whole subtree disappears silently.

Measured on a 9,667-file slice: **9,667 of 9,667 files carry both size and mtime.**

### SIH-RD has at least nine schema generations, not three

The brief's regression target: *"SIH-RD resolves to three generations — 35 columns (1992), 86
columns (2008–2014, has `DIAG_SECUN`), 113 columns (2017+, has `DIAGSEC1..9` and no
`DIAG_SECUN`)."*

Measured across January files for Acre, decoded and hashed by ordered field list:

| file | columns | schema signature |
|---|---|---|
| `RDAC9201.dbc` | 35 | `25acd6ef` |
| `RDAC9801.dbc` | 41 | `d572a887` |
| `RDAC0001.dbc` | 60 | `b94037e0` |
| `RDAC0501.dbc` | 69 | `32f7b80f` |
| `RDAC0701.dbc` | 75 | `3b553258` |
| `RDAC0801.dbc`, `RDAC0901.dbc` | 86 | `bc6a3d49` |
| `RDAC1101.dbc`, `RDAC1201.dbc` | 93 | `8066395a` |
| `RDAC1401` … `RDAC2401` | 113 | `e2f7244a` |
| `RDAC2601.dbc` | 114 | `d7f8d30a` |

The brief's three generations are real and present; they are simply a subset of what exists. Its
compendium held two sampled files for the family, so the intermediate generations could not be
seen — which is precisely defect D2, showing up in the brief's own numbers.

Note also that the 113-column schema appears from **2014**, not 2017.

### `DIAG_SECUN` in the 113-column generation is present, not absent — and that is worse

The brief calls this "a silent trap: a query asking for `DIAG_SECUN` against a 2020 file returns
empty with no error."

Measured in `RDAC2001.dbc` (113 columns, 3,784 rows): `DIAG_SECUN` **is present**, with **3,784
non-null values, every one of them `'0000'`** — one distinct value. `DIAGSEC1` in the same file has
514 non-null values across 99 distinct codes.

So the query does not return empty. It returns 3,784 rows of `0000`, which looks like data and
will be counted. An empty result at least invites suspicion.

This produced a detector the brief does not specify: `constant_column`, which fires on any
non-null column with exactly one distinct value, flags whether that value looks like a retired
placeholder, and raises an open question asking which field superseded it.

---

## 3. Design corrections the implementation required

These are not disagreements with the brief so much as places where building the thing revealed a
structure the brief left implicit.

### Codelists are not columns

Modelling `.CNV` entries as `(system, field, value) → label`, as the brief's `dictionary` DDL
suggests, produced **1,339,916 "conflicts"** on two kits. Almost all were spurious: `SEXO.CNV`,
`SIMNAO.CNV`, `REGIAO.CNV` and dozens of others all define the code `1`, and with `field_name`
NULL they collided with each other.

Codes are now stored once per **codelist** and attached to fields through a `field_codelists`
table populated from the `.DEF` declarations. Same two kits, same data: **41 conflicts**, all
genuine.

This also avoids duplicating 5,653 municipality rows once per column that uses `MUNICBR`.

### Dictionary entries need their validity window

With codelists separated, ingesting the modern `TAB_SIH.zip` alongside `TAB_SIH_199201-199712.zip`
still produced **76,115 conflicts** — because the same codelist name genuinely carries different
mappings in different eras. Municipalities were created, merged and renamed across twenty-five
years; both kits are correct for their own window.

Kits name that window in their filename (`TAB_SIH_199201-199712` → 1992-01 to 1997-12; a bare
`TAB_SIH.zip` is current), so `valid_from`/`valid_to` are read from it and made part of the entry
identity. §6.3 already calls for versioned entries; this is what makes the versioning operational.
Six kits now ingest with **5,133 conflicts** — real disagreements within a single window.

### Choosing which codelist labels a field

TabNet binds several codelists to one field on purpose: `DIAG_PRINC` binds to the full CID table
*and* to `CID10CAP` (21 chapters), `CID10GRUPO` (blocks) and per-chapter lists; `MUNIC_MOV` binds
to `MUNICBR`, `REGIAO`, `UF`, `CAPITAL` and the health-region roll-ups. These are not conflicts —
they are alternative aggregation levels.

Two rankings were tried and rejected before one worked:

- **By row count** — picks a grouping CNV that maps 14,000 codes onto 275 labels, silently
  relabelling every diagnosis as its chapter.
- **By distinct-label ratio** — picks `GCARDIO` (221 cardiac procedures, ratio 1.00) over `TPROC`
  (7,717 procedures, ratio 0.61), leaving 97% of procedures unlabelled; and `DISTRFEDERAL`
  (21 Brasília regions) over `MUNICBR` (5,653 municipalities).

What works is **observed coverage**: the codelist covering the most of the field's actual value
mass wins, with granularity breaking ties. That is a measurement, not a preference. The other
codelists stay reachable and `describe()` lists them as roll-ups.

Separately, `bind_by_semantic_type` attaches a reference table where the detectors measured
membership in it but no `.DEF` names it — the CID-10 table is bound to `DIAG_PRINC` this way,
recorded as `source='semantic_match'` so the weaker basis stays visible.

### Parquet is not smaller than a `.dbc` — and that is the wrong comparison

P3 calls raw DATASUS "a storage bomb" and expects Parquet to be a fraction of it.
Measured on `RDAC1901.dbc`, a 113-column modern SIH-RD file:

| form | bytes | vs `.dbc` | vs decoded |
|---|---|---|---|
| `.dbc` as published | 237,472 | 1.00× | 0.10× |
| decoded `.dbf`, row-wise | 2,309,017 | 9.73× | 1.00× |
| Parquet, labels + raw (default) | 318,163 | 1.34× | **0.14×** |
| Parquet, labels only | 240,365 | 1.01× | 0.10× |
| Parquet, raw only | 247,428 | 1.04× | 0.11× |
| Parquet, neither | 169,626 | 0.71× | 0.07× |

So the lake is **1.34× the published `.dbc`** and **0.14× the decoded form**. Both numbers are true and
only the second one means anything: a `.dbc` is itself compressed and cannot be queried at all until
it is inflated whole, which is the 2.3 MB row-wise DBF. The relevant saving is against the form you
would otherwise have to materialise, and there it is a factor of seven — before counting partition
pruning, row-group statistics and column projection, which are the actual reason a filtered read is
fast.

The gap between 1.34× and 0.71× is the cost of §7.1's rule that both the raw code and the decoded
label are kept. It is real — 215 columns instead of 129 — so `build --no-labels` exists to decline it.
Nothing is lost by declining: every code and every dictionary entry is still there, and
`load(..., labels=True)` can apply them at read time. The default keeps the brief's behaviour, and the
verify report now states which comparison it is making rather than quoting the flattering one.

### One outlier file must not redefine a directory

The date convention is inferred per directory, exactly as §5.2 requires. The first
implementation of the first rule was: *a tail outside 01–12 cannot be a month, so the directory is
annual.* That is sound logic and it was wrong in practice.

`SIHSUS/200801_/Dados` holds 22,807 files. All but two are monthly — `RDAC1901.dbc`,
`CHBR1901.dbc`, `SPAC2603.dbc` — and two are annual ZIP bundles: `RDAC2017.zip` and
`RDSP2017.zip`, whose tail is `17`. Under "any outlier proves annual", those two files flipped the
entire directory, and `CHBR1901.dbc` was dated to **the year 1901** instead of 2019-01. The whole
modern SIH series landed a century early, silently, and every stratum built on it was wrong.

`RDAC2017.zip` is the same file the brief singles out — the one whose accidental placement in a
separate family was the only reason the 113-column schema surfaced in the prior compendium at all.
It is an unusually load-bearing filename.

The convention is now the **dominant** pattern (≥98% of tails being valid months), and the outliers
that motivated the inference are themselves left undated with `date_format = 'ambiguous'` rather
than forced into the majority reading — under a monthly reading `2017` would mean month 17, and
inventing a date for it is precisely what §13 forbids. Measured after the fix: SIHSUS spans
1992–2026, zero files date before 1990, and exactly two files are undated.

### Codepage detection cannot be "first one that works"

cp850 and latin-1 both map all 256 byte values, so neither ever raises and "try in order, take the
first that decodes" always returns the first candidate regardless of correctness.

Measured: `IDENT.CNV` decoded as cp850 gives `Longa permanÛncia`. The byte is 0xEA — `ê` in
latin-1, `Û` in cp850. The file is latin-1 and the ordered approach chose wrong, silently, for
every accented label in the kit.

`textenc.py` scores candidates on how much the decoded text looks like Portuguese: letters
Portuguese actually uses count for, and the box-drawing and Nordic glyphs that appear when a DOS
codepage is read as a Windows one count heavily against.

### Performance corrections found by running it

- **Range expansion against a code universe** was a linear scan per range. The per-chapter CID
  files carry thousands of ranges each and there are dozens per kit — roughly a billion string
  comparisons. Truncation preserves sort order, so the matching codes are always one contiguous
  slice and bisect finds it.
- **Dictionary merging** read the whole `dictionary` table into Python per call. By the third kit
  that was scanning millions of rows to check a few thousand keys. The batch now goes into a temp
  table and the rest is a join.
- **Re-profiling an archive member** re-expanded the whole archive and derived seven new member
  strata from each existing one, multiplying on every run. A stratum that names a member now
  profiles only that member.

---

## 3b. Corrections after review

Three things were reviewed and changed after the first pass. All three were right.

### Labels for hierarchical classifications do not belong in the lake

The first implementation materialised a `<field>_label` column for every decoded field, following
§7.1 step 3 literally. For `SEXO` that is correct. For `DIAG_PRINC` it is wrong for three reasons
that have nothing to do with size:

* **It fixes a granularity choice invisibly.** `E11` and `E119` are distinct rows in CID-10.
  Whichever codelist won the coverage ranking became *the* label, and the analyst inherited that
  choice without being told one was made.
* **It discards the versioning this module built.** The 1992–1997 CID-10 has 14,197 codes and
  today's has 14,253; `valid_from`/`valid_to` exist precisely to keep both true. A string baked into
  a 2019 row throws that away and cannot be corrected without rewriting the lake.
* **The published wording is lossy and dated.** `DESCR` is 50 characters: `N39.0` reads
  "Infecc do trato urinario de localiz NE".

Code tables now live in `lake/reference/<table>/window=<valid_from>/` and are joined on demand:

```python
cid = load_reference("CID10", year=1995)   # 14,197 codes, the 1992–1997 table
cid = load_reference("CID10", year=2019)   # 14,253 codes, the current one
cbo = load_reference("CBO", code_width=6)  # CBO-2002, not CBO-1994
```

Small closed codelists still get a materialised label. `describe()` reports which policy applies,
names the reference table, lists its validity windows and its roll-up levels, and says how to join.
Meaning stays fully recoverable — P1 and §12 step 10 are unaffected — it simply stops being frozen.

`bind_by_semantic_type` was demoted at the same time. A distributional membership rate is an
inference, and §13 keeps inferences out of the labelling path; it is now promoted only when a record
layout independently names the same classification.

### `official_name`: one source is not "no source"

Reporting that `DIAG_PRINC` "has no official name" was scoped to `.DEF` and stated as though it were
general. `.DEF` enumerates TabNet's tabulation axes, so of course it names only roll-ups. The record
layouts carry the real thing, and they were sitting uncrawled in the `Doc/` trees:

```
41 DIAG_PRINC char(4) Código do diagnóstico principal (CID10).
36 VAL_TOT numeric(14,2) Valor total da AIH.
```

`IT_SIHSUS_1603.pdf` yields **144 SIH fields** with official descriptions and declared types, now in
`field_documentation`. `official_name` consults the record layout first, then a `.DEF` bound to the
labelling codelist, then a `.DEF` naming the field directly — and only reports `None` when all three
miss. That same layout text is what corroborates the CID-10 binding, which is how `DIAG_PRINC` now
resolves to the full table rather than to a 529-label roll-up.

### Codelist coverage is a measured gap list, not a whitelist

`pegasus-data gaps` ranks every undecoded field by observed row mass. Unrecognised lookup tables no
longer fall back to "first two columns": code and label columns are inferred from the data
(uniqueness and length) and recorded as inferred, at reduced confidence.

**CBO resolves at the first step of the search order** — it is already in the TabWin kits, no SIGTAP
or MTE trip needed. And the version question was real: `CBO` in the current SIH kit mixes **3,000
three-digit CBO-1994 codes with 2,813 six-digit CBO-2002 codes in one file**, with `CBO2002` shipped
separately at 2,445 codes. Reference tables therefore carry `code_width`, 452 mixed-width tables are
flagged as open questions, and `load_reference(..., code_width=6)` keeps a join on one vintage.

### Three idempotence bugs this work exposed

Derived state was being *accumulated* rather than *replaced*, in three places, with the same
consequence each time: a correction upstream could not propagate.

* `stratum_members` kept a file listed in the stratum it used to belong to, so a 2008 stratum went on
  claiming a 2020 file's 113-column schema after the date fix moved it.
* Orphaned strata survived re-inventory, dragging `families.time_min` back to 1901 long after the
  facts were corrected.
* `family_files` kept stale links, so the 113-column SIH-RD family pointed at 86-column files and
  normalised **zero rows** — a silent, total failure that produced no error at all.

All three now replace their derived rows, and a stratum whose sample is no longer among its members
is invalidated so the next profile re-derives it.

## 3c. The full-tree crawl, and what it found (2026-08-19)

### The prior inventory was missing a third of DATASUS, silently

The full crawl found **207,251 files** against the prior scan's 124,810 — **+82,441 (+66%)**, in
49 seconds across 362 directories, with size and mtime on 100% of them.

The delta decomposes almost entirely into directories the old scan never listed: 81,934 files from
53 such directories, plus 575 genuinely new ones. Of those 53, the old scan had *reported* 32 as
failures. The rest it never knew existed.

The largest is `SIASUS/200801_/Dados` at **54,199 files** — SIA outpatient production, 2008 to the
present, the biggest dataset on the tree. The old scan recorded `Dados` as a **file** under
`SIASUS/200801_`, and `uploads` as a file under the root. NLST returns bare names with no type
information, so an extensionless directory name is indistinguishable from a file; the crawl typed
both as leaves and never recursed. **No warning was emitted for either.** The inventory reported a
clean bill of health over a third of the archive it had never opened.

A silent loss is strictly worse than a loud one, and this is why the crawler now gives every entry
it cannot type a per-file `SIZE` probe, treating only a successful probe as evidence of a file. All
32 previously-failed directories now list successfully as well; three are genuinely empty on the
server and nine are container directories holding only `csv`/`json`/`parquet` subdirectories.

One coverage gap remains: `/dissemin/publicos/uploads` returns `550 Access is denied` to both LIST
and NLST. That is a server-side ACL, not a dialect failure, and is recorded rather than passed over.

### Reconciliation held at scale

All 34,029 previously-known files classified `unchanged`, with **0 gone, 0 moved, 0 unresolved** —
no mass-withdrawal artifact from the tree tripling in size. `Dados_Abertos/BackUp_Ducks_SIASUS_PA`
(66 `.duck` files) *did* disappear server-side, replaced by `PA_SIASUS` and `APAC_SIA`; it correctly
produced no `gone` rows, because those files were never in this catalog.

### The sticky prefix map held a wrong answer, correctly

`CM` was established as SIHSUS from 42 files seen in the partial crawl. The full crawl found 1,717
files at 98% agreement under SISCAN — `CM` is SISMAMA's mammography series. The map held its first
answer, which is the designed behaviour and was right: a reorganisation and a shared prefix are
indistinguishable from one crawl. But holding with *no way out* meant the first crawl owned the
answer forever, and the first crawl is the most likely to be wrong because it sees least.
`pegasus-data prefix-adjudicate` settles it deliberately. After adjudicating, system disagreements
fell from 1,675 to 42 — and those 42 are real: `CM` genuinely appears in both trees, 98/2.

### Low-trust prefixes cover almost nothing

1,351 of 1,436 learned prefixes are low-trust, which sounds alarming and is not: they cover 4,219 of
207,251 files (**2.04%**), and none carries as many as a thousand. 1,313 are simply thin (fewer than
five observations). The 38 genuinely ambiguous ones are SINAN diseases published in both the legacy
tree and `Dados_Abertos` — shared prefixes, not a reorganisation. The count alone would have hidden
that; ranking by file count is the point.

---

## 3d. Measured results that changed the design (2026-08-19)

### `lake_partitions` duplicated rows rather than zeroing them

`next_part_number` returned the count of parquet files already in the directory, so a rebuild after
a schema correction numbered itself *after its own stale output*: `part-00003` landed beside
`part-00000` and both stayed registered. `ds.dataset()` globs the directory rather than consulting
the catalog, so it read the union and returned **every row twice**. Pinned by a test at 10 rows
rebuilt into 20. Emptiness gets noticed; doubling gets published.

### `SP_ATOPROF` and `SP_PROCREA` are not 8-digit

The instruction expected 8-digit codes wanting `TPROC` rather than `TPROC10`. Measured: both columns
appear at **two widths** — `SP_ATOPROF` at 398 distinct 8-character and 400 distinct 10-character
values, `SP_PROCREA` at 400 and 395. `TPROC` holds 23,151 8-character codes and `TPROC10` holds
23,136 10-character ones, so the columns span the 1994-era table and the post-2008 Tabela Unificada.
Binding either alone leaves half the history unlabelled. Both are bound, and because matching is
exact-width, merging them is safe — the width selects the era.

### SIM's `CAUSABAS` contains ICD-9, not malformed data

386 of 5,000 sampled values failed ICD-10 shape validation. 338 of those are valid **ICD-9** codes
(`7999`, `7680`, `8199`): SIM ran on CID-9 until 1996 and those years are still on the tree. Filing
them as "malformed" hides a revision boundary and invites someone to clean real records away. The
quality report separates "valid under another revision" from "structurally broken", because one
wants a second reference table and the other wants investigation.

### SIM's `ATESTADO` separates on `/`, not `*`

The causal-chain fields `LINHAA`–`LINHAD` and `LINHAII` are `*`-delimited four-character codes —
confirmed independently by measurement (10,196 of ~12,000 inter-`*` segments are exactly 4
characters) and by curation. `ATESTADO` is not: it uses `/` (`T71/X700`, `S069/X954`). The delimiter
is now chosen by measured coverage rather than by position in a candidate list, which took
`ATESTADO`'s multi-code detection from 66 to 2,031 values and its malformed count from 2,526 to 486.

### `IBGE.IDADE` is bound to CID10 and matches nothing

A distributional detector bound it at 0.35 confidence because age-band codes like `2559` and `1524`
have exactly the shape of an ICD-9 code. Shape is not identity. A near-zero match rate is now
reported as a *finding* rather than as poor coverage, because the two want opposite responses: one
needs a better table, the other needs the binding deleted.

### 29 SIH columns are dead in the current generation

Testing for sentinel-only content in the **newest** generation rather than across a column's whole
history flagged 29 columns, not 13. Among them `DIAG_SECUN` (the known case), `CID_ASSO`,
`CID_MORTE`, `SP_CIDSEC`, and the `UTI_MES_*` and `TPDISEC*` families. A column that is still
emitted and carries only `'0000'` is worse than an absent one, because absence is visible.

### SIGTAP is reachable, over HTTP only

HTTPS times out on both `sigtap.datasus.gov.br` and `tabela-unificada.datasus.gov.br`; HTTP/80
answers 200. The exports live on `ftp2.datasus.gov.br/public/sistemas/tup/downloads` — **224 monthly
vintages, 200801 to 202608**. Not "unreachable" and not "not permitted": plain HTTP only, which is a
different finding with a different remedy. Every table ships its own fixed-width layout file, so
nothing hardcodes an offset.

Ingesting the newest export gave 44,984 entries and closed the CBO width problem from a
**first-party** source: `tb_ocupacao` carries 2,719 occupation codes at a single width, where the
FTP tree's CBO file mixes 3,000 three-character CBO-1994 codes with 2,813 six-character CBO-2002
codes in one file.

### Layout documents exist for SIM and SINASC, in a different dialect

The harvester only knew the `IT_*` dialect, so `Estrutura_do_SIM_2025.pdf` and
`Estrutura_SINASC_para_CD.pdf` — both sitting on the tree — yielded nothing. Adding the `Estrutura_*`
dialect took layout coverage from 163 field descriptions across 5 documents to **331 across 8**.

The extraction needed three passes to be trustworthy, and the failure is worth recording: those
tables number their rows with exactly the syntax a value list uses (`4- Naturalidade`), so the loose
value-line rule was reading the document's own row counter and attributing it to whichever field
came last. SIM's causal-chain fields were being told they had a code `40` meaning "Causas da". Fixed
by detecting the dialect and taking values only from the valid-values cell, where the shape can be
checked: at least two distinct codes, numeric runs starting at 0 or 1.

### `COD_IDADE` is deliberately unbound

The instruction expected five distinct values and that "the codelist certainly exists". Measured:
**six** distinct values (0–5), and **no codelist of time units exists** in the 4.0M dictionary rows
ingested. The `.DEF` files bind `COD_IDADE` to `IDADEPUB`, `IDADEBAS`, `IDADEDET` and `IDADE18` —
all four are TabNet age-**band** axes with 3-character codes labelled `< 1 ano`. They decode a
tabulation axis, not this column.

Guessing here is the one error in the gap list with clinical consequence: `IDADE=030` with the wrong
unit turns thirty-month-old infants into thirty-year-olds. It is recorded as the open question
`semantics.cod_idade_units`, naming exactly what would close it, and the derived `IDADE_anos` column
is withheld until it is. No derived age beats a wrong one.

### CEP: settled, and recorded as settled

Three independent reasons, any one sufficient. No CEP table exists anywhere on the tree, and there
is no reason to expect one — CEP is Correios' property, not the Ministry's. The Correios data that
would close it is licensed. And CEP combined with sex and date of birth, both present in these
files, narrows a patient to a household. Recorded as a **resolved** question rather than left open,
because a settled "no" that keeps appearing as unfinished work is indistinguishable from a task
nobody has got to.

---

## 3e. The contradiction was ours (2026-08-19)

### 311,844 contradictions, all manufactured

Sweeping every bound codelist for self-contradiction — a code carrying more than
one label — measured **311,844 (code, window) pairs across 264 codelists**.
Grouped by system as well as by codelist: **zero**. Every single one was created
here, not shipped by DATASUS.

Reference tables were keyed on the codelist name alone. Thirteen systems ship a
file called `SEXO.CNV` and they do not agree — SIHSUS codes sex `1`/`3`, SINASC
`1`/`2`, SINAN `M`/`F` — so all thirteen were merged into one table in which `1`
meant Masculino *and* Feminino. `ANO` is shipped by 15 systems, `MUNICBR` by 11.
Reference tables are now scoped by system, and a field decodes against its own
system's copy.

A second class was cross-**vintage**: reading with no year merged every validity
window, and SIHSUS renders `C96.7` as "…tec linf hematop e relac" today and "…e
corr" in the 1992–1997 kit. That is one code whose label was reworded, not two
meanings. A read with no year now returns the current vintage.

SIHSUS/RD went from sixty warnings to **zero**: `SEXO` renders as *Feminino*,
`MUNIC_RES` as *120020 Cruzeiro do Sul*, `DIAG_PRINC` with its label.

### The damage was never written to disk

The important question was not whether the code was fixed but whether wrong
labels had already reached Parquet, where no test would find them and a consumer
would read them as fact.

They had not. Every stored `*_label` value in every built partition was compared
against the labels its field's own binding allows, scoped to that partition's
system: **149 values checked, 0 contradicting, 0 unverifiable**. The build
normalises through a system-scoped dictionary cache and never had the merge bug —
it was introduced later, in the read path only, and lived for hours in one
working tree. Stored `SEXO` labels read `1 → Masculino, 3 → Feminino`, which is
SIH's correct coding and an independent cross-check of the render fix.

This is now a standing verify assertion rather than a one-off audit. The loose
form of it — matching a code against every codelist in the system — produces
false alarms, because `4` means one thing in `FINANC` and another in `REGIAO`;
the check scopes to the field's own binding.

---

## 3f. Classification changes, not data going bad (2026-08-19)

### SIM: CID-9 and CID-10 overlap on the tree

The instruction proposed a 1996 boundary. Measured, a year boundary is wrong:
`SIM/CID9` spans **1979–1998** and `SIM/CID10` spans **1996–2024**, so the two
overlap for three years and any threshold mis-assigns them.

Both classifications are bound instead, which resolves it per row rather than per
year. That is safe because the code spaces are disjoint — SIM's 9,740 CID-9 codes
and 14,198 CID-10 codes share **exactly zero** codes, CID-9 being numeric and
CID-10 letter-prefixed — so exact matching selects the right classification
without anything needing to know a row's vintage. Recorded as `vintage_note` in
the variable dictionary, which is now a first-class field.

### SIH: the same, in a different shape

The same applies to SIHSUS and nobody had noticed, because its CID-9 era does not
look like SIM's. **426 of the 1,590 distinct `DIAG_PRINC` values are 6-digit
numeric**, and they are CID-9: `065099` decodes to "650 - Parto normal". The kit
ships CID-9 as **seventeen chapter files** rather than one table, so all
seventeen are bound alongside `CID10`. Safe on the same grounds: 7,681 codes
across the seventeen chapters with **zero** contradicting labels, and zero
overlap with CID-10.

### Presence in a bound table now outranks shape

Finding SIH's 6-digit form changed the rule. A shape regex is a heuristic and a
narrow one — SIM writes CID-9 as three or four digits, SIH as six — and no
pattern should have to know that. If a codelist bound to the column decodes the
token, the token is valid. That is proof; the regex is inference.

### ATESTADO mixes two separators

`T07/X366*Y96` — one cell, both `/` and `*`. Splitting on the heavier one leaves
the other inside a token, and the whole value then fails every check. A token
rule may now name a *set* of separators.

### The measurement, before and after

| column | malformed before | after |
|---|---|---|
| `SIM.CAUSABAS` | 386 (7.7%) | **0** |
| `SIHSUS.DIAG_PRINC` | 552 (11.0%) | **0** |
| `SIM.ATESTADO` | 2,526 → 486 | **283 (8.8%)** |
| `SIM.LINHAA–LINHAD` | 3 | 3 (0.06%) |

Across all 23 ICD-bound columns: **913 of 53,156 values malformed (1.72%)**.

`IBGE.IDADE` still reports 619 malformed and should: it holds age bands like
`2559` and is bound to CID10 only because a distributional detector matched on
shape. That is the false binding already recorded as an open question, and
leaving it visible is the point.

---

## 3g. A schema census, not a schema sample (2026-08-19)

### The catalogue was a sample because a census looked unaffordable

Profiling reads a file to learn what its columns *contain*, and that needs the
payload. One representative file per stratum totals **183 GiB**, and 63% of
strata hold exactly one file, so there is no cheaper member to substitute. Every
schema statement this project made therefore came from a sample, and "SIH-RD has
N generations" always meant "N generations were sampled".

That constraint turned out to be an artefact of asking the wrong question. A DBF
declares its entire schema — every field name, type, width and decimal count — in
a header of a few hundred bytes. A `.dbc`, DATASUS's compressed DBF, stores that
header **uncompressed** ahead of the compressed payload. So the schema is
readable from a ranged fetch of the first few KB, and the payload is needed only
for questions about values.

Measured on `RDAC9201.dbc`: all 35 fields read from the first **1,153 of 91,967
bytes**, 1.25% of the file. Run over the whole tree: **3,701 strata examined, 2,813 schemas read for
19.23 MB**, against 183 GiB for the decode-everything route — a reduction of
about 9,750x. 859 targets are not DBF-shaped (CSV, XML, JSON, archives) and are
counted apart from the 29 that failed on the network after four retries.

### Validated two independent ways

The shortcut is only worth having if it gives the same answer as a full decode.

* **Against full decodes.** 571 cached `.dbc`/`.dbf` blobs had their
  prefix-parsed field list compared against the field list from a complete
  decode: **571 identical, 0 differing**, including an 87-column SIM file and
  48-column CID-9-era files.
* **Against the files' own arithmetic.** Every catalogued schema's field widths
  sum exactly to its declared record length, plus one byte for the DBF deletion
  flag: **100%**. A misread descriptor array would not add up.

Only two DBF type codes appear anywhere on the tree — `C` (character) and `N`
(numeric) — which is consistent with DATASUS writing dates and codes as text.

### What the census found that the sample could not

| series | generations | field range | span |
|---|---|---|---|
| `SIHSUS/RD` | **20** | 35–114 | 1992–2026 |
| `SIM/DOFET` | 18 | 40–99 | 1979–2026 |
| `SIM/DOEXT` | 13 | 40–88 | 1979–2026 |
| `SIM/DO` | 11 | 40–88 | 1996–2026 |
| `CNES/ST` | 3 | 200–208 | 2005–2026 |

The brief said SIH-RD had "exactly three" schema generations (35, 86, 113). An
early sample found 13. The census finds **20**, from 35 to 114 columns. The
progression is not a correction of the brief so much as a demonstration of what
sampling does: each wider look found more, because the answer was always "more
than you have looked at".

### Recorded apart from profiles, deliberately

Census results land in `schema_header_facts` and mark the stratum `'header'`,
never `'ok'`. A profile has read the data and can speak about values; the census
has read a few hundred bytes and can speak only about columns. Merging them would
let "we know this column exists" be read as "we know what is in it", which is the
class of error this project exists to prevent. They share `schema_signature`, so
a census entry and a profiled sample of the same shape land on the same family.

---

## 3h. Reading what DATASUS never published (2026-08-19)

CNES is the clearest gap on the tree: 163 categorical columns, a thin record
layout, and value codings that live almost entirely off the FTP tree. No crawl
closes that, and leaving it blank means columns are unlabelled that every
practitioner in the field can already read.

`rfsaldanha/microdatasus` (MIT) is an R package that recodes DATASUS microdata,
and its `process_*.R` files encode value labels as literal `"code" ~ "label"`
pairs. Parsed — never executed — it yields **4,655 code→label pairs across 582
labelled columns**, including CNES (163 fields, 726 pairs) and SIA (37 fields,
570 pairs).

It is ingested at `source='community'`, which sits below `pdf` and above
`inferred`, and two properties make that safe. It cannot outrank a first-party
table: `SOURCE_AUTHORITY` places it behind `cnv`, `def`, `sigtap`, `dbf_lookup`,
`demas_api` and `pdf`, and a test drives a contradicting community label against
a stored `.CNV` one to confirm the `.CNV` holds. And every entry carries the
repository, the **commit SHA** and the file in `source_ref` — a transcription
without a version is a rumour; with one it is a citation someone can re-run.

One parsing detail worth recording: a pair belongs to the field whose
`if ("X" %in% variables_names)` block encloses it. Scanning the file for pairs
without that bracketing would smear every column's codes across every other
column, which is worse than extracting nothing.

---

## 3i. What the catalogue holds now (2026-08-19)

After the census, the community ingestion and the reference rebuild:

| | |
|---|---|
| files crawled | **207,251** |
| strata | 4,418 |
| strata with a known schema | **3,688** (83%) |
| distinct schemas | **273** |
| distinct columns known | **4,354** |
| dictionary rows | 19,905,196 |
| codelists | 10,748 |
| field→codelist bindings | 9,304 |
| systems documented | **16** |
| columns that decode | **2,159** |

The gap between "described" and "decodable" is worth stating because they are
different facts and only reporting the first buries the second. CNES has 4
described columns and **156** whose values now translate; SINAN has 0 and
**1,178**. Across all systems, 268 columns carry a prose description and 2,159
have a working codelist.

The 1,339 open questions are not a backlog that grew — they are the mixed-width
tables, the unlabelled codelists and the suspect bindings that the system names
rather than papering over. A gap you can query is a different thing from a gap
you cannot see, which is the whole thesis of §0.

### Where the schema catalogue still stops

705 strata are sampled by a `.zip`, whose members need the archive rather than a
prefix; a `.parquet` keeps its footer at the end of the file; 7 are LHA
self-extracting `.exe`. These are counted apart from the 30 that failed on the
network, because "needs a different reader" and "the fetch broke" want different
responses and only one of them is fixed by trying again.

---

---

## 3j. Identifiers and re-identification risk in public SIASUS files (2026-08-21)

**This section is the reason the personal-identifier detector exists, and it is
the one finding here that is not about data engineering.**

An earlier draft of this section (2026-08-20) claimed that CPFs were published
alongside HIV results. **That claim was wrong and has been withdrawn.** It was
drawn from column *names* and value *shapes* without testing either. Both are
now tested, and what is actually there is set out below. The correction is kept
in view rather than quietly edited away, because the difference between the two
readings is exactly the difference between a credible referral and one that
falls apart on first inspection.

### Method

Two things make these claims decidable rather than a matter of appearance:

- **CPF, CNPJ and CNS all carry check digits.** A value either satisfies its
  algorithm or it does not. A random 11-digit string passes the CPF check about
  1% of the time, so a 0% or 100% rate over hundreds of values is not chance.
- **The join can be executed** rather than inferred from two columns happening
  to hold values of the same width.

Everything below is measured on the files, not on the catalogue's metadata.

### Finding 1 — patient identifiers are obfuscated, not published

Measured on `SIASUS/APAC/2002/acac0201.exe` (Acre, January 2002) and on four
2008-schema `.dbc` files (16,918 rows):

| column | values | distinct | pass check digit |
|---|---:|---:|---:|
| `PAC_CPFPCN`, `EXA_CPFPCN` | 52 each | 52 | **0 (0%)** |
| `APA_CPFPCN` | 305 | 117 | **0 (0%)** |
| `COB_CPFPCN` | 485 | 119 | **0 (0%)** |
| `PAF_CPFPCN` | 98 | 98 | **0 (0%)** |
| `OPC_CPFPCN` | 155 | 1 | **0 (0%)** |
| `AP_CNSPCN` | 16,918 | ~93% distinct | **0 (0%)** |

Every column whose name ends `PCN` — *paciente* — fails. `AP_CNSPCN` fails
harder than that: its values contain **no digits at all** (`é{~…|{{`,
`âäâ{{|{|äü}Çââ}`), fifteen characters of transformed bytes. They stay highly
distinct, so they still function as a per-patient pseudonym that links a
person's records to each other — but they are not a readable CNS, and they do
not identify anyone outside DATASUS.

**There is no evidence in this data that DATASUS publishes patient CPFs or
CNSs in the clear.** The apparent CPFs in the 2002 files are eleven digits that
are not CPFs.

### Finding 2 — professional and director CPFs *are* real, and are published

The same file, same test, opposite result:

| column | whose | values | distinct | pass check digit |
|---|---|---:|---:|---:|
| `APA_CPFRES` | responsible professional | 305 | 42 | **305 (100%)** |
| `APA_CPFDIR` | clinic director | 305 | 4 | **305 (100%)** |
| `UDI_NFRCPF` | nurse | 2 | 2 | **2 (100%)** |
| `UDI_DIRCPF` | director | 2 | 2 | **2 (100%)** |

100% validity over 612 values is not an accident of formatting. These are real
CPFs of identifiable individuals, in an unauthenticated FTP directory. The
distinct counts are small — **four** directors, forty-two responsible parties —
so each value maps to one named professional at a known clinic in a known
municipality, which is what makes it identifying rather than merely sensitive.

`AP_CNPJCPF` also validates 100% (16,918/16,918) but as **CNPJ**, with 3–62
distinct values per file: those are establishments, not people. It does not
belong on a list of personal identifiers, and the earlier draft was wrong to
put it there.

### Finding 3 — the patient record is re-identifiable, and carries serology

This is the finding that survives, and it is the serious one.

`EXAC0201.DBF` holds `EXA_HIV`, `EXA_HBSAG`, `EXA_HEPAT` and `EXA_HLA` **in the
same table** as the patient block's key. The join to `PCAC0201.DBF` was executed,
not assumed: `PAC_NUM` ↔ `EXA_NUM`, 52 rows against 52 rows, 52 distinct keys
each, **52/52 matching, one to one**. `EXA_HIV` over those rows: 51 `N`, 1 `P`.

What sits on the joined record, all of it real and unobfuscated:

```
PAC_NASCPC  19351014   full date of birth
PAC_SEXOPC  M          sex
PAC_MUNPCN  120040     municipality
PAC_CEPPCN  69900000   postcode
PAC_UFNASC  AC         state of birth
PAC_DIAGPR  N189       CID-10 primary diagnosis
PAC_DIAGSE  N189       CID-10 secondary diagnosis
```

The modern schema is no better on this axis: in `ADGO1403.dbc`, `AP_CEPPCN`
holds full eight-digit postcodes with 2,484 distinct values over 5,670 rows,
beside age, sex, race, municipality and CID-10.

Date of birth, sex and postcode are the classic quasi-identifier triple, and in
Brazil an eight-digit CEP frequently resolves to a single street segment. Fifty-two
dialysis patients in one small municipality, each with an exact birth date, is not
an anonymous population. **No direct identifier is needed to re-identify these
people, and an HIV result is attached to the record.**

### And it is data the earlier scan never saw

The 2002 files are self-extracting `.exe` archives. The prior scanner excluded
them by extension — defect D1 — so 1,723 APAC files were absent from its
inventory entirely. Recovering them was a correctness win for coverage (§1) and
is *also* what surfaced this.

### What this module does, and deliberately does not do

Every one of these columns **passes through unmodified**. Nothing is masked,
hashed, truncated or dropped, and that is a decision rather than an omission:

- Masking in a library would destroy the evidence that the data was published.
  A researcher receiving a masked extract cannot tell whether the Ministry
  publishes these columns or whether a tool removed them.
- The remedy is not a client-side transformation. It is a decision about what
  DATASUS publishes, and that requires the Ministry to see the finding.
- Deciding what may be disclosed about a named person is not a call a data
  library is entitled to make.

What the module does instead is **make it impossible to miss**: the detector
flags the columns, the ledger raises an open question, the generated
documentation carries the warning, and this section records the measurement.

### What is NOT established

Stated plainly, so that nobody carries these forward as though they were:

1. **Whether the patient pseudonyms are reversible.** They are stable and highly
   distinct. Whether the transformation is recoverable was not investigated, and
   deliberately so — that work would itself be an attempt at re-identification.
2. **Whether `CNS_PAC` in PAINEL_ONCOLOGIA and CMD behaves like SIASUS's.** It
   appears in 11,628 files across two systems and was **not** tested; the
   obfuscation measured here is a SIASUS result and must not be generalised to
   it. The curation note on that column is marked unverified.
3. **Whether the 2002 pattern holds across all 1,723 APAC files.** One file was
   joined. The schema is shared, so the structure almost certainly is, but
   "almost certainly" is not a measurement.
4. **Actual re-identification was not attempted.** Finding 3 is an argument from
   the quasi-identifiers present, not a demonstration.

### For whoever takes this forward

The column-name census (this counts *names in DBF headers*, not verified values
— all 144 `AP_CNSPCN` strata are `sample_status='header'`):

```sql
SELECT sp.field_name, SUM(s.file_count) AS files
  FROM schema_presence sp
  JOIN strata s ON s.schema_signature = sp.schema_signature
 WHERE sp.field_name LIKE '%CPF%' OR sp.field_name LIKE '%CNS%'
 GROUP BY 1 ORDER BY files DESC;
```

The claims that matter are the value-level ones, and they are reproduced by
reading `SIASUS/APAC/2002/acac0201.exe`, running each identifier column through
its check-digit algorithm, and joining `PAC_NUM` to `EXA_NUM`.

**The referral should lead with Findings 2 and 3.** Finding 1 is exculpatory and
should be stated in the same breath: DATASUS is already protecting the patient
CPF and CNS, which is evidence that the omission in Findings 2 and 3 is an
oversight in the same system rather than indifference.

Open question: `V.pii_disclosure`. It is not resolvable by this project — it
closes when the Ministry answers, and until then it stays open on purpose.

---

## 3k. A municipality labelled as its health region (2026-08-23)

### Four correct mechanisms produced a wrong answer

`CODMUNRES = 120040` is Rio Branco. It came back **"Baixo Acre e Purus"** — the
health region Rio Branco sits in — and had done for weeks. Nothing was broken.
Each layer did what it was designed to do:

1. `.DEF` binds SINASC's `CODMUNRES` to **145 codelists**, every one at
   confidence 0.9. TabNet declares tabulation axes beside code systems and the
   file format cannot distinguish them, so every axis a municipality can be
   rolled up along arrives as a "binding".
2. `_rank` breaks a confidence tie on name affinity, then **alphabetically**. No
   table is called `CODMUNRES`, so with 145 candidates tied the tie-break that
   actually decided the label was alphabetical order.
3. `CIRAC` sorts 3rd. `BR_MUNICIPALFA` sorts **118th**.
4. `_choose_binding` measures only the first `_MAX_CANDIDATES` (12) candidates —
   a deliberate cost bound, since `.DEF` binds `DIAG_PRINC` to 114 tables.

So the correct table **was bound, was never loaded, and was never measured**.
`CIRAC` — 24 rows, 4 distinct labels — decodes 100% of Acre's municipality codes
and won.

The granularity tie-break added for `CNES → HOSFEDRJ` (§3, "Choosing which
codelist labels a field") was written for exactly this shape and could not fire:
it only ranks candidates that were *measured*. The rollup guard did fire and
named the problem in a warning — which is not the same as not doing it. A caller
who did not read warnings got a region where they asked for a city.

The candidate counts are worth recording, because they are what makes ranking
unusable here:

| column | codelists bound | where `BR_MUNICIPALFA` sorts |
|---|---:|---:|
| `SIM.CODMUNRES` | 156 | 123 |
| `SIM.CODMUNOCOR` | 152 | 119 |
| `SINASC.CODMUNRES` | 145 | 118 |
| `SINASC.CODMUNNASC` | 144 | 118 |
| `SINAN.ID_MUNICIP` | 51 | 11 |
| `SIA.AP_MUNPCN` | 49 | 34 |
| `SIH.MUNIC_MOV` | 33 | 23 |

**The fix is that the link is stated, not inferred.** The variable → decoder
link is a static build object; a municipality column names its table in curation
and ranking never gets to decide. 167 corrections across 36 curation files.

### DATASUS ships six municipality tables and they are not interchangeable

This is the durable knowledge, and nothing in the tree says it:

| table | rows | exact keys | distinct labels | granularity | notes |
|---|---:|---:|---:|---:|---|
| `BR_MUNICIPALFA` | 5,647 | 5,642 | 5,596 | **0.992** | accented, **UF-suffixed** (`Rio Branco, AC`), 5 ranges |
| `BR_MUNICGESTOR` | 5,645 | 5,641 | 5,595 | 0.991 | the same cities **plus** `120000 → 'Acre - Gestão estadual'` |
| `BR_MUNICIP` | 56,753 | 5,721 | 5,660 | 0.989 | ALL-CAPS, unaccented, ~10 duplicate rows per key |
| `MUNICBR` | 12,470 | 6,078 | 5,687 | 0.936 | **41% of rows are ranges**; sentinels read `12eeee AC - gestão estadual` |
| `??_MUNICIP` / `MUNIC??` | ~32–5,130 | — | — | — | one state each. `MUNICAC` is Acre's 32 municipalities |
| `CIRAC` and kin | 24 | 24 | **4** | **0.17** | health regions. A rollup wearing a municipality's key space |

Three consequences:

* **`BR_MUNICIPALFA` is the municipality table.** The UF suffix is not
  decoration: roughly 250 Brazilian city names are shared across states, so
  without it the label is ambiguous exactly where a national analysis needs it
  not to be.
* **The `gestor` columns need `BR_MUNICGESTOR`, not a plain city list.** SIA and
  SIH record the managing authority as a municipality code *with a state-level
  sentinel* — `UF0000`, and `129999`-style variants. In real SIA-PA data
  `120000 → 'Acre - Gestão estadual'` is the **most common value** (40,650 of
  55,963 rows). A plain municipality table has no row for it.
* **`MUNICBR` is kept as a secondary, not discarded.** It holds 436 keys
  `BR_MUNICIPALFA` lacks. 371 are ignorado/exterior variants and 3 are
  gestão sentinels, but **62 are real municipalities**: the Goiás towns
  transferred to Tocantins in 1988 (`520040 Almas (transf. p/TO)`,
  `520210 Araguaína`…). They can only appear in SIM's earliest years, and
  dropping the table would silently lose them.

### A curated codelist that does not exist decodes nothing, silently

A curated `codelist:` **bypasses measurement by design** — it is a human
decision and nothing may widen it. The consequence had not been thought through:
a name that does not ship does not fall back to a bound table. It produces an
empty label column, no warning, and no error.

**56 references were in this state, across 16 distinct names.** Two dominate:

* `ibge_municipio` on **30 columns** (SINAN and PAINEL_ONCOLOGIA) — a name
  invented in curation that was never a DATASUS table;
* `'..._MUNICIP (per-UF IBGE municipality lists)'` on **6 columns** — a **prose
  placeholder** sitting in a codelist list, in SIASUS `pa.yml` and `_shared.yml`.

The rest were near-misses worth recording as a dialect note: `AGRAVNET` for
`AGRAVONOTS`, `IMUNOCOB` for `IMUNOC`, `TPAPAC` for `TP_APAC`, and six
`CADGER**` names for per-state CNES registries that **do not ship at all** —
those are registry-by-design, and the claim was dropped so measurement runs
instead.

`tests/test_every_curated_codelist_actually_exists` now makes this
unrepresentable.

### Per-UF lists were being applied to national data

A separate defect in the same family, and not a rollup — simply the wrong 0.6%
of the country:

* `SIM.MUNIOCOR` and `SIM.MUNIRES` named `AC_MUNICIP` — Acre's 32 municipalities;
* `SINAN.ATE_MUNICI` and `NM_MUNIC_H` named `MUNICAC`;
* `SINASC.MUNI_MAE` and `MUNI_OCOR` named `BR_CAPITAL` — a list of **capitals**,
  so every birth outside one was unlabelled or folded onto one.

### `code_system` disagreed with itself on 14 municipality columns

§5 names "IBGE município" in its own definition of `external`: the code **and**
the label, because the code is a join key. Fourteen columns said otherwise, and
the two ways of disagreeing failed differently:

* **`internal` (4 columns)** *replaces* the code with the label. `SIM.CODMUNRES`
  came back holding `'120001 Acrelândia, AC'` and nothing joinable — while
  SINASC's identically-meant column kept both. The same fact had two shapes
  depending on which system you asked.
* **`none` (10 columns)** means "the value as typed" and skips labelling
  entirely, so ten columns had a municipality table bound and quietly never
  used it.

### Two defects found by reading a produced CSV, not by a test

Both had passed 1,125 tests. Neither had an assertion anywhere on the rendered
*string* a person actually opens.

**A combined value repeated the code.** `--profile report` joins `code – label`,
and many DATASUS `.CNV` tables write the code into the label itself
(`BR_MUNICIPALFA` maps `120001` to `'120001 Acrelândia, AC'`). Every
municipality cell of every report-profile export read:

    120001 – 120001 Acrelândia, AC

`_combine` now skips the prefix when the label already opens with the code and
the next character is a boundary — the boundary check is what stops code `12`
being swallowed by label `'120001 Acrelândia'`, where the match is a coincidence
of digits.

**The data dictionary described nothing on the CLI's default path.** The
`report` profile translates headers *during* rendering, so a dictionary built
from the rendered table was looking up `"Mother's age"` in a curation layer keyed
on `IDADEMAE`. Every entry came out a bare heading with no prose.
`RenderReport.renamed_headers` now carries `rendered → DATASUS`.

### What was measured, and against what

Real fetches against the live tree on **2026-08-23**, not fixtures:

| dataset | rows | result |
|---|---:|---|
| `SINASC-DN` AC 2022 | 28,966 | `120040 → 'Rio Branco, AC'` on 10,706 rows; **0** unlabelled municipality cells; **0** rollup warnings |
| `SIM-DO` AC 2022 | 4,159 | `CODMUNRES`, `CODMUNOCOR`, `CODMUNNATU`, `COMUNSVOIM` all correct, code **and** label |
| `SIH-RD` AC 2022-01 | 3,977 | `MUNIC_RES`, `MUNIC_MOV` correct; `UF_ZI → '120000 Acre - Gestão estadual'` |
| `SIA-PA` AC 2022-01 | 55,963 | `PA_MUNPCN`, `PA_UFMUN`, `PA_GESTAO` — **0 unlabelled of 55,963** each |
| `SINAN-DENG` BR 2022 | 1,405,095 | `ID_MUNICIP`, `MUNICIPIO`, `COMUNINF` all resolve to cities (395 s, 132 cols) |

`999999 → 'Ignorado ou exterior'` on 18,769 SIA rows is the genuine DATASUS
sentinel for unknown/foreign residence, not a decode failure.

Final state: **128 columns** bound to `BR_MUNICIPALFA`, **12** to
`BR_MUNICGESTOR`, **0** phantom codelist references, **0** municipality columns
on a rollup or a per-UF list, 1,131 tests passing, ruff clean.

### The lesson, stated plainly

Every one of these six defects was invisible to the test suite and visible in
the first CSV anyone opened. The suite asserted on column lists, coverage
percentages and report objects — never on the rendered value. Ranking, coverage
and "labelled: yes" are all measurements of the *process*; only the string in
the cell measures the *answer*.

---

## 3l. Review closure exposed four reusable engineering rules (2026-08-23)

The second external review mostly found software defects, recorded formally in
`DEFECTS.md`. Four conclusions belong here because they generalise beyond the
individual fixes and consolidate the durable parts of `HANDOFF.md`:

1. **Semantic provenance may be hidden from the result, never from the
   operation.** `_source_path` and `_competencia` are internal columns used to
   choose a family and a month-exact codelist window. Projection may remove them
   only after rendering. A provenance column is not optional merely because the
   caller did not ask to see it.
2. **A resource cap cannot decide meaning.** Loading twelve of 145 candidate
   codelists is a valid cost limit and an invalid evidence rule. Uncurated sets
   above the cap are now refused; a declared codelist bypasses ranking.
3. **System independence is positive evidence.** A `system = NULL` row in the
   shipped pack means every observed system agrees and can be shared. The
   absence of one system's table does not mean a neighbour's table is safe.
   Foreign-system borrowing is therefore opt-in and reported.
4. **The transaction unit is the unit readers observe.** A state-year lake
   partition, a population series and a DEMAS endpoint are directories, not
   individual Parquet files. Staging one file and sweeping siblings later still
   exposes mixed generations. Complete trees are built aside and swapped.

`HANDOFF.md`'s ranking incident, output-inspection warning, settled PII policy
and operational cautions are otherwise already represented in §3j–§3k and the
architecture; duplicating them here would create a second, drifting bookkeeper.

---

## 3m. The next architecture is evidence compilation, not warehouse shipping (2026-08-23)

Three read-only audits settled the design before implementation:

1. `scripts/storage_report.py` measured the recovered 15.0 GB catalog with
   SQLite `dbstat`. There were no free pages. `code_tables`, `dictionary` and
   four repeated B-tree indexes explain nearly all of the file. SQLite is not
   intrinsically the cost; expanded maintainer evidence and duplicated lookup
   paths are. Runtime resources should remain compiled Parquet projections.
2. `scripts/audit_representations.py` found 4,422 logical publications with
   alternatives: 14,446 physical files, of which 10,024 can be avoided by a
   deterministic decode-cost preference. The grouping key must retain archive
   member identity; suffix similarity alone is not proof of equivalence.
3. `scripts/audit_crosswalk.py` measured the rebuilt CNES↔CNPJ pack. Temporal
   ambiguity and reverse one-to-many relations are real, not corner cases. A
   dictionary overwrite or a default join would silently select an identifier
   or multiply fact rows. Exact-window grouping understated both: 951 source
   ambiguities become **1,816 pairwise-overlapping relation pairs**, and 12,619
   reverse multi-source windows become **13,923 pairwise-overlapping relation
   pairs**. These are pair counts, not canonical disjoint ambiguity segments.

The implementation follows those measurements:

- `query()`/`plan()` separate source-publication intent from physical lake/fetch
  mechanics, expose requested versus effective time, and preserve structural
  absence as report data and Arrow metadata.
- Annual files answer a subannual source request by retrieving the enclosing
  annual publication with a warning, or refusing under a strict policy. Event
  dates never manufacture a row-level month in the source API.
- `label_of`, `rollup_to`, `attribute_of` and `crosswalk_to` are distinct typed
  relations. Only the first may become an automatic `*_label`; the middle two
  require a dimension request.
- CNES↔CNPJ is additive and temporal. It preserves observed identifiers,
  returns safe nulls for conflicts/ambiguity, and changes row count only through
  explicit `explode=True`.
- The resource manifest carries schema/content versions, build identity,
  checksums, sizes and budgets. Compact semantics ship; CNES history and names
  are optional local resources whose requirement and estimated cost appear in
  the plan before retrieval begins.
- Semantic uncertainty above a cost cap creates a stable adjudication item.
  Evidence can be exported and a reviewed typed relation applied; truncation is
  never allowed to become truth.

`HANDOFF.md` was rechecked during this pass. Its durable novel lessons had
already been consolidated in §3l; the remaining text is operational history or
duplicates the architecture, so no second copy was introduced.

---

## 3n. Query completeness is a publication-set property (2026-08-23)

The external follow-up review correctly identified that “some lake partition
exists” cannot choose the source for an entire query. Completeness is now
evaluated for each requested year against the selected logical publications and
the `source_paths` recorded in lake partitions. A partially built year routes as
one unit to fetch; complete and incomplete years can form a non-overlapping
hybrid. Comparing logical publication identity, rather than the current physical
suffix, also means a lake built from DBC remains complete if Parquet later
becomes the preferred representation.

Three related lessons were established while closing that review:

1. **Semantic axes are descriptive knowledge, not retrieval predicates.**
   `MUNIC_RES`, `MUNIC_MOV`, `DTOBITO` and `DT_INTER` remain documented because
   their meanings matter, but source capabilities contain only publication
   resolution and physical partition coordinates.
2. **Semantic vintage belongs to the row.** A multi-year dimension lookup must
   select the packed relation for each row competence/year. Choosing one current
   table for the result silently rewrites historical categories.
3. **A committed adjudication must be visible across connections.** The apply
   path previously issued two uncommitted `execute()` calls, so the writer saw
   its decision while a query opened immediately afterward did not. Applying a
   relation and closing its work item is now one committed transaction; the
   ordinary renderer and dimension resolver share the effective relation view.

Representation conflicts now block analytical execution. In particular, two
same-format objects claiming one logical publication are evidence of a revision,
collision or stale mirror—not a reason to prefer the smaller file. Expert
inspection may explicitly retain all alternatives, but the default cannot emit
duplicate facts.

---

## 3o. Source selection and analytical filtering are different products (2026-08-23)

The replacement review adjudicated a scope ambiguity left by §3m–§3n:
Pegasus-Data retrieves, decodes, harmonizes and semantically serves DATASUS
publications; the researcher defines the analytical population afterward.

The resulting rules are durable:

1. **Publication coordinates may select observations; fact meanings may not.**
   `period="2024-03"` selects the March publication when one exists. It does not
   mean `DT_INTER`, `DTOBITO` or another event date falls in March. Likewise a
   publication UF never becomes a `MUNIC_RES`/`MUNIC_MOV` predicate.
2. **Source competence is immutable provenance.** `_competencia` may choose a
   monthly lake slice or historical semantic relation, but no ordinary record
   field may overwrite it. Annual source enclosure has no invented month; its
   safe semantic vintage is the coarse January–December interval.
3. **Completeness belongs to logical source units.** The required key is at
   least `(family, logical publication, archive member)`. Path-only lake
   provenance cannot prove a multi-member archive complete; alternate physical
   representations remain equivalent when that complete key agrees.
4. **Reconciliation precedes family execution.** A logical publication split
   across two schema families is still one representation decision. An open
   conflict blocks even when a later family sees only one candidate.
5. **Unknown historical validity resolves to null, not “current”.** Temporal
   relation windows and packed mappings require source vintage unless explicitly
   time-invariant. Local adjudication then outranks shipped curation, which
   outranks the legacy bridge, with dataset/system specificity deterministic.
6. **Runtime resources have one resolution interface.** Optional CNES artifacts
   carry local manifest identity, checksum and exact covered years and are opened
   through `ResourceManager`. Static packs validate there; lake-backed resources
   delegate integrity/completeness to lake catalogs and fingerprints. Registry
   lookup follows the CNES identifiers and validity period in the selected slice,
   not the fact publication's UF.
7. **Planning is metadata-only.** Catalog/inventory/schema/resource metadata may
   be scanned during planning; fact rows are opened only for requested-slice ETL
   or an explicit bounded resource/maintainer operation.

The old `time_by`, `geography_by` and `unresolved_time` query switches were
removed. Their semantic knowledge remains under `semantic_axes` in curation for
`describe()`, documentation and future opt-in analytical helpers. The compact
`query_capabilities.json` is now compiled from separate `source_publication`
curation and carries no record-field predicates.

The closing real-resource audit re-read the shipped 1,774,993-row crosswalk and
reproduced all published cardinalities, including 1,816 and 13,923 pairwise
overlaps. The current 92.8 MB working catalog (not the historical recovered
15 GB evidence warehouse measured in §3m) contained 3,716 logical publications
with alternatives, 12,323 physical files in those groups and 8,607 avoidable
decodes. A metadata-only `plan("SIH-RD", period="2023-01", geography="AL")`
completed against that catalog without opening fact data.

---

## 3p. Temporal truth has extent, identity and authority (2026-08-23)

The hardening review exposed three variants of the same false-precision bug.
A source vintage is an interval: a monthly publication is one month, an annual
publication spans January through December, and missing provenance is unknown.
Semantic dimensions and CNES↔CNPJ enrichment may resolve a coarse interval only
when one effective assertion and mapping covers all of it; a bare year is never
silently converted to December.

Catalog relations likewise identify temporal assertions, not only semantic
slots. Stable `relation_id` values include validity boundaries and authority, so
adjacent historical adjudications persist together. Overlaps within one
authority/slot fail explicitly. During legacy migration, a row is local only
when its complete content is recoverable from resolved adjudication decision
JSON; otherwise it is classified as curated. Curated rows are synchronized as a
transactional compiler snapshot on every seed, while local decisions persist.
The v4 migration reapplies this classification to catalogs already opened by
the short-lived v3 all-local migration.

Resource compatibility is separate from resource freshness. The schema/ABI,
manifest identity and checksum are strict, while a newer compatible content
epoch is accepted without reinstalling Pegasus. CNES-name coverage is an
explicit source-snapshot build claim; individual record windows cannot prove a
directory complete. Lake-backed resources use the same resolution interface but
delegate physical completeness to the lake catalog and fingerprints.

---

## 3q. The artifact is a separate correctness boundary (2026-08-23)

A repository import and an installed-wheel import are different systems. The
first distribution audit found a direct `numpy` import that metadata provided
only transitively, and current PEP 639 tooling rejected the old license
classifier once the project adopted an SPDX expression. Neither issue was
visible in the runtime suite.

The release boundary is now executable. `verify_distribution.py` compares all
SQL, YAML, JSON and Parquet package data in both wheel and sdist with the source
tree, validates the resource manifest's byte counts and SHA-256 digests, checks
the license, version and CLI entry point, and rejects local databases, caches
and source archives. CI rebuilds a wheel from the sdist so the source archive is
not merely present but sufficient.

The first clean-room acceptance run installed
`pegasus_data-0.1.0a1-py3-none-any.whl` outside the repository. The import
resolved inside that environment's `site-packages`; all seven manifest
resources, 116 curated YAML files and `catalog/schema.sql` loaded; the CLI help
rendered; and an offline `plan("SIH-RD", period=2024, geography="AL")` resolved
from the shipped source map without a catalog or fact download. The sdist then
rebuilt an independently verified generic wheel.

Distribution version is authoritative in `pyproject.toml`; runtime
`__version__` reads installed metadata. Publication remains a deliberate
external action through a release-triggered, OIDC-backed PyPI workflow.

---

## 3n. DATASUS publishes supramunicipal geography, and disagrees with itself (2026-08-23)

### Every national classification was already shipping

`normalize/geo.py` canonicalises a municipality — six digits to seven, check
digit, UF — and stops. "Which health region is this municipality in" had no
answer, and it is the question almost every roll-up asks.

The answer was already in the label pack. DATASUS publishes each supramunicipal
classification as an ordinary `.CNV` codelist keyed on the six-digit
municipality code. 139 national municipality-keyed codelists ship. Among them:

| classification | codelist | municipalities | members |
|---|---|---:|---:|
| health region (CIR) | `CIRBRN` | 5,680 | 478 |
| IBGE microregion | `MICROBR` | 5,697 | 586 |
| IBGE mesoregion | `MESOBR` | 5,632 | 165 |
| colegiado de gestão | `CSAUDBR` | 5,417 | 303 |
| metropolitan region | `BR_REGMETR` | 1,325 | 95 |
| PNDR region | `BR_PNDR` | 1,126 | 14 |

**`CIRBRN` is the national health-region table.** `CIRAC` — the 24-row Acre table
that labelled Rio Branco "Baixo Acre e Purus" and cost this project days (§3k) —
is one state's slice of that same classification. The fix compiles to 98,584 rows
in a **140 KB** artifact.

Note what that resolves: Rio Branco's health region genuinely *is* "Baixo Acre e
Purus". It was never wrong as a region, only as a municipality's name. It is now
reachable under its own name, deliberately, which is what the rollup guard was
groping toward.

### The compile is deterministic only when scoped by publishing system

Grouped by municipality alone these tables look self-contradictory. Add the
validity window and the publishing system and every contradiction vanishes:

| scoping | CIRBRN | RSAUDBR | MSAUDBR | MICROBR | MESOBR |
|---|---:|---:|---:|---:|---:|
| municipality only | 295 | 2,612 | 951 | 50 | 50 |
| + validity window | 295 | 2,612 | 951 | 50 | 50 |
| + **system** + window | **0** | **0** | **0** | **0** | **0** |

The same lesson as §3e: most apparent contradiction was manufactured by the
comparison. The window alone resolves nothing — it is the *system* that carries
the disagreement.

### What survives the scoping splits in two, and only one half is real

**Encoding variance.** `CIRBRN` differs on 295 municipalities but the region
*name* differs on only **46**. The other 249 are the same region under a
different code width — `420005 → SIM:42008 | SINASC:4208`, both "SC Meio Oeste" —
or an accent, `Xanxerê` vs `Xanxere`.

**Two schemes under one codelist name.** `RSAUDBR` differs on 2,612 and the name
differs on **1,944**:

```
130002 -> CIH:1306 "DIRES 6" | SIASUS:1302 "Triângulo"
          SIHSUS:1302 "Triângulo" | SINASC:1306 "DIRES 6"
```

That is not a disagreement about where a municipality is. It is **two different
regionalisations published under one name** — CIH and SINASC on the older DIRES
scheme, SIA and SIH on the named-region scheme. `MSAUDBR` has it on 858 and
`BR_DIVADM` on 2,979.

**Consequence:** a supramunicipal roll-up is not system-neutral. An aggregate
over SIH must roll up through SIH's regionalisation or its totals will not
reconcile with DATASUS's own TabNet output for the same query. The compiled pack
is therefore keyed `(municipality, classification, system, window)`, and the 46
residual health-region conflicts are reported to the caller rather than resolved
by picking.

### Health macroregion is an honest gap

A municipality does belong to a health macroregion. **No shipped table says which
one without contradicting itself**: `BR_MACSAUD` conflicts on 66% of
municipalities (and 220 of its rows carry no member code at all), `MSAUDBR` on
4%. Neither is compiled. `curation/geography.yml` records both exclusions with
their measurements, because "we ship no macroregion mapping" is a finding and
picking one system's answer for two-thirds of Brazil is not.

### Sentinels are members

`999999 → Ignorado/Exterior` and `120000 → Município ignorado - AC` are kept.
Folding them into a real municipality is the §3k error; dropping them biases
every count, because the rows carrying those codes do not disappear from the
data.

### The same defect was live in `joins.yml`, in relation form

Found while building the above, not by looking for it. `curation/joins.yml`
declared:

```yaml
  field: MUNIC_RES
  relation: rollup_to
  target_name: health_region
  artifact: CIRAC        # <- Acre's 24 rows, as the NATIONAL roll-up
```

`_apply_dimensions` loads `relation.artifact` directly, so
`query("SIH-RD", dimensions=["MUNIC_RES.health_region"])` decoded municipality
codes with a 24-row Acre table. Measured:

| capital | under `CIRAC` | under `CIRBRN` |
|---|---|---|
| São Paulo `355030` | *not covered* | 35054 SP São Paulo |
| Rio de Janeiro `330455` | *not covered* | 33005 RJ Metropolitana I |
| Fortaleza `230440` | *not covered* | 23001 CE 1ª Região Fortaleza |
| Belo Horizonte `310620` | *not covered* | 31008 MG Belo Horizonte… |
| Rio Branco `120040` | 12002 Baixo Acre e Purus | 12002 AC Baixo Acre e Purus |

Every roll-up outside Acre returned nothing, and nothing said so.

This is §3k exactly — the per-UF form of a classification that also exists
nationally — surviving in a layer built after that fix, because the fix was
applied to curated `codelist` declarations and this is a `relations` entry.
Changed to `CIRBRN`, and
`test_every_declared_rollup_artifact_spans_many_states` now refuses any
municipality-keyed roll-up whose table covers fewer than 20 states, so the shape
cannot be reintroduced anywhere in `joins.yml`.

---

## 3o. Building the aggregate layer (2026-08-23)

### The compression that justifies an artifact, and the limit on it

| measured | value |
|---|---|
| `fetch("SIH-RD", uf="AC", years=2022)` | 130 s, 49,547 admissions |
| the same rows at municipality × month × sex | 989 cells — **50×** |
| at municipality × month × sex × **race** | 2,417 cells — **20.5×** |
| the build, end to end | 199 s for one state-year |

The second and third rows are the design constraint, not a curiosity. **Each
retained dimension spends the compression that justifies the artifact.**
Adding race alone halved it. `DIAG_PRINC` has ~14,000 ICD codes and would
multiply cells by roughly a thousand, at which point the artifact is larger than
the microdata it replaces. Hence one artifact per (dataset, binding, dimension
set) rather than one universal cube.

### The artifact reproduces a direct GROUP BY exactly

Checked, not assumed: 2,417 cells against 2,417 from a direct `GROUP BY` on the
same microdata, **identical key sets, zero disagreeing cells**, and totals
reconciling to the row count (49,547 admissions, 1,706 deaths,
R$ 43,377,991.73).

### Marginalising an axis is the same operation as rolling one up

"Total" is the pushforward to a one-point space. On live data, Total over sex
was 49,547 and the sum of its two observed categories was 49,547 — not because
that is asserted anywhere but because both derive from one base cuboid by the
same merge. A table whose total is not the sum of its parts discredits
everything else on it, and deriving rather than recomputing makes that
consistency structural.

### The partial-map failure, in real numbers

Rolling municipality up to `metropolitan_region` over Acre data serves **70 of
49,547 admissions**. A naive implementation returns 70 and it reads as a
national figure. The pushforward is not total — that classification covers 1,325
of ~5,570 municipalities — so the layer reports **49,477 unmapped** and says the
result is a subset total.

Even `health_region`, which covers 5,680 municipalities, left 5 admissions
unmapped in this slice. Small, and not zero, and now visible.

### `query(select=[...])` raises on synthesised hidden dependencies — FIXED in §3q

Found while wiring the build. Recorded here as it stood; the fix is in §3q.

```
query("SIH-RD", period="2022-01", geography="AC",
      select=["ANO_CMPT", "MES_CMPT", "MUNIC_RES", "SEXO"])
-> MissingColumnError: column '_competencia' is not present in family
   SIHSUS_RD_e2f7244ae5 (also absent: _source_resolution, year)
```

The planner adds `_competencia`, `_source_resolution` and `year` as hidden
dependencies, and they reach the *source* projection — but they are synthesised
during normalisation and no DATASUS family carries them, so the read refuses. It
only bites when `select=` is given; the unprojected call works.

The aggregate build therefore does not pass `select=` and projects afterwards.
That is a workaround, not a fix, and the defect is recorded as open.

---

## 3p. Auditing DATASUS geography against IBGE (2026-08-23)

Full account in `docs/IBGE_LOCALIDADES.md`. The findings that belong in the
project's knowledge repository:

### The publication year is not the record year — 7.44%, measured

The SIH file published under **year 2022** for Acre contains **3,687 admissions
(7.44%) that happened in 2021**, the earliest in February 2021.

| column | means | years inside the "2022" file |
|---|---|---|
| `ANO_CMPT`/`MES_CMPT` | billing competence | 2022 only |
| `DT_INTER` | when the patient went in | **2021: 3,687** · 2022: 45,860 |
| `DT_SAIDA` | discharge | 2021: 3,100 · 2022: 46,447 |

An admission in December is billed in January, so the lag is structural, not
noise. **Never infer record time from the publication coordinate.** A series by
admission date requires reading `DT_INTER` AND fetching the neighbouring
publication years, or the edges are silently short.

### Comparing labels instead of partitions manufactures disagreement — again

`MESOBR` against IBGE's mesorregião agrees on **14.3% of labels**. That number is
worthless. `.CNV` labels are width-limited, so DATASUS writes `Leste RO` for
`Leste Rondoniense`.

Compared as **partitions** — which municipalities group together, regardless of
the group's name:

| | DATASUS groups | IBGE groups | split by IBGE | split by DATASUS |
|---|---:|---:|---:|---:|
| `MICROBR` vs microrregião | 558 | 558 | **0** | **0** |
| `MESOBR` vs mesorregião | 139 | 137 | **0** | 2 |

`MICROBR` **is** IBGE's classification, exactly. `MESOBR` differs only because
DATASUS files three municipalities (`431936`, `432146`, `510619`) under
"Ignorado" where IBGE knows the answer.

This is the third time this project has been caught by it — §3e (311,844
manufactured contradictions), §3n (295 municipality conflicts that were code-width
variants), and now this. **The rule: when two sources look like they disagree,
compare the structure before the strings.**

### DATASUS's geography is built on a classification IBGE retired in 2017

IBGE replaced mesorregiões and microrregiões with **Regiões Geográficas
Imediatas** (510) and **Intermediárias** (133). Neither appears in any of the
2,348 codelists the label pack ships. Every DATASUS roll-up above the
municipality uses a nine-year-deprecated classification.

The legacy ones stay — thirty years of health data is tabulated against them —
but the current pair now ship alongside, from IBGE.

### Municipality coverage was nearly fine, and I reported it wrongly first

Only **three** IBGE municipalities are absent from `BR_MUNICIPALFA`, and two are
explicable (Brasília is covered by a range row; Pinto Bandeira exists under an
older code). Boa Esperança do Norte was created in 2021 and not yet installed.

An earlier pass of this audit reported *"Pescaria Brava (420547) appears in zero
codelists"* as a headline. **The code was wrong** — it is `4212650` → `421265` —
and the municipality is present. The finding was an artifact of a misremembered
code checked against nothing. Recorded because the failure mode is the one this
project keeps repeating: a confident claim resting on an unverified premise.

### What each institution actually owns

IBGE has **no health regions**. The *Região de Saúde*, the *colegiado* and the
health macroregion are Ministry of Health constructs with no IBGE equivalent and
no crosswalk. That is why the outcome is a supplement rather than a replacement:
IBGE for territorial identity, DATASUS for the health-service geography it
invented, and an `authority` column on every membership so a caller can see which
institution answered.

### Datasets inside a system share their axes — 5 to 90 in two edits

`semantic_axes` (which column carries the municipality, which carries the date,
and what each role IS) existed for **5 of 132** datasets, which made the
aggregate layer look general and was not.

The leverage is that DATASUS datasets are not independent. All **58 SINAN
agravos** carry the same notification block, so `ID_MN_RESI` is the municipality
of residence in every one; SIH's datasets are all views of an AIH; CIHA's rows
all carry the same `MUNIC_RES`/`MUNIC_MOV` pair. A file-level `shared:` for SINAN plus a
`shared_by_system:` block covering fourteen systems took coverage to **125 of
132**, and the seven left out are each left out for a stated reason: five are
not datasets (TABWIN is a Windows application), `IBGE.PROJUF` is projected by
state, and `PCE.PCE` uses a 12-character composite geocode.

**Saying "none" is a different claim from saying nothing.** `IBGE.PROJUF` shares
a system with five municipality-keyed files. Staying silent would have given it
their `MUNCOD` and keyed its cells on something no municipality table resolves —
every roll-up unmapped, every total a subset. So inheritance tests for the key's
PRESENCE, and `semantic_axes: {}` is an explicit opt-out.

**Grain must NOT inherit, and that is the load-bearing part.** CNES's 13 datasets
share `CODUFMUN` and have *different* grains — establishment-month,
professional-establishment-month, establishment-bed type-month. Inheriting grain
would make `COUNT(*)` mean one thing across them, which is the assumption §14.15
exists to refuse.

What is **not** derivable is the ROLE. Nothing in the bytes says `MUNIC_RES` is
where the patient lives and `MUNIC_MOV` is where they were treated. The columns
themselves are already identifiable from their curated codelist binding; only the
naming is an assertion.

A declared field that does not exist yields an aggregate with **no rows and no
error** — the phantom-codelist failure of §3k wearing another costume. So
`tests/test_semantic_axes.py` checks every declared field against curation, and
caught one immediately: `DTREGISTRO`, invented for SIM, where the column is
`DATAREG`.

### Still unresolved

* No health macroregion ships. `BR_MACSAUD` conflicts on 66% of municipalities,
  `MSAUDBR` on 4%, IBGE has none.
* IBGE's endpoint returns **today's** division. A 1995 record rolled up through
  it is placed where it would be now. Validity windows are left empty to say the
  vintage is unknown rather than asserting timelessness; IBGE publishes historical
  divisions and wiring them in is the next step.

---

## 3q. Reviewing my own aggregate layer (2026-08-23)

A self-review of the code in §3o, measured rather than read. Three defects, all
mine, all found by asking "what does this cost at national scale" rather than
"does it pass".

### `memberships()` scanned the whole pack on every call

The lookup read every column of the 75,000-row geography pack to Python lists
**inside each call**. Measured: **665 ms per municipality**, so resolving one
national roll-up would have spent **62 minutes on geography alone** — for an
artifact whose entire purpose is answering in seconds.

Indexing once, at first use:

| | before | after |
|---|---:|---:|
| per lookup | 665 ms | **168 µs** |
| all 5,706 municipalities | 3,708 s | **0.96 s** |

Same answers. A ~3,900× difference that no test caught because every test used
a handful of codes.

### The merge was a Python loop, in both directions

`aggregate()` merged cell by cell and `build_aggregate()` lifted row by row.
Measured on a synthetic national year (133,680 cells): 2.6 s per roll-up, and a
realistic artifact is ~5× larger — about 13 s per question.

Both are now Arrow grouped aggregation, and **that is a property of the algebra
rather than an optimisation**: every accumulator is a commutative monoid whose
merge IS a column aggregate. `count` and `sum` merge by summing one column,
`mean` by summing `(n, sum)`, `ratio` by summing `(num, den)`, `min`/`max` by
`MIN`/`MAX`. The whole vocabulary maps onto `group_by().aggregate()` with no
special cases — which is a decent sign the abstraction was right.

| | before | after |
|---|---:|---:|
| serve, 133,680 cells, worst roll-up | 2.6 s | **1.1 s** |
| serve, 66,564 output rows | — | **1.5 s** |
| build, SIH-RD/AC/2022 end to end | 199 s | **113 s** |

The build's remaining time is the fetch; its aggregation went from ~70 s to
~3 s. Every figure on the rebuilt artifact is byte-identical to the loop's:
49,547 admissions, 1,706 deaths, R$ 43,377,991.73, mean stay 4.702323.

### Arrow's cast raises on DATASUS's blanks

Naively casting a text column to double fails on `''`, and DATASUS writes
numbers as fixed-width text where blank means ABSENT. Non-numeric cells are now
nulled before the cast, because a null contributes nothing to a sum and nothing
to a mean's denominator — which is what "not observed" should do. Coercing them
to zero instead would drag every mean down invisibly, which is the same class of
error as counting a structural absence as a clinical zero.

### And the `query(select=)` defect from §3o is fixed

The planner adds `_source_path`, `year`, `_competencia` and `_source_resolution`
as hidden dependencies because the semantic layer needs them. **Three of the four
are derived after retrieval** by `_with_competence`, out of `_source_path` and
the source report — no DATASUS family carries them — and all four were being
passed to the source projection. So every `select=` query refused.

The fix is one subtraction in the executor: a source projection excludes what is
synthesised downstream. `_source_path` stays, because it is a real column and is
the thing the other three are derived FROM.

Verified against live data: `query("SIH-RD", period="2022-01", geography="AC",
select=[7 columns])` now returns 3,977 rows × exactly those 7 columns.

It survived a suite that exercises this path hard because **without `select=`
nothing is projected and every column arrives regardless** — the defect needed
the narrow projection an aggregate build happens to want.

### The lesson

None of these were correctness bugs and every test passed throughout. They were
found by asking what the code costs at the scale it is *for* — and the artifact
exists precisely because scale is the problem. **A layer built to make something
fast should be measured at size before it is called done.**

---

## 3r. An artifact knows its scope and was throwing it away (2026-08-29)

**Found by a user looking at a map**, which is the part worth recording: every
test passed, every number was correct, and the screen said something false.

### What was seen

The frontend's ranking put **Rio Branco, AC** first for hospital admissions, and
the map coloured Acre while 5,452 municipalities sat pale grey. Acre has ~900,000
people; São Paulo has 46 million. The reaction — "I don't understand how Acre is
leading admissions" — was exactly right.

### What was true

Nothing was wrong with the data. `build_aggregate(..., uf="AC")` had been run, so
the artifact held 49,547 admissions from **Acre's SIH files only**: 2,417 cells
over 118 municipalities, 1,897 of them with UF prefix `12`. The other twenty
prefixes are residents of other states admitted in Acre's hospitals — the
geography binding is *residence*, so a patient from Manaus treated in Rio Branco
lands under `13`.

So the artifact was a correct answer to "admissions in Acre's hospitals in 2022,
by the patient's municipality of residence". The interface presented it as
Brazil.

### Why nothing caught it

`build_aggregate` **took `uf` and did not record it.** The manifest carried
`years`, `support`, `partial_periods`, `warnings` and a fingerprint — every
qualifier about time and about dimensions, and none about space. `aggregate()`
then served a total that was a subset total, with nothing to say so.

This is the SAME distinction the layer already makes twice elsewhere, missing on
the one axis nobody applied it to:

| axis | the distinction | where it was already made |
|---|---|---|
| dimensions | `absent` is "could not have known", not "zero" | the support mask |
| time | a record-date build cannot fill its own edges | `partial_periods` |
| **space** | **a municipality outside the fetch was never in view** | **nowhere** |

A partial classification already produced a warning when a roll-up left mass
unmapped. A partial *fetch* produced none, because from inside the cells it is
invisible: 118 municipalities with data and 5,452 without looks precisely like a
national build of something rare.

### The fix

`AggregateReport.uf` is recorded at build time, written to the manifest, and
carried back on read as a warning. `capabilities()` projects it as
`spatial.coverage` with three fields that mean different things:

- `declared_ufs` — what the build FETCHED. Authoritative when present.
- `observed_ufs` — the prefixes present in the cells. A measurement, and **not a
  substitute**: a national build of a rare condition also touches few states, so
  inferring scope from the cells would be a guess dressed as a fact. Artifacts
  built before this change report `kind: "unknown"` and say so.
- `municipalities` — how many the artifact actually holds.

The interface then restricts the map to what the build could have seen, names the
real scope in the state bar and in every ranking, and carries a banner saying a
municipality with no cell was *not observed*.

### The rule this generalises to

**Every qualifier a build applies to its input is part of what the output means,
and belongs in the manifest.** `uf` was the one that got away because it reads
like a performance knob — "fetch less" — rather than like a claim. It is a claim:
it decides what the totals are totals OF.

Worth re-checking on the same grounds: `years` is recorded (good), but a build
restricted by any future predicate must record that too, or the same failure
recurs in a new shape.

---

## 3s. DATASUS does not use one date format (2026-08-29)

Found by building the SECOND artifact. SIH had worked for weeks, and it worked
because its time axis happens to be a competence held in two columns.

### What came out

`build_aggregate("sim_do_municipality_month", years=[2022])` produced **62,040
cells from 75,707 rows** — nearly one cell per row, which is the opposite of
what an aggregate is for. Its periods were named `0101`, `0102` … `3112`.

Those are day-and-month, not months.

### Why

`_competencia_column` took the **first six characters** of a single packed time
field. That is correct for a competence — `AP_CMP` is `202201` — and wrong for a
record date, because DATASUS writes dates **day-first**:

| dataset | column | value | layout |
|---|---|---|---|
| SIH-RD | `DT_INTER` | `20211227` | `AAAAMMDD` |
| SIM-DO | `DTOBITO` | `07052022` | `DDMMAAAA` |
| SINASC-DN | `DTNASC` | `16041976` | `DDMMAAAA` |

**The format is not uniform across systems.** SIH is year-first; SIM and SINASC
are day-first. `07052022` sliced to six characters gives `070520`, whose first
four characters are `0705` — hence 366 "months".

### Why nothing caught it

Nineteen `(system, field)` pairs declare a `date` encoding and **none of them
had ever been built**. Both existing specs use a competence, so every test,
every measured figure and the whole SIH verification exercised the one path
where the assumption happens to hold. The defect was not hiding — it had never
been asked a question.

### The fix, and why it is a measurement

A table of nineteen declared formats is nineteen things to maintain and to get
wrong, and it grows with every new binding. The layout is **decidable from the
column**:

* year-first requires `text[0:4]` to be a plausible year and `text[4:6]` ≤ 12;
* day-first requires `text[4:8]` to be a plausible year and `text[2:4]` ≤ 12.

These are **disjoint for every real date after 1900**: if `text[4:8]` is a year
then `text[4:6]` is `19` or `20`, which is not a month, so year-first cannot
also hold. There is no ambiguous eight-digit date. A sample of a few thousand
values settles it exactly, and the confidence threshold is a guard against junk
rather than a tie-break.

`_date_layout()` scores both hypotheses and **returns None when neither
dominates**, which the build reports as a skipped year naming the fields — a
column it cannot read is refused rather than bucketed under a period that means
nothing.

### The rule this generalises to

**A format assumption that holds for the dataset in front of you is not a
format fact.** The tell was structural rather than statistical: 62,040 cells
from 75,707 rows is a compression ratio of 1.2, and an artifact whose whole
purpose is compression should have been challenged by that number alone.

Worth applying the same suspicion to: fixed-width numeric fields (SIH bills in
centavos in some eras and reais in others), and any column whose meaning is
inferred from position rather than declared.

---

## 3t. The serve path met its first national artifact (2026-08-30)

Third instance of the same lesson (3q, 3s, now this): **correct at fixture size
is not a property of the code.** The serve path had been verified exhaustively
at 2,417 cells. The first national artifact has 422,203.

### Measured

Every HTTP roll-up cost 2.8–4.4 s — including a ONE-ROW national total. The
floor was not Arrow and not the network: `aggregate()` began with
`{c: table.column(c).to_pylist()}` and ran Python loops for the mask, the
pushforward application, the unmapped-mass scan and the index build — ~3.8
million Python objects per request. On top of it, the HTTP handler consulted
`capabilities()` on every cell request, and the projection re-read the parquet
and the catalog each time (~1.2 s), putting a constant floor under even cached
answers.

### The fix, and what stayed in Python

Arrow end to end: `is_in` masks, pushforwards applied with `index_in` + `take`
over a mapping decided in Python on the DISTINCT codes only (a few thousand
lookups — where `uf_from_code` and `memberships` own the rule), lost mass via
`sum(filter(...))`, vectorised finalize mirroring `Kind.finalize`'s 0/0-is-null
semantics, Arrow sort. Three caches keyed on on-disk identity (mtime): the
artifact table, the classification map, the finished Capability. orjson on the
wire for the megabyte payloads.

| request | before | after (warm) |
|---|---|---|
| national total (1 row) | 2,674–3,304 ms | **181 ms** |
| uf × year | 2,853 | 255 |
| municipality × year (569 KB) | 3,082 | 539 |
| municipality × month (3.8 MB) | 4,400 | ~1,470 |
| health_region × year | 2,755 | ~250 |
| capabilities | 1,211 | 96 |

All 81 serve/capability tests passed **unchanged** across the rewrite, and the
national invariants held: total = 12,520,914 = sum of sex parts; mean LOS
5.210395 = sum/n to the last digit.

### The boundary that keeps this honest

The RULES stayed in Python where their owners live; only the APPLICATION moved
to Arrow. A pushforward is still `memberships()`'s answer — computed once per
distinct code, not re-derived in compute kernels. The columnar finalize is tied
to the scalar one by `test_formula_matches_finalize`, the same test that ties
the wire formula: one projection, three spellings, one test holding them
together.

The frontend had the same defect in miniature: the time surface rebuilt each
territory's series by rescanning all cells — 5,570 × 66,832 ≈ 370M operations
per render — and drew 5,570 overlapping polylines where ~300 are a solid band.
One pass now, and a sample taken evenly across the by-total ordering so the
band keeps its true spread; the legend states the sampling.

---

## 3u. The build spent an hour labelling nothing (2026-08-30)

The national SIH build took 65 minutes for 12.5 million rows, and the question
was where the hour went. Not where anyone would look first: not the network
(the lake was warm), not the DBC decode (native, already parallel across
files), not the aggregation (columnar since 3o). Profiled on one state-year,
**205 of a 209-second fetch was codelist selection whose result was then
discarded** — `fetch(labels=False)` still ran every column of every file
through `_select_codelists`, which reads packed reference tables, queries the
relations catalog and parses YAML, so that the `codes` profile could then emit
the column exactly as filed.

Four layers, four fixes, each measured before the next:

| layer | defect | fix |
|---|---|---|
| `_render_table` | selection runs when every column renders as its code | `codes_only` gate: emit as filed, skip selection |
| `relations.load_relations` | joins.yml re-parsed per call (1,359 parses, 84 s) | parse cached by CONTENT, not mtime |
| `labelpack._read_packed` | cache keyed by vintage, so 12 competencias = 12 expansions of the same rows | scan, runs and expansion cached by what is actually read/expanded |
| `view._lookup_map` / `_contradictions` | dict rebuilt from the packed table per call | `lru_cache`, returns treated as read-only |

Numbers, same machine, warm lake: `labels=False` one state-year 233.7 s →
44.8 s; `labels=True` 218 s → 46.7 s; the national build 65 min → **12.9
minutes**, byte-identical artifact, and the warning spam (a labelling warning
per file for a fetch that asked for no labels) gone with the work that
produced it.

Three of the lessons are old ones wearing new clothes. *Work whose result is
discarded is still work* — the serve path's finalize-then-refuse (3q), the
frontend's 370M-operation render (3t), and now selection under `codes`. *A
cache key must carry exactly what the answer depends on* — no more (the
vintage key that split identical expansions twelve ways), and no less. The
mtime variant of "no less" is worth naming: **Windows advances mtime on a
~16 ms timer tick**, so two writes in quick succession can share one, and a
mtime-keyed cache serves the first write's parse for the second's content.
joins.yml is now keyed by its text.

The fourth lesson is new. A process-lifetime cache is a claim that the world
underneath it stands still, and `lake/reference/` does not: the reference
stage, first-use materialisation inside `fetch`, and a bundle unpacked
mid-process all rewrite it. The bundle round-trip test caught exactly this —
labels cached from the shipped pack kept answering after the bundle landed.
Invalidation lives at the mutation site (`write_reference_tables` calls
`view.clear_lookup_caches`), not scattered across callers; and
`labelpack.clear_caches` clears the WHOLE derivation chain, because clearing
one layer of a cache stack leaves the layers beneath it serving the old
world.

What remains of the 12.9 minutes is the honest floor for this design: native
DBC decompression and DBF parsing of 12.5 million rows, four files at a time.
The next lever, if rebuild time ever matters again, is a decoded-blob cache
keyed by content digest — the lake is already content-addressed, so decode
would happen once per blob ever, and a rebuild would be a parquet read. Not
built now: rebuilds at 13 minutes are no longer where development time goes.

---

## 3v. Reviewing the whole with fresh eyes (2026-08-30)

A structured review of three fronts -- retrieval/persist, serve/capabilities,
semantics/catalog -- surfaced sixteen findings; thirteen verified and were
fixed, one was judged self-healing, two were narrowed to notes. What is worth
keeping is not the list (the commit carries it) but the shapes:

**The unexercised path is where the corruption lives.** `min`/`max` measures
were declared, advertised in the capability tables, and broken at every stage
-- the lift filled blanks with 0.0 instead of the identity, the intra-chunk
group summed extreme-state columns into totals, and the columnar finalize
passed the identity through as literal Infinity. No shipped spec declares one,
which is precisely how all three survived; the first spec author to write
`kind: min` would have gotten silently wrong numbers with no refusal anywhere.
The generic lift fallback that summed "whatever it was handed" is now an
explicit refusal: a new kind must be added by hand or not at all.

**A rule enforced everywhere except one entry path is not enforced.** The
vintage guarantee held when a year was asked and not when none was; the
"visibly unfinished" rule held for bound codelists and not for curated columns
nothing was bound to; adjudications carried validity windows the runtime never
consulted. Each fix was two lines; each gap was the sacred rule with one door
left open.

**Caching discipline, consolidated.** Since 3t the codebase has grown a real
cache layer, and the review closed its remaining holes: keys must carry
exactly what the answer depends on (the manifest mtime joined the descriptor
key; the geography pack's mtime joined its readers), writes that a cache
derives from must invalidate at the mutation site (`build_label_pack` now
clears its own chain -- including the cached pack PATH, which froze `None`
forever on a fresh install), and a multi-file artifact must move atomically
or its caches read a torn pair (the manifest now stages+renames like the
cells beside it).

**Self-healing beats transactional, when it is real.** `load_curation` is four
separately committed writes, and the reviewer flagged the torn state a crash
leaves. But the curation fingerprint is recorded only AFTER all four land, so
an interrupted reload re-runs whole on the next fetch. That is a legitimate
design -- noted here so nobody "fixes" it into a lock.

Also in this pass: the population stage had rotted against the decode
refactor (`_RemoteTable` promised DecodedTable's shape and lacked
`to_table`), and `build_aggregate`'s national fallback was unreachable for
exactly the datasets it was written for, because an empty per-UF probe RAISED
instead of returning empty. Both were found not by the review but by running
the paths -- the fallback by building SINAN dengue, the population stage by
materialising denominators for B6. A review reads what the code says; a build
finds out what it does.

---

## 4. What remains open

Run `pegasus-data questions` for the live list. As of the last full pass:

- **No health macroregion mapping ships.** §3p. Both DATASUS candidates
  contradict themselves and IBGE has no equivalent; it needs a Ministry source
  this project does not yet read.
- **Supramunicipal geography carries no vintage.** §3p. IBGE's endpoint returns
  today's division, so a 1995 record rolled up through it is placed where it
  would be now. IBGE publishes historical divisions.
- **V8** — which population series backs the Ministry's published rates. Requires reproducing a
  published figure; the interface makes the comparison cheap but does not settle it.
- **Per-directory date ambiguity** — any directory whose 4-digit codes parse equally as `YYMM` and
  `YYYY`, and whose file multiplicity does not break the tie, records its members' years as NULL
  and raises a question naming the directory. Guessing would shift a whole series by nineteen
  years.
- **Unexpanded range rules** — alphanumeric ranges in codelists with no known code universe are
  preserved verbatim in `dictionary_rules` and applied at lookup time, rather than dropped.
- **`categorical_undecoded` fields** — every low-cardinality field with no dictionary mapping is
  a named, countable gap with a coverage penalty, not a guess.
- **Fields TabNet only names at roll-up level** — `RD.DEF` declares `DIAG_PRINC` more than two
  hundred times, and every one is an aggregation ("Diag CID10 (capit)", "Diag CID10 (grupo)",
  "Diag CID10 cap 01"…). None names the raw ICD code, because TabNet never offers it as an axis.
  The ledger therefore records **no official name** for such fields and raises a question saying so,
  rather than borrowing a roll-up's label — which would tell a reader that a 774-value diagnosis
  column is called "CID Capítulos", the name of a 24-category grouping.
