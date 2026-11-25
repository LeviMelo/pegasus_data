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
- **Two clocks** (2026-10-24, ADR-0200). LIST's time is the server's wall
  clock, truncated to the minute. MDTM's is UTC with seconds. The wall clock is
  UTC−3 for every date, including the summer-time months before 2019 (files
  dated 2018-02-05 read 09:45 by LIST and 12:45:17 by MDTM). Measured on 1,290
  pairs in the catalogs and 6 files live.
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
  file holds and none fewer (`docs/history/DEFECTS.md`, HI-23). That was measured
  on inflated payloads before the first-party inflater; of 6,551 real `.dbc`/`.dbf` blobs up to 8 MB
  (2026-10-14) none declares more records than its stream inflates to, and the
  inflater refuses one that does as damaged (ADR-0169). A DBC declaring zero records
  has no stream and is an empty table.
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
- SINASC's first layout (DNR, 1994-1995) sits in three places for AC 1995 (listed 2026-11-09): `ANT/DNRES/DNRAC95.DBC` and `1994_1995/Dados/DNRES/DNRAC1995.dbc` (293,208 bytes each) and `ANT/DNRES/DNRAC1995.dbc` (222,112 bytes); the two ANT files carry the same server minute (2020-01-27 12:22), so the newest-edition rule cannot choose and a read refuses the publication (contradictory schema signatures). Decoded: all three hold 12,635 records; the two 293,208-byte files are byte-identical, and the 222,112-byte one is the same publication in a narrower layout (field widths 8/4/8/1/7... against 8/8/9/10/9..., `CODIGO` for `CONTADOR`). One publication in two layouts, not two editions. DNR is declared no event source; the population account's 1994-1995 births come from SINASC-DN.
- SINASC was published byte-identically into two trees during a transition
  (2026-08-30, F §3w).
- SIM publishes 27 per-state files plus a consolidated `DOBR` file for the same
  year (commit `2e85e97`, 2026-08-30).
- **The national file cuts what the state files hold** (header census of all 3,149 SIM and SINASC files, 2026-11-21;
  ADR-0230). The national DBF should be at least as wide as the widest state file, and is not: SIM's cause lines in
  1999-2008 and 2011-2017 (`DOBR2012` `LINHAA` 10 characters, `DOES2012` 20; `LINHAII` 15-20 against 30) and
  SINASC's `CODANOMAL` (congenital anomalies) in 2006-2013 (9-16 against 20). On ES 2012 the two readings are equal as
  multisets on every column but `LINHAA` (18 rows), `LINHAC` (2), `LINHAD` (28), `LINHAII` (8): `*I10X*E149*I420`
  becomes `*I10X*E149`. In 2009 each cuts something (national `LINHAA`/`LINHAB`, states `LINHAD`/`LINHAII`). SINASC
  2014-2017 is published in two trees (`NOV`, `1996_`) whose state files pad some fields (`SEXO` 4 characters).
  The underlying cause is equal in both.
- **The infant-death link's yield falls with age at death** (defect sweep, AL 2019, `sim_infant_deaths_to_sinasc`, 654
  deaths): linked 79.6% at day 0, 69.5% at 1-6 days, 72.8% at 7-27, 53.2% at 28-90 and 25.0% at 91-364 days; 24% of the
  deaths of children born the year before against 67.5%. Both passes need the certificate's birth weight or the mother's
  age, which SIM leaves blank for 50% and 36% of deaths at 91-364 days (5% and 16% at day 0). The linked share is not a
  sensitivity: a study of infant deaths by age corrects or bounds by age band.
- **SINASC's `CODANOMAL` misses many anomalies a baby is born with** (measured by the ABNc study t04, 2026-11-22, on
  `sim_infant_deaths_to_sinasc` 2013-2023). Of 748 infant deaths whose underlying cause is spina bifida (Q05), 517
  (69%) link to a birth record, level with the link's overall 66-72%, so the link is not the bottleneck. The birth
  record codes Q05 in 298 of the 517 (58%), any neural tube defect (Q00-Q07) in 360 (70%) and any anomaly in 399 (77%).
  Conditional on the baby dying in infancy: recording among survivors may differ. Published: about
  40% of defects unreported (Luquetti & Koifman, Cad Saude Publica 2009, PMID 19649413; 2010, PMID 20877936).
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
  (these two state-months checked; 2026-09-30). Every SP AIH is in the same month's RD in nine more reads of Acre and
  Roraima, 2008 to 2025 (AC 2008-06, 2010-06, 2013-06, 2016-06, 2019-01, 2023-02, 2023-01 to 03; RR 2023-01,
  2025-06; 2026-10-24, ADR-0199). On the matched AIH SP's residence, principal diagnosis, admission date and facility
  equal RD's in every AIH of AC 2008-06, 2013-06 and 2023-01 and RR 2025-06.

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
- **Units are declared per column** (`curation/roles`, `unit` with its document line; `pegasus-data roles <dataset>`; ADR-0184).
  - SIH's `VAL_*` are nominal reais, "valores correntes" (`GEOCOD_AIH.pdf` p.5, the CEM-USP dictionary; the SIH layout does not name
    the currency) of the competence `ANO_CMPT`/`MES_CMPT`; `VAL_TOT` = `VAL_SH` + `VAL_SP` + the two federal complements on all 2,959,773
    Alagoas AIHs 2009-2025. Only `US_TOT` is documented as dollars.
  - SIA's values are reais of the production competence (`MANUAL_SIA_Maio_2008.pdf` p.46): `AP_CMP` for APAC, `PA_CMP` for PA. `AP_CMP`
    equals the processing month `AP_MVM` on 92-94% of Alagoas AD 2012 and 2025 and is never later (up to 3 months earlier).
  - SIM's and SINASC's `SERIESCFAL`/`SERIESCMAE` are a grade number read with the schooling level (SIM-DO 2020: level 1 grades 1-4,
    level 2 grades 5-8, level 3 grades 1-3, blank for the rest), not codes.
  - SIASUS-AN's `AN_ALBUMI`, `AN_PESO` and `AN_HB` mix scales (28.2%, 4.5% and 8.2% of positive values are tenths without the decimal
    point); `AP_NUIDADE` and `IDADEPAC` carry their unit in a companion column per row.
- **TabNet's SIH "Internações" excludes long-stay continuation AIHs
  (`IDENT` 5); its "Valor total" includes them.** Its Acre file for
  September 2009 (`niac0909.dbf`) returns no table, so TabNet's 2009 Acre
  total omits that month (2026-10-03).
- **Sex codes differ by system**: SIHSUS `1`/`3`, SINASC `1`/`2`, SINAN
  `M`/`F`; thirteen systems ship a `SEXO.CNV` (F §3e). SIH's own table maps
  `1→Masculino`, `2→Feminino` and `3→Feminino` (`docs/history/DEFECTS.md`).
- **Race/colour codes differ**: Parda is `03` in SIH's `RACA_COR` (two digits: 01 Branca, 02 Preta, 03 Parda, 04 Amarela,
  05 Indígena, 99 Sem informação; the kit's `RACACOR.CNV` and the SISAIH01 layout agree, and every SIH-RD file read, 2009-2025,
  holds only these), `4` in SIM and SINASC (one digit; 3 is Amarela). This line said "`3` in SIHSUS.RACA_COR" until 2026-10-14:
  SIH has no one-digit race table. A consumer that asks `pg.levels` for codes `0`-`9` of SIH's `RACA_COR` gets none decoded;
  it asks for the codes its records hold.
- **SIH-RD's `GESTRISCO` is asked only of sterilisation AIHs and RD fills `1` on every other** (measured 2026-10-14, raw
  and lake). SISAIH01 (`sources/Layout_SISAIH01.pdf` p. 6/8, field 88 `ST_GESTRISCO`, "Gestação de Alto Risco (Somente para
  Laqueadura)") codes `0-Sim 1-Não`; TabNet's `RD2008.DEF` binds the field to `SIMNAO` (`1` Sim), the opposite. Raw
  `RDAL1607.dbc` (15,734 AIHs): `1` on 15,733, 5,850 of them men; the one `0` is a woman on a laqueadura. RD 2014-2023, all
  states: `1` on all 969,672 AIHs of "parto normal em gestação de alto risco" as on 9,450,303 of "parto normal"; `0` on 148,028
  of 859,946 AIHs of the three laqueadura procedures (0409060186, 0409060313, 0411010042) and on 4,747 of 118 million others;
  among laqueadura AIHs the indication `CID_NOTIF` is an O-chapter code in 5.6% of the `0` and 1.3% of the `1`. So `1` is a
  default outside sterilisation, and the column carries no information for any other admission (an infarction study read "Sim"
  on 5,517 men). The curation codes it by the layout and declares `1` not recorded (ADR-0180).
- **SIH `INSTRU`, `VINCPREV`, `CONTRACEP1/2` and `CNAER` are almost always the "not classified" code** (RD 2010, 2016, 2023,
  36.6 million AIHs): `INSTRU` 0 (`Ignorado/não se aplica`, 98.8%), `VINCPREV` 0 (`Não classificado`, 99.99%), `CONTRACEP1/2` 00
  (98.8%, 99.2%), `CNAER` 000 (99.99%). The layout lists INSTRU 1-4, VINCPREV 1-6 and the contraceptives 01-12 only. A level
  of schooling was held by 0.7% of AIHs in 2009 and 2.6% in 2024. `RACA_COR` `99` is 34-36% of AIHs in 2009-2012, 19% in
  2022, 2.8% in 2023 and 0.0% from 2024, with `03` rising 43% -> 55% -> 57%: race shares do not compare across 2022 and
  2023. `NACIONAL` is `010` on 99.7% and does carry information (Venezuelans in Roraima: 55 AIHs in 2012, 7,604 in 2019).
- **SIM-DO's two schooling columns** (measured 2026-10-14, national files 2009-2025): `ESC` (years bands, 1 Nenhuma ... 5 12 anos
  e mais, 9 Ignorado) is filled every year; `ESC2010` (level: 0 Sem escolaridade ... 5 Superior completo, 9 Ignorado) is empty in
  the 2011 files that carry it and filled from 2012 (952,366 of 1,181,166 deaths), on 98.9% of the deaths ESC fills from 2014. Of
  2014-2025 deaths with both, `ESC` 1 is `ESC2010` 0 on all 2,679,156: one measurement in two scales. `ESC` 0 (no code of the
  layout; 70,688 deaths in 2014, 83,226 in 2012, none after 2014) is read as not recorded. `ESCFALAGR1` and `ESCMAEAGR1` are
  filled from 2014 (130 and 2 deaths in 2012, none in 2013).
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
- **SINASC's `SEXO` is coded three ways by the files** (measured 2026-10-14 on DNBR2009-2024, 44,934,834 births; corrected: the 2026-10-04 line said no file wrote the letters). `1`/`2`/`0` in 2009, 2012-2013 and 2015-2024; `1`/`2`/`9` in 2010 and 2011 (442 and 436 births, no `0`); `M`/`F`/`I` in 2014 alone (1,526,907 / 1,451,693 / 659). The 1996-2019 evolution document (`SINASC_Estrutura.pdf`, field 16) codes it `1` M, `2` F, `0` I; the 2019 layout and the DN dictionary list the letters; TabNet's current `SEXO.CNV` decodes `0 1 2 F I M` and the 1994-95 kit `3-9` as Ignorado. `9` is no layout's code: its births have the profile of the ignored sex of the other years (Q56 on 41-46% against 32-42% of the `0` and 34% of the `I`; a congenital anomaly flagged on 64-68% against 51-66%; mean weight 2.4 kg against 3.2 kg for sex 1 or 2) and replace the `0` exactly where it is absent, so the curation declares it Ignorado for 2010-2011 only (ADR-0189). Every year decodes to Masculino, Feminino and Ignorado; a table keyed on the raw code lists `1` and `M` apart, a table keyed on the label does not.
- **SIH-RD writes the Federal District's residents with administrative-region codes until 2017-12** (measured 2026-10-04, DF files): `MUNIC_RES` holds 530020 to 530180 and 530135, which are no municipality (Brasília is 530010). Read: January of 2008, 2010, 2012, 2014, 2015, 2016 and 2017, and December 2017, carry them (January 2008: 2,220 of 7,754 rows; January 2017: 11,941 of 16,649); January 2018, 2019 and 2022 carry none (2018: 12,207 of 15,631 rows are 530010). The whole of 2017 in the DF files: 11,025 rows 530010 and 140,876 region codes, 151,901 together, against TabNet's 152,622 residents of Brasília (the other 721 sit in other states' files). Years before 2008 are unmeasured. Curation recipe `MUNIC_RES_municipio` maps them inside 2008-01 to 2017-12; `MUNIC_RES` is untouched. `MUNIC_MOV` (the hospital's municipality) carries them in the same years (DF files of the lake, 2026-11-22: 111,115-125,592 rows a year in 2010-2017, none from 2018); `MUNIC_MOV_municipio` maps them in the same window.
  Other systems, DF files: SIM-DO (2000, 2010, 2017) and SINASC-DN (2000, 2017) write 530010 only; SINASC-DN 2010 has 6 of 44,251 rows with one region code. SIA-PA `PA_MUNPCN` carries them (January 2010: 4,192 of 127,264 rows, 20 codes; January 2017: 50,666 of 197,152, 24 codes) and so does CNES-ST `CODUFMUN` (2010: 2,511 of 5,583; 2017: 1,876 of 4,081). Windows (measured 2026-10-05 on DF files, one month per step, bisected at both edges): SIA-PA `PA_MUNPCN` has none in 2008-07 (0 of 113,624), 19 of 116,709 in 2008-08, then every year and still in 2026-06 (26,598 of 531,506): mapped by `PA_MUNPCN_municipio` from 200808, open-ended; CNES-ST `CODUFMUN` from the first file, 2005-08 (1,305 of 3,256), to 2017-11 (1,358 of 2,522), 1 of 2,589 in 2017-12 and none from 2018-01: mapped by `CODUFMUN_municipio` for 200508-201712 (CNES-LT and -EQ 2012-01 carry them too, 392 of 715 and 5,838 of 11,702, none in 2018-01; the recipe is shared by all CNES types). SIA-PA has other 53xxxx codes no region list holds (530005, 530015, 530000, 5399xx; 2022-01: 417 rows): left as written. The pre-2008 PA layout has no `PA_MUNPCN`. SINAN has only national files, not read.
- **SINASC's newborn `RACACOR` is the mother's declaration** (measured 2026-10-04, SINASC 2020-2022 linked to SIM infant deaths): where both are known, `RACACOR` equals `RACACORMAE` in 50,078 of 50,078 records. Codes 1 Branca, 2 Preta, 3 Amarela, 4 Parda, 5 Indígena in both SIM and SINASC (layouts); TabNet's `RACACOR.CNV` abbreviates them (`Bra`, `Amar`, `Indig`), and SINASC's pre-1996 kit files a different table under the same name (1 Amarela, 2 Branca, 3 Indígena, 5 Preta).
- **Whose colour the birth record holds changed with the 2011 form** (measured 2026-11-21, SINASC-DN 2000-2024 lake).
  `RACACORMAE` is filled on 0 births of 2009, 2.5% of 2010, 55% of 2011, 93% of 2012 and 97-98% from 2021; wherever both
  are filled `RACACOR` equals it (1.0000 every year, 0.9996 in 2023). Preta is 3.2% of births in 2000, 1.6% in 2010,
  4.1% in 2011, 5.5% in 2012 and 8.1% in 2024; Branca 55.8%, 46.8%, 43.5%, 39.0%, 33.6%. So the line above holds from
  2012; to 2010 `RACACOR` is the newborn's colour, another quantity, and 2011 is a mixture (ADR-0226).
- **SIM, who certifies and where, by municipality** (measured 2026-11-21, SIM-DO 2013-2023 by residence;
  `papers/race_at_death/analysis/context.py`). Of 383,971 infant certificates with a valid age, 2,148 have no `SEXO` and
  317 no municipality of residence. On the 291,677 linked infant deaths of White, Brown and Black mothers, `ATESTANTE` is
  the attending physician on 54%, a substitute on 22%, other on 10%, blank on 7%, a death verification service on 3.7%
  and a medical examiner on 3.2%; `LOCOCOR` is hospital on 95%. Between municipalities the share of natural deaths
  certified by a verification service runs from 0 to 38% (median 0.8%), of external deaths by a medical examiner from 0 to
  100% (median 85%), and of all certificates with no race from 0 to 43% (median 2.2%; infants 4.3%). The one-to-one infant
  link finds 80-81% of certificates recorded White, Brown or Black alike and 62% of those recorded Indigenous.
- **SIH records a mother's race differently from her own declaration** (measured 2026-11-21, `sinasc_births_to_delivery_admission`
  2012-2023, 13.45 M deliveries with both races): of mothers who declared themselves Black on SINASC, the admission
  (`RACA_COR`) records Black for 0.36, Brown 0.53, White 0.10, and leaves 21.8% blank; White mothers White 0.76, Brown
  mothers Brown 0.80. The share recorded Black varies between hospitals from 0.01 to 0.64 (10th to 90th percentile); net, the
  admissions record 0.74 as many Black mothers as declared themselves Black.
  The admission's race is filled from 2023: among Black-declared mothers' linked deliveries it was blank on 34.5% in 2012,
  21.5% in 2022 and 2.8% in 2023 (youth admissions: race filled on 62-80% to 2022, 97% in 2023, 100% in 2024).
- **SINASC's colour fields after the 2011 form** (measured 2026-11-22). `RACACOR` equals `RACACORMAE` on every record that has
  both, from 2011: it is the mother's race copied, not the newborn's. The newborn's own colour (`RACACORN`) is filed on
  52 records of 2012 and 160 of 2013, so it cannot be used. `TPFUNCRESP` (who filled the record: 1 physician, 2 nursing,
  3 midwife, 4 registry clerk, 5 other) is absent before 2014 and filled on 94-97% from 2014; among linked deliveries,
  "other" (766,688 in 2016) and nursing (691,407) fill most records.
- **SIM's certifier and investigation fields** (infant deaths, measured 2026-11-22). The certifying physician's
  registration (`CRM`) is filed for 2014-2018 only (98%), with no state, so a physician is identified as state plus CRM.
  `TPPOS` (investigated) is filled on 72-77%, and `FONTEINV` (the investigation's source: 1 committee, 2 home visit or
  family interview, 3 health establishment or chart, 5 SVO, 6 IML, 8 several) on about half. `FONTES` is filled from 2016.
- **Census 2022 public sample microdata** (released 2026-08-31, `ftp.ibge.gov.br/Censos/Censo_Demografico_2022/
  Microdados_e_Areas_de_Ponderacao/`; read 2026-11-22). Fixed-width files by state, about 1 GB for the country. The person
  record has the state but no municipality and no weighting area. Age is in five-year groups (P0180), and there is no
  order number of the mother, only whether she lives in the household (P0300). The relationship to the person responsible
  (P0170) uses the 2010 codes, and the level of instruction (P0770) is compatible with 2010. New against 2010: who gave
  each person's information (P1210, with the informant's order number P1220). The pairing script is
  `data/probes/census2022/pairs.py`, with 5.33 M mother-child records under 25.
- **SINASC writes 7-digit municipality codes to 2005** (measured 2026-11-21): `CODMUNRES` and `CODMUNNASC` are 7
  digits on every birth of 2000 and 2005, 6 from 2008 (lake years 2000-2024).
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
  SINAN pack it in the leading digit of `IDADE`/`NU_IDADE_N`. `COD_IDADE` is the
  unit of `IDADE`: 0 unknown, 2 days, 3 months, 4 years, 5 = 100 + `IDADE` years
  (CEM/USP AIH dictionary, `sources/sih_batch/usp_dict.txt`; measured against
  `NASC` and `DT_INTER` on SIH-RD 2023, 13.36M rows; `_age.UNITS`, ADR-0070).
  *Corrected 2026-11-08: this line said no unit codelist was found.*
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
  (no duplicate `(AP_AUTORIZ, AP_CMP)` in any slice read; corrected 2026-10-14: ATD nationally holds 2,029 such pairs twice in 15.6 million rows). `AP_TPAPAC` is 1 on the first row, 2 on later months, 3 on a
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
- **SIA ATD itself (measured 2026-10-14, the lake of every UF, 15,579,053 rows).** The files begin with competence **2014-08** (`ATDAC1408.dbc`;
  27 UFs, 95,928 rows that month; `AP_MVM` 201408-201412 are the five months of 2014). An APAC is up to three monthly rows (5,590,747 APACs, 2.79
  rows each: one row 421,205, two 352,991, three 4,814,579). `AP_TPAPAC`: 1 on 5,491,060 rows (every one has the month of `AP_DTINIC` equal to
  `AP_CMP`; 5,491,059 APACs hold one and it is on their earliest competence), 2 on 10,056,063, 3 on 31,842 (single-row APACs), 4 on 88 (no layout value);
  67,846 APACs began before the first file and show later months only. `AP_CIDCAS` is `0000` on 76.2% of the authorisations of type 1 or 3 in 2014 and
  88.1% in 2025; N18 on 23.7% in 2014, 17.0% in 2015, 8.7% in 2023, 8.4% in 2025. `ATD_CARACT` 1 ('caso novo') is 42.9% of them in 2014 and 17.8%
  in 2023 and is no new patient: 403,686 of 566,867 patients hold a flagged APAC, 173,217 two or more, and the first dialysis precedes it by a median 1.35
  years (the dataset note in `datasets/declared.yml` has the rest). The laboratory fields (`ATD_HB`, `_FOSFOR`, `_KTVSEM`, `_TRU`, `_ALBUMI`, `_PTH`)
  are 4-character text: zero in 17-30% of the rows (the export of a blank), `9999` on 14,940 rows (14,939 with it in five of the six at once, RS above
  all), values at several scales (10, 100 and 1000 are one 10.0 g/dL), comma decimals, and letters from shifted columns (`S`, `N`, `N180`). AN
  (2009-2014) has the same fill: the all-nines of each field's width on 9,091 lines (`AN_ALTURA` 999, `AN_PESO` 999, `AN_DIURES` 9999, `AN_GLICOS` 9999,
  `AN_ALBUMI` 99).
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
  `99` is the not-recorded value of the two-digit counts (CONSPRENAT
  2022: 11,107 at `99`, single records at 66–72), named by no layout for them
  (2026-10-07, `scripts/propose_missing.py`); declared missing from 2026-10-14 (ADR-0189), with the national spikes: DNBR2009-2024, `99` on 223,344 births
  of CONSPRENAT, 52,296 of QTDFILMORT, 27,715 of QTDFILVIVO, 30,468 of APGAR1, 23,887 of APGAR5, 2,079-3,389 of the three previous-pregnancy counts and
  743 of IDADEMAE, against at most 58 for any other value above 60 (80 in CONSPRENAT); PESO `9999` on 107 births.

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

### 2.3a TabNet's state territorial tables (measured 2026-10-25; ADR-0210)

TabNet's state forms classify by `territorio/{UF}_macsaud.cnv` and `{UF}_regsaud.cnv` (`sih/cnv/nrro.def`), not by `br_macsaud.cnv` and `br_regsaud.cnv`. The state tables place 110001 (macroregion 1101) and 110002 (region 11001), which the national ones leave in "Ignorado - RO", and agree with them on every other municipality. Their labels decode wrongly with the national table's encoding ("CafÚ").

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

- **SINAN's notifying unit is stored as a number (2026-10-12).** `ID_UNIDADE` has 2 to 6 digits on a sixth of DENG 2023's
  notifications and of TOXC 2023's ("477", "11843"). Zero-filled to CNES's 7 digits, the commonest short codes are CNES
  establishments registered in their notifications' municipality: TOXC 8 of 8 (0000477 is Hospital Oswaldo Cruz, Recife),
  DENG 20 of 20. Declared `width: 7` on the column's role in every SINAN agravo. The lake keeps the value as filed; a
  join restores the width (PegaSUS `facility.facility_cube`).

## 4. SIGTAP (2026-08-19, F §3d)

- HTTPS times out on `sigtap.datasus.gov.br` and
  `tabela-unificada.datasus.gov.br`; HTTP on port 80 answers 200.
- Exports are on `ftp2.datasus.gov.br/public/sistemas/tup/downloads`: 224
  monthly vintages, 200801 to 202608. Every table ships its own fixed-width
  layout file, and the layout drifts between vintages (ARCH §14c).
- **History** (2026-11-21, `docs/evaluation/2026-11-21-sigtap-history.md`): 227 exports 200801 to 202611, one file per month (names carry a
  `_v<yymmddhhmm>` stamp from 201301), 5,785 procedure codes ever. `tb_procedimento` has three layouts (a column added 201209; money 10 to
  12 characters from 202506), money in centavos; the FTP stalls a session after about twenty transfers.
- The newest export gave 44,984 entries; `tb_ocupacao` holds 2,719 occupation
  codes at one width.

- **Which instruments record a procedure** (2026-10-11, `docs/evaluation/2026-10-11-sigtap-instruments.md`). `rl_procedimento_registro`
  (CO_PROCEDIMENTO 10, CO_REGISTRO 2, DT_COMPETENCIA 6) lists, per procedure, the instruments it may be recorded on; `tb_registro`
  names them: 01 BPA Consolidado, 02 BPA Individualizado, 03 AIH Proc. Principal, 04 AIH Proc. Especial, 05 AIH Proc. Secundário,
  06 APAC Proc. Principal, 07 APAC Proc. Secundário, 08 RAAS Atenção Domiciliar, 09 RAAS Atenção Psicossocial, 10 e-SUS APS.
  The 202609 export has 5,023 procedures; **no procedure lists 08** (all but 1,494 of SIA-SAD's 3.32 M RAAS-AD rows carry procedures registered on 02), and a
  procedure retired before the export is absent. The APAC files' `AP_PRIPAL` is always 06; the SIA-PA production file holds
  every instrument (`PA_DOCORIG` P, S, C, I, A, B), so SIGTAP's code tree is the code tree of all of SIA but each APAC family
  holds only what 06 registers.

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

- **BNAFAR stock, read by filter (2026-10-10, `sources/bnafar.py`, `docs/evaluation/2026-10-10-medicines.md`).** A row is an
  establishment x CATMAT product x lot x day of stock position (from 2023-12 at least; `anomes_posicao_estoque` 201901 is empty).
  `codigo_catmat` matches whole and exactly: the product is `BR` + the 7-digit CATMAT item + a national supply-unit suffix
  (`U0042` comprimido, `U0041` cápsula, `U0062` a 100 mL bottle...), not the PDM's own unit number. The open catalogue
  (`dadosabertos.compras.gov.br/modulo-material`: PDMs `3_consultarPdmMaterial`, items `4_consultarItemMaterial`, 1,901 PDMs in
  class 6505; no key, 500 per page) lists items and no unit codes. The medicines' CATMAT items: pirimetamina PDM 10768 (25 mg =
  item 268158), sulfadiazina 12314 (500 mg = 267765), espiramicina 7021 (1.5 MUI = 343494), folinato de cálcio 1930 (15 mg = 268292).
  The BPS endpoint (`economia-da-saude/bps`) filters by item number without the unit.
  Verdicts: 35 use DEMAS (ESAVI, mpox, yellow fever, SIES, BNAFAR, COVID occupancy, SIASI/SESAI, SISAB, SIAPS, health-region
  mapping, BPS), 49 original with DEMAS as fallback, 29 not relevant.

- **Sources off the FTP, intake (2026-10-10, `intake.py`, ADR-0162, `docs/evaluation/2026-10-10-intake.md`).** DEMAS tables whose
  rows are not stable under offset paging (BNAFAR's live stock: consecutive pages overlap by a third, the same request returns
  different rows) are read by splitting the filter by state until it fits one 1,000-row page; static tables (SIES, ESAVI, yellow
  fever) page stably. **Yellow-fever monitoring** (Portal `Febre Amarela/fa_casoshumanos_1994-2026.csv`, `fa_epizpnh_1994-2026.csv`,
  semicolon, Latin-1, ends with an empty row; dictionary `Dicionario de variaveis.pdf`): 2,911 human cases (1994-2026; ID 1-2911) and
  2,637 epizootics (2000-2026), placed at the probable place of infection and of occurrence, dated by year and month columns; DEMAS
  holds one copy more of the first case and lacks the month of 13 epizootics, so the Portal is the source. **SIES** (`vacinacao/sistema-de-informacao-de-insumos-estrategicos`,
  Portal `SIES/csv/sies_csv.zip`, dictionary `dicionario-de-dados-do-sies-ok.pdf`): 137,914 rows, secretariat x supply x month x
  kind (`ORIGEM` Solicitado / Distribuido), 2018-2026; the `IBGE` column holds the secretariat's seat (27 codes), so the unit is the
  state secretariat. DEMAS equals the file row for row (read as the declared origin).
  **SI-PNI dose records** (Portal `PNI/csv/vacinacao_<jan..dez>_<year>_csv.zip`, 2020 on; dictionary
  `dbbni/Dicionario_tb_ria_rotina.pdf`, which lists fields, not code lists). There is one row per applied dose, with a
  pseudonymous person hash. The files hold 1–several million rows a month and about 215 GB zipped for 2020 to 2026-09.
  They are Latin-1 and `;`-separated. The code lists are the files' own descriptor columns beside each code
  (`sg_imunobiologico`/`co_vacina`, `ds_tipo_dose`/`co_dose_vacina`). `co_vacina_fabricante` is mostly empty and does
  not pair with `ds_nome`. `nu_idade_paciente` holds -1, 120 and 220. **Size, measured (2026-11-08):** 81 monthly files,
  200.1 GiB zipped for 2020-01 to 2026-09 (2021 alone 54.5 GiB), from the bucket's HEAD answers; five months of 2023 landed
  in October gave 93.6 million rows and 8.2 GiB of Parquet for 12.8 GiB zipped, so the whole is about 1.47 billion rows and
  128 GiB landed. The bucket rewrites published months (September 2026 on 2026-11-08); October and November 2026 answer
  403. Declared as the on-request source `pni_doses` (`PNI.DOSES`, curation/intake.yml): built only by naming its years.

## 6. IBGE

### 6.1 Population

  **Correction (2026-10-10):** the endpoint holds each lot's current position (no lot at two dates; 3,000 SP levothyroxine rows all of 2026-10), not a history: present stock by establishment, never a series.
- On the DATASUS tree: POPSVS (municipal), POPTCU, POP, censo, and `projpop`
  (UF-level projections 2000–2070, which complement rather than supersede
  POPSVS) (F §1 V7, V8). The Ministry's published rates divide by POPSVS
  (below; *corrected 2026-11-08: this line still called it open*).

- **The Ministry's tables divide by POPSVS** (2026-10-03). TabNet's
  population form (`ibge/cnv/popsvs2024br.def`, "Estudo de Estimativas
  Populacionais por Município, Idade e Sexo 2000-2025", RIPSA/CGIAE) reads
  `IBGE/POPSVS`. Its 2022 equals the local POPSVS in all 27 states:
  210,862,983. OQ-12 is settled.
- **Dados_Abertos republishes POPSVS** (2026-11-08). `Dados_Abertos/SINAN/Populacao_SVS/{csv,json,xml,parquet}/POPyy`
  (POP00-POP25; columns `COD_MUN` 7 digits, `ANO`, `SEXO`, `IDADE`, `POP`) equals `IBGE/POPSVS`: POP22 against
  POPSBR22, all 902,340 municipality × sex × age cells identical, 210,862,983 people. The prefix `POP` is shared with
  IBGE's older `IBGE/POP/POPBRyy` (1980-2012), a different series.
- **What POPSVS is** (2026-10-14; `curation/populations.yml`, returned with `load_population` as `pegasus.series`).
  - **Producer and vintage.** The Ministry of Health (SVSA/CGIAE/Coesv), by the method of RIPSA's municipal-estimates committee,
    with IBGE's maps. The files listed 2025-01-07 (2000-2024) are the 2024 edition, built on IBGE's *Projeções da População,
    Revisão 2024* (after the 2022 Census) and on IBGE's municipal estimate of 1 July 2024 (Ministry's note
    `ftp.datasus.gov.br/dissemin/publicos/IBGE/doc/NT-POPULACAO-RESIDENTE-2000-2024.pdf`, 521,092 bytes, read in full 2026-10-14;
    IBGE notes 01/2024; Fiocruz OPGH note 1/2025 for the editions: 2013 → 2000-2015, 2018 → 2000-2021, 2024 → 2000-2024).
    This confirms what was relayed 2026-10-05 (below). `POPSBR25` (listed 2025-10-29) is later than the note, which does not describe it.
  - **Reference date and years.** 1 July. IBGE's state series is estimates for 2000-2022 and projections for 2023-2070 (notes 01/2024,
    Apresentação), so POPSVS 2023-2025 rest on projected state totals; 2024 is forced to IBGE's published municipal total.
  - **Method.** Census sex-age populations of 2000, 2010 and 2022 per municipality, adjusted to the state totals of the projection;
    RCoortes smoothing of each cohort's growth (intermediate region against state, municipality against region; 2000-2010 and
    2012-2022); mid-period populations, interpolation between; sums by sex and age equal the state projection throughout.
  - **Why Alagoas grows 0.017% in 2022 and 0.007% in 2023** (POPSVS totals 3,217,819 → 3,218,381 → 3,218,607; Brazil
    210,103,642 → 210,862,983 → 211,695,158, +0.361% and +0.395%). The state total is IBGE's projection (births, deaths, internal and
    international migration; interstate migration from the 2022 Census's fixed-date question, held through 2022 and falling to 70% of
    its 2022 rate by 2040). Registered births less deaths of Alagoas residents (SINASC-DN and SIM-DO lakes) are 22,620 in 2022 and 24,578 in 2023
    (2021: 23,718), about 23,200 and 23,600 between the 1 July dates, so the +562 and +226 imply a net out-migration of about 22,600 and
    23,400 a year (0.70% and 0.73%); Brazil's implied net balance is -171,700 and -212,600 (0.08% and 0.10%). Registered (not
    IBGE's corrected) events, spread evenly over the year: the order of magnitude, not IBGE's published component, which the note does
    not print by state. The state's growth was +1.25% in 2001, +0.43% in 2010 and +0.09% in 2021: a decline, not a break in 2022.
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
  - **POPSVS 2022 is IBGE's *Projeções Revisão 2024*** (IBGE notes liv102111 and liv102112, relayed 2026-10-05; the Ministry's note and liv102111's periods and migration sections read 2026-10-14): a demographic
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

### 6.3a Census 2022 below the municipality: the Grade Estatística, tract aggregates, CNEFE (read 2026-10-24; ADR-0203)

- **Grade Estatística 2022** (`geoftp.ibge.gov.br/recortes_para_fins_estatisticos/grade_estatistica/censo_2022/`, Notas
  metodológicas 01/2025): 56 zipped shapefiles `grade_estatistica/grade_idNN.zip` (711 MB), also `grade_1km` to `grade_500km`;
  14,127,809 cells (5,486,725 of 200 m in urban tracts, 8,641,084 of 1 km); Albers equal-area SIRGAS 2000 (−54°, −12°, −2°/−22°,
  5,000,000 E, 10,000,000 N), the shapefiles in geographic SIRGAS 2000. Fields `ID_UNICO`, `nome_1KM` … `nome_500KM`,
  `QUADRANTE`, `TOTAL` (people), `TOTAL_DOM` (occupied households, private and collective); no sex, age or municipality. The 1 km
  name is the south-west corner in km (`1KME6300N8809`: 6,300,000-6,301,000 E, 8,809,000-8,810,000 N); the 200 m name is the west
  edge and the **north** edge in hectometres (`200ME63250N88392`: N 8,839,000-8,839,200). People placed by CNEFE's coordinate levels
  1-4 only: 203,002,064 of the census's 203,058,293 (levels 5 and 6, 56,229 people, left out), households 72,546,543 of 72,560,624.
- **Agregados por Setores Censitários** (`ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/`,
  dictionary of 2026-05-20): per tract CSVs by theme (basic, literacy, three household parts, colour or race, **demography**,
  parentage, deaths, indigenous and quilombola), also by neighbourhood, district, subdistrict and municipality. **Sex × age per tract
  exists**: the demography file (22 MB zip, 458,772 tracts) has `V01006` residents, `V01007`/`V01008` men/women, `V01009`-`V01019`
  men and `V01020`-`V01030` women in 11 bands (0-4, 5-9, 10-14, 15-19, 20-24, 25-29, 30-39, 40-49, 50-59, 60-69, 70+), and
  `V01031`-`V01041` both sexes. Disclosure: a suppressed cell is `X` (V01006 in 8,684 tracts, 1.9%; 721,091 of the 10,092,984
  sex-band cells, 7.1%); the published sex-band cells hold 201,752,886 people of the 203,080,756 residents that the basic file's
  `v0001` counts (never suppressed). **The municipal file of the theme is the sum of the same published cells** (201,752,886,
  equal cell by cell): it falls short as the tracts do (5,472 municipalities, 102 by more than 5%, the worst by 65%); a whole
  municipal count by sex and age is SIDRA's, not this file's. The basic file is Windows-1252 and writes "." for "not
  applicable" (the lagoons 4300001/4300002 have `CD_MUN` "."); the demography file is ASCII. The tract mesh with the basic attributes (`malha_com_atributos/.../BR_setores_CD2022.gpkg`,
  1.5 GB, 472,780 rows: tracts in several pieces repeat their counts) is in `registries/ibge_points/tracts.gpkg`.
  **The other themes** (read 2026-11-21, `tract_aggregates`): literacy V00644-V01005 (362; the bare age bands V00644-V00656 are all
  persons aged 15+, the literate are V00748-V00760), household characteristics V00001-V00643 in three parts (89, 406, 148),
  colour or race V01317-V01411 (95), all 458,772 tracts with residents, `X` for suppressed (6-14% of cells); the dictionary is
  `dicionario_de_dados_agregados_por_setores_censitarios_20261113.xlsx` in the folder above the CSVs (it has no universe field;
  the description carries it). The basic file has only V0001-V0009. Tracts' sums fall 0.04-0.6% short of SIDRA's
  municipal values (evaluation 2026-11-21).
  **Income of the household head IS published by tract** (read 2026-11-21, `tract_aggregates("renda_responsavel")`): a separate folder
  `Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/` (release 2026-05-08) with the tract, neighbourhood,
  district, subdistrict and municipality CSVs (`Agregados_por_{setores,bairros,distritos,subdistritos,municipios}_renda_responsavel_BR_20260508_csv.zip`,
  also `_xlsx.zip`) and `dicionario_de_dados_renda_responsavel_20260508.xlsx` (Tema, Variavel, Descricao). Six variables: V06001 heads, V06002 residents,
  V06003 variance of the number of residents, V06004 mean and V06006 median nominal monthly income of heads *with income*, V06005 its variance.
  The tract file has a decimal point, the municipal file a comma (Windows-1252); `X` suppressed, `.` not applicable. 458,772 tracts: 8,904
  (1.9%, 531,151 residents) have `X` in V06001-V06003, 337 more have no mean or median.
- **Weighting areas** (Areas de Ponderacao, the sample's unit; 14,270 with residents), `Microdados_e_Areas_de_Ponderacao/` (read 2026-11-21):
  `Areas_de_Ponderacao/tabelas_xlsx_20261106.zip` (44 MB; 34 xlsx `XLS/Tab<n>_<m>.xlsx`, each 2 title rows, 1-2 header rows, a `Brasil` row and 14,270
  area rows: households, education, disability, religion, fertility, migration, work, **income (8.1 work income, 8.2 all sources, 8.3 per capita household
  income by sex, mean and median)**, commuting, marital status, families). `Documentacao/Areas de ponderacao/Composicao das Areas de Ponderacao.xlsx` **maps each
  tract to its area** (468,097 tracts; 14,406 areas, 136 of them empty: 252 tracts, no residents; the two lagoon tracts are unplaced), with the area lists for public and
  controlled microdata (14,270 each: type, tracts, persons and households of the universe and the sample), `Fracoes.xlsx` and variation coefficients.
  **Microdata of the sample** (`Microdados_de_acesso_Publico/{csv,txt}/`, per UF 3-182 MB zipped, `Todas_as_UFs.zip` 1.0 GB): record types Domicilios (55 variables), Pessoas (169),
  Familia (28), Mortalidade (14), with `Peso Amostral`; AL (read, 16 MB): 114,514 households, 347,165 persons, 103,380 families, 6,601 deaths. **The public files carry no
  municipality, tract or weighting-area code** (UF, `Controle`, the tract's situation and the weight only; areas are in the controlled-access version): they cannot be placed below the UF.

- **CNEFE 2022**: §6.5 (files, columns, levels; the CEP aggregate holds counts and no coordinates).

### 6.4 SIDRA, the aggregates API v3 (measured 2026-10-05 through `sidra/`)

- **Table notes** (2026-10-24, ADR-0206): not in `/metadados`. `apisidra.ibge.gov.br/desctabapi.aspx?c=<t>` and `sidra.ibge.gov.br/Ajax/JSon/Tabela/1/<t>` (`Notas`) answer 403 with Cloudflare's "Just a moment..." to httpx (any headers, any TLS context) and to curl's own agent; a browser gets 200. The note is where a table says "Dados do Universo", "Dados da Amostra" or "Dados dos Resultados preliminares da amostra, estimados a partir de áreas de ponderação preliminares" (Census 2022), sometimes per census year (200, 202, 206).

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
- **Projections** in SIDRA (research XE, 5 tables) are state level only and stop at the 2018 revision; IBGE's own tree holds the
  2024 revision (`ftp.ibge.gov.br/Projecao_da_Populacao/Projecao_da_Populacao_2024/`: ages, indicators, life tables), which
  `projpop`/POPSVS read; its indicators and life tables are not held (corrected 2026-11-21: this said the projections stopped
  at 2018). The estimates (XF, table 6579) are
  municipal totals only, without 2007 or the census years. Neither carries municipal age and sex: POPSVS does.
- **The same Total differs between tables of one census**: 2010 households are 57,324,185 in table 3154 and 57,324,167 in
  tables 1436 and 3218 (18 apart).
- **IPCA, table 1737 (measured 2026-10-14; ADR-0183).** National level only (`N1`), no classification, six variables; variable 2266 is the
  index number, December 1993 = 100: 562 months, 1979-12 to 2026-09, one request (about 5 s with the table's metadata), no month missing. Its 393 months of 1994-01 to
  2026-09 equal, value for value, IBGE's own historical-series workbook (`ftp.ibge.gov.br/Precos_Indices_de_Precos_ao_Consumidor/IPCA/Serie_Historica/ipca_SerieHist.zip`,
  `ipca_202609SerieHist.xls`, two decimals); January 2014 3,836.37, December 2020 5,560.59, December 2025 7,403.29 and September 2026 7,695.82
  are what SIDRA's query service (`apisidra.ibge.gov.br`) returns for January 2014, December 2020 and December 2025, and SIDRA's table page shows September 2026 ("7.695,82", of "Mês [1/562]"). Values before the real are on the base's scale (1.1e-8 in
  1980): a ratio of two months is the inflation between them. The values are `.` decimals with 13 digits; SIH and SIA amounts are nominal, so
  an amount of competence month m is in reais of month r when multiplied by index(r) / index(m) (`price_index(reference=...)`).
- **IGP-M and IGP-DI, Banco Central SGS 189 and 190 (measured 2026-11-23).** FGV's general price indices are not in SIDRA; the SGS serves each as the month's percentage change, the whole monthly series in one request (`api.bcb.gov.br/dados/serie/bcdata.sgs.<n>/dados?formato=json`). The bare URL answered `304 Not Modified` with no body to a client that sent no validator; with `dataInicial`/`dataFinal` it answers 200. `price_index(index="IGP-M")` chains the changes into an index number (first month = 100), stored with its provenance (`sources/bcb_sgs.py`).

### 6.5 CNEFE 2022, the Census's georeferenced addresses (measured 2026-10-24; ADR-0205; docs/evaluation/2026-10-24-cnefe-cep.md)

- **Files** under `ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/`:
  `Arquivos_CNEFE/CSV/UF/<code>_<UF>.zip` (27 files, 3,922,077,434 bytes: RR 4.5 MB, AL 29.2 MB, MG 537 MB, SP 1,082 MB; Last-Modified 2024-05-20,
  RO 2024-06-12), the same by municipality in `Arquivos_CNEFE/CSV/Municipio/`, `Arquivos_CNEFE/GeoJSON/`, the dictionary
  `Arquivos_CNEFE/CSV/Dicionario_CNEFE_Censo_2022.xls`, and `Agregados_por_CEP/` (a zip and its dictionary). The release folder also holds
  `Coordenadas_enderecos/` and `Trajetos_dos_Recenseadores/` (not read). A UF zip is one CSV: `;`, UTF-8, CRLF, no quote character, 34
  columns, the last header cut (`COD_TIPO_ESPECI`; the dictionary says `COD_TIPO_ESPECIE`; 22 of 22 zips read). Alagoas: 1,626,565 records,
  263,756,151 bytes, 29 MB zipped. The country: 111,102,875 records (every zip's lines equal its landed rows), 18.2 GB of CSV, 3.45 GB as zstd Parquet.
- **A record is an address species.** `COD_UNICO_ENDERECO` repeats on one record per species at the address (a dwelling and a shop under it): in
  Alagoas 62,917 addresses have two records, 1,003 three, 3 four; 106,814,877 addresses in 111,102,875 records nationally. Every record of an
  address carries the same CEP, municipality, tract, coordinate and level (0 exceptions in 27 UFs). `CEP` is eight digits on every record and
  never empty; `COD_SETOR` is 16 characters (15 digits and a letter, `270470805000105P`). `NUM_ENDERECO` 0 with `DSC_MODIFICADOR` `SN` is "sem
  número" (358,933 records in Alagoas); its largest value there is 1,153,287,964.
- **Dictionary codes** (`NV_GEO_COORD`, the coordinate's level): 1 original Census coordinate, 2 modified (apartments at one number), 3
  estimated (none or invalid originally), 4 block face, 5 locality, 6 census tract. Addresses by level, nationally: 99,670,725, 6,050,088,
  740,088, 330,498, 9,094, 14,384; no coordinate is empty. `COD_ESPECIE`: 1 private household, 2 collective household, 3 agricultural
  establishment, 4 educational, 5 health, 6 other purpose, 7 building under construction or renovation, 8 religious. `COD_TIPO_ESPECIE` (101
  house, 102 house in a village or condominium, 103 apartment, 104 other) is filed on species 1 and 2 only, and every collective household is 104.
- **IBGE's aggregate by CEP** (`Agregados_por_CEP_CNEFE_Censo_2022.zip`, 38.7 MB CSV, 931,499 CEPs, 14 count columns, **no coordinate**): `TOT_END`
  is the distinct `COD_UNICO_ENDERECO` of the CEP, not the records (equal in 931,499 of 931,499 CEPs; the records in 640,355);
  `TOT_DP`, `TOT_DC`, `TOT_EAGRO`, `TOT_EENSINO`, `TOT_ESAUDE`, `TOT_EOF`, `TOT_ECR`, `TOT_ERELIG` are the records of species 1, 2, 3, 4, 5, 6, 7, 8;
  `TOT_TIPO_101` to `_104` the dwellings (species 1 and 2) of each type. `TOT_DOM_COND` has no counterpart among the record's columns and is not
  compared. The CNEFE holds the same 931,499 CEPs; 398 of them span two to four municipalities and 6 span two UFs.
- **What a CEP is** (CNEFE, nationally): 5,570 municipalities, 1,694 of them with one CEP (8.0% of the addresses); the p90 distance of a CEP's
  addresses from their median is under 300 m for 754,707 CEPs, 300 m to 1 km for 123,418, 1 to 2 km for 16,845 and over 2 km for 36,968, which hold
  46.8 of the 106.8 million addresses. São Paulo's 01001-000 (Praça da Sé) holds 6,973 addresses, all in the city, half within 17.8 km of
  their median; the Congresso Nacional's 70160-900 is in neither the CNEFE nor the aggregate.

- **A record's CEP places half the people at a point** (2026-11-21, evaluation 2026-11-21-record-places): of SIH
  neurosurgical and TBI admissions 2023-2024, 39% and 47% carry a generic municipal CEP (xxxxx-000) and 7% one the CNEFE
  does not list; a specific CEP's addresses lie within 600 m (p90) for half. Small and rural places write the town's
  CEP, so CEP-level context is missing not at random.

### 6.6 Mobility between municipalities (read 2026-10-25; ADR-0211)

- **Road distance and car travel time between municipal seats** (Saldanha 2024, Zenodo doi:10.5281/zenodo.11400243, CC-BY 4.0; `pegasus-data mobility --layer road_matrix`, `proximity_graph('road_osrm')`): OSRM car routes over OpenStreetMap between the 5,565 seats IBGE published in 2010, every unordered pair (15,481,830, taken as symmetric); minutes and metres. 44,482 pairs (0.29%) have no road route (boat- or plane-only). Six municipalities created after 2010 have no seat and no row. Speeds are OSRM's car profile, so a road in poor condition counts at its class speed (BR-319: Porto Velho-Manaus 997 min). The OSM date is not stated. The access measure for studies (ABNc D-17); river and air travel come from the IBGE and ANAC layers.
- **IBGE Ligações rodoviárias e hidroviárias 2016** (`geoftp.ibge.gov.br/organizacao_do_territorio/redes_e_fluxos_geograficos/ligacoes_rodoviarias_e_hidroviarias/base_de_dados/`, `xls/` and `ods/` identical; latin-1 `leiame.txt`; methodology only in the book liv100602.pdf): one row per pair, both directions summed; `VAR05` waterway, `VAR06` road, `VAR07` their sum; frequencies weighted by vehicle and period; 35 South American cities (codes 80xxxxx-92xxxxx) among the nodes; 320 "sem objeto" municipalities listed apart.
- **ANAC Dados Estatísticos** (`sistemas.anac.gov.br/dadosabertos/`, an nginx index; works with a browser agent): one row per flight stage, company and month (a passenger on A-B-C counts twice); rewritten with a new date line and Last-Modified on days the data does not change (2026-10-25 and 2026-11-05: the same 361,057,599 bytes after the first line, data to 2026-09), so neither dates a release; a dated first line, UTF-8 with BOM, `;`, 36 columns; `NATUREZA` DOMÉSTICA needs a Brazilian operator as well as both ends in Brazil. The aerodrome registers (cp1252, a dated first line) carry ICAO, municipality and decimal coordinates (`LATGEOPOINT`/`LONGEOPOINT`), no IBGE code; closed airports leave them (SBNT Natal-Augusto Severo, 21 M passengers before 2014), and ANAC reuses an ICAO code for another aerodrome (SNQY: Juazeiro do Norte in the statistics, an airfield of Ribeirão Preto now). gov.br answers HEAD with 403.
- **ANAC's open file against its Anuário** (2026-11-05): equal to 0.04% in 2010-2022 except November-December 2020, where the file lacks about 752 thousand of LATAM's domestic paid passengers (Anuário 2021 edition, Fig 3.9 and 3.11-3.12).
- **Census 2010 work and school place, DF** (2026-11-05): 96,623 of the 113,076 DF residents working "em outro município" carry `8888888` in both UF and municipality ("Não sabe UF nem país estrangeiro"); they return home daily like intra-DF workers, so they read as commuting between administrative regions. Goiás has 3,511 such workers.
- **The Ligações book's printed tables** (Tabelas 1-3) are not computed from the published workbook (RS printed equal to PR; Tabela 3 by REGIC class above and below it); the workbook is the data.
- **IBGE Arranjos Populacionais, 2nd edition** (`geoftp.../divisao_regional/arranjos_populacionais/`): the composition with codes is only in the geodatabase (`base_de_dados_2ed/ArranjosPopulacionais_mbd_2ed.zip`, an 88 MB zip of a 240 MB Access .mdb, table `ComposicaoRecortes_01_PorMunicipio`, 2010's 5,567 municipalities, `<Null>` its blank); an arrangement's code is its core municipality's; `tab01.xlsx` names arrangements without codes.
- **IBGE predominant biome per municipality** (`geoftp.../informacoes_ambientais/estudos_ambientais/biomas/documentos/Bioma_Predominante_por_Municipio_2024.csv`, read 2026-11-06): UTF-8 with BOM, `;`-separated, `Geocódigo;Nome do município;Sigla da UF;Bioma predominante`, 5,579 rows; the area shares per biome are a separate list (`Lista_Municipio_Bioma_250mil.xls`). ADR-0213.
- **Census 2022 commuting** (SIDRA 10321, 10330-10333): preliminary sample results; each Total includes the persons whose place was "ignorado", and 10331-10333 leave out persons working in more than one municipality.

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

## 10. Climate: BR-DWGD, its municipal series, INMET (measured 2026-10-14)

- **BR-DWGD** (Xavier, Scanlon, King & Alves 2022, Int J Climatol 42:8390): daily 0.1° grid, 1961 on; pr, Tmax, Tmin, RH, Rs, u2,
  ETo. Its page (Google Sites, read 2026-10-14) lists v3.2.3 (2024-12, to 2024-03-20) and **v3.2.4 (2026-04, 1961-01-01 to
  2025-12-31)**. Distribution: Google Drive (the daily archives answered "Quota exceeded"; the 355 MB monthly archive downloads
  at about 45 MB a minute), Dropbox, Earth Engine. v3.2.4 moves the past against v3.2.3 (EVALUATION 2026-10-14 "Climate from BR-DWGD").
- **Its municipal series** are published by Saldanha et al. (`brclimr`, MIT): mean, max, min, stdev, count (and sum) of the cells a
  municipality covers, daily, IBGE's 2010 mesh (5,565 municipalities and the lagoons 4300001/4300002), Parquet long form
  `code_muni, date, name, value` sorted by name then date. (1) `brclimr` 0.2.0 (2024-04-04) reads DigitalOcean copies (Zenodo
  7824920, v1.0.0, 2023-04-13), fast (5 MB/s), every variable ending **2020-07-31**. (2) Zenodo **13906834** (2024-10-09, concept
  7824919): v3.2.3, to **2024-03-20**; `<Var>_3.2.3.parquet`, 2.0-2.2 GB, rows named `<Var>_3.2.3_mean`; Zenodo serves 60-120 KB/s
  a connection and 133 requests a minute (429 beyond; Range works, 8 streams add up). Fernando de Noronha and Bombinhas have no value
  on any day; the six municipalities created after 2010 are absent.
- **ERA5-Land municipal means** by the same authors: yearly Zenodo records 2023 (10947952), 2024 (15748125), 2025 (18257037, 2026-01-15),
  1950-2022 (10036212): 2 m temperature mean/min/max (K), dew point, surface pressure, 10 m wind u/v, total precipitation (m), 40 MB a
  variable-year, the same 5,567 codes.
- **INMET's mirror** (Zenodo 14925215) ends 2025-01-01; its station tables hold more than the lake's `climate` keeps (pressure, dew
  point, humidity, radiation, wind, insolation, evaporation). A station-year with 11 complete months of temperature: 397 municipalities
  at most (2010), 341 in 2023.
- **Needs an account, so out:** ERA5 through the Copernicus CDS; Google Earth Engine's BR-DWGD and ERA5-Land assets.
- **CPTEC/INPE's daily grids** (`https://ftp.cptec.inpe.br/modelos/tempo/`, an Apache index, browser UA, 1.6-2.3 MB/s a connection;
  read 2026-10-24, ADR-0204). **MERGE** `MERGE/GPM/DAILY/<yyyy>/<mm>/MERGE_CPTEC_<yyyymmdd>.grib2` (about 0.43 MB, with a GrADS
  `.ctl` and `.idx`), 1998-01-01 to the day before yesterday (2026-10-23 listed at 02:38 on the 24th); two GRIB2 messages, PREC
  (eccodes names it `rdp`, the `.ctl` `PREC 0,1 0,15,5`, mm) and NEST (gauges per grid point; eccodes `prmsl`; 9999 where none);
  1001 × 924 points, −120.05 to −20.05° E, −60.05 to 32.25° N, 0.1°, south to north; the day is the 24 h ending 12 UTC of its date
  (Rozante et al. 2020: "between 12 GMT of the previous day and 12 GMT" of the day; `.ctl` `tdef 12Z`). The 2025 rebuild (Read-me of
  2025-05-26) moved to IMERG V07B and the ONS gauges and regenerated 1998 on; the whole history is also one archive,
  `MERGE_NEW_1998_2024.tar.gz` (3.8 GB). **SAMeT** `SAMeT/DAILY/{TMAX,TMIN,TMED}/<yyyy>/<mm>/SAMeT_CPTEC_<VAR>_<yyyymmdd>.nc`
  (1.7 MB in 2000, 2.2 MB in 2026; zlib NetCDF4, CF-1.6, CDO), 2000-01-01 on; variables `tmax`/`tmin`/`tmed` (°C) and `nobs`
  (stations per point), 1001 × 1381 points, −83 to −33° E, −56 to 13° N, 0.05°, land only (54.5% of the points have no value); the
  2000-2024 files are dated 2022-06-01 and later (regenerated). Its Read-me: while ERA5 is not out (about 5 days) a day is made from
  24-hour observations and model forecasts, and regenerated when ERA5 arrives. The index's times are UTC (equal to `Last-Modified`):
  in October 2026 a TMAX day appeared at 03:06 the next day and was rewritten at 03:06 seven days later (TMAX of 10-15 at 10-22,
  TMIN at 17:04 of the same day and six days later), sometimes once more (TMAX of 10-01 at 10-14); MERGE's days were written once,
  at 02:38 the next day. Neither product has humidity. Measured (ADR-0204, evaluation 2026-10-24-cptec-daily-climate): MERGE's day fits
  the 24 h ending 12 UTC and SAMeT's the UTC calendar day (INMET's hours, 2023); MERGE holds 0.83 of INMET's automatic gauges'
  totals (0.64 in cells with no merged gauge) and 0.845 of BR-DWGD's in every month; SAMeT's Tmax is BR-DWGD's +0.06 °C (RMSE 0.75).

## 11. Garbage codes: the GBD levels as a declared classification (measured 2026-10-14; ADR-0182)

- **What they are.** The codes of underlying cause that say little about what the person died of (ill-defined R00-R99, heart failure,
  septicaemia, unspecified stroke, ...). The Global Burden of Disease classes them 1 to 4 by how far the true cause could lie: 1 in any of
  the three broad groups (communicable, non-communicable, injuries), 2 within a group across its level-2 causes, 3 across level-3, 4
  across level-4 (França et al. 2020). `garbage_codes(edition)` serves them from `curation/garbage_codes.yml`: code (DATASUS spelling),
  `level`, `package` (GBD 2019: the group of codes redistributed together), the printed token that holds it, the source.
- **Two editions, both transcribed from open-access supplements (Springer Nature's Figshare records `10.6084/m9.figshare.13023345.v1` and `.14721984.v1` read "CC BY + CC0"), none typed from memory.** `GBD2017`: França E et al., *Popul Health Metr*
  2020;18(Suppl 1):20, Supplementary file 1 (the GBD 2017 Causes of Death Collaborators' appendix 1, *Lancet* 2018): 5,835 codes, each with
  its level (3,449 / 1,869 / 393 / 124). `GBD2019`: Johnson SC et al., *BMC Med Inform Decis Mak* 2021;21:175, Supplemental Appendix Figure 3
  (membership: 5,891 codes) and Figure 4 (class and package: 147 packages; 71 rows are a second package of a code): 3,341 / 399 / 436 / 153 rows by class 1 to 4;
  1,633 members have no class or package (S00-T98, the mycoses, I50.0 and I50.1 heart failure, N17, ...), and 23,310 of Brazil 2016's 518,806
  member deaths are in them (I50.0 13,661, N17.9 4,684). IHME's own mapping (GHDx) is under a non-commercial agreement and is not shipped (ADR-0140).
- **Ranges are read by sort position.** A printed range lists every code between its endpoints in ICD-10's order with the point
  (A00 < A00.0 < A01), closing at its last endpoint ("R58.0-R78" stops at R78 itself; "A01" alone is the three-character code). The sources
  print endpoints no code has ("ID5.9", "TO7.", "E998", "ZB0", "unsp.") and two-character blocks ("C1", "D0"); the rule reads them where
  they fall and no per-token fix is needed. The rule was found by reproducing the supplement paper's Table 1 on SIM-DO Brazil 2016
  (docs/evaluation/2026-10-14-garbage-codes-and-prices.md); no code of the 2017 list falls at two levels under it (the loader raises if one did).
- **A list is a claim about its own date.** A code ICD-10 created later is not in the edition however a range spells it (GBD 2017's
  "U07-U81" lies over U07.1, COVID-19, created 2020-01). **For deaths of 2020 onwards use GBD2019.** SIM-DO codes COVID-19 as **B34.2**
  (Alagoas by residence: 3,589, 4,239, 735 and 80 deaths in 2020-2023; U07.1 and U07.2 do not occur), a level-2 garbage code in GBD 2017 and
  none in GBD 2019: on GBD 2017 Alagoas's level 2 is 5.2 % of its deaths in 2019 and 19.9 % in 2020, 22.5 % in 2021 (17 % of 2021's deaths are B34.2).
- **The supplement's own note** moves four printed level-1 codes (J47, K70.4-K70.9 to level 3; E12-E15 to 4; K73 to 2): applied, with the
  printed level kept in `amended_from`.
- **Against the Ministry's list** (`SIM-POUCO-UTEIS`, 3,090 codes, types as the TabWin kit writes them): 2,498 are GBD 2017 garbage codes
  (81 %); Tp 5, the R codes, 381 of 389; Tp 3, 19 of 19; Tp 1 1,586 of 1,897. The kit's list also holds the in-situ neoplasms
  D00-D09 (Tp 4), which neither GBD list does: the two are different lists, and neither stands for the other.

## 12. Reaching the non-FTP servers (measured 2026-10-14; ADR-0188)

- **Certificates.** `servicodados.ibge.gov.br` sends an incomplete chain: the `certifi` roots refuse it ("unable to get local issuer
  certificate"), the operating system's store accepts it. `download.inep.gov.br` resets connections intermittently, with or without certificate checks (`curl -k`: "Connection was
  reset", 2026-11-21; this said the reset came from verifying against `certifi`). Every other
  server read here (MIDR, ANS, TabNet, INMET, Zenodo, IPEA, DEMAS, ckan.saude, NOAA, GitHub) answers either way. The transport uses the system store.
- **Zenodo.** From this network `zenodo.org` answers 403 to every request over IPv6, its front page included, and serves over IPv4
  (`/api/records/7824919/versions/latest` 301 to record 13906834, 200). The transport uses IPv4.
- **S2iD** (`dadosabertos.mdr.gov.br`, bare `/download` route): 86,323,744 bytes, cp1252, `;`, 76,190 events 1991-2025 (all dated, all in an IBGE
  municipality); quoted fields hold line breaks, so the lines are not the records.
- **INEP** school census: the zip holds two CSV tables (schools; the technical-courses supplement). 2023: 217,625 schools, 408 columns; the total
  margin sums to 47,304,632 enrolments in 5,570 municipalities.
- **ANS PDA-024**, December 2022: 28 state files (27 states and `XX`), 14,070,694 rows. `XX` has `SG_UF` "XX" and municipality `-1`; each state
  has an "ignored" municipality code ending in `0000`. 41,879 of 50,530,569 medical-hospital links (0.08 %) are in neither.
- **ANS rewrites its December files.** The 2022 state files were republished on 2026-11-05 (SP, RJ, MG `Last-Modified`):
  landed again on 2026-11-09 they give 50,500,350 medical-hospital links (30,219 fewer than the 50,530,569 measured on
  2026-10-04, which then equalled TabNet) and 42,301 unplaced. A landed December is a version of it, not the year.

## 13. SISAGUA on the Portal de Dados Abertos (measured 2026-10-14; ADR-0162, ADR-0192)

- **Where.** `dadosabertos.saude.gov.br/dataset/sisagua-<name>` (the CKAN API route now answers 404: the Portal is a Next.js app; the S3
  bucket listing is `AccessDenied`, so the file list is each dataset page's). 15 datasets, files `s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/SISAGUA/<file>_{csv,json,xml}.zip`
  (`;`, one CSV per zip, UTF-8 and Windows-1252 mixed even within a line) and a dictionary `dicionario_<name>.odt` beside each (a PDF for the monthly control's basic parameters).
- **Landed** (2014-2026, `curation/intake.yml`): vigilância parâmetros básicos `vigilancia_parametros_basicos_<year>_csv.zip` (13 files, 85-212 MB,
  1.79 GB; 34,195,729 rows, one per sample x parameter; 2018: 2,674,342 rows, 5,082 municipality codes, 10 parameters of which E. coli 551,959,
  total coliforms 552,670, turbidity 539,055, free chlorine 411,766, pH, apparent colour, fluoride; SAA 2,143,317, SAC 359,212, SAI 171,813; reason
  Rotina 2,650,491, Desastre 12,229, Denúncia 5,962, Surto 5,660; 7,541 rows in the Distrito Federal's `5300xx` regions); `vigilancia_demais_parametros_csv.zip`
  (106 MB; 1,310,890), `vigilancia_cianobacterias_cianotoxinas_csv.zip` (2.4 MB; 49,288); controle mensal `controle_mensal_parametros_basicos_<year>_csv.zip`
  (13 files, 40-145 MB, 1.30 GB; 118,949,333 rows, supplier x system x point x month x parameter x measure), `controle_mensal_demais_parametros_csv.zip`
  (147 MB; 3,857,900), `controle_mensal_amostras_fora_padrao_csv.zip` (45 MB; 867,963). `RESULTADO` is a decimal-comma number, `MENOR_LD`/`MENOR_LQ`
  or `PRESENTE`/`AUSENTE` (coliforms); `NU_MES` is `01`..`09` in the surveillance files and `1`..`12` in the control files; `CO_MUNICIPIO_IBGE` has 6 digits.
- **Landed 2026-11-07 (ADR-0214)**: cadastro população abastecida (`cadastro_populacao_abastecida_csv.zip`, 77 MB, 1,918,496 rows, 2014-2026, one per supply form x
  municipality x year with `NU_VALOR_POPULACAO_ESTIMADA`, rural and urban, filtration, disinfection, intakes; a SAC or SAI that also receives SAA water is counted in both) and
  cadastro carro-pipa população (2,174 trucks from 2023; its people supplied repeat the municipality's population on each truck, so only trucks are counted).
- **Not landed**: cadastro tratamento de água (82 MB), pontos de captação (55 MB), carro-pipa procedência (under 0.1 MB), controle semestral (`controle_semestral_<year>_csv.zip`, 27-199 MB a year),
  plano de amostragem (`controle_mensal_plano_amostragem_<year>_csv.zip`, 80-121 MB a year, CSV only from 2022), infraestrutura operacional (42 MB).
- **Standard.** The out-of-standard shares use the limits read from Portaria GM/MS 888/2021 (Anexo XX of the Portaria de Consolidação 5/2017): E. coli absent in
  100 mL, turbidity at most 5 uT in the network, free chlorine at least 0.2 and at most 5 mg/L, fluoride at most 1.5 mg/L, apparent colour at most 15 uH,
  each with its article in the field's `what`. The files publish no out-of-standard flag for the surveillance samples (the control has its own list).

## 14. SRAG, the yellow-fever monitoring files and three SINAN/SISPRENATAL structures (measured 2026-10-19; docs/evaluation/2026-10-19-srag-fa-event-types.md)

- **SRAG (SIVEP-Gripe)** is `SRAG/YYYY/INFLUDyy-DD-MM-YYYY.parquet` on the Portal's S3 (the date is the cut: 23-03-2026 for 2019-2024, then 28-09-2026 and 19-10-2026 for the current years, rewritten weekly). One
  schema of 194 columns, 4,666,910 notifications in the nine onset years of the lake; the dictionary is `SRAG/dicionario-de-dados-2019-a-2025.pdf` (SIVEP-Gripe, 25/05/2023) and the files are anonymised (no name, CPF,
  CNS, address or notifying unit). The parquet types are the export's: dates timestamps, codes decimals, so the INFLUD19 and INFLUD20 files carry `5.0` where the others carry `5`, and `RAIOX_RES` is `6.0000000000`
  in all. `CS_SEXO` is M, F, I; names and codes come in pairs (`ID_MN_RESI`/`CO_MUN_RES`); the Distrito Federal resides in its 5300xx administrative regions; `SEM_NOT` is the epidemiological week of `DT_NOTIFIC`
  (the dictionary says the first symptoms); `TP_IDADE` 1, 2, 3 is days, months, years. A file holds its epidemiological year and 29 notifications repeat in two files.
- **Yellow fever** is `Febre+Amarela/fa_casoshumanos_1994-2026.csv` (2,912 rows, the last one empty) and `fa_epizpnh_1994-2026.csv` (2,637), `;` and latin1, with a dictionary that gives no code table. The monitoring period runs July to June.
  The human cases are the Ministry's confirmed ones (above), `DT_IS` may be the word `Assintomático`. The informes read: COES informe 40/2017 (10 May 2017), the monitoring report of 8 May 2018, PAHO/WHO's update of 13 December 2017.
- **SINAN-ESPO** is the Sinan Net epizootics base (serial `ID_NOTIFICACAO`, gapless 1 to 32,492 for 2013-2022; no classification column). **SINAN-NTRA** holds survey batches whose positives SINAN-TRAC lists one by one.
- **SISPRENATAL-PN** rows are pregnancy-months with cumulative consultation counts; `NU_GESTA` is a record serial that reaches 122,739, not a gravidity.

## 15. ANS TISS, the private plans' hospital and outpatient events (D-TISS; measured 2026-11-21; docs/evaluation/2026-11-21-ans-tiss-intake.md)

- **Tree.** `dadosabertos.ans.gov.br/FTP/PDA/TISS/{HOSPITALAR,AMBULATORIAL}/<year>/<UF>/<UF>_<yyyymm>_{HOSP,AMB}_{CONS,DET,REM}.zip` (Apache index, answers a browser User-Agent), 2015-2025, 27 states (no `XX`),
  one zip of one CSV per state, month and kind: 3,564 files each of CONS and DET, 972 of REM (2023-2025 only). Zipped sizes, summed from the listing: hospital CONS 1.18 GiB, DET 4.24, REM 0.19 (5.6 GiB);
  outpatient CONS 105.9, DET 79.7, REM 11.9 (197.6 GiB); the outpatient 2025 files alone are 30 GiB. Beside them `DICIONARIO/` (two `.ods`: to 2022, from 2023) and `DADOS_DE_PLANOS/PLANOS.zip` (1.4 MB, 31.9 MB CSV,
  166,107 plans: segmentation, coverage, financing, scope, moderating factor, accommodation; keyed by `ID_PLANO`).
- **Layout.** `;`, UTF-8, quoted strings. CONS: one row per event (`ID_EVENTO_ATENCAO_SAUDE` unique in the sample), with the plan, the beneficiary's age band, sex and municipality of residence (empty together when the
  SIB/CNS crossing found none), the operator's size class and modality, the provider's municipality and state, the month (`ANO_MES_EVENTO` hospital, `DT_REALIZACAO` outpatient, `yyyy-mm`), and the hospital stay
  and ICD-10 (`CID_1`-`CID_4`, optional, mostly empty) or the outpatient CBO and consultation type. DET: one row per item, same event key, `CD_TABELA_REFERENCIA` + `CD_PROCEDIMENTO` (TUSS 19, 20, 22; 63 groups; 90
  and 98 operator packages; `0`/`00` with `TABELA PROPRIA` for an operator's own code), quantity and value billed. REM: event, remuneration model (TUSS 79), value. In the hospital sample every CONS event had
  DET items and every DET item a CONS event. **Two layouts**: to 2022 as above; from 2023 CONS adds `VL_EVENTO_INFORMADO/PAGO/GLOSA` (outpatient also `REGIME_ATENDIMENTO`, `SAUDE_OCUPACIONAL`) and DET adds
  `QT_ITEM_EVENTO_PAGO`, `VL_ITEM_EVENTO_PAGO`, `UNIDADE_MEDIDA`; the dictionary says the payment fields were published in 2026 for 2023 on. Headers read in RR for January of every year 2015-2025 and April,
  May and December 2023: the break is 2022/2023, not May 2023.
- **Spellings.** Age bands are `30 a 39` to 2022 and `30 a 39 anos` from 2023 (also `<1`, `Menos de 1 ano`, and `N¿o identificado` with a literal `¿`); numbers use a decimal comma (`1,0`, the 2022 hospital stay
  length too); some codes are float text in 2022 (`11.0`). The files hold no operator registry number, no CNES and no beneficiary identifier: the operator is its modality and size class, the plan an opaque `ID_PLANO`.
- **Dictionary codes.** Given: character of care (`1` elective, `2` urgent), modality (21/55 administradora, 22 medical cooperative, 23 dental cooperative, 24 self-management, 25 group medicine, 26 group dental,
  27 philanthropic, 28/29 insurer), size class, the pre-established-value and package flags. Named by TUSS table but not listed, so left undecoded: 23, 57, 41, 39, 50, 76, 52, 24, 77, 36, 60, 79. The two
  dictionaries disagree on `LG_FATOR_MODERADOR` (0 or 1 for "present"); the first rows of PLANOS.zip file `Ausente` with 1.

## 16. ANS beneficiaries by municipality, the quarterly TabNet base (measured 2026-11-22; docs/evaluation/2026-11-22-ans-beneficiaries-history.md)

- **Where.** `dadosabertos.ans.gov.br/FTP/Base_de_dados/Microdados/dados_dbc/beneficiarios/municipios/tb_bb_<yyyy>-<mm>.dbc` (Apache index, plain HTTPS), quarter-end months 03, 06, 09, 12, 2000-03 to 2026-09 (107 files, 16-18 MB
  each, DATASUS-compressed DBF; read by the package's own decoder). The base behind the TabNet "Beneficiários por Município" (`DEF/tabnet_02.def`); the code lists are the CNV files of
  `arquivos_auxiliares_de_tab_def_e_cnv/arquivos_auxiliares_de_tabulacao.zip` (`cd_idade_faixa5`, `tp_sexo`, `cd_tp_contratacao3`, `cd_segmentacao_plano`, `tp_vigencia_plano`).
- **Layout.** 13 text columns, one row per cell: `ID_CMPT` (YYYYMM), `SEXO`, `TP_VIGENCI` (A before / P after Law 9.656/98), `SG_UF`, `CD_MUNICIP` (6-digit IBGE), `CD_CAPITAL`, `CD_RM`, `CD_CONTR` (1-4, 0 not informed),
  `CD_SEGMENT` (00-15, 99), `CD_FAIXA_E` (00-27, 99), `NR_BENEF_T` = `NR_BENEF_M` (medical-hospital, with or without dental) + `NR_BENEF_O` (dental only). 1.5-1.8 million rows a file.
- **Age codes.** The CNV groups two codes into each five-year band from 15-19 to 55-59 and 26+27 into 80 and over; the RN 63 table (`cd_idade_rn63`) is consistent with the pair being the band's earlier years and its last year.
  Code 99 is inconsistent (3,468 links in December 2012, 190 in 2021).
- **The same count as PDA-024.** December 2021: tb_bb 49,252,210 medical-hospital links (49,209,906 in an IBGE municipality), PDA-024 (`ans_beneficiaries`) 49,252,210 and 49,209,904; one municipality (430210) differs, by 2. ANS publishes
  one SIB count in two layouts. PDA-024 files age by finer labels (15-17, 18-19) that the 5-year bands unite.
- **Municipality is the operator's registered residence** (SIB). Beneficiaries in a code that is no IBGE municipality (the "ignored" codes ending 0000, state-only codes) are unallocated: 801,709 of 30,966,522 in December 2000 (2.6%),
  94,320 of 47,846,092 in 2012 (0.2%), 42,304 of 49,252,210 in 2021.
- **Landed in the lake** by `pegasus-data fields --name ans_beneficiaries_quarterly` (declared `ans_beneficiaries_municipal`, whole records, every column; dental-only counts are `ans_dental_beneficiaries_quarterly`): 2012 7,071,709 rows, 2020-2021
  13,944,450, all 107 quarters 176,199,297. National medical-hospital links in December: 41.0 million (2008), 47.7 (2012), 50.5 (2014), 47.0 (2019), 47.9 (2020), 52.8 (2025); municipalities placed 5,558 (2012), 5,570 (2020-2021).

## 17. TUSS, the supplementary-health terminology, and its correspondence to SIGTAP (measured 2026-11-22; docs/evaluation/2026-11-22-tuss-terminology.md)

- **Terminology.** `dadosabertos.ans.gov.br/FTP/PDA/terminologia_unificada_saude_suplementar_TUSS-049/pda-049-tuss.zip` (PDA 049, 1.4 MB, listed 2026-06-26, dictionary `.ods` 2026-07-14; answers a
  browser User-Agent): one CSV per table (18, 19 OPME 1.39 M terms, 20 medicines 45,355, 22 procedures, 23-79 small domains, 63 groups, 64 the "forma de envio"). Table 22 has 5,966 terms of 8
  digits; `NM_TERMO`, `DT_INICIO_VIGENCIA`, `DT_FIM_VIGENCIA` (empty for all 5,966: only terms in force are listed), `DT_FIM_IMPLANTACAO`. **One name per code**, the current version: a term revised
  in 2024-06 starts then though its implementation is 2010-10, so a code's window here is from the earlier of its start and its implementation. The same data are served by ANS's OCL service
  (`consulta-ocl.apps.sa-1a.mendixcloud.com/rest/oclservice/ANS/concepts/tuss-22`, 20 per page, `extras` with the dates; `/source` lists the tables), linked from gov.br/ans "Códigos da TUSS".
  Held: tables 22 and 63 (`resources/tuss.parquet`, key `table+code`); 19, 20 and the small domains are not.
- **Correspondence to SIGTAP.** The official one is a workbook, `padraotiss_mapeamento_tuss_sigtap.zip` (1.2 MB, `Last-Modified` 2017-03-30; at gov.br/ans "Padrão TISS - Tabelas relacionadas" and the older
  `ans.gov.br/images/stories/.../tiss3/`), "MAPEAMENTO TUSS x SIGTAP 2017 04": TUSS table 22 of 2016-06 against the SIGTAP of that time, 6,919 pair rows, degrees of equivalence 1-5. It is **not
  current and not complete**: 4,299 mapped pairs for 3,172 TUSS and 2,911 SIGTAP codes, 152 terms marked "does not exist in SIGTAP", 2,468 rows with no answer (`not_yet_mapped`); of the 5,966 current terms 266
  are not in the workbook at all. A term maps to several procedures (up to 111) and a procedure from several terms: a pair is not a conversion. Grades: 1 same meaning, 2 same with a synonym, 3 TUSS less
  specific than SIGTAP, 4 more specific, 5 not mappable, 59 pairs "dúvida"; 1,082 pairs are marked "validated by the Ministry". ANS's "Compatibilização TUSS x SIP/Rol" and the TUNEP (ressarcimento ao SUS)
  are other tables, not read. The SIGTAP wiki of the Ministry points at the same workbook; no newer TUSS-SIGTAP file was found on gov.br, dadosabertos or the wiki (2026-11-22).
- **Use in TISS.** A TISS item is the pair `CD_TABELA_REFERENCIA` + `CD_PROCEDIMENTO`; the label is looked up by their concatenation (`22` + `10101012`), a code of table 63 being 3 digits and 19, 20, 22 8.

## 18. Subnational health spending: SIOPS and SICONFI (measured 2026-11-23; docs/evaluation/2026-11-23-subnational-health-spending.md)

- **SIOPS** (Ministério da Saúde, DESID/SE) is the declaration of health revenue and spending by which EC 29/2000 and LC 141/2012 are checked (15% of the tax base for municipalities, 12% for states).
  Its machine-readable access is **TabNet**, on `siops-asp.datasus.gov.br/CGI` over plain http (https does not connect from this network; the same host answers http):
  `deftohtm.exe?SIOPS/serhist/municipio/indic<UF>.def` (26 states; the Distrito Federal is in `ESTADO/indicdf.def`), one file per year `indmun00.dbf` to `indmun25.dbf`. `siops.datasus.gov.br` redirects to gov.br; its PHP
  consultation (`relindicadoresmun2.php`, POST by year, state, municipality) is one HTML page per municipality and year. No SIOPS dataset on the FTP; the open-data portal and `dados.gov.br` were not found to hold one
  (their searches redirected or answered 401: not excluded). The site's licence is CC BY-ND 3.0 (the gov.br notice); no separate data licence is stated.
- **What TabNet gives.** 22 contents: Frequência, População, indicators 1.1-1.6, 2.1-2.5, 3.1, 3.2 and five reais amounts (R.Impostos e Transf.Const, R.Transf.SUS, D.Pessoal, D.R.Próprios, D.Total Saúde), plus two per
  inhabitant. Relations hold to the rounding of the published 2 decimals: 2.1 = D.Total/População (reais, not %, despite its name), 2.2 = D.Pessoal/D.Total, 3.1 = R.Transf.SUS/D.Total, 3.2 = D.R.Próprios/R.Impostos
  (the EC 29 share), R.Transf.SUS/Hab and D.R.Próprios/Hab are the amount over População (Acre and Sergipe 2023, all 97 municipalities: no difference above 0.005). TabNet's Total row is the sum of the rows for the amounts. The subfunction shares 2.21-2.26 hold values for 2013-2015 only (mostly
  0,00), `...` from 2016, and asking for one beside other contents returns no rows for 2000-2012: they are not usable, spending by subfunction is SICONFI's.
- **Pitfalls.** (1) **A municipality that did not declare is absent**; TabNet lists it, as Frequência 0 and zeros, only with "show zero rows" (`exibirlz`), so never read that option's zeros as spending. (2) **Stage of
  expenditure changes within the series**: empenhada before 2002, liquidada 2002-2003, empenhada less restos a pagar without financial availability from 2004 (the TabNet page's own note). (3) **Declaration and
  retification**: entes declare by bimestre (2023: 1st until 30 March, 2nd 30 May, 3rd 30 July, 4th 30 September; Portaria 53/2013 sets the terms, LC 141 art. 39), the manager homologates, and the Tribunal de Contas's
  declaration overrides the manager's where it has one (FAQ); the table is the version held when read, so a past year can change and the latest years are provisional. (4) Amounts are current reais of the year. (5) The
  population is SIOPS's own estimate for the year. (6) 2.1 is labelled "%" and is reais. (7) TabNet **sums the files** it is given (a table of several years is a sum); each landing asks for one.
- **SICONFI** (Tesouro Nacional, `apidatalake.tesouro.gov.br/ords/siconfi/tt/`; open JSON answering a browser User-Agent; `limit`/`offset`, 5,000 rows a page, `hasMore`; an empty `items` for a request that matches
  nothing): `entes` (5,598 entities: IBGE code, esfera, population), `extrato_entregas?id_ente&an_referencia` (what an entity delivered), `dca?an_exercicio&no_anexo&id_ente`, `rreo?an_exercicio&nr_periodo&co_tipo_demonstrativo&
  co_esfera&id_ente`. **DCA-Anexo I-E** (2013 on; named `Anexo I-E` in 2013, `DCA-Anexo I-E` from 2014) has spending by function and subfunction in the columns Despesas Empenhadas, Liquidadas, Pagas and Inscrição de
  Restos a Pagar (processados and não processados), one row per account (`10 - Saúde`, `10.301 - Atenção Básica`, ...), about 280 rows per municipality-year; function 10 holds only the subfunctions the entity used.
  **The RREO has no Anexo 12** (ASPS) for São Paulo 2019/2023, Rio Branco 2018/2023 or Acre 2023 (anexos 01-04, 06, 07, 09-11, 13, 14 only), and a municipality under 50,000 files `RREO Simplificado` (Acrelândia 2023:
  anexos 01, 02, 06): the ASPS statement reaches SIOPS, not SICONFI. A municipality that has not delivered the DCA has no rows (`extrato_entregas` says what was delivered).
- **Between the two.** SIOPS D.Total Saúde equals DCA function 10 empenhada to R$ 1 for 198 of 289 AC and SE municipality-years (2018, 2021, 2023) and differs both ways otherwise (ratio 0.946-1.721; larger in total by
  3-8%); the cause is untested (OQ 102). They are different declarations of the same spending, not one figure: do not add them or fill one from the other.
- **Landed.** `siops_municipal` (dataset `SIOPS-MUNICIPAL`, fields `siops_health_spending`, `_own_resources`, `_transfers_sus`, `_tax_base`, `_spending_personnel`, `siops_declarations`). National command in
  RUNBOOK ("Subnational health spending").

## 19. SIH billing routes and the records of one stay (measured 2026-11-24; docs/evaluation/2026-11-24-sih-stay-continuation.md)

- **Operations billed inside 0415* AIHs.** A multiple, sequential or polytrauma surgery AIH (SIGTAP 0415*) names the
  billing rule as its main procedure; the operations are its SIH-SP act lines (SP_ATOPROF). They grew from 279,678
  AIHs in 2010 to 1,059,895 in 2025. Those with a neurosurgical act (0403*) went from 12,300 to 94,579. In 2023
  (AC, AL, PE, held whole) 68% of AIHs with a 0403 act were 0415*; no third route was seen. A cohort selected by the
  main procedure (PROC_REA) misses them, and the share differs by state (RN billed spine 444 against 31 in 2019).
- **An act line is a billed step, not always an operation.** The act lines list every step billed, so a code can mean
  something else than as a main procedure. Inside 0415*, 41.7% of AIH stays with the decompressive-craniectomy code
  (0403010020) also bill cranioplasty or cranial reconstruction: a craniotomy whose bone was put back. That holds for
  3.7% of main-procedure stays (2010-2025; ABNc t03).
- **A stay continues across COBRANCA 51** (encerramento administrativo), as across 21-29: declared since 0da8018e.
- **A spine code that is mostly cranial.** SIGTAP 0408030372 (craniocervical decompression, filed under spine surgery,
  0408) is mostly posterior-fossa surgery. 1,346 of 2,265 stays in a national spine cohort carry a cranial principal
  diagnosis: haemorrhage, head injury, hydrocephalus (ABNc t08, decisions D-11; 1,798 with Chiari, Q07, counted).
  A cohort selecting by 0408 holds it, and a cranial cohort misses it.
- **Secondary diagnoses and their type (2015 on).** DIAGSEC1-9 with TPDISEC1-9: 1 present on admission, 2 acquired
  in the stay (0: none). A comorbidity score counts type 1 only: type 2 is a complication. For injury admissions the
  external cause (V-Y) is filed here on every stay, with an unreliable type: in national decompressive craniectomies
  for head injury (2015-2024) the same causes are typed 2 about as often as 1. A third carry only unspecified causes
  (X58, X59, Y34, W99), and that share is a hospital habit (92% at one Curitiba trauma reference, 17% elsewhere).
  CID_ASSO, the older external-cause field, is empty after 2012 in these cohorts (ABNc D-14, 2026-11-25).
- **Long-stay continuation records (IDENT 5)** carry deaths that the principal AIH does not: 1,376 in 2019, 1,171
  sharing N_AIH with a principal AIH whose record shows none (OQ 104).
- **Payment follows the billing route (ABNc D-12).** A 0415* AIH's value (VAL_TOT) pays every act it bills, the
  devices and the intensive-care days, so a stay found by one act inside it carries far more than that operation. In
  2023 the median subdural stay was paid R$ 7,954 on the act route against R$ 3,576 on the main route, and craniectomy
  R$ 10,780 against R$ 8,339. The act-route share rises every year, so a pooled payment trend mixes the billing rule's
  shift with the operation's price (real median payment 2012-2024: subdural -14% pooled against -25% on the main route;
  craniectomy -6% against +9%). Report payment by route, or decompose route, procedure mix and price (Das Gupta; ABNc
  `lib/decompose`); per operation on the act route, take the value of the topic's act lines, not the AIH's.
- **Admission character (CAR_INT) is partly a billing habit (ABNc D-13).** The hospital sets it when it bills, and for
  the same diagnoses it varies by state and hospital far beyond case mix (2019-2023, the stay's first AIH): unruptured
  aneurysm (I67) coded elective 47% nationally, from 1.8% (PE) to 67.8% (RS); craniectomy 11%, from 0% (TO) to 34% (MA);
  degenerative spine (M4, M5) coded urgent 46%, from 14% (RN) to 82% (MS), with 29% of those stays in hospitals that
  code under 10% or over 90% of them urgent. A model comparing hospitals, regions or periods that adjusts for it shows
  the contrast without it; a diagnosis-based severity marker is preferred.
- **A stay that ends on an administrative closure with no continuation (ABNc D-15).** After the chain (51 continues a
  stay), 0.4-1.6% of a cohort's stays still end on a 51 with no next AIH within a day. Their end is not a discharge:
  among 1,335 craniectomy stays that end so, in-stay death is 1.5% against 41.9% for the rest, a death only the link
  finds 29.5% against 8.0%, and 6.9% die within 3 days of the AIH's end. They concentrate: one hospital (CNES 2525569)
  ends 37% of its spina-bifida-cohort stays on a 51, with median length 0 days and the same person's next AIH there a
  median 3 days later (repeated same-day AIHs a readmission count reads as returns). In-stay death and length of stay
  are lower bounds for them; hospital comparisons report each hospital's share.
- **Concurrent AIHs make two stays of one admission (ABNc D-16).** The chain links an AIH that starts within a day of
  the previous one's end; an AIH that overlaps another of the same person at the same hospital stays a stay of its own.
  0.27% of neurosurgical stays (t10) and 0.38% of a paediatric cohort's (t04) overlap another, almost all at the same
  hospital, and concentrated: CNES 2088193 has 25% of its stays overlapping, a main-procedure AIH and a 0415* AIH on the
  same dates with different codes; CNES 0017884 13%. They count operations, volume and in-hospital deaths twice; among
  newborns part may be twins, whom a birth-date, sex and postcode key merges. OPEN_QUESTIONS 110.
- **The false share of link-only deaths climbs with the window (ABNc D-11).** On a cohort's own subset, the share of
  deaths found only by the `sih_admissions_to_sim` link (the stay records none) that are expected by chance rises with
  the horizon, because the year pass matches more namesakes the longer it looks: craniectomy 23.6% at 30 days, 30.3% at
  90, 40.5% at 180, 59.4% at 365; aneurysm 22.7%, 35.3%, 45.6% (to 180); subdural 33.9%, 37.5%, 40.2%; head injury
  24.2%, 36.3%, 47.0%; thrombectomy 13.7%, 20.2%, 32.1%; glioma radiotherapy 20.0%, 12.8%, 14.1%, 18.6%. Report the
  false share at the horizon a claim uses, on its own subset, and word a 180- or 365-day death by its worst case.

## SINAN residence codes and representations (measured 2026-10-24; ADR-0207)

- `ID_MN_RESI` (SINAN-DENG 2010-2026) writes Federal District residents with region codes as well as 530010: 5300xx (530020-530180, as SIH did before 2018) and SINAN's 5399xx (539901-539934), 22,958 rows, 13,585 of them in 2024; DATASUS's TabWin tables AGLBR and BR_CAPITAL map 530000-539999 to Brasília. `XX0000` is the state with its municipality unknown (BR_DIVADM: "Município ignorado - UF").
- The Dados Abertos export of a SINAN year is not its `FINAIS` DBC: DENG 2020's CSV holds 1,495,117 rows with 538,654 discarded notifications (`CLASSI_FIN 5`) and no `DT_DIGITA`; the DBC 975,842, none discarded; LEPT 2015-2024's exports hold 412 rows more than the DBCs, TOXG 46 fewer.

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

- **Toxoplasmosis' entry dates are 70 years early in two years.** In the FINAIS `.dbc` of TOXG (and TOXC) for 2021 and 2022, `DT_DIGITA` holds the year minus 70 on most records: TOXG 2022 has 11,190 of 12,447 in 1952–53, and 2021 has 8,998 in 1951, raw in the file. 2020 and 2023 are clean. The Dados Abertos CSV republication, which the lake holds for 2019–2023, carries the same defect (TOXC 2021: 3,766 of 3,876 entry dates before 2000; 2022: 4,412 of 4,583; read 2026-10-13, correcting "not yet read"); no count uses DT_DIGITA.
- **Trial copies among SIA-PA's (2026-10-12, corrected 2026-11-05).** `/dissemin/publicos/SIASUS/teste/` holds eleven Paraná files, `PAPR2408`-`PAPR2506` (dated 2025-09-24), each a publication also in `200801_/Dados` (dated 2025-09-25 and later; four the same size, seven different). They are earlier copies, not stray files: the 2026-10-12 note called one file a test matching no family. A query reads the `Dados` copy (newest edition); the extract listed both, failed on the trial copies and held neither 2024 nor 2025 whole, until it chose one representation per publication (`extract._files`).
- **SINAN-TOXC's classification and outcome, and what its links can match (2026-10-12).** `CLASSI_FIN` holds 1, 2 and 8 (2021: 2,346 / 794 / 372, 364 blank): the generic form names 1 "Confirmado" and 2 "Descartado" (Protocolo de notificação e investigação, 2018, p. 23, Figura 1); DATASUS's `CLASSIFI` table names 8 "Inconclusivo". `EVOLUCAO` 1 is "Vivo" in DATASUS's table and "Cura" on the generic form: two claims, both kept here; the labels follow DATASUS's table (2 and 3 agree: deaths by the condition and by another cause). TOXC carries an age (`NU_IDADE_N`), not a birth date: its links match a birth date derived from age and onset, so a pair they miss is a person counted twice in a capture–recapture (TOXC × SIH 2021: 365 children on both lists of 2,337 confirmed notifications and 2,110 admitted). SINAN-SDTA holds 2 B58 outbreaks in 2018, none notified in Santa Maria.
- **Toxoplasmosis' Nota Técnica 133/2022-CGZV/DEDT/SVSA/MS** (`sources/sinan_docs/Nota_Tecnica_Toxoplasmose.pdf`). Gestational = a notification with ICD-10 O98.6, P37.1 or B58 of a pregnant woman aged 10-49; congenital = the same codes in a child under one year. Data valid only from 2019; a year's national database is frozen three years after the notification year; ICD codes are sometimes entered wrongly (pregnant women with B58 or P37.1); the data may not be representative; the form is the generic Ficha de Notificação/Conclusão. Declared as `source_notes` (ADR-0160), as is Rotavirus' 30/2024 (sentinel surveillance of under-5 diarrhoea, not compulsory notification). Also declared
  (2026-10-11):
  - foodborne outbreaks' 45/2024. An outbreak is two or more ill from one food or water, or one case of botulism or
    cholera. The free-text agent and food fields are standardised into AGENTE_ET1-3 and ALIMENTO_C with "Ignorado",
    "Inconclusivo" and "Inconsistente". The database is frozen after three years.
  - Creutzfeldt-Jakob's 48/2025. It means A81.0, notified since 2005. Records change for two years. Confirmation was
    intermittent (no brain histopathology for years). Cases unclassified after 60 days were set to "Inconclusivo".
  - exogenous poisoning's 5/2026 (downloaded 2026-10-11 from `/dissemin/publicos/SINAN/DOCS/`, the only other note
    there). It selects methanol, lead and mercury poisonings by text descriptors and exclusions over the free-text
    agent fields. TabNet applies that selection.
- **The Ministry's own notes on SIM, SINASC, SIH and SIA (2026-10-14).** Declared as `source_notes` (ADR-0160) on SIM-DO,
  SIM-DOFET, SINASC-DN, SIHSUS-RD and SIA-PA, every statement carrying its document and page:
  - Portaria SVS 116/2009 arts. 34-37 (`sources/sim_tab/Docs_Tabs_CID10/DOCS/Legislacao_PDF.pdf`, pp. 97-98): SIM and
    SINASC data are preliminary from 30 June to 30 August and official by 30 December of the year after the year of
    occurrence, so `final_after_years: 1`; the TabNet notes add that corrections still occur.
  - The DO and DN manuals (MS/SVS 2022, bvsms) define death, foetal death and live birth; the TabNet *notas técnicas* and
    RIPSA's *Indicadores básicos*, 2nd ed., 2008 (`tabnet.datasus.gov.br/tabdata/livroidb/2ed/capitulo[A-F].pdf`, one
    "Limitações" list per indicator) give the limits: coverage of the SIM (90.1% of estimated deaths in 2004, 72.4% in
    the Northeast) and Sinasc (75.1% of estimated births in 1994, 89.4% in 2004), ill-defined causes, SIH counting only
    admissions paid by the SUS (an AIH, not a person). RIPSA's figures are dated 2004; no newer ones were found.
  - The DATASUS *Informe Técnico SIASUS* says PA holds BPA-C, BPA-I, APAC and RAAS records from January 2008, and that
    PA_MUNPCN is the establishment's municipality when the patient is not identified (BPA); the consolidated rows of AC
    2023-01 hold 999999 there (the SIA.PA event note in declared.yml), so the two claims differ and the note cites only TabNet's: the
    residence is available for BPA-I and APAC only.
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

### CNES complementary beds in TabNet (measured 2026-10-25)

TabNet's `leiutibr.def` (Leitos Complementares) classifies by `TPCO_LEITO` (type and code) through `Leitos_compl2.cnv`, which holds the COVID-19 beds the label pack's ESP_LEIT lacks: 351 UTI adulto II COVID-19, 352 UTI pediátrica II COVID-19, 396 Suporte Ventilatório Pulmonar COVID-19 (`CODLEITO` 51, 52, 96 of type 3). They are in the LT files of 2020-2021 (code 51: 19,859 existing beds in December 2020, 24,559 in 2021) and absent in December 2019, 2022 and 2023. LT is published monthly; 2026-09 appeared on 2026-10-15.

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

### CNES-PF: hours and occupation codes change meaning at 2011 (measured 2026-11-24)

- **Hospital hours sit in HORAOUTR before 2011.** Share of professional records with hours > 0 (lake, December
  competence, BR):

  | year | HORAOUTR | HORAHOSP | HORA_AMB |
  |---|---:|---:|---:|
  | 2008 | 29.4% | 5.9% | 74.0% |
  | 2010 | 32.6% | 7.9% | 73.2% |
  | 2011 | 9.6% | 32.3% | 73.2% |
  | 2013 | 11.8% | 32.9% | 72.0% |

  Alagoas 2010 against 2011: HORAOUTR plus HORAHOSP sum to 217,622 and 232,783 hours, so the total holds while the
  split flips. A series of hospital hours across 2010-2011 breaks unless both columns are read together. Reported by
  t10: neurosurgeons' HORAHOSP was 1,310 h in 2010 against 42,789 in 2011.
- **Occupations change CBO edition at 2011:** the neurosurgeon is 223140 to 2010 and 225260 from 2011 (OQ 103).
- The lake holds one competence a year for 2009-2013 (December), so the month of the switch is not measured here.

### CNES December files as municipal supply (measured 2026-10-05)

- **Layout.** `CNES/200508_/Dados/<DS>/<DS><UF><YY>12.dbc` on the mirror (the S3 key has no `dissemin/publicos` prefix). Compressed December files for 2005-2025: ST 277 MB, LT 13 MB, EQ 131 MB, EP 49 MB, PF 3,795 MB (SP 2023 PF: 68 MB, 0.5 GB peak, 28 s). EP starts 2007-04.
- **Keys.** EQ `TIPEQUIP` (one character) + `CODEQUIP` (two) is the kit's code without its leading zero (CT is '111'); LT `QT_EXIST` = `QT_SUS` + `QT_NSUS` (off by 17 in 2008, exact in 2015 and 2023); `VINC_SUS` is only 0 or 1; EP `DT_DESAT` 900001 means "not deactivated" and every team in a December file carries it; the team id is `IDEQUIPE`. Labels: `TAB_CNES.zip` (127 MB, `200508_/Auxiliar/`) members `CNV/TP_ESTAB.CNV`, `Esp_leit.CNV`, `Equip_Tp.cnv`, `DBF/EQUIPE.dbf`.
- **The team typology changes in 2020.** December 2019 teams are types 02, 01, 06, 04, 03, 45; December 2020 are 70 (ESF), 71 (ESB), 72, 76 (EAP). ESF-type teams go from 43.6 k to 49.0 k across the change.
- **Specialists before 2011 are 2231xx codes** (measured 2026-11-07, ADR-0215): December 2010 has no 2252xx code; the same CNS in the same municipality moves 223144 → 225265 ophthalmologist (84%), 223136 → 225103 infectologist (55%), 223149 → 225124 paediatrician (66%). EQ's ophthalmic codes (337-350, slit lamp 349) first appear in December 2013.
- **HB and SR December files (measured 2026-11-21).** An HB December file holds only accreditations in force (every row CMPT_FIM >= December, 2014-2024; 2-39 rows start later). Its 16xx codes are only 1601, 1602, 1615-1618 (1618 from 2023); the neurosurgery codes 1606-1614 of the codelist do not occur. SR `SERV_ESP` 105 is neurology/neurosurgery (785 establishments, 2023). CBO 223140 / 225260 neurosurgeon and 223142 / 225112 neurologist are continuous across 2010-2011; 225355 radiologista intervencionista exists only from 2020; 225350 is the neurophysiologist.
- **Physicians in PF** carry CBO 2231xx (the original 2002 codes, flagged "not in the current CBO 2002" by the label pack) as well as 225xxx. Distinct `CNS_PROF` physicians summed over municipalities are 805,369 in 2023, above the profession's own count (about 570,000, CFM): a CNS is not one per person, and a person can work in several municipalities.

### SIM codes changed in 1996 under the same names (measured 2026-10-05)

The SIM kits `CID9/TAB/OBITOS_CID9_TAB.zip` (1997 files) and `CID10/TAB/OBITOS_CID10_TAB.zip` (2024) carry **same-named `.CNV` files with different codes**. Checked against the layout `sim2025.txt` (CGIAE/DASNT/SVS, 07/2025) and against the records (cause of death by code, RJ 1990 and 1995, Acre 1996 and 2000):

| Field | 1979-95 (`TIPOVIOL`, `LOCOCOR`) | 1996 on (`CIRCOBITO`, `LOCOCOR`) |
|---|---|---|
| violent death | 1 homicide, 2 suicide, 3 accident, 4 other, 0/9 ignored | **1 accident, 2 suicide, 3 homicide**, 4 other, 9 ignored |
| place | 1 hospital, **2 street**, 3 home, 4 other | 1 hospital, **2 other health establishment, 4 street**, 3 home, 5 other, 6 indigenous village, 9 ignored |

The 1996 `.DEF` binds `CIRCOBITO` to `TIPOVIOL.CNV`, which in that kit is the new coding. The schema, not the year, decides in 1996-98: `DOFET96` and `DOFET98` still carry `TIPOVIOL` with the old codes, `DOFET97`, `DOFET99` and `DORES` 1996 on carry `CIRCOBITO` with the new ones. `SINASC` kits split the same way (`ANT` 1994-95, `NOV` 1996 on; `RACACOR` 1 is Amarela before 1996, Branca after).
- **Extent.** 35 same-named codelists differ between the two eras of the kits (SIM 21, SINASC 14), 19 of them in meaning (SIM TIPOVIOL/CIRCOBITO, LOCOCOR, ESTCIV 5, GRAVIDEZ, INSTRUC, SEMANAS, PARTO, IDADEMAE, NUMFILH; SINASC RACACOR, GESTACAO, PRENATAL, GRAVIDEZ, INSTRUC, PARTO, PAISES), the rest an age band the 1979-95 kit leaves "Ign" or a spelling. EVALUATION 2026-10-05 (SIM code eras).
- **SIM's dictionary (tabela DO, updated 07/2025) writes some code lists inline (2026-10-12).** `TPOBITOCOR`'s nine
  codes run on as "1-Durante a gestação, 2- Durante o abortamento, …, 9- O óbito não ocorreu nas circunstancias
  anteriores, Branco - Não investigado". The harvester had read them as one label of code 1, which was wrong. It now splits
  them and reads "Branco" as the meaning of a blank, not as a code. `SERIESCMAE` and `SERIESCFAL` hold "Números de 1 a 8",
  the last school grade completed: the value is the grade itself, and no code table exists.
- **SIH's congenital toxoplasmosis admissions (P37.1) in Rio Grande do Sul step up from 2018 because two hospitals
  begin coding it (2026-10-13).** Principal AIHs with P37.1 as the main diagnosis, nearly all "tratamento de infecções
  específicas do período perinatal", rise from 66 (2017) to 118 (2018), 124, 118, 111, then 76 and 70 (2022–2023):
  - Hospital Universitário de Canoas (CNES 3508528): 0, 11, 50, 52, 42, 28, 15, 25 over 2016–2023;
  - Hospital Materno-Infantil Presidente Vargas (2237822): 0 until 2018, then 17, 15, 28, 19, 6;
  - the other hospitals are flat.
  It is recording at two facilities, not incidence. Nationally, P37.1 admissions per 1,000 live births rise 4-fold over
  2010–2024 (0.21 → 0.87), with deaths flat (about 30 a year).


### SIM undercounts head injury among in-hospital deaths (measured 2026-11-24, ABNc t06)

Of the SIM certificates linked (`sih_admissions_to_sim`) to 84,512 SUS stays that ended in death with a principal head-injury
diagnosis (S06), 2015-2023, **66.9% carry S06 on any line** (LINHAA-D, LINHAII or CAUSABAS). The share falls with age (76.4% at
15-29, 55.7% at 75+), with the certifier (77.3% by the forensic service, ATESTANTE 3, against 37.6% by the attending physician, 1)
and with time to death (72.3% at 2-7 days, 51.3% at 31+). False links do not explain it: on links made by the stay's own AIH
67.8% carry S06. Of those without S06, 44.8% have an external underlying cause, 16.2% T06/T07 and 13.0% S02, and 24.7% I60-I64
(mostly stays billed S06.5: a spontaneous haemorrhage billed as trauma or a traumatic one certified as stroke, which neither source
separates). **A count of head-injury deaths from SIM's cause lines undercounts in-hospital ones by about a third**, unevenly by
age and certifier. ABNc QUESTIONS Q-12; t06 data notes and `t06_s3_certification.json`.

## Facts read off the codes the whole partitions left bare (measured 2026-10-24; docs/evaluation/2026-10-24-bare-codes-whole-partitions.md)

- **DATASUS publishes its CID-10 of 2019.** `SIM/CID10/TAB/CNVS_CID10_v2019.rar` (1.1 MB, 2025-10-13) holds 58 files: one `CID10_NN.CNV` per chapter (full descriptions, flat; `_ST` the same as a tree), `CID10_3DN.CNV` (the 2,065 three-character categories), the sex-restricted and trivial-cause lists. A line starts `&` when the code is new since 2008, `@` when reworded, `#` when retired (`A90 ... >> A97`); some descriptions are cut at the column. `SIM/CID10/TABELAS/CID10.DBF` (2020-05-11) differs from its 2011 copy by 59 added codes (U07.1 among them) and still lacks A97, R65, K64 and C86. DATASUS's v2019 table keeps A09 undivided, WHO's 2019 edition has A09.0 and A09.9, and the SIM files of 2025 write them (3,313 and 1,741 cells of `CAUSABAS` in the year's largest file): they read through the category fallback ("categoria A09 ... não consta").
- **TabWin's "Ign/Branco" is `,0-9`.** In the SINAN kits' `Sim_nao.cnv`, `Resultado.cnv`, `Sorodeng.cnv`, `Classdeng.cnv`, `Reage.cnv` the first line sends blank and every digit to "Ign/Branco" and later lines override the digits they list, so a digit no line lists (0, 9, or 4 in `Reage.cnv`) is tabulated Ign/Branco. `Classdeng.cnv` lists 8 as `Inconclusivo`, which the Sinan Online dictionary of 2015 omits (`LeptoNET.def`'s `Classifi.cnv` the same).
- **Espírito Santo's dengue file is zero-filled.** In SINAN-DENG 2018-2024 every cell of 0 in `SOROTIPO`, `HISTOPA_N`, `IMUNOH_N`, `RESUL_*`, `CLINC_CHIK`, `EVOLUCAO`, `CLASSI_FIN`, `CRITERIO`, `ALRM_*`, `GRAV_*` (and of 9 in the sign and condition fields) is on a notification of that state (SG_UF_NOT 32; none of the other 26 UFs), where the form was not answered; its `TP_SISTEMA` 0 (8,726 rows in 2021, 136,988 in 2024) marks two batches. `NDUPLIC_N` is 2 on no dengue row.
- **SIA `MN_IND` is `M` or `U`, never the kit's `I`.** In SIA-PS 2012-2025 `U` is on the rows of the 22 establishments whose `CNPJMNT` ("or zeros if it has none") is blank, and `M` on all but 0.01 % of the rows of the 3,053 that have one.
- **SIA `AQ_TRANTE` is 0 on 47 % of the chemotherapy APACs** (2023-2025), on every row of 157 of 338 establishments, and 28 % of those rows give a previous treatment; `AP_UFNACIO` holds two-character values (28,257 of 8.3 M rows, 18 establishments), `10` for most.
- **SIH-RD's `DIAGSEC9` is `C(1)` in the file header** (4,592 + 457 files): the ninth secondary diagnosis is kept as its first character.
- **The Painel de Oncologia dictionary prints the stages `0 - 0, 1 - I, 2 - II, 3 - III, 4 - IV`;** its `ESTADIAMENTO.CNV` carries the digits as their own labels.
- **CIHA's `GESTAO` holds `D` on 11 to 15 % of the rows;** its kit lists 0, 1/M, 2/E and 3-9, the CIH kit "Dupla = D", and the 836 hospitals in both files of 2011-01 to 2011-04 agree on the code.
- **SINAN-TUBE's `POP_SAUDE` and `POP_IMIG` hold 3 in São Paulo alone** (4,804 and 389 of 24,922 notifications in 2023; 2019-2023, no other UF, never in `POP_LIBER` or `POP_RUA`), where the dictionary prints 1, 2 and 9. `TPUNINOT` is C(2) and holds `2` and ` 2` (left- and right-justified), never `02`: the single digits 1, 2, 4, 5, 7 are the single-digit-capable codes of `TipoUnidade.cnv` (01, 02, 04, 05, 07), left undecoded because the table is keyed `02`.

## Facts read off the context sources' files (measured 2026-10-19; docs/evaluation/2026-10-19-dataset-use-and-context-roles.md)

- **SISAGUA headers.** The surveillance basic files and the control's other-parameters and outside-the-standard files use the system's `NO_`/`CO_`/`NU_` names, the other three (the surveillance other-parameters and cyanobacteria files and the control's basic file) the dictionary's accented ones
  (`Código IBGE`, `Ano de referência`); the monthly control's basic file has no per-sample columns (`Campo`, `Valor` per parameter and month). In the surveillance basic files `ANALISE_REALIZADA`
  and `PROVIDENCIA` are filled to 2022 and `DT_ANALISE`, `LD`, `LQ` from 2023. The outside-the-standard file pads every value with blanks to its column width, and the dictionary says its
  results are not obligatory to fill; the other-parameters control holds the kind of company (`Empresa Estadual`) in the column the dictionary calls Local or Regional.
- **SNGPC.** ANVISA's open files have no pharmacy, prescription or patient identifier; the 2020 dictionary says a row can stand for several identical sales. The industrialised files write whole numbers
  with a trailing period (`TP_RECEITUARIO` `5.`, `NU_IDADE` `67.`), the compounded ones do not. The dictionary of February 2026 (v3.00) lists the prescription codes `1`-`5`; the 2020 one lists none.
- **BNAFAR.** `codigo_cnes` is served as a number (leading zeros lost); the endpoint returns the establishment's address and contact fields beside the ones landed. REGIAO's `municipio` carries its state (`AL - AGUA BRANCA`).
- **S2iD** (MIDR, 76,190 events 1991-2025): the human-damage columns are per-event counts that cannot be added as persons (`DH_OUTROS AFETADOS` sums to 295,022,756); the dictionary published is that of 2021, with other column spellings.
- **ANS PDA-024** has 22 columns (the dictionary `dicionario-pda-024-informacoes_consolidadas_de_beneficiarios.ods`, updated 2024-06-25); **INEP's school census** has 426, with a dictionary in each year's zip (`ANEXO I`).

- **Census 2010 sample microdata** (`ftp.ibge.gov.br/Censos/Censo_Demografico_2010/Resultados_Gerais_da_Amostra/Microdados/<UF>.zip`, `SP1` and `SP2_RM` for São Paulo; `Documentacao.zip`): fixed-width records with CRLF line ends, one file per state and record type: Domicilios (172 characters, 76 variables), Pessoas (540, 244), Emigracao (74, 19), Mortalidade (66, 19), positions, digits and code lists in `Layout/Layout_microdados_Amostra.xls` (sheets DOMI, PESS, EMIG, MORT; the code list is the text of the NOME cell). The first 44 characters are the same key block in every record: `V0001` UF (1-2), `V0002` municipality (3-7; the 7-digit IBGE code is positions 1-7), `V0011` weighting area (8-20), `V0300` control (21-28, unique per household within a state's file, the key from person to household), `V0010` sample weight (29-44, 3 integer and 13 decimal digits, point implied). Weighted by `V0010` AC sums to 733,559 and RR to 450,479, the census populations; race by municipality (SIDRA 136) matches in every cell (checked 2026-11-23, `docs/evaluation/2026-11-23-census-2010-microdata.md`). The emigrant records weigh 14.0% above SIDRA table 3172 (491,645 emigrants, all 27 states above): the emigration question is in both questionnaires (IBGE methodology p. 284, "investigada censitariamente"), so 3172 is a count, the file holds the sample's records only, and no subset of them gives the municipal counts (a municipality of 4 emigrants has one sampled record); the weight is the sample's own (equal to the weighting areas' initial weights to 0.16%). Use 3172 for the total, the file for composition (`docs/evaluation/2026-11-23-census2010-codes-emigrants.md`). The code lists of the variables are workbooks in `Documentacao.zip`, `Anexos Auxiliares/`: UF (7-digit, `xx00000`), municipalities (5,590 codes, but not Acrelândia 1200013 and Urucará 1304302, and `9999999` is in none), countries (`8000` plus the ISO number; filed twice, the `Países` copy lacking 8000710), COD 2010 occupation (the military residuals are numeric cells that lost their zero: `0299`, `0599`, `0999`), CNAE-Domiciliar 2.0, courses (`085`, `097` likewise), religion (`Religião 2010.txt`, 150 codes) and the Census 2000 activity (sheet `Plan2`) and occupation (PDF) lists. Unlike 2022's public sample, the 2010 records carry the municipality and the weighting area.
