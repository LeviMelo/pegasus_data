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

## 4. What remains open

Run `pegasus-data questions` for the live list. As of the last full pass:

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
