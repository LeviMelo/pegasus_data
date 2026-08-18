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
