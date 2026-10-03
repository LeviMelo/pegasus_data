# DATA_SOURCES.md

Verified facts about DATASUS and the other sources this project reads:
**measured, not remembered.** Each fact names the date it was measured and
where the measurement is recorded: an evaluation entry (`EVALUATION.md`), a
frozen document under `docs/history/`, or a commit. Where this file disagrees
with an assumption, a brief or a code comment, this file wins and the
correction is written where the wrong claim was.

Written on 2026-09-28 from the August 2026 record. Nothing here was
re-measured against the live server on that date except where §1.2 says so.
DATASUS reorganises without notice: a fact about the tree is true of the crawl
that measured it.

Abbreviations: **F** = `docs/history/FINDINGS.md` (each section is also an
evaluation entry, see the `group` column of `EVALUATION.md`); **ARCH** =
`docs/history/pegasus_data_ARCHITECTURE.md`; **IBGE-L** =
`docs/history/IBGE_LOCALIDADES.md`.

---

## 1. The DATASUS FTP tree (`ftp.datasus.gov.br/dissemin/publicos`)

### 1.1 Server and protocol (2026-08-18, F §1 V1, §2)

- Microsoft FTP Service on Windows_NT.
- `MLSD` returns `500 Command not understood`. `LIST` works and returns the
  **IIS MS-DOS dialect** (`05-29-15  04:10PM  18550 acac0201.exe`, `<DIR>`
  for directories), which carries size and mtime for every entry. On a
  9,667-file slice, 9,667 carried both.
- `NLST` returns bare names with no type information: an extensionless
  directory (`Dados`, `uploads`) is indistinguishable from a file.
- `FEAT` reports `LANG EN*`, `UTF8`, `AUTH TLS;TLS-C;SSL;TLS-P;`, `PBSZ`,
  `PROT C;P;`, `HOST`, `SIZE`, `MDTM`, `REST STREAM`. Per-file metadata is
  available on demand, and interrupted transfers can resume.
- Nothing answers on ports 80 or 443; DATASUS publishes no HTTPS mirror
  (ADR-0003).
- **A third-party mirror exists** (corrected 2026-10-03; this line used to
  say there was none). It is
  `https://datasus-ftp-mirror.nyc3.digitaloceanspaces.com/<path under
  /dissemin/publicos>` (Raphael Saldanha). 8 of 8 files compared were
  byte-identical to the FTP's. CIHA is not mirrored. The fetcher falls back
  to it, size-checked (ADR-0122).
- **The data channel can fail while the control channel works.** On
  2026-10-03 every passive data port (5539–5800) was dropped, while login,
  `CWD` and `SIZE` answered. Listings and downloads both failed. Record:
  `data/probes/ftp/data_channel.jsonl`.
- `/dissemin/publicos/uploads` returns `550 Access is denied` to both LIST and
  NLST: a server-side ACL (2026-08-19, F §3c). `SIHSUS/Doc` returns `550 The
  system cannot find the file specified`: it does not exist (F §1 V11).
- A full crawl took 49 seconds across 362 directories (2026-08-19, F §3c).

### 1.2 Size

- **207,251 files** (full crawl, 2026-08-19, F §3c). The prior scan found
  124,810; the 82,441-file difference is directories it typed as files (F §0).
- **About 991 GiB in total.** The sum of `size` over the 207,251 rows of the
  shipped `resources/tree.parquet` is 990.98 GiB (read 2026-09-28; the crawl
  behind it is 2026-08-19). ARCH §14.1's `explore()` example also says 990 GiB.
- **183 GiB is not the tree's size.** It is the cost of decoding one
  representative file per stratum (F §3g). ARCH §0.3 ("207,251 files, 183 GiB")
  and `CLAUDE.md` §3 ("the full tree is ~183 GiB compressed") conflate the two.
- 20 systems and 131 declared datasets; 207,030 data files bind to a declared
  dataset and 221 are support files (codelists, layouts, PDFs) (ARCH §17, §21,
  as of 2026-08-23). Years 1979–2026 (ARCH §14.1).
- 4,418 strata, 3,688 with a known schema; 273 distinct schemas; 1,633
  families (ARCH §21). 63% of strata hold exactly one file (F §3g).

### 1.3 Directory layout

- One subtree per information system under `/dissemin/publicos/`
  (`SIHSUS`, `SIASUS`, `SIM`, `SINASC`, `SINAN`, `CNES`, `SISCAN`, `IBGE`, `PNI`,
  …), plus `Dados_Abertos`, which republishes several systems in modern
  containers (F §1 V10).
- Modern monthly data sit in `…/200801_/Dados`: `SIHSUS/200801_/Dados` held
  22,807 files (2026-08-18, F §3), `SIASUS/200801_/Dados` 54,199, the largest
  dataset on the tree (F §0, §3c).
- `SIASUS/APAC/<year>/` holds the pre-2008 APAC data as self-extracting `.exe`
  (1,723 files) (F §3j).
- `SIM/CID9` spans 1979–1998 and `SIM/CID10` 1996–2024: the two revisions
  overlap for three years (2026-08-19, F §3f).
- `PNI/AUXILIARES/` holds 79 uncompressed `.CNV`/`.DEF` files (F §1 V3).
- `IBGE/projpop` holds 71 files `PROJUF00.dbf` … `PROJUF70.dbf`, 93,560 bytes
  each (F §1 V7).
- Documentation (`Doc/`, `Estrutura_*` PDFs, `IT_*` layouts) sits in per-system
  trees; the tree carries 56 documents in total (`docs/history/RESUME.md`).

### 1.4 File naming grammar

- Classic form: prefix + geography + date, e.g. `RDAL2401.dbc` → prefix `RD`,
  UF `AL`, `2401` (ARCH §5.2). Four grammars cover the tree, including
  `descriptive` and `descriptive_uf` for tails such as `apac_atd.duck.zip`,
  `siasus_pa_ac.duck`, `base_aih1.duck` (F §1 V10).
- `Dados_Abertos` uses the classic grammar with **composite suffixes**:
  `DENGBR20.csv.zip`, `LEPTBR07.json.zip`, `CHAGBR15.xml.zip` (F §1 V10).
- The date field is `YYMM` in some directories and `YYYY` or `YY` in others;
  it can only be decided per directory. Two annual bundles (`RDAC2017.zip`,
  `RDSP2017.zip`) sit among monthly files in `SIHSUS/200801_/Dados` and are
  left undated (F §3; ADR-0013).
- Two-digit years need a per-directory epoch: projpop's `00`–`70` are
  2000–2070, SIM's are 1996–2023 (F §1 V7).
- Of 1,505 observed `(system, series)` pairs, 181 are clean dataset codes; 976
  are whole filenames (`PASP2509A`, a split part), 213 leak an archive member
  (`RD:RDAC1701`), 130 carry a year (`SISCAN_CITO_COLO_2013`), and 5 are
  template names left on the tree (`EFUFAAMM`) (ARCH §5.4, 2026-08-21).
- A filename prefix is not unique to a system: `CM` is SISMAMA mammography in
  1,717 files (98%) and appears under SIHSUS too; 38 SINAN prefixes are shared
  by the legacy tree and `Dados_Abertos` (2026-08-19, F §3c).

### 1.5 Formats

- **`.dbc`**: a DBF whose header is stored **uncompressed**, followed by a
  payload compressed with PKWare DCL "implode". `RDAC9201.dbc`: all 35 field
  descriptors in the first 1,153 of 91,967 bytes (F §3g). The container
  sometimes stores `0x00` where the DBF header terminator belongs (2026-08-30,
  F §3x).
- **`.dbf`**: only two field types appear anywhere on the tree, `C` and `N`;
  dates and codes are text (F §3g). Field widths sum to the record length plus
  one deletion byte in 100% of catalogued schemas (F §3g). The header's record
  count errs **high**: of 132 real payloads, 16 declare more records than the
  file holds and none fewer (`docs/history/DEFECTS.md`, HI-23).
- **`.exe`** under `SIASUS/APAC/`: `LHA's SFX 2.13S (c) Yoshi, 1991`, an LHA
  `-lh5-` archive with header level 0 at offset 1636, holding seven DBF
  members with seven schemas (`ACAC`, `COAC`, `OPAC`, `PFAC`, `PCAC`, `UDAC`,
  `EXAC`). No `PK\x03\x04`, no `Rar!` (2026-08-18, F §1 V2).
- **`.zip`**: the TAB kits (§2) and `Dados_Abertos` `.csv.zip`, `.json.zip`,
  `.xml.zip`; `.duck.zip`.
- **`.duck`**: DuckDB databases; the storage version is at offset 8 after the
  `DUCK` magic (LE uint64), and DuckDB refuses a newer version (F §1 V6).
- **`.rar`**: `TAB_SISCAN.rar` is RAR5 (ARCH §22.1b).
- **Parquet** and CSV also occur. A Parquet schema is in its footer, at the end
  of the file, so a prefix read cannot catalogue it (F §3i).
- Size comparison on `RDAC1901.dbc` (113 columns): 237,472 bytes as
  published, 2,309,017 decoded row-wise, 318,163 as Parquet with labels and raw
  codes (F §3).

### 1.6 Text encoding

- `.CNV` and DBF text is a DOS or Windows codepage, and cp850 and latin-1 both
  decode every byte. `IDENT.CNV` is latin-1: read as cp850 it gives `Longa
  permanÛncia` (byte `0xEA`) (2026-08-18, F §3).

### 1.7 Reorganisations and duplicate publication

- `Dados_Abertos/BackUp_Ducks_SIASUS_PA` (66 `.duck` files) disappeared
  between crawls, replaced by `PA_SIASUS` and `APAC_SIA` (2026-08-19, F §3c).
- 4,422 logical publications exist in more than one physical form, covering
  14,446 files; a cost preference avoids 10,024 reads (recovered full catalog,
  2026-08-23, F §3m).
- SINASC was published byte-identically into two trees during a transition
  (2026-08-30, F §3w).
- SIM publishes 27 per-state files plus a consolidated `DOBR` file for the same
  year (commit `2e85e97`, 2026-08-30).
- **SIM's DOINF, DOMAT and DOEXT are copies of DO rows** (checked nationally
  for 2022, 2026-09-30, after omnisus reported it for RR and SP). Every row
  equals a DO row on all 87 shared columns: DOINF 32,257 of 32,257, DOMAT
  1,370 of 1,370, DOEXT 152,945 of 152,945. DOFET (27,394) matches none; it
  is the separate register of fetal deaths. Adding a subset to DO
  double-counts deaths.
- **Listed but not retrievable.** `SINAN/DADOS/PRELIM/CHAGBR25.dbc` was
  republished 2026-09-28 10:23 at 502,836 bytes (515,731 before). On
  2026-09-30, LIST and SIZE answer, but RETR refuses it three times running
  with `550 The parameter is incorrect`. The library reports it as a gap
  ("could not be fetched or decoded"), never as zero cases.
- **Datasets published per state have no national file** (SIH, CIHA, SIA,
  CNES). `geography="BR"` reads every state for them; for SIM and SINASC it
  reads the national file (ADR-0109).
- **CIHA mixes admissions with outpatient records.** SP 2023-01, 580,210
  records by `MODALIDADE`:
  - 86,920 admissions (02);
  - 430,210 individualised outpatient (01);
  - 63,080 consolidated outpatient (00).
  
  16.4% of the records have an ignored residence ("Município ignorado"). In
  AC 2023-01 every record's residence is 120000, the ignored code. RR
  published no CIHA for 2023-01.
- **CIHA completes SIH's admissions** (June 2022, national, EVALUATION
  2026-09-30):
  - CIHA: 215,649 admissions against SIH's 1,034,013, about 17% of the two
    together;
  - only 387 CIHA admissions (0.18%) match an SIH admission;
  - residence is missing in 18% of CIHA admissions;
  - RR published no CIHA for the month.
- **CIHA's `MUNIC_RES` on deliveries and deaths is mostly the hospital's
  municipality.**
  - **The test.** 2022 births were linked to CIHA deliveries without
    residence as a key. Where SINASC places the mother outside the hospital's
    municipality, CIHA records the hospital's municipality in 85–100% of
    cases (SP 85.0% of 22,788; MG 89.7%; PR 86.0%; BA 84.5%; SE 330 of 330)
    and her SINASC residence in 0–15%.
  - **SINASC by contrast** places 35–63% of these mothers in the hospital's
    municipality.
  - **Aggregate match.** Across all admissions, a filled `MUNIC_RES` equals
    `MUNIC_MOV` in 92–100% (June 2022), against 71.8% in SIH for SP.
  - **Deaths, the same test** (CIHA deaths linked to SIM nationally, SIM's
    residence as the comparison; EVALUATION 2026-09-30 "National linkage,
    2022"). Where SIM places the deceased elsewhere, CIHA records the
    hospital's municipality in SP 85.1% of 5,653, MG 91.9% of 2,143 and SE
    14 of 14.
  - **Untested beyond deliveries and deaths.** The match rate alone would
    also fit patients living near private hospitals, so other admission types
    are not established.
  - **Unfilled.** The field is "ignorado" in 12–51% of admissions (SE 49% in
    2022).
  - **Source.** The layout says only "Município de residência" (2026-09-30;
    corrected the same day from a claim first based on the match rate alone).
- **SIH-RD is nearly one row per AIH.** A long admission is billed as a
  principal AIH (IDENT 1) plus long-stay parts (IDENT 5) under one number
  (SP 2023-01: 56 of 210,161). RD 2023 carries types 1 and 5 only. Count
  admissions as distinct `N_AIH`.
- **SIH-SP and SIH-RD hold the same AIHs, competence by competence.** 2023-01:
  AC 4,164 = 4,164, SP 210,161 = 210,161, each set equal to the other
  (these two state-months checked; 2026-09-30).

- **SINAN publishes each disease-year in exactly one of `DADOS/FINAIS` and
  `DADOS/PRELIM`** (catalog, 2026-09-30):
  - 1,100 files, 58 diseases, no disease-year in both;
  - 13 diseases exist only as preliminary: AIDA, AIDC, EXAN, HEPA, HIVA,
    HIVC, HIVE, HIVG, SIFA, SIFC, SIFG, SRC, VARC;
  - the last final year differs by disease, from 2018 to 2025;
  - a preliminary year is revised afterwards (omnisus reports final files
    rewritten with 2026 dates; not re-checked here).

### 1.8 Schema generations (header census, 2026-08-19, F §3g)

| series | generations | columns | span |
|---|---|---|---|
| `SIHSUS/RD` | 20 | 35–114 | 1992–2026 |
| `SIM/DOFET` | 18 | 40–99 | 1979–2026 |
| `SIM/DOEXT` | 13 | 40–88 | 1979–2026 |
| `SIM/DO` | 11 | 40–88 | 1996–2026 |
| `CNES/ST` | 3 | 200–208 | 2005–2026 |

- SIH-RD's 113-column schema starts in **2014**, not 2017 (F §2).
- `DIAGSEC1`–`DIAGSEC9` do not appear before 2014 (ARCH §14.7).
- In the 113-column generation, `DIAG_SECUN` is present and holds `'0000'` on
  every row (3,784 of 3,784 in `RDAC2001.dbc`) (F §2). 29 SIH columns are
  sentinel-only in the current generation, among them `CID_ASSO`, `CID_MORTE`,
  `SP_CIDSEC`, `UTI_MES_*`, `TPDISEC*` (F §3d).

### 1.9 Value conventions in the records

- **Dates are not in one format.** SIH `DT_INTER` is `AAAAMMDD`; SIM `DTOBITO`
  and SINASC `DTNASC` are `DDMMAAAA`. A competence (`AP_CMP`) is `AAAAMM`
  (2026-08-29, F §3s).
- **The publication year is not the record year.** The SIH file published for
  Acre under 2022 holds 3,687 admissions (7.44%) from 2021; `ANO_CMPT`/
  `MES_CMPT` are the billing competence (F §3p, second).
- **Numbers are fixed-width text; a blank means absent** (F §3q, second).
- **Sex codes differ by system**: SIHSUS `1`/`3`, SINASC `1`/`2`, SINAN
  `M`/`F`; thirteen systems ship a `SEXO.CNV` (F §3e). SIH's own table maps
  `1→Masculino`, `2→Feminino` and `3→Feminino` (`docs/history/DEFECTS.md`).
- **Race/colour codes differ**: Parda is `03` in SIHSUS.RACACOR, `3` in
  SIHSUS.RACA_COR, `4` in SINASC (ARCH §14.3).
- **SIH `RACA_COR` 04 is not always "amarela"** (2026-10-03). In some
  hospitals it is a default given to almost everyone (CNES 2499363, CE:
  90–97% of admissions every month of 2022, whites included). In others it
  is SIM's code for brown written into SIH's field (CNES 2705982, SP: 03
  unused until 2022-08, then 11–17% from 2022-10). Linked to SIM and
  SINASC, 16,252 of 908,601 persons brown there are asian in SIH (OQ-66).
- **ICD revisions coexist**: SIM `CAUSABAS` holds ICD-9 before 1996 (338 of
  386 shape failures in a 5,000 sample); SIH writes CID-9 as 6-digit numerics
  (426 of 1,590 distinct `DIAG_PRINC`). CID-9 and CID-10 code spaces share no
  code (F §3d, §3f).
- **Procedure codes have two widths**: 8 characters (1994-era `TPROC`) and 10
  (post-2008 `TPROC10`) in `SP_ATOPROF` and `SP_PROCREA` (F §3d).
- **Causal chains**: `LINHAA`–`LINHAD` separate on `*`; `ATESTADO` on `/`, and
  sometimes both in one cell (`T07/X366*Y96`) (F §3d, §3f).
- **Municipalities are six digits**, without IBGE's check digit (IBGE-L §2).
  `999999 → Ignorado ou exterior` is a genuine sentinel; the managing-authority
  columns use `UF0000` sentinels, and in SIA-PA Acre 2022-01
  `120000 → Acre - Gestão estadual` is the most common value (40,650 of 55,963
  rows) (2026-08-23, F §3k).
- **Age encodings differ by system**: SIH has the unit in `COD_IDADE`; SIM and
  SINAN pack it in the leading digit of `IDADE`/`NU_IDADE_N`. `COD_IDADE` has
  six values (0–5) and no unit codelist was found (F §3d; `src/pegasus_data/_age.py`
  docstring; OQ-7).
- **CNES installation grid**: `QTINST07` and `QTINST08` are the male and
  unsegregated rest rooms of the emergency block, not consulting rooms and
  beds; beds are `QTLEITP1`–`QTLEITP3` (2026-08-30, F §3y).

- **SINAN tuberculosis files are years of diagnosis, not of notification**
  (two files checked):
  - `TUBEBR20`: all 86,160 records have `DT_DIAG` in 2020, while `NU_ANO`
    spans 2020–2023 (2,915 in 2021).
  - `TUBEBR25`: all 112,482 in 2025, 1,513 with `NU_ANO` 2026.
- **`ID_AGRAVO` "A16." in SINAN-TB** (1,513 in TUBEBR20, 2,289 in TUBEBR25) is
  category A16 with the subcategory left blank. It reads as the category with
  "subcategoria não informada", not as a code missing from ICD-10
  (2026-09-30). The same holds for `A50.` in congenital syphilis: 614 of
  26,515 records in SINAN-SIFC 2022 (`A509` the rest).
- **SINAN-HANS files carry no `CLASSI_FIN`** (0 of 26 files; catalog
  2026-09-30). The notification dictionary's Anexo I
  (`sources/dic_notif_indiv.txt`) says a leprosy notification enters as
  "Confirmado", a category "atribuída pelo sistema", and becomes "Descartado"
  only for diagnostic error. Fifteen other SINAN datasets also lack the column
  in every file (ACBI, ACGR, ANIM, ANTR, CANC, DERM, ESQU, LERD, LTAN, PAIR,
  PNEU, TUBE, AIDA, AIDC, ESPO); CHAG, DENG, HANT, LEIV, LEPT and MALA carry
  it in only some files.
- **Half of `AIDABR24` is not ordinary notifications.** 10,622 of 21,096
  records have `ORIGEM` 2 or 3, and none of them has `ID_AGRAVO`, a
  notification date, a notification type, a notifying geography or
  `EVOLUCAO`. The other 10,474 have `ORIGEM` 1, and all but one are `B24`
  notifications. No document defines `ORIGEM` (2026-09-30; omnisus's counts
  reproduced exactly).
- **SIH-RD RR 2022-06 is short at the source**: 668 AIHs, against 4,372 in
  May and 4,134 in July. The file is 50,318 bytes, against 252,712–368,638
  for the state's other 2022 months. Linkage and counts for RR 2022 lack most
  of June's admissions (2026-09-30).
- **The SIM `IDADE` TabWin table reads 000–099 as "Ignorado".** The data put
  minutes there (ADR-0070). Brazil 2022 has 2,598 deaths with unit 0, all
  quantities 1–59, and 2,537 of them died on their birth day. The curation
  labels 001–099 as minutes; the table still labels `000`, which is unfilled.

### 1.10 Identifiers in public files (2026-08-21, F §3j)

- SIASUS patient identifiers (`*_CPFPCN`, `AP_CNSPCN`) fail their check
  digits 0% of the time; `AP_CNSPCN` holds no digits. They behave as
  pseudonyms.
- Professional and director CPFs (`APA_CPFRES`, `APA_CPFDIR`, `UDI_NFRCPF`,
  `UDI_DIRCPF`) validate 100% over 612 values.
- `AP_CNPJCPF` validates 100% as CNPJ (establishments).
- APAC patient blocks carry full date of birth, sex, municipality and
  eight-digit CEP; `EXAC` carries HIV, HBsAg, hepatitis and HLA results, joined
  one-to-one to the patient block. `AP_CEPPCN` in the modern schema holds 2,484
  distinct full CEPs over 5,670 rows.

## 2. TabNet: `.CNV`, `.DEF` and the TAB kits

### 2.1 `.CNV` grammar (2026-08-18, F §1 V3)

- Header `<n_categories> <code_width>`, then rows of sequence number, label,
  and a match expression (a code, a list, a range, or a mix). The expression
  column sits at 60 in most files and 64–66 in others.
- **Last match wins**: `SEXO.CNV` lists `Ignorado → 0-9` first and overrides
  it; `IDADE18.CNV` opens with `Ign → 000-999`.
- A `.CNV` is a codelist, not a column: it never says which field uses it.
- Many tables write the code into the label (`BR_MUNICIPALFA`: `120001 →
  '120001 Acrelândia, AC'`) (F §3k).
- A `.CNV` expands ranges: one "Brasília" rule is 10,000 codes (ARCH §22.7).
- **SIM's `TABPAIS` names three codes twice**, in both the CID-9 and CID-10
  kits: 044 Camboja and Laos, 073 Eire and Irlanda, 081 Falkland and
  Malvinas. The first pair is two countries. The country labels keep both
  names (2026-09-30).

### 2.2 `.DEF` grammar (F §1 V3)

- Line types: `;` comment (the first is the title), `A` the data glob it reads,
  `?` help file, `I` an additive measure (**the Ministry's statement that a
  variable is summable**), `L`/`C`/`S`/`X` row, column, selection, all three, and
  a DBF lookup form naming its label column. `RD.DEF` has 547 lines.
- Usage markers are written in either case; a parser matching upper case only
  lost 881 of 22,675 variable lines (ARCH §22.1b).
- `.DEF` binds tabulation axes and code systems alike: SINASC `CODMUNRES` is
  bound to 145 codelists at one confidence, SIM `CODMUNRES` to 156,
  `DIAG_PRINC` to 114 (F §3k). `RD.DEF` declares `DIAG_PRINC` more than two
  hundred times, never as the raw code (F §4).

### 2.3 The kits

- `TAB_SIH_199201-199712.zip`: 2,926,349 bytes, 246 members (177 `.CNV`, 62
  lookup `.DBF`, 4 `.DEF`, 2 help, 1 DLL). `CID10.DBF` 14,197 rows; `TPROC`
  7,717; `TCNESBR` 7,543 plus 26 per-UF variants (F §1 V4).
- Modern `TAB_SIH.zip`: 6,005,360 bytes, modified 2026-08-17, 794 `.CNV`, 81
  lookup tables (F §1 V4).
- A kit names its validity window in its filename (`199201-199712`); a bare
  name is current (F §3).
- `TAB_SINANNET.zip`: 44 MB, 626 `.CNV`, 60 `.DEF`. `TAB_SISCAN.rar`: RAR5, 103
  `.CNV` whose titles name the columns (ARCH §22.1b).
- CID-10 grew from 14,197 codes (1992–1997 kit) to 14,253 (current) (F §3b).
  `DESCR` labels are 50 characters.
- `CBO` in the current SIH kit mixes 3,000 three-digit CBO-1994 codes with 2,813
  six-digit CBO-2002 codes; `CBO2002` ships separately with 2,445 (F §3b).
- The vendored source documents are 11,379 files including 2,563 `.CNV`
  (`sources/`, gitignored; ARCH §21).

### 2.4 Municipality and geography tables (2026-08-23, F §3k, §3n second)

| table | rows | exact keys | notes |
|---|---:|---:|---|
| `BR_MUNICIPALFA` | 5,647 | 5,642 | accented, UF-suffixed (`Rio Branco, AC`); **the** municipality table |
| `BR_MUNICGESTOR` | 5,645 | 5,641 | the same plus `UF0000` "gestão estadual" sentinels |
| `BR_MUNICIP` | 56,753 | 5,721 | all caps, unaccented, about 10 duplicate rows per key |
| `MUNICBR` | 12,470 | 6,078 | 41% ranges; alone carries 62 pre-1988 Goiás codes moved to Tocantins |
| `??_MUNICIP`, `MUNIC??` | about 32–5,130 | | one state each |
| `CIRAC` and kin | 24 | 24 | per-state health-region roll-ups in a municipality key space |

- National classifications keyed on the six-digit municipality: `CIRBRN`
  (health region; 5,680 municipalities, 478 regions), `MICROBR` (5,697; 586),
  `MESOBR` (5,632; 165), `CSAUDBR` (colegiado; 5,417; 303), `BR_REGMETR`
  (metropolitan; 1,325; 95), `BR_PNDR` (1,126; 14). 139 such codelists ship.
- They are consistent only per publishing system: `CIRBRN` differs across
  systems on 295 municipalities (46 by name), `RSAUDBR` on 2,612 (1,944 by
  name: two regionalisations under one name). `BR_MACSAUD` conflicts on 66%,
  `MSAUDBR` on 4%.

## 3. Record layouts and other documentation

- `IT_SIHSUS_1603.pdf` yields 144 SIH fields with official descriptions and
  types (2026-08-18, F §3b).
- `Estrutura_do_SIM_2025.pdf` and `Estrutura_SINASC_para_CD.pdf` use a
  different dialect whose row numbers look like value lists; with both
  dialects, layout coverage was 331 field descriptions across 8 documents
  (2026-08-19, F §3d).
- SINAN field dictionaries are not on the FTP tree: they are at
  `portalsinan.saude.gov.br/images/documentos/Agravos/<AGRAVO>/DIC_DADOS_<AGRAVO>_v5.pdf`,
  with the shared block in `DIC_DADOS_NET_Not_Individual_rev.pdf`.
  `Dados_Abertos/SINAN/` names agravos in Portuguese (`ACBI` is
  `Acidente_tbr_mat_biologico`). SISCAN's notes are at
  `tabnet.datasus.gov.br/cgi/SISCAN/doc/` (`docs/history/RESUME.md`).

## 4. SIGTAP (2026-08-19, F §3d)

- HTTPS times out on `sigtap.datasus.gov.br` and
  `tabela-unificada.datasus.gov.br`; HTTP on port 80 answers 200.
- Exports are on `ftp2.datasus.gov.br/public/sistemas/tup/downloads`: 224
  monthly vintages, 200801 to 202608. Every table ships its own fixed-width
  layout file, and the layout drifts between vintages (ARCH §14c).
- The newest export gave 44,984 entries; `tb_ocupacao` holds 2,719 occupation
  codes at one width.

## 5. DEMAS open-data API (`apidadosabertos.saude.gov.br`) (2026-08-18, F §1 V9)

- Swagger 2.0, `DEMAS - API de Dados Abertos`, version 1.8.32, 87 paths.
- `/daf/estoque-medicamentos-bnafar-horus` takes `codigo_uf`,
  `codigo_municipio`, `codigo_cnes`, `anomes_posicao_estoque`,
  `data_posicao_estoque`, `codigo_catmat`, `sigla_programa_saude`,
  `tipo_produto`, `sigla_sistema_origem`, `limit`, `offset`: per
  establishment, monthly, by medication (CATMAT).

## 6. IBGE

### 6.1 Population

- On the DATASUS tree: POPSVS (municipal), POPTCU, POP, censo, and `projpop`
  (UF-level projections 2000–2070, which complement rather than supersede
  POPSVS) (F §1 V7, V8). Which series backs the Ministry's published rates is
  open (OQ-12).

### 6.2 Localidades API (audit headed 2026-08-23, committed 2026-08-27; IBGE-L §2–§3)

- `servicodados.ibge.gov.br/api/v1/localidades` is current and the only
  version for localidades; `/api/v2/localidades/*` and `/api/v3/localidades/*`
  return 503. `/api/v3/agregados` is a different service (statistical tables).
- Rows: 5 regions, 27 UFs, **5,571 municipalities**, 137 mesoregions and 558
  microregions (both retired in 2017), 133 intermediate and 510 immediate
  geographic regions (current).
- `/municipios` nests both hierarchies (legacy and current) inside each
  municipality, so one request is enough. Ids are 7 digits.
- Against `BR_MUNICIPALFA`, three IBGE municipalities are absent: Brasília
  (covered by a range row), Pinto Bandeira (under an older code in `MUNICBR`),
  Boa Esperança do Norte (created 2021).
- Compared as partitions, `MICROBR` equals IBGE's microrregião (558 groups
  each, none split) and `MESOBR` differs by three municipalities filed as
  "Ignorado". Compared as labels, agreement looked like 74.1% and 14.3%.
- IBGE has no health regions, colegiados or macroregions.
- The endpoint returns today's division only (OQ-11).

### 6.3 Meshes

- IBGE `/api/v3/malhas` returns gzip **without** `Content-Encoding`; the body
  starts `1f 8b` (ARCH §14.16, 2026-08-29). The built meshes have 5,570
  polygons.

## 7. CNES

- `CADGERBR` lists 687,789 establishments; its labels pack a CNPJ and a name
  into one string (ARCH §14.9).
- `CNES.ST` is one row per establishment per month (a stock); CNES's 13
  datasets share `CODUFMUN` and differ in grain (F §3p, second).
- CNES↔CNPJ evidence (rebuilt pack, 2026-08-23, F §3m, ARCH §14.13): 1,774,993
  rows, 273,514 CNES and 265,418 CNPJ identifiers; 951 ambiguous source
  windows (1,816 pairwise-overlapping relation pairs); 1,218 CNES changing
  target over time; 12,619 reverse multi-source windows (13,923 pairwise
  overlaps).

## 8. Community transcriptions

- `rfsaldanha/microdatasus` (R, MIT): `process_*.R` files encode `"code" ~
  "label"` pairs; parsed, they gave 4,655 pairs across 582 columns, CNES 163
  fields (726 pairs), SIA 37 (570) (2026-08-19, F §3h).

## 9. Independent reference figures

- Low birth weight: 9.5% of 5,099,498 births in the SINASC build, matching
  Brazil's published figure (2026-08-30, F §3w).
- SIH-RD Acre 2022: 49,547 admissions, 1,706 deaths, R$ 43,377,991.73, mean
  stay 4.702323 (F §3o and §3q, second). National SIH-RD artifact: 12,520,914
  admissions, mean length of stay 5.210395 (F §3t).

## SINAN birth dates after the LGPD (measured 2026-09-28)

- **Every SINAN file on the server is dated 2021-11 or later**, including data
  years 1999–2006 in `SINAN/DADOS/FINAIS` (`files.modified`, full crawl of
  2026-09-28). The archive was republished after the LGPD took effect
  (2020-09).
- **The current files mostly reduce the birth date to the year.** 63 of 98
  SINAN families carry `ANO_NASC` without `DT_NASC`; 28 carry neither.
- **7 families still carry `DT_NASC`:** BOTU 2007–15, COLE 2007–19,
  TETN 2014–19 and 2020, DERM 2019, IEXO 2006, and SIFC 2023 (PRELIM). The
  reduction was applied unevenly. These families are identifying data under
  the project's personal-identifier policy (ADR-0032).
- **The form itself collects `DT_NASC`** (`sources/dic_notif_indiv.txt`). A
  Ministry note on a public export states the reduction and its reason:
  "Data de nascimento configurada para ANO_NASC (classificação como dado
  pessoal sensível)" (`sources/nota_chagas.txt`).
- What the pre-2021 files carried is not measurable from today's tree
  (OQ-56).

### The CNES establishment registry in the TabWin kit (measured 2026-09-29)

- **What it is.** `TAB_CNES.zip` ships `DBF/CADGER<UF>.dbf`, one table per
  state: 692,004 establishments. Columns: `CNES`, `CPF_CNPJ`, `FANTASIA`,
  `RAZ_SOCI`, `RSOC_MAN` (maintainer), address, `REGSAUDE`, `CODUFMUN`,
  `EXCLUIDO`, `DATAINCL`, `DATAEXCL` (`99991231` = not excluded), and
  `NATUREZA`.
- **`CPF_CNPJ` is 14 characters but not always a CNPJ.** 372,831 are CNPJs,
  170,203 are **CPFs zero-padded to 14 digits** (sole practitioners), and
  148,967 are zeros. Only the CNPJ check digits tell them apart.
- **`RAZ_SOCI` glues the identifier onto the name:** `CNPJ 00.000.000/0000-00-NAME`,
  `CPF 981.489.152/53-NAME`.
- **The team registry is in the SIA kit, not the CNES kit.**
  `TAB_SIA.zip!DBF/INE_EQUIPE_<UF>.dbf` and `INE_EQUIPE_BR.dbf` (107,438
  teams) map `CHAVE` (the 10-digit INE) to `DS_REGRA` (the team's name).
  `TAB_CNES.zip!DBF/EQUIPE.dbf` holds the 64 team TYPES.
