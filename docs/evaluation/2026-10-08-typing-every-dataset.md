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

**CNES counts.** 38 CNES count columns had been typed as categories (ST's `QTLEIT##` and `QTLEITP#`, `QTINST32`-`37`; DC's `QT_*`). They are numbers. QTLEITP1 holds 6, 129, 22 surgical beds; the SCNES installations table gives `QTLEIT##` as the beds of installation ##. Found while reading the SCNES layout notebook (DATA_SOURCES).

**Dataset declarations read from their names, tested against the records.** Every `confidence: low` or `medium` declaration in `ontology.yml` was a name guess. Eleven were wrong:
- **SIM**
  - **DOR** is the 1979–1995 base, filed by state of residence, not a corrected republication (`MORT98.HLP`, SIM/CID9/DOCS).
  - **DORIG** is the deaths of residents abroad or of unknown residence, 1995, not an original version.
  - **DOREXT** is the deaths in Brazil of residents abroad, from 2013, every cause; it is not a corrected external-cause base. In 2022 it holds 451 deaths, all with residence code 90…, mostly occurring in PR and MS.
  - DO's files are by state of residence and hold none of these (DO PR 2022: 0 of 89,808). DOREXT and DORIG are DO's *complement*: the declaration had warned that pooling them double-counts.
- **SINASC** follows the same pattern, from `NASC98.HLP`:
  - DNR is the 1994–1995 base by residence;
  - DNRIG is births to residents abroad or of unknown residence, 1995;
  - DNEX is births in Brazil to mothers resident abroad, from 2014 (684 in 2022).
  - A gotcha calling DNR "the denominator most published rates use" had no source and is gone.
- **SINAN**
  - **NTRA** is trachoma survey batches (school or household, numbers examined and positive), not occupational accidents.
  - **TRAC** is the trachoma case follow-up sheet. Both come from DIC_DADOS_Tracoma_v5, now harvested.
  - **ESPO** is animal epizootics.
  - NTRA and ESPO no longer inherit SINAN's shared *notification* event type: `event_types: []` now declares a dataset without one.
- **SIH**
  - **MT** is the 1995–1997 professional acts, not procedure changes.
  - **BASE_AIH1** is every approved AIH from 2008 in one DuckDB file, not a side file.

**Event types for the newly typed record files.** PegaSUS surveys 71 datasets, from 67.
- **Declared:**
  - SIM.DOREXT: death and foetal death; in 2022, 18 of its 451 records are foetal.
  - SINASC.DNEX: birth.
  - CIH.CR: hospitalisation, by ICD-10 diagnosis and SIGTAP procedure.
  - PAINEL_ONCOLOGIA.PO: cancer case, by three-character ICD-10.
  - RESP.RESP: notification (Excluído excluded), case (Confirmado) and probable case (Provável).
  - ESUSNOTIFICA.DCCR: notification.
- **Age.** PegaSUS needs the subject's age in years as a stratum.
  - CIH and e-SUS Notifica now carry the SIH and SINAN recipes.
  - SIM's sub-series and DCCR carry `IDADE_anos`; Painel Oncologia's IDADE is plain years.
  - Read on records: CIH SP 2010-06 has 123,481 of 123,481 aged, median 40 and maximum 111 (COD_IDADE 5 is 100+). DCCR 2025 has 8,256 of 8,256 aged, median 62.
- **Running in PegaSUS:** DOREXT, CIH-CR, Painel Oncologia and DCCR.
- **RESP has no age column:** its subject is a newborn or foetus. It is declared but not yet surveyed.
- **Not declared, each for its reason:**
  - DOEXT, DOINF and DOMAT are subsets of DO.
  - SIA's PA, BI, PS and SAD rows carry quantities, and an event type has no weight.
  - The pre-1996 bases are ICD-9, which PegaSUS does not read.
  - SISCAN's exams have no event kind yet.

**SISCAN's declarations split.** Each exam dataset (SISCAN.CC, HC, CM, HM, MM) was declared over both SISCOLO/SISMAMA's DBFs (2006–2015) and SISCAN's CSVs (2013–2025). A query resolved to the DBF series, so the CSVs, the current system, could not be reached at all.
- **Eleven datasets now:** the five DBF series; the five CSV exam series (`SISCAN.SISCAN_CITO_COLO`…, one row per exam); and their `_PACNT` counterparts.
- **PACNT is per patient, not a dimension.** The PACNT files carry the patient (`CO_PACIENTE`) and a summary result, and no exam key. In 2024's first rows about 97% of rows are distinct patients (CITO_COLO 72,956 of 75,497). PACNT is TabNet's "pacientes" beside the exam files' "exames"; it had been declared a patient dimension joined to the exams.
- **Read after the split:** SISCAN-SISCAN_CITO_MAMA 2013 gives 604 exams, 50 columns.

**Missing codes and ages for the new event datasets** (`scripts/propose_missing.py`, logs in `data/probes/p3/`).
- **DOREXT and DNEX:** nothing new to declare; their categories carry SIM-DO's and SINASC-DN's declarations.
- **RESP:** declared from its own form (DIC_DADOS_RESP), written by `--write` (107 lines).
- **Painel Oncologia:** declared from `Dicionario_Painel_Oncologia.pdf` (painel_oncologia/Doc):
  - TRATAMENTO 5, ESTADIAM 9, IDADE 999 and TEMPO_TRAT 99999 are not recorded;
  - TEMPO_TRAT is signed days.
  - On records, ESTADIAM is Ignorado on exactly the 157,330 rows whose TRATAMENTO is "sem informação de tratamento" (2026, of 213,834): stage is not recorded where no treatment is.
- **CIH-CR:** declared from its form, the FQA in the TAB_CIH kit: COD_IDADE 0 ignorada; MORTE and GESTAO have no missing code. COBRANCA, NATUREZA and FONTE name tables the FQA does not print, and stay undeclared.
- **DCCR (e-SUS Notifica):** its dictionary gives category labels without codes, so no code can be called "not recorded" from it, and nothing is declared. Its tabulation alone labels `000`-`009` Ign/Branco, which is not a reading of a 1-character field.
- **The age unit 5 in CIH and CIHA is decades (OQ-74 answered).**
  - IDADE 10 measures 100.0–109.9 years against NASC and the admission date, 11 measures 110–119 and 12 measures 120–126. That holds on CIH 2009–2010 (1,422 records) and CIHA MG and PR 2021.
  - SIH's unit 5 is 100 + value (SP 2015-06: 4 = 104.0–104.7).
  - The new `cih` encoding in `_age` reads 10 × IDADE, the decade's first year: a lower bound.
  - CIHA now has its age stratum and runs in PegaSUS (31 columns, 14 read); its rows without an age are its 128,261 consolidated outpatient rows (MODALIDADE 00, PR 2021), which carry no patient.

**IBGE schooling: ESCA and ESCB were summed.** IBGE.ESCA was declared over both files, so `query("IBGE-ESCA", 2010)` returned 498,155 rows and 167.7 million people. Each file alone tells another story:
- ESCA totals the population aged 15 and over: 95.35, 119.56 and 143.98 million in 1991, 2000 and 2010;
- ESCB totals the population aged 18 to 24: 19.30, 23.37 and 23.71 million.
ESCB is now its own dataset. The ages are read from the totals; no layout found states them. The declaration's own gotcha already said adding the two double-counts; the ontology did it anyway.

**Other multi-series declarations, tested on their totals:**
- PNI.DPNI and CPNI: the IG and UF variants are not read with the municipal files (DPNI SP 2015 reads DPNISP15 only).
- RESP: RESPBR is not read with the state files (PE 2016 reads RESPPE16 only).
- The SIA APAC republications are the same files under Dados_Abertos.

**Two rules for columns without a form dictionary** (`scripts/propose_missing.py`, logs in `data/probes/p4/`).
- **SINAN's yes/no convention.**
  - Of the 1,128 harvested SINAN tables with 1 Sim and 2 Não, the 943 that define 9 all define it as Ignorado. Codes 3 and 8 vary from form to form (não se aplica, indeterminado, não realizado).
  - So a form-less SINAN column, labelled 1 Sim / 2 Não by its tabulation and whose records hold only 1, 2 and 9, declares 9.
  - Run on the forms with the most candidates: VIOL 25, ACBI 8, CANC 4, TUBE 3, HANT 2, PFAN 2 and SIFC columns declared; MENI, CHIK and DENG none (their records use other codes).
  - The full sweep was stopped: about 10 minutes a form for a few columns each.
- **A code table is not a tabulation.**
  - "The tabulation alone declares nothing" was decided for SINAN, whose tabulations spread "Ign/Branco" over every undefined code.
  - A bound table that names each code the records use with its own label, and has no catch-all label anywhere, is a code table and now speaks for those codes.
  - Examples: SIA's ALTA (0 não, 1 sim); CIH's NATUREZA (01-13) and SAIDAPERM (11-24); SIFC's 1 sim, 2 não, 3 não se aplica, 9 ignorado, where only 9 is declared missing.

**The APAC code tables, and domains tested against the records** (`scripts/propose_missing.py`, logs `data/probes/p4/SIASUS-*.log`, `*.num.log`).
- Code-table declarations were written for SIA AQ (27 columns), AR (18), ATD (21), AN (19, read on 2013: AN ended in 2014) and CIH-CR (1). AP_TIPPRE 00 "não preenchido" is a not-recorded label, so NOT_RECORDED now matches it. A year in which no column is published is now reported instead of skipped silently.
- **A tabulation band is the column's domain only where the records stop at its edges.** The first AN run proposed AN_ALBUMI [1, 2], with 1,064,661 of 1,099,019 values outside it. Two band shapes do not bound their values:
  - a linear CNV (`L`), whose one or two sample codes are a display format: AN_ALBUMI, HB, TRU, INTFIS, DIURES, GLICOS;
  - a band the records run across, meaning an edge value and its outside neighbour are both held. AQ_TOTMAU labels 1–99 months; the files hold 99 (2,762) beside 100 (1,709) and 1 (79,509) beside 0 (869,185).
- A code beside an edge that the records do not reach stays outside: SIM SEMAGESTAC 99, with 98 empty.
- Columns with no value in the year are left undeclared, since nothing tests the band: AR_NUMC1–3 in 2023.
- **The committed proposed domains were re-tested the same way** (SIM-DO and SINASC-DN 2022, RESP 2016, SINAN 2021).
  - Five are withdrawn, with their sub-series copies: SINAN-ACGR HORA_JOR [1, 24] (1: 13,980 beside 0: 13,871, so 00, the first hour of the shift, had been discarded); SIM PESO [1, 8000] (1 g: 1 beside 0: 4); SINASC IDADEPAI [10, 99] (10: 3 beside 9: 1); QTDPARTCES [0, 30] (30: 17 beside 31: 1); SINAN-IEXO NUTEMPO [0, 99] (0 beside −1: 6).
  - Eighteen stand, among them AN_ALTURA [0, 254] and AN_PESO [0, 999] (outside: 999, "1,6", "56,") and CIH DIAS_PERM [0, 9999] (2 of 2.6 M outside).
- **Labels that begin with a number lost it.** The presentation layer drops a label's first word when it repeats the code (CID "O80.0 Parto…" for O800). It also cut "1,60 m" for 160 down to "m", and would cut "2.500 g" for 2500 to "g". A first word written as a Brazilian number (decimal comma or thousand dots) is now kept as the value. AN_ALTURA reads "1,69 m (169)" (AC 2013).

**Events that carry a quantity: SIA PA, BI and PS (2026-10-09, ADR-0155).** Measured on AC 2023-01 (`pg.query`, `count_events`).
| PA_DOCORIG | rows | approved procedures | patient |
|---|---|---|---|
| I (BPA-I) | 68,554 | 81,366 | residence, sex, age |
| C (consolidated BPA) | 21,398 | 1,046,221 | age only (MUNPCN 999999, SEXO 0) |
| P, S (APAC) | 4,001 | 62,860 | yes |
| B (RAAS psychosocial) | 1,461 | 2,002 | yes |
- BI equals PA's I rows (68,554 rows, 81,366 approved), and PS equals PA's B rows (1,461, 2,002), so the three are never pooled. No quantity is empty; 623 rows approve 0.
- `count_events` now returns 1,192,449 for PA, 81,366 for BI and 2,002 for PS. PegaSUS's `event_counts` and `monthly_counts` (run on AC with the store stubbed) allocate PA's 146,228 and leave the 1,046,221 consolidated procedures unallocated by municipality. BI allocates 79,876 and leaves 1,490 without an age (TPIDADEPAC 9).
- BI's `IDADE_anos` reads units 2 (0–0.08 years), 3 (0.08–0.92), 4 (1–99) and 5 (100–109). PA_IDADE declares 998 ("Idade informada com erro") missing beside 999 ("Idade não exigida (BPA-C)").
- Two documented claims were wrong and are corrected. `SIA.PA` said "no patient exists in it at all". `SIA.BI` said smaller municipalities report "through the aggregate PA instead": BI *is* PA's BPA-I rows.
- SAD equals PA's A rows: 289 rows and 289 approved in AC 2014-01, 1,631 and 1,656 in TO 2015-10. It was published 2012–2018 only (1,088 files, 19 in 2018). Its event counts 1,656 in TO 2015-10.
- A state asked of SAD for 2023 used to fail with "requested UF is not a source/publication partition". The UF axis was measured on the requested years' files, and there were none. A year with no publication now takes the axis from the dataset's other years, so the answer is NothingPublished. A state asked of SINAN, which is published nationally, is still refused.

**SIA's production families' missing codes; every event dataset readable (2026-10-09).** `propose_missing.py --sample UF:YYYY-MM` reads one state-month instead of a national year: a national PA year is ~400 M rows, and the codelists supply the codes a sample lacks.
- Code tables were declared for PA (23 columns, AC 2023-01), PS (14), BI (10) and SAD (9, TO 2015-10): RACACOR 99 'sem informação' and TIPPRE 00 'não preenchido'.
- PA_MNDIF and PA_UFDIF 9 'município de residência ignorado' had been written `missing: []`, because NOT_RECORDED matched whole labels only. Both are now declared by hand, and they were the only two such labels among the declared code tables. *(Corrected 2026-10-09: f719e4e also let any label ending in "ignorado/a" count as not recorded. That was withdrawn the same day: it took DCCR's CS_GESTANT "Idade gestacional ignorada", a pregnancy of unknown age, for an unknown pregnancy status. A phrase names its own subject, which may not be the column's. Nothing written in between used it.)*
- PegaSUS's coverage could not run on five event datasets.
  - RESP had no age column. It now derives `IDADE_anos` from DT_NASC and DT_NOTIFIC (ADR-0070 addendum).
  - SINAN COLE and TETN lacked the `IDADE_anos` stratum the other forms carry. TETN 2016's one case is 9 days old; COLE's files are published empty.
  - TRAC's ID_MUNI_RE ("Município de residência") was a mark and is now the residence stratum (2015: 24,852 records, all with an age).
  - SDTA is one foodborne outbreak per row. It had inherited SINAN's person-level notification event and now declares none; OQ-76 holds the counting of its cases, which are columns by sex and age band.
- `pegasus-core coverage`: 74 of 74 event datasets now run, with 3,556 of 6,137 columns read. Before this branch's last three commits, 70 of 75 ran with 3,374 of 5,847 read.

**SINAN's notification block, and a dictionary's annexes (2026-10-09).**
- The notification block (CS_SEXO, CS_RACA, CS_GESTANT, CS_ESCOL_N, TP_NOT) is printed by its own dictionary, DIC_DADOS_NET Notificação Individual (rev. Nov/2018, `sources/dic_notif_indiv.txt`), not by the agravos' dictionaries. Only six forms reprint CS_ESCOL_N, and all six agree with it. Every form's roles now declare the block from it:
  - CS_SEXO I, CS_RACA 9, CS_GESTANT 9 and CS_ESCOL_N 9, 212 declarations. A form whose own dictionary also defines a code as Ignorado (CS_SEXO 9 on two forms) adds it.
  - TP_NOT `[]`, in 50 forms: 1 Negativa, 2 Individual, 3 Surto, 4 Agregado, a mandatory field.
  - In the records, 9 is one character (MENI 2019, DENG 2015, TUBE 2010). CS_GESTANT 4, "idade gestacional ignorada", is a pregnancy, not a missing value. TUBE 2010's CS_GESTANT 0 (26 records) is not in the dictionary and stays undecoded.
- MENI v5's dictionary prints its laboratory, criterion and etiology codes in annexes (Quadros I–XII) that the fields cite: "Colocar o número da etiologia Segundo Quadro VIII (anexo)". `harvest_codes.py` now resolves a field's cited Quadro to the annex table printed after ANEXOS. A name the dictionary closes with a period ("LAB_CTLIQU.") is the name. 22 MENI fields gained codes:
  - LAB_* declare 62 'Ignorado'; 61 'Não realizado' and 75 'Não identificado' are results.
  - CRITERIO and CLA_* declare none.
  - LAB_PCLIQU's cell is cut at a page break and stays undeclared.
  - No other harvested dictionary cites an annex.
- `pegasus-core coverage`: 3,727 of 6,137 columns read, up from 3,556; 594 columns still lack missing codes.
- The form decides even where no record can be read. SINAN COLE's files are published empty, and TETN's hold a case or two a year. A column with no value read now takes its form's own not-recorded codes (`propose_missing.py`, logs `SINAN-COLE.form.log` and `SINAN-TETN.form.log`): COLE 26 columns, TETN 27; coverage 3,783 of 6,137. A measurement needs records to test its band and stays undeclared.
- e-SUS Notifica's DCCR (chronic Chagas) records its labels as the values ("Sim", "Nao", "EF Completo", "Ignorado"), and its dictionary (`sources/dic_chagas.txt`) has labels but no codes. A column whose records hold only written words (lowercase letters) now declares the values that read as not recorded by their own wording, and no others. 54 columns are declared (2023–2025; coverage 3,838 of 6,137): CS_ESCOL_N and CS_GESTANT 'Ignorado'; EIE, HAI, IFI and QUIMIO IgG 'Sem informacao'; the rest `[]`. PCR 'Nao Realizado', FORMA 'Indeterminada' (a clinical form of Chagas) and 'Em investigacao' are values.
- Two harvester faults hid a form's codes. TUBE's 2020 NET dictionary ends some rows in empty cells after the DBF name (TRATAMENTO, NU_PRONTUA), so the name is now read from the last non-empty cell. Its type-less rows put an internal name before the codes (BENEF_GOV: `tp-benef_gov`), so the codes are now looked for past it. The re-harvest added 40 fields over 13 forms, 13 of them with codes, and changed none. PFAN's CLI_A_S_FA 9 read "gnorado", the text layer having lost the capital; a supplement restores 'Ignorado', as its sibling fields print it. TUBE declares TRANSF 9, BENEF_GOV 9 and TRATAMENTO none: 4 "Não Sabe" is a category the form keeps apart from Ignorado.

