# Typing every dataset: all 166 catalog datasets carry roles and every column a note

**Date and regime.** 2026-10-08; branch pegasus-core-fixes, on the repo's own data home.
- Evidence: `scripts/role_evidence.py <DATASET>` writes one sheet per dataset under `data/probes/review/`. Each column's sheet holds its variable note, its form layout and a value profile. The profile reads the latest file. A column absent there is read from its own last year; a file that will not read gives way to the year before.
- Drafts: `scripts/draft_column_roles.py`, which now covers every (system, series) in the catalog.
- Each column was then decided from its sheet. The decisions are in `data/probes/review/*.review.tsv`, `legacy_fixes.tsv` and `single_fixes.tsv`.

**What was counted, and why.** The catalog datasets whose every column has a role, and the columns still drafts. A dataset without roles cannot be read by PegaSUS. A role is the column's meaning, so a wrong one is a wrong label.

| | before | after |
|---|---|---|
| catalog datasets with a role file | 72 of 170 | 100 of 170 |
| columns typed | – | 7,273 |
| columns left as drafts | about 420 | 0 |

Typed in this pass:
- **SIM:** DOEXT, DOINF, DOMAT, DOR, DOREXT, DORIG and DOFET's legacy columns.
- **SINASC:** DNEX, DNR, DNRIG.
- **SIH:** SP, MT, ER, RJ, CH and BASE_AIH1.
- **CIH:** CR.
- **SIA:** all 20 families, PA among them; PA, the main outpatient production file, had no roles before.
- **SINAN:** the 2000–2006 columns of 14 forms, ESPO from its dictionary, and the shared birth year.

Still to do: CNES (18 datasets), SISCAN (15), DADOS_ABERTOS (13), IBGE (9), PNI (6), RESP (2), SINAN COLE and TETN, e-SUS Notifica, Painel Oncologia, PCE and SISPRENATAL.

**Principles applied.**
- A 1979–1995 or 1994–1995 column takes its 1996+ role where the quantity is the same:
  - SIM: DATAOBITO is `death.date`, MUNIRES is `deceased.residence`, PESONASC is `birth.weight`;
  - SINASC: MUNI_MAE is `mother.residence`.
  This way a 1979–2024 series reads as one quantity.
- A legacy category keeps a `_legacy` role. Its codes differ from the 1996+ table: TIPO_PARTO holds 3 and 4, which PARTO does not define.
- Seven-digit legacy municipality codes carry `BR_MUNICIPALFA`, because `geography.memberships` reads both widths. No code is padded or cut.
- SIM-DOR/DORIG's cause is ICD-9 (`CID9WHO`).
- Two columns read the same in overlapping years get distinct roles, each suffixed with its own name.

**Found in the records** (a source is a claim, the records are the test):
- **SIH-SP `SP_PF_DOC` is the professional's CNS.** All 11,816 non-zero values pass the CNS mod-11 check (2026-04 RR). The Informe Técnico describes it as the legal-person document, and SP_PJ_DOC as the natural person's. The names hold and the IT's two descriptions are transposed: `SP_PJ_DOC` holds the hospital's CNES, zero-filled to 14. Both variable notes were corrected and record both claims.
- **SINAN Windows (2000–2006).** Variable notes inferred from names borrowed other forms' meanings. The values refute them:
  - MALA `MINTERNA` holds municipality codes (3550308), not a CNES;
  - MALA `PUSUARIO` is a 1/2/9 flag, not a body weight;
  - LEPT `LAB_BD` is direct bilirubin (0,2), not a batch code;
  - CHAG `SINAIS` was read as the mother's rubella symptoms, and `RAI_RESULT` holds X-ray results;
  - HANT `ANT_CONTAT` was read as anti-rabies treatment.
  Each is now named for what it holds, with the evidence, and its codes stay undecoded.
- **ESPO is an epizootic form.** Its dictionary says it counts sick and dead cats and dogs. The earlier notes read coordinates and a bite contact.
- **SIA-PQ `PAQ_DIAGSE` holds CID-O morphology** (M85003), not a secondary ICD.
- **SIA-PA `PA_CODPRO`** (1994–2007) had been given SIH's TPROC table. The TAB_SIA DEFs bind it to SIA's own PROC1199 and PROCSIA.
- **SIA-PA `PA_IDADE` 999** marks age not recorded: 141,475 of 4,813,028 rows in 2026-04 PR.
- **SIM-DOR's cause codes filled with X** (436X, 410X, 966X) are absent from `CID9WHO`. They stay undecoded, not mapped to 4360.

**Sources found by searching, not assumed absent:**
- **The FTP's `/siasus/` tree, outside `/dissemin/publicos`**, which the catalog does not crawl. It holds 214 documents (`data/probes/ftp_outside_siasus.txt`):
  - export layouts for APAC, BPA and RAAS;
  - the APAC, BPA, RAAS and SIA operational manuals;
  - oncology manuals 2008–2022;
  - layout spreadsheets 2008–2012.
  The server answers LIST but not MLSD.
- **The pre-2008 TAB_SIA kits** carry DEFs naming PF (Pacientes Medicamentos), PQ (Quimioterapia), PR (Radioterapia) and OP. **SIA.PR was in the catalog but undeclared**, so `query()` refused it. It is now declared and reads 172 records for TO 2007-10.
- **`sources/apac_layout1.txt`**, the 1999–2007 APAC layout, documents PQ and PR's oncology fields, the CNS columns and the credit assignment. 107 variable notes were added. UO's census columns are documented by no source found; they are read from their names against the oncology manual's equipment vocabulary, and said so.
- **base_aih1.duck** (12 GB, 221.5 million admissions) reads over HTTP from the mirror, its 12 dimension tables included. It was typed from its header and a 100,000-row profile.
- **SINAN Windows (2000–2006):** no dictionary is published. Searched: SINAN/DOCS, Docs_TAB_SINAN, TAB_SINANNET, Goiás's SINAN NET 4.0 mirror and the web. Those columns carry that statement on their roles.

**Second batch, the same day.** 134 role files, all of them loading:
- **CNES (13).** Each dataset's record has its own entity: establishment, bed, equipment, team, service, habilitation or professional. A column repeated from ST takes ST's role. The establishment's municipality is `where`, because a stratum must be a population property.
- **CNES's five `*UFAAMM` series were not datasets.** They were five header-only template files (`EFufAAmm.dbc`, about 1 KB), read as series names. `inventory/naming.py` now parses a template grammar: the file belongs to its series with no UF and no date. `inventory` and `families` were re-run, and the catalog lists 165 datasets, not 170.
- **Dados Abertos.**
  - The 11 APAC exports take their SIASUS family's reviewed roles, column by column.
  - `SIPNIBD/Doses_Residencia.parquet` and `SIPNIBD/Cobertura_Residencia.parquet` were declared aliases of PNI.DPNI and PNI.CPNI, so `query()` read the old DBF tables. They are another publication: SI-PNI/RNDS, by residence, another layout. Declared as their own datasets:
    - coverage: 1,088,479 rows, 2015–2026, coverage as a fraction (0.96);
    - doses: 236,140,984 rows, starting 2026-01, by sex, race, age, strategy and source system.
- **PNI (6).** Published aggregates. Coverage and dropout rates are finished rates (`measure: false`), never summed. The municipality is the place of application by its variable note, while the open-data republication is named for residence; both claims are recorded.
- **More documentation found on the FTP, outside the crawled tree.** `/cnes/Download` holds the SCNES glossary (`GLOSSARIO_SCNES_Geral.xls`), the TXT layout notebooks for SIA, SIH, CIHA and CIH, and the CBO-service glossary. `/territorio/doc` holds the territorial base documents (`data/probes/ftp_outside_rest.txt`).

**Third batch.** 150 role files.
- **SISCAN (15).** The SISCOLO and SISMAMA DBFs (2006–2015) and the SISCAN CSVs (2013–2025) are typed apart: their layouts share no column names. The ontology binds both to one dataset, so `query()` on a CSV series read the DBFs, and its sheets were built from the CSVs' first 20 MB, read over FTP (the mirror carries no SISCAN). Every column has a variable note.
  - The person's attributes are on `patient` (residence as stratum, sex, race, age, education).
  - The `NU_` result columns are 0/1 on each exam: summing one counts the exams with that finding.
- **SIH's maintainer register (`CMBRaamm.dbc`, 42 files from 2019) was filed under SISCAN.**
  - The learned prefix CM (SISMAMA's 1,670 files) outvoted the SIHSUS directory the files sit in.
  - The filename now overrides the path only in a republication tree (`republishes: true` in the ontology: Dados_Abertos). Every one of the other 2,221 recorded name-versus-path disagreements lies there.
  - SIH.CM is declared, and SIH.CH corrected: it was said retired, but its files run to 2026.
  - `inventory`, `schemas --system SIHSUS` and `families` were re-run: 166 datasets.

**Fourth batch: every dataset.**
- **The count.** 166 of 166 catalog datasets carry roles: 10,456 columns, no drafts, every role file loading. All but the derived columns have a variable note: the last 8 were written from their values and names, and say so.
- **IBGE.POP was declared over three publications.**
  - POP (censuses and intercensal estimates), POPS (SVS estimates) and POPT (TCU totals) were all aliases of one dataset, so `query("IBGE-POP", 2015)` summed them: 404.8 million in POP plus 204.5 million in POPULACAO.
  - Each is now its own dataset. POP and POPS give 202,403,642 for 2015 (the same SVS estimate) and POPT gives 204,482,459.
  - The population lake (`population`, POPSVS and POPTCU) never read through this declaration.
- **RESP:** the cheapest file of each year is published empty, so the sheet sampled the largest state-year (PE 2016, 1,174 records). Its dates are DDMMYYYY, which `role_evidence` now recognises.
- **SINAN COLE and TETN:** cholera's files are about 3 KB each. Their shared blocks take the role every other SINAN form gives the column, where at least 5 forms agree at 80% or more (23 and 22 columns).
- **e-SUS Notifica (chronic Chagas):** SINAN's names, but `ID_MN_RESI`, `ID_MUNICIP` and the like hold municipality names, and the codes sit in `CD_*`. The SINAN convention was applied only where the kind agrees.
- **Painel Oncologia** diagnoses are three-character ICD-10, the case's event type. **PCE's** `ID_LOC` is a 12-digit locality code that no municipal table matches; it is never cut to make one.
