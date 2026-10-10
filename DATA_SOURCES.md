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
  - **Diagnosed at 17:25 the same day:** the route reaches DATASUS
    (`189.28.137.254`), and only TCP 21 of `189.28.143.164` accepts
    connections. Freshly advertised `PASV` ports time out at connect;
    active mode is refused (`501`); `ftp2.datasus.gov.br` times out; ports
    80 and 443 are closed. The passive range is filtered on DATASUS's side,
    not by the client.
  - **Still so on 2026-10-04** (143 probes since, none with data). From the
    same machine, `ftp.ibge.gov.br` lists over passive mode, which rules
    out the client side.
  - **Reopened by 2026-10-05 17:16 UTC.** The last failed probe was at 17:01;
    every probe since has connected in 0.1 s (230 failed, then 39 open).
- **Documentation lives outside `/dissemin/publicos` too** (2026-10-08). The FTP root holds 40 directories (`siasus`, `catalogo`, `siscam`, `tabwin`, `territorio`, `municip`, `caderno`, ...), which the catalog does not crawl. `/siasus/Documentos` and `/siasus/{APAC,BPA,RAAS,SIA}` alone hold 214 documents (`data/probes/ftp_outside_siasus.txt`): the APAC, BPA and RAAS export layouts, the operational manuals, oncology manuals 2008-2022, and layout spreadsheets 2008-2012. The server answers `LIST` (IIS format) but not `MLSD`.
- **CNES publishes template files** `Dados/{EF,GM,HB,IN,RC}/<DS>ufAAmm.dbc` (about 1 KB, header only), whose names are the naming pattern itself. They belong to their series with no UF and no date (2026-10-08).
- **`Dados_Abertos/SIPNIBD/`** holds SI-PNI/RNDS extracts by municipality of residence: `Doses_Residencia.parquet` (1.17 GB, 236,140,984 rows from 2026-01) and `Cobertura_Residencia.parquet` (1,088,479 rows, 2015-2026, coverage as a fraction). They are not the PNI DBF tables (2026-10-08).
- **`/cnes/Download`** (outside `/dissemin`) has the SCNES glossary, the CBO-service glossary and the TXT layout notebooks for SIA/SIH/CIHA/CIH; `/territorio/doc` has the territorial base documents (2026-10-08).
- **Two systems share the file prefix CM**: SISMAMA's `SISCAN/SISMAMA/Dados/CMuuaamm.dbc` (mammography cytology, 2009-2015) and SIH's `SIHSUS/200801_/Dados/CMBRaamm.dbc` (maintainer register, 2019-). A prefix identifies a system only inside a republication tree (2026-10-08).
- **CNES-ST is a pivot of the SCNES database's own tables** (2026-10-08). The layout notebook `ftp.datasus.gov.br/cnes/Download/Caderno_Layout_TXT_SIA_SIHD_CIHA_CIH_2.0.pdf` (local `sources/ftp_cnes_docs/`) documents them, one row per (establishment, code):
  - LFCES004 establishments → ST's identity columns;
  - LFCES006 attendance provided (CODATPREST × COD_CONVEN) → the 49 flags `AP##CV##`;
  - LFCES007 management of activities (CODPROG × IND_ESTMUN) → `GESPRG#E/#M`;
  - LFCES015 physical installations (COD_INSTAL, QTDE_INST, NUM_LEITOS) → `QTINST##` with `QTLEIT##`, the beds in installation ##.
  ST spreads these onto one row per establishment and month, so a code lives in a column name. The other CNES files come from their own tables: LT ← LFCES002, PF ← LFCES018/021, SR ← LFCES032, EP ← LFCES037/038, HB ← LFCES045, RC ← LFCES046.
  The same folder's `GLOSSARIO_SCNES_Geral.xls` lists the entry software's validation messages, and `leia_me.pdf` (505 pages) is its release notes; neither is a data dictionary.
- **SIA-PA mixes documents** (Informe Técnico SIASUS 2019-07, §2.1): PA_DOCORIG I = BPA-I (one row per attendance, with the patient), P/S = an APAC's main/secondary procedure, A/B = RAAS home care/psychosocial, C = BPA-C (a count per procedure and CBO, no patient). The BI, APAC and RAAS files republish the patient-level parts, so PA is never pooled with them (2026-10-08).
- **The mirror carries 8 of the tree's top-level directories** (2026-10-03,
  its own index): CNES, SIASUS, SIHSUS, SINASC, SIM, SINAN, Dados_Abertos
  and ESUSNOTIFICA. It has no IBGE and no CIHA.
- **SIDRA's limits** (API v3 `agregados`, measured on table 9514 on 2026-10-04; the planner in `sidra/planner.py` applies them, §6.4).
  1. **At most ~50,000 values per request.** A value is localities × selected categories × variables × periods; a classification fixed at its total does not count.
     - Pass: 49,474, 49,600 and 49,800 values.
     - Fail with HTTP 500: 50,310, 50,400 and 51,180 values.
  2. **The ID lists must stay short.** Explicit `localidades` and `classificacao` lists fail with HTTP 500 once their text passes about 4.1 KB, whatever the value count: 500 municipalities × 2 sexes × 10 ages fails, 500 × 2 × 8 passes. A long unrelated parameter does not count. State selectors (`N6[N3[uf]]`, `N6[all]`) avoid the problem.
  3. **IBGE's firewall rejects URLs of about 8 KB with an HTML page and HTTP 200.** A 200 status therefore does not mean data.
- **TabNet's web side is another first-party source over HTTP.**
  `http://tabnet.datasus.gov.br/cgi/territorio/<table>.cnv` serves the
  current territorial tables its tabulations use, and `tabcgi.exe?<def>`
  answers a tabulation (`sources/tabnet.py`).
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
- **`Dados_Abertos` SINAN exports are not the DBC in another format** (2026-10-03, ADR-0135):
  - the CSV strips leading zeros from codes (`08` becomes `8`);
  - IEXO 2023 has 66 columns against 80–82;
  - SIFA holds Python bytes reprs as values (`b'2',b'A539'`) in 2018–2020 and 2023 (2026-10-08 sweep); the text reader unwraps them;
  - the exports are dated 2026-01-29, while PRELIM DBCs are republished later.
- **SINAN dates** (2026-10-04): the DBCs declare type `D` on 1,077 date fields (213 names) in 96 of 98 families, written `YYYYMMDD`; the `Dados_Abertos` CSVs write the same dates as ISO text. HANT 1999–2006 declares its dates `N8` (`YYYYMMDD`, `0` for blank), and a few fields named like dates are `C` (`DT_DOSE_*`, `CON_DT_OBI`).
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
- **CIHA starts in 2011** (catalog, 2026-10-09: 4,798 files, 2011–2026); a
  link asking for CIHA 2010 finds no publication, which is a gap, not zero.
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
- **SIH money is in reais from 1995 on, with no centavos era** (Acre
  1992–2023 against TabNet, 2026-10-03).
  - 1992 is in cruzeiros, 1993 in cruzeiros reais, and 1994 mixes both
    currencies (reais from July).
  - `US_TOT` (dollars) is the comparable measure across 1994.
- **TabNet's SIH "Internações" excludes long-stay continuation AIHs
  (`IDENT` 5); its "Valor total" includes them.** Its Acre file for
  September 2009 (`niac0909.dbf`) returns no table, so TabNet's 2009 Acre
  total omits that month (2026-10-03).
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
- **`SIHSUS/2010/XML/` holds 324 empty files** (`RD*.xml`, 0 bytes, listed since 2014). They share their logical ids with the 2010 DBCs in `200801_/Dados/`, and the mirror does not carry them. They are placeholders, not publications (2026-10-04).
- **SINASC's `SEXO`: the layout says letters, the files measured say numerals** (corrected 2026-10-04; this line first said the national files write M/F/I and the state files 1/2/0, which no file read supports). The 2019 layout lists `M`, `F`, `I`. Read: `DNBR2020`, `DNBR2021` and `DNBR2022` (`1996_/Dados/DNRES/`, 2,730,145 / 2,677,101 / 2,561,922 rows) hold only `1`, `2`, `0` (2021: 1,369,558 / 1,307,126 / 417), and so does `DNSE2021` (31,206 rows). The letters are decoded as well, in case an edition writes them (curation `SEXO`); no file seen does. Not yet read: other state files and years, and the `Dados_Abertos` CSVs.
- **SIH-RD writes the Federal District's residents with administrative-region codes until 2017-12** (measured 2026-10-04, DF files): `MUNIC_RES` holds 530020 to 530180 and 530135, which are no municipality (Brasília is 530010). Read: January of 2008, 2010, 2012, 2014, 2015, 2016 and 2017, and December 2017, carry them (January 2008: 2,220 of 7,754 rows; January 2017: 11,941 of 16,649); January 2018, 2019 and 2022 carry none (2018: 12,207 of 15,631 rows are 530010). The whole of 2017 in the DF files: 11,025 rows 530010 and 140,876 region codes, 151,901 together, against TabNet's 152,622 residents of Brasília (the other 721 sit in other states' files). Years before 2008 are unmeasured. Curation recipe `MUNIC_RES_municipio` maps them inside 2008-01 to 2017-12; `MUNIC_RES` is untouched.
  Other systems, DF files: SIM-DO (2000, 2010, 2017) and SINASC-DN (2000, 2017) write 530010 only; SINASC-DN 2010 has 6 of 44,251 rows with one region code. SIA-PA `PA_MUNPCN` carries them (January 2010: 4,192 of 127,264 rows, 20 codes; January 2017: 50,666 of 197,152, 24 codes) and so does CNES-ST `CODUFMUN` (2010: 2,511 of 5,583; 2017: 1,876 of 4,081). Windows (measured 2026-10-05 on DF files, one month per step, bisected at both edges): SIA-PA `PA_MUNPCN` has none in 2008-07 (0 of 113,624), 19 of 116,709 in 2008-08, then every year and still in 2026-06 (26,598 of 531,506): mapped by `PA_MUNPCN_municipio` from 200808, open-ended; CNES-ST `CODUFMUN` from the first file, 2005-08 (1,305 of 3,256), to 2017-11 (1,358 of 2,522), 1 of 2,589 in 2017-12 and none from 2018-01: mapped by `CODUFMUN_municipio` for 200508-201712 (CNES-LT and -EQ 2012-01 carry them too, 392 of 715 and 5,838 of 11,702, none in 2018-01; the recipe is shared by all CNES types). SIA-PA has other 53xxxx codes no region list holds (530005, 530015, 530000, 5399xx; 2022-01: 417 rows): left as written. The pre-2008 PA layout has no `PA_MUNPCN`. SINAN has only national files, not read.
- **SINASC's newborn `RACACOR` is the mother's declaration** (measured 2026-10-04, SINASC 2020-2022 linked to SIM infant deaths): where both are known, `RACACOR` equals `RACACORMAE` in 50,078 of 50,078 records. Codes 1 Branca, 2 Preta, 3 Amarela, 4 Parda, 5 Indígena in both SIM and SINASC (layouts); TabNet's `RACACOR.CNV` abbreviates them (`Bra`, `Amar`, `Indig`), and SINASC's pre-1996 kit files a different table under the same name (1 Amarela, 2 Branca, 3 Indígena, 5 Preta).
- **COVID-19 in SIM is `CAUSABAS` B34.2, not U07.1** (measured on SIM-DO 2020, all
  1,556,824 records, 2026-10-04):
  - 212,706 records have B34.2 as underlying cause, and none has a U07 code there;
  - U07.1 appears in the cause lines (LINHAA–D, LINHAII) of 173,561 records, 165,393 of them B34.2 deaths.

  A COVID count by underlying cause therefore reads B342. The ICD-10 U07 node (WHO 2020) serves the systems that code U07.1 directly.
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

- **SIH-RD's `CID_MORTE` and `CID_ASSO` stop in 2014** (measured 2026-10-08 from the decoded lake): through 2014 they hold the cause of a death in hospital and an associated cause on 3–4 % and about 1 % of AIHs (2013: 439,319 and 133,866 of 11,197,160); from 2015 every record holds `0000`. The roles end their years at 2014. SIM-DO's `CB_PRE` (the underlying cause before reselection) is filled 2006–2010 (2010: 1,126,944 of 1,136,947), absent from the 2011–2013 files, and present but empty from 2014. A column's presence in a schema (`field_available`, `field_coverage`) does not say it is filled.

- **TabNet's SIM labels call documented categories 'Ignorado'** (2026-10-08): the 2022 labels give 'Ignorado' to every code from 5 up for `ESC`, `ESCMAE` and `LOCOCOR`, where the record layout (`sources/sim2025.txt`) defines 5 = '12 anos e mais' (both schooling bands) and 5 = 'outros', 6 = 'aldeia indígena' (place of death). A missing code proposed from the labels alone (`scripts/propose_missing.py`) is checked against the layout; SINASC's declarations agree with theirs.

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

### 1.11 SIA APAC families (2026-10-05)

- **Where and what.** `SIASUS/200801_/Dados/<FAM><UF><YY><MM>.dbc`, one file per state and month, all with the same
  45-column `AP_*` block (competence `AP_CMP`, processing `AP_MVM`, APAC number `AP_AUTORIZ`, main procedure `AP_PRIPAL`
  (SIGTAP, 10 digits), CNES `AP_CODUNI`, CIDs `AP_CIDPRI`/`AP_CIDSEC`/`AP_CIDCAS`, patient sex, race, residence
  `AP_MUNPCN`, age `AP_NUIDADE` + unit `AP_COIDADE`, pseudonymous `AP_CNSPCN`) plus the family's own clinical block.
  Rows per file are in bytes 4-7 of the DBC header (uncompressed), so an 8-byte ranged read of the mirror counts a file
  without downloading it: 41,832 files, 0 failures, and the counts equal the rows `query()` returns (AQ DF 2023 60,620).
- **Families** (files, years, rows over all years, rows in 2023, columns of the newest schema):
  AQ chemotherapy (5,979, 2008-, 62.1 M, 4.32 M, 74), AR radiotherapy (5,465, 2008-, 4.07 M, 0.15 M, 74), AN pre-dialysis
  nephrology (2,145, **2008-2014**, 6.53 M, 60), ATD dialysis (3,884, 2014-, 16.5 M, 1.49 M, 65), ACF vascular access
  (3,768, 2014-, 0.41 M, 56), AM specialised medicines (5,957, 2008-, 387.8 M, 29.75 M, 51), AD various (6,019, 2008-,
  60.9 M, 3.62 M, 46), AB follow-up after gastroplasty (635, 2008-2017 and 2025, 0.23 M, 58; written "bariatric surgery" here until
  2026-10-10: every row read carries 0301120056, ACOMPANHAMENTO DE PACIENTE POS-GASTROPLASTIA, and the surgery is an
  AIH) and ABO, the same follow-up from 2014 (1,607, 2014-, 0.55 M, 78),
  AMP (891, 2016-, 0.20 M, 65). PS (4,394, 2012-, 170 M) and SAD (1,088, 2012-2018, 3.5 M) are person-level but not APAC.
  The 2001-2007 `AC` (self-extracting `.exe`) is the old dialysis APAC (§1.10).
- **A row is an APAC-month, not an APAC.** An APAC (`AP_AUTORIZ`) lasts up to three months and has one row per competence
  (no duplicate `(AP_AUTORIZ, AP_CMP)` in any slice read). `AP_TPAPAC` is 1 on the first row, 2 on later months, 3 on a
  single-row APAC; for type 1 the month of `AP_DTINIC` equals `AP_CMP` (AQ AC 2023: 2,921 of 2,921). AQ AC 2023: 8,417
  rows, 3,287 APACs, 2,921 type-1 rows; the other 366 began in the previous year's files. AR 2023, ACF 2023 and most AD rows (7,946 of 8,585 in AC 2023) are type 3.
- **The patient key.** `AP_CNSPCN` is 15 non-digit characters, the same pseudonym in every file read: stable across months
  and years (AQ AC: 203 of the 882 patients of 2019 recur in 2023) and across families (AR AC 2023: 280 of 413 patients are
  also in AQ; ATD and AM: 384 of 679). One APAC has one pseudonym; in AQ AC 2023 1,360 patients hold 3,287 APACs (491 hold one, 310 two, 211 three, 198 four). It is the person key
  for cohorts within SIA APAC (its link to SIH or SIM was not tested). `AP_APACANT` (previous APAC number) is all zeros.
- **Age** has no birth date: `AP_NUIDADE` with the unit `AP_COIDADE` (2 days, 3 months, 4 years, 5 = 100 + value; units
  2, 3, 4 and 5 occur), decoded to `IDADE_anos` as in SIH. AQ SP 2023-01: unit 4 ages 1-99, unit 5 values 00-07.
- **`AP_MNDIF` is constant `1`** on every row of every family read (AQ SP 2023-01: 80,069 of 80,069, patient outside the
  facility's municipality in 40,935), so it is not a municipality mismatch flag and is left undecoded. `AP_UFDIF` equals
  the state comparison exactly.
- **Brasília.** `AP_MUNPCN` holds administrative-region codes 530020-530180 in some years (AQ DF: 2008 308 of 20,086;
  2012 17,892 of 26,173; 2018 425; 2021 91; 2022 and 2023 none) and `AP_UFMUN` holds 530180 for a second unit in AQ 2017
  and AN 2008-2014. Derived `AP_MUNPCN_municipio` maps the residence in 2008-2021.
- **Where the diagnosis is.** AQ, AR, AN: `AP_CIDPRI` (tumour site C/D codes; N18x for AN). ATD and ACF: `AP_CIDPRI` and
  `AP_CIDSEC` are `0000` on every ATD row read (2015, 2019, 2023; ACF 2023 `AP_CIDPRI` likewise); the renal CID is in `AP_CIDCAS` (N180 in 2015, N188 in 2019 and 2023, `0000` on 10-41% of rows). ABO has
  no `AP_CIDPRI`. `AQ_CID10` is empty in the 74-column files.

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
- **A band `.CNV` on a measurement labels its out-of-range values "Ign"**: it
  is TabNet's tabulation domain, not a sentinel (IDADEMAE 66+ `Ign`, SINASC
  PESO ≥ 9000 `ign`, SIM PESO > 8000). SIM's QTDFILVIVO/QTDFILMORT bands label
  `0`/`00` `Ignorado`, yet zero is a real count: SIM 2022 holds 5,947 `00`
  against 9,832 `01`, SINASC 2022 1,046,860 `00` of 2.56 M. In the files,
  `99` is the de facto not-recorded value of the two-digit counts (CONSPRENAT
  2022: 11,107 at `99`, single records at 66–72), documented nowhere for them
  (2026-10-07, `scripts/propose_missing.py`).

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
- IBGE's yearly territorial divisions (DTB) on `geoftp.ibge.gov.br` (2026-10-03):
  - publish meso- and microregions for 1994, 2000 and 2005–2022, and
    immediate and intermediate regions for 2019–2025;
  - no municipality's region code in any year differs from today's, and no
    municipality left; only new ones appeared (4,974 in 1994; 5,571 now);
  - 2001–2002 are not published, and 2003–2004 carry no regions.
- The 46 `CIRBRN` contests left after scoping are all SIM against SINASC
  (2026-10-03, ADR-0129).
  - 33 are one region in two code schemes: SINASC's Santa Catarina table
    writes UF plus two digits (`4214`), where SIM and TabNet write UF plus
    three (`42014`).
  - 13 are region changes, two vintages of the regionalisation. TabNet's
    current table sides with SINASC in 11 and with SIM in 2.

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
- **The DATASUS CID-10 release in CSV** (`sources/cid10csv_v2008.zip`, its fields defined in
  `sources/ds_descrcsv.htm`; read 2026-10-06):
  - Category and subcategory rows carry `CLASSIF` (blank, `+` etiology, `*` manifestation), `REFER` (the code in
    the other dual classification, *not always filled*) and `EXCLUIDOS` (retired codes now part of this one).
  - Only subcategory rows carry `RESTRSEXO` (`F` or `M`: the code may be used for that sex only) and
    `CAUSAOBITO`.
  - `CAUSAOBITO = N` means "pouca probabilidade de causar óbito" (unlikely to cause death). It does *not* mark
    the codes barred as an underlying cause: the release says separately that manifestation (asterisk)
    codes and chapters XIX and XXI must not code a cause of death.
  - A category without subcategories appears as a subcategory row with a blank fourth character.
  - Groups nest ("um grupo pode conter outros grupos"): 11 groups contain others (C00-C97 ⊃ C00-C75 ⊃ C51-C58;
    V01-X59 ⊃ V01-V99 ⊃ V40-V49 and W00-X59; M00-M25 etc.; T20-T32; Y40-Y84), 63 groups sit inside one. The tree
    hangs a group on the smallest group enclosing it and a category on the smallest group containing it; before
    2026-10-06 every category hung on the outermost group (C53 under C00-C97, not C51-C58).
  - Counts: 12,451 subcategory rows (300 `*`, 78 `+`; 758 `F`, 116 `M`; 1,291 `N`) and 2,045 categories. Served
    as `code_attributes()`.
  - Subcategories of W00–Y34 name their place of occurrence after their last " - " ("residência", "rua e
    estrada" … "local não especificado"). X59, Y06 and Y07 do not: their 4th character is something else
    ("causando fratura", the perpetrator).
- **The NCHS External Cause of Injury Mortality Matrix for ICD-10** (`cdc.gov/nchs/injury/ice/matrix10_sas.htm`,
  November 2002, terrorism codes 2003; a US federal publication).
  - Its SAS statements assign mechanism (20 classes), intent (5), the motor-vehicle person (6) and adverse
    effects.
  - On 2026-10-06 `curl` got 403 from the CDC edge (Akamai), with and without a browser User-Agent. A browser
    read the page, and its text is kept as `sources/cdc_matrix10_sas.txt`.
- **NCHS Instruction Manual Part 11, Computer Edits for Mortality Data (2023)** (`cdc.gov/nchs/data/dvs/2023_PT11_A.pdf`;
  `sources/nchs_pt11_2023.pdf` and its text). Read 2026-10-06: curl got 403 from the CDC edge again, and the
  PDF came through the web fetcher.
  - Table G gives the age/cause and sex/cause edits for codes valid as underlying cause: 607 entries. Each is
    *absolute* (impossible; the limits explicit in ICD-10) or *conditional* (highly improbable). Its legend
    defines each edit code's allowed set (14 = female, 10–54 years). Served as the `nchs_*` columns of
    `code_attributes()`.
  - Some absolute age edits are coding rules rather than biology: sepsis (A40, A41) and diabetes (E10–E14) under
    28 days belong to chapter XVI.
  - Against the release's RESTRSEXO, there is no contradiction. 885 codes agree. Only RESTRSEXO restricts 117
    (O08, O80–O84, Z32–Z39, N51, N74, N77); only NCHS restricts Q97 and Q98.
- **The NCHS ICD-9/ICD-10 comparability study** (`ftp.cdc.gov/pub/Health_Statistics/NCHS/Datasets/Comparability/icd9_icd10/`,
  2004; the report is Anderson et al. 2001, NVSR 49(2); `sources/nchs_comparability/`). The US deaths of 1996 were
  coded in both ICD-9 and ICD-10.
  - The public-use file holds 2,318,212 records, 720 characters each. The ICD-9 underlying cause is at positions
    142–145 and the ICD-10 one at 444–447. 21,290 records carry "Y" at 441 and no ICD-10 code; the study excludes them.
  - The FTP host answered curl (unlike www.cdc.gov), at about 80 KB/s.
  - It is served as `code_bridge("ICD9-ICD10")`: for each ICD-9 code, the ICD-10 categories its deaths fell in, and
    their shares. The shares are US 1996's, not Brazil's.
  - Against SIM: in DORRS95 (RS, 1995; 65,039 deaths, CAUSABAS 4 characters), 99.45 % of the underlying causes are
    a bridge code or its category. The unmatched are led by 0091 (159 deaths), 0861 (29) and 5089 (25). The ICD-9
    era's DO files also carry a `CRITICA` field.
- **DATASUS's population estimates 1980–2012** (`/dissemin/publicos/IBGE/POP/POPBRyy.zip`, 2.4–8.8 MB a year; each zip
  holds DBF, CSV and XML; read 2026-10-06, POPBR95).
  - Columns: `MUNIC_RES` (6 digits), `ANO`, `SEXO` (1, 2), `SITUACAO` (3 in 1995), `FXETARIA` (single ages 0–4,
    then five-year bands to 80+, and `I000`, age ignored) and `POPULACAO`.
  - Every year carries sex and age (POPBR80, 95, 05, 12 checked; 22 to 34 age codes by year; 3,991 municipalities in
    1980, 4,974 in 1995). The series table (`sources/ibge.py`) had recorded it as totals only; corrected.
  - The age–sex denominators the ICD-9 era of SIM (1979–1995) needs; the population account starts in 1991, as
    totals. Not yet a source of `population()`.
- **No age table in the DATASUS publications.**
  - The SIM dictionary (`sources/dicdo.txt`) lists the system's own record critiques ("Óbito com restrição de
    idade", "CID Implausíveis", "Causas Asterisco"). Neither the rules behind them nor the per-record flags are
    published: the 2023 DO file has 87 fields, none of them a critique.
  - SIGTAP's `tb_cid` has no age field, and its `TP_SEXO` is not the restriction (C53 is "I").
  - The TabWin kit's SIM lists (ASTERISC, CBPOUCOUTEIS with garbage-code types, IMPROVAVEISSTRIVIAIS,
    TRIVIAL_32) are in the lake as reference tables.
  - CBPOUCOUTEIS ("Pco Uteis detalhada" in the DO .DEF) types 3,094 codes Tp 1–Tp 5 (1,899 / 164 / 19 / 623 / 389).
    The kit defines no type: Tp 5 holds the R codes, Tp 4 the unspecified ones. It is served as the code list
    `SIM-POUCO-UTEIS`, item = the type as written (3,090 codes in the tree).

## 4. SIGTAP (2026-08-19, F §3d)

- HTTPS times out on `sigtap.datasus.gov.br` and
  `tabela-unificada.datasus.gov.br`; HTTP on port 80 answers 200.
- Exports are on `ftp2.datasus.gov.br/public/sistemas/tup/downloads`: 224
  monthly vintages, 200801 to 202608. Every table ships its own fixed-width
  layout file, and the layout drifts between vintages (ARCH §14c).
- The newest export gave 44,984 entries; `tb_ocupacao` holds 2,719 occupation
  codes at one width.

## 5. DEMAS open-data API (`apidadosabertos.saude.gov.br`) (2026-08-18, F §1 V9)

- Swagger 2.0, `DEMAS - API de Dados Abertos`, version 1.8.32, 113 paths (87 on 2026-08-18; corrected 2026-10-10).
- `/daf/estoque-medicamentos-bnafar-horus` takes `codigo_uf`,
  `codigo_municipio`, `codigo_cnes`, `anomes_posicao_estoque`,
  `data_posicao_estoque`, `codigo_catmat`, `sigla_programa_saude`,
  `tipo_produto`, `sigla_sistema_origem`, `limit`, `offset`: per
  establishment, monthly, by medication (CATMAT).

- **Assessed 2026-10-10** (`docs/evaluation/2026-10-10-demas-source-assessment.md`, every endpoint). JSON lists keyed by the
  dataset name, no total; `limit` ≤ 1000, `offset` a row offset; 1e7 deep ≈ 15-35 s, 3e7 ≈ 42-60 s, beyond that `502`. On the
  CNES, SIA and SIH endpoints and the municipality list the limit applies before de-duplication (a short page is not the end).
  DEMAS is **not** the full source on most tables: SISAGUA cianobacterias holds 5,000 of 49,288 rows, carro-pipa 60%, SG leve
  2023/2024 and SISAGUA plano-amostragem stop at 5,000, SIM holds 2025-2026 only, SINASC is empty, SRAG 2019-2026's `dt_notific`
  is wrong; it equals SIES and one SISAGUA slice. The origin of the non-FTP datasets is the Portal de Dados Abertos do SUS
  (`dadosabertos.saude.gov.br`; the old `opendatasus.saude.gov.br` redirects): yearly or monthly CSV/parquet files under
  `s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/` (SISAGUA 2014-2026, PNI monthly 2020-2026, SRAG parquet, SISVAN, SG).
  Verdicts: 35 use DEMAS (ESAVI, mpox, yellow fever, SIES, BNAFAR, COVID occupancy, SIASI/SESAI, SISAB, SIAPS, health-region
  mapping, BPS), 49 original with DEMAS as fallback, 29 not relevant.

## 6. IBGE

### 6.1 Population

- On the DATASUS tree: POPSVS (municipal), POPTCU, POP, censo, and `projpop`
  (UF-level projections 2000–2070, which complement rather than supersede
  POPSVS) (F §1 V7, V8). Which series backs the Ministry's published rates is
  open (OQ-12).

- **The Ministry's tables divide by POPSVS** (2026-10-03). TabNet's
  population form (`ibge/cnv/popsvs2024br.def`, "Estudo de Estimativas
  Populacionais por Município, Idade e Sexo 2000-2025", RIPSA/CGIAE) reads
  `IBGE/POPSVS`. Its 2022 equals the local POPSVS in all 27 states:
  210,862,983. OQ-12 is settled.
- **`POPTBR22.zip` and `POPTBR23.zip` hold the national table and its 27
  per-state parts**; other years hold the national table alone. Reading every
  member double-counts (fixed in the population build).

- **The Census series and how complete each census was** (2026-10-05).
  - **Raw counts** (`CENSO`, SIDRA tables 1552 for 2000, 1378 for 2010, 9514 for 2022; `sidra/population.py`):
    169,799,170, 190,755,799 and 203,080,756 people. SIDRA writes `-` for an absolute zero and `...` (not available) for the
    58 municipalities created after 2000, which table 1552 lists with no value; those cells are kept as nulls.
  - **2022 enumerated vs imputed:** 195,101,203 enumerated plus 7,979,553 imputed (occupied households without an interview;
    PES report Table 1, by state: São Paulo 7.7%, Rio de Janeiro 4.2%).
  - **PES 2022** (`sources/pes.py`; IBGE, *Pesquisa de Pós-Enumeração do Censo Demográfico 2022*,
    https://biblioteca.ibge.gov.br/visualizacao/livros/liv102110.pdf, read 2026-10-05). Dual-system estimation on 4,795 tracts,
    applied to the enumerated count only. Net error 8.3% (omission 12.2%, wrongful inclusion 3.3%); the net error is
    `(N − C) / N`, so the corrected population is `C / (1 − ε)`. By age and sex 3.3% (women 75–79) to 11.2% (women 20–24);
    by state 3.8% (PB) to 15.5% (RJ); by municipality size 3.9% (<14,000) to 13.2% (>1 million). Only the margins are published.
    The age-sex margins give 211.96M, the state margins 213.39M and the size margins 213.02M (the report's 8.3% on 195.10M gives
    212.76M); the three do not reconcile exactly, and the rates are published to one decimal.
  - **POPSVS 2022 is IBGE's *Projeções Revisão 2024*** (IBGE notes liv102111 and liv102112, relayed 2026-10-05): a demographic
    reconciliation of 2000, 2010 and 2022 with the PES, not an observation. Its 2000 (174.70M) and 2010 (194.75M) are 3.0% and
    2.2% above the raw counts (ages 0–9: 5.3% and 7.4%); at 60 and over it sits 0.25M below the raw 2022 census because IBGE
    carries 2010 forward there. It rests on the same births and deaths as a vital-registration account, so it is no
    independent check of one.
  - **Births test, 2022** (relayed): the raw census at ages 0–4 is 12.705M against about 13.73M surviving registered births
    (92.5%); PES-corrected it is within 1.1% of them.
  - **The same test in 2010** (`population_account`, births 2005–09 against the census at 0–4): the census matches the registered
    births to within about 1% (the fitted discrepancy is −0.2% ± 0.6%), so the 2010 census did not show the child undercount of 2022.

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
- `pg.mesh(level, quality)` serves `qualidade=minima` for maps (2026-10-10): 27 states and 5,570
  municipalities, 3.6 MB for both, codes 2 and 7 digits.
- **Which SINAN agravo holds an ICD-10 code** is read from its records' `ID_AGRAVO` (`concept_index`, 2026-10-10,
  lake years): SINAN-TOXG 2025 holds O98.6 11,852, B58 2,804, P37.1 162 (the miscoding Nota Técnica 133/2022 names);
  TOXC 2025 P37.1 6,879, B58 247, O98.6 153; SINAN-SDTA 2023 (foodborne outbreaks) B58 18. SIGTAP 202609's
  `rl_procedimento_cid` has 82,103 procedure–code pairs; toxoplasma serology (0202030768 IgG, 0202030873 IgM,
  0202110150 heel-prick IgM) is tied to no code there and is found by its label.

### 6.4 SIDRA, the aggregates API v3 (measured 2026-10-05 through `sidra/`)

- **The catalog.** `GET /agregados` (1.95 MB) lists 9,336 tables of 70 researches; `?nivel=N6` selects 4,448 and
  `?nivel=N3` 6,269. A table's `/metadados` gives its variables with units, its classifications with every category
  (`nivel` 0 is the Total), its frequency, first and last period and territorial levels (median 5 KB, 0.7 s).
- **`N6` does not mean every municipality.** Sampled tables: PNS, PeNSE and PNAD Contínua list the 27 capitals at N6;
  the Census, MUNIC, PNSB, GDP and the CEMPRE list 5,507 to 5,570 (the lattice of their year); Registro Civil 1,506 to 5,570.
  The table's own `/localidades/N6` is the count that matters.
- **Category ids are global.** Over the tables scanned, a (classification, category) pair has one name everywhere (0
  conflicts in 20,855 pairs over 6,095 tables), so crosswalks are keyed by classification.
- **A classification can have no Total** (392 of 15,233). Leaving it out of `classificacao` is answered with category id
  `0` and an empty name (table 307).
- **A classification left out is its Total; `[all]` includes the Total**; the response holds one `resultados` entry per
  category combination, each with a `series` of localities, and states the classifications in its own order.
- **Selectors.** `N6[N3[27]]`, `N6[N3[11,12]]`, `N6[N2[2]]`, `N3[all]`, `N1[all]` work; two selectors joined by `|` fail with HTTP 500.
- **Cost.** About 125 bytes of JSON a value; 48,000 values in 5 to 9 s (median 5.6 s for 4 MB), about 8,000 values a second
  sequentially; gzip on disk is 14 times smaller. A body can be gzip without `Content-Encoding` (ADR-0127): it is read by its magic bytes.
- **Numbers** use `.` for decimals and no thousands separator. Marks: `-` zero, `..` not applicable, `...` not
  available, `X` withheld. Table 1552 (Census 2000) answers `...` for the 58 municipalities created after 2000.
- **An id the catalog does not list answers HTTP 500** on `/metadados`, `/periodos` and `/variaveis` (404 on the bare id, "Tabela inválida" on the old API): table 306, once taken for a limit, is not a table (2026-10-05). The Contagem 1996 (research CM, 21 tables) has its sex × age tables at 472 (single age) and 475 (groups to 70+; 4,974 municipalities, 156,658,740 people in the groups); 305 is by head of household. The 1991 Census race: municipal only as a total (136, 5,565 municipalities), by age and sex for N1-N3 only (140).
- **SIM before 1996** is `SIM.DOR` (1979-1995, per state, corrected base; `IDADE_anos` exists; `SIM.DO` starts in 1996) and SINASC from 1994 (`SINASC.DN`: 2.57M births in 1994, 2.87M in 1995). Until 1998 both write the city of Rio de Janeiro as 3345xxx (50,000 deaths a year; 330455 itself 700-1,500), from 1999 as 330455.
- **Projections** (research XE, 5 tables) are state level only and stop at the 2018 revision; the estimates (XF, table 6579) are
  municipal totals only, without 2007 or the census years. Neither carries municipal age and sex: POPSVS does.
- **The same Total differs between tables of one census**: 2010 households are 57,324,185 in table 3154 and 57,324,167 in
  tables 1436 and 3218 (18 apart).

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

### Facts read off SINAN forms and files during role review (2026-10-08)

- **Toxoplasmosis' entry dates are 70 years early in two years.** In the FINAIS `.dbc` of TOXG (and TOXC) for 2021 and 2022, `DT_DIGITA` holds the year minus 70 on most records: TOXG 2022 has 11,190 of 12,447 in 1952–53, and 2021 has 8,998 in 1951, raw in the file. 2020 and 2023 are clean. Whether the Dados Abertos CSV republication carries the right year is not yet read.
- **Toxoplasmosis' Nota Técnica 133/2022-CGZV/DEDT/SVSA/MS** (`sources/sinan_docs/Nota_Tecnica_Toxoplasmose.pdf`). Gestational = a notification with ICD-10 O98.6, P37.1 or B58 of a pregnant woman aged 10-49; congenital = the same codes in a child under one year. Data valid only from 2019; a year's national database is frozen three years after the notification year; ICD codes are sometimes entered wrongly (pregnant women with B58 or P37.1); the data may not be representative; the form is the generic Ficha de Notificação/Conclusão. Declared as `source_notes` (ADR-0160), as is Rotavirus' 30/2024 (sentinel surveillance of under-5 diarrhoea, not compulsory notification).
- **Dictionaries are sources, not the truth.**
  - Meningitis's v5 dictionary prints `ANT_TRAUMA` as 1 Sim / 3 Não, while the records use 2 for Não and never 3.
  - Schistosomiasis's prints `EVOLUCAO` "1 – Cura 2, Não Cura" without a separator.
  - Both are corrected in `curation/codes/supplements.yml`, with both claims cited (evaluation 2026-10-08-declarations-by-form).
- **SINAN-SDTA (foodborne outbreaks) counts its ill in a grid** (2026-10-09, ADR-0156):
  - **The grid.** Field 32 counts the ill by sex × band (<1, 1–4, 5–9, 10–19, 20–49, 50+, ignorada). The
    dictionary makes it sum to the ill who were interviewed (field 28), not to every ill person (NU_TOT, field 29).
  - **The place.** `ID_MUNI_RE` is the outbreak's municipality of occurrence (field 11), though it is named RE and
    TabNet tabulates it as residence.
  - **2014.** No SDTA file exists for 2014 (FTP listings, 2026-10-09):
    - `SINAN/DADOS/FINAIS` holds SDTABR07–13 and SDTABR15–24;
    - `PRELIM` holds no SDTA;
    - `Dados_Abertos/SINAN` has no outbreak folder.
- **"Não se aplica" is a category, not a missing value**, on several forms (SIFC `LABC_IGG` 4: 15,353 of 27,186 recorded in 2021). TabNet's labels call it "Ign/Branco".

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

### Completeness and private coverage (measured 2026-10-05)

- IDB 2012 (tabnet.datasus.gov.br/cgi/idb2012/): A.17 `a17b.htm` (SINASC) and A.18 `a1801b.htm` (SIM), `a1802b.htm` (infant deaths): registered/estimated events by UF, 2000-2011, estimate = municipal events corrected by the 2008 Busca Ativa factors (Legal Amazon, Northeast); South, Southeast, MS and DF read 100.0 to 2009 (assumed); IBGE's base changes in 2010. The SIM consolidation `tabnet.datasus.gov.br/cgi/sim/Consolida_Sim_2011.pdf` gives 96.1% for 2011 where IDB gives 94.2%. RIPSA DEM.4.01/DEM.4.02 describe the indicators (SINASC municipal coverage from 2015 by capture-recapture); the municipal series was not located.
- ANS open data (dadosabertos.ans.gov.br/FTP/PDA/): `informacoes_consolidadas_de_beneficiarios-024` has monthly folders from 2021-05; `taxa_de_cobertura_de_planos_de_saude-047` and `dados_de_beneficiarios_por_regiao_geografica` hold the current year only; `beneficiarios_identificados_sus_abi` identifies plan holders found in SUS reimbursement. Older series: ANS TabNet (now anstabnet-ds.ans.gov.br), not retrieved. The `ans_beneficiaries` field stores the coverage label with a replacement character ("M?dico-hospitalar").
- www.ibge.gov.br answers 403 to curl with a browser user agent; ftp.ibge.gov.br answers. IBGE's sub-registro estimates are of civil registration, not of SIM or SINASC.

### CNES December files as municipal supply (measured 2026-10-05)

- **Layout.** `CNES/200508_/Dados/<DS>/<DS><UF><YY>12.dbc` on the mirror (the S3 key has no `dissemin/publicos` prefix). Compressed December files for 2005-2025: ST 277 MB, LT 13 MB, EQ 131 MB, EP 49 MB, PF 3,795 MB (SP 2023 PF: 68 MB, 0.5 GB peak, 28 s). EP starts 2007-04.
- **Keys.** EQ `TIPEQUIP` (one character) + `CODEQUIP` (two) is the kit's code without its leading zero (CT is '111'); LT `QT_EXIST` = `QT_SUS` + `QT_NSUS` (off by 17 in 2008, exact in 2015 and 2023); `VINC_SUS` is only 0 or 1; EP `DT_DESAT` 900001 means "not deactivated" and every team in a December file carries it; the team id is `IDEQUIPE`. Labels: `TAB_CNES.zip` (127 MB, `200508_/Auxiliar/`) members `CNV/TP_ESTAB.CNV`, `Esp_leit.CNV`, `Equip_Tp.cnv`, `DBF/EQUIPE.dbf`.
- **The team typology changes in 2020.** December 2019 teams are types 02, 01, 06, 04, 03, 45; December 2020 are 70 (ESF), 71 (ESB), 72, 76 (EAP). ESF-type teams go from 43.6 k to 49.0 k across the change.
- **Physicians in PF** carry CBO 2231xx (the original 2002 codes, flagged "not in the current CBO 2002" by the label pack) as well as 225xxx. Distinct `CNS_PROF` physicians summed over municipalities are 805,369 in 2023, above the profession's own count (about 570,000, CFM): a CNS is not one per person, and a person can work in several municipalities.

### SIM codes changed in 1996 under the same names (measured 2026-10-05)

The SIM kits `CID9/TAB/OBITOS_CID9_TAB.zip` (1997 files) and `CID10/TAB/OBITOS_CID10_TAB.zip` (2024) carry **same-named `.CNV` files with different codes**. Checked against the layout `sim2025.txt` (CGIAE/DASNT/SVS, 07/2025) and against the records (cause of death by code, RJ 1990 and 1995, Acre 1996 and 2000):

| Field | 1979-95 (`TIPOVIOL`, `LOCOCOR`) | 1996 on (`CIRCOBITO`, `LOCOCOR`) |
|---|---|---|
| violent death | 1 homicide, 2 suicide, 3 accident, 4 other, 0/9 ignored | **1 accident, 2 suicide, 3 homicide**, 4 other, 9 ignored |
| place | 1 hospital, **2 street**, 3 home, 4 other | 1 hospital, **2 other health establishment, 4 street**, 3 home, 5 other, 6 indigenous village, 9 ignored |

The 1996 `.DEF` binds `CIRCOBITO` to `TIPOVIOL.CNV`, which in that kit is the new coding. The schema, not the year, decides in 1996-98: `DOFET96` and `DOFET98` still carry `TIPOVIOL` with the old codes, `DOFET97`, `DOFET99` and `DORES` 1996 on carry `CIRCOBITO` with the new ones. `SINASC` kits split the same way (`ANT` 1994-95, `NOV` 1996 on; `RACACOR` 1 is Amarela before 1996, Branca after).
- **Extent.** 35 same-named codelists differ between the two eras of the kits (SIM 21, SINASC 14), 19 of them in meaning (SIM TIPOVIOL/CIRCOBITO, LOCOCOR, ESTCIV 5, GRAVIDEZ, INSTRUC, SEMANAS, PARTO, IDADEMAE, NUMFILH; SINASC RACACOR, GESTACAO, PRENATAL, GRAVIDEZ, INSTRUC, PARTO, PAISES), the rest an age band the 1979-95 kit leaves "Ign" or a spelling. EVALUATION 2026-10-05 (SIM code eras).
