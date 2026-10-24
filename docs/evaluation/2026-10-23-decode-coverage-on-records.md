# Decode coverage on real records, after the metadata work of 2026-10-19

**Regime.** `scripts/decode_coverage.py --root C:/Users/Galaxy/pegasus_core_data`, pegasus-core-fixes `a694f30`,
2026-10-23; artifact `data/probes/decode_coverage/2026-10-23.json`. Every lake family's latest partition, its first
20,000 records through the renderer (`view.render_table`, what `query` applies), every column whose role is coded
(kind category or code_tree). It measures what a reader meets, not what the catalog's stored decisions say: those date from
2026-10-08 and predate the week's curation (they had counted SINAN-DENG 31 columns undecoded; rendered, 1 is).

**Counted.** 81 families, 40 datasets (the others hold no records on this machine), 2 families unreadable (the catalog
lists partitions no longer on disk: REGIAO-MUNICIPIO, one SIH-RD generation). Coded columns holding values: 1,063.

| state | columns |
|---|---|
| labelled ("Label (code)"; every labelled column at 100 % of its cells) | 927 |
| words as filed (SISAGUA's sample points, leptospira serovars, SIES's supplies): read as they are | 70 |
| codes left bare | 66 |
| empty or constant in the sample | 95 |

The 66 bare: CIH-CR's basics (SEXO, COBRANCA, NATUREZA, GESTAO, COD_IDADE, MORTE, FONTE); SINAN-SDTA (TP_LOCAL, the
incubation flags; NU_* are counts with a category role), SINAN-SIFG (TPMOTPARC, TPESQPAR, TRATPARC), SINAN-TUBE
(IN_VINCULA, TRATAMENTO), SINAN-SIFC ANT_IDADE (an age with a category role); SRAG-NOTIF (COD_IDADE, CS_ETINIA, RAIOX_RES,
HISTO_VGM, PAC_COCBO, RES_IGG/IGM/IGA, TP_POV_CT, REINF; several `review: draft`, no document names their codes); SNGPC's
TP_RECEITUARIO (OQ 90) and CO_CID10; SIA's AP_CODEMI and AP_MNDIF on the APAC files, NACION_PAC, PERMANEN, CO_INE;
BNAFAR's CODIGO_CATMAT and TIPO_PRODUTO; SIM's and SINASC's VERSAOSIST/VERSAOSCB (software versions); SINAN FLXRECEBI;
FA's MONITORAMENTO season strings. Open question 3 carries the list.

---

## After the metadata pass (branch `meta-decode`, same day)

**Regime.** The same script and sample, on a scratch copy of the catalog with the branch's curation loaded (`ensure_current`) and the real lake read through a
junction; artifacts `data/probes/decode_coverage/2026-10-23-head-curation.json` (before) and `2026-10-23-meta-decode.json` (after). The shipped catalog's
`variable_docs` date from 2026-10-19 (5,129 docs against 5,419 in the YAML); loading the head's curation gave the same counts as the table above, so the
66 stand.

| state | before | after |
|---|---|---|
| labelled | 927 | 949 |
| words as filed | 70 | 70 |
| codes left bare | 66 | 18 |
| empty or constant | 95 | 91 |
| coded columns holding values | 1,063 | 1,037 |

**Of the 66:** 19 bound (22 more columns label: SINAN's IN_VINCULA reaches TOXC, TOXG and ZIKA too); 29 are not codes and leave the coded set; 18 stay undecoded.
- **Bound.** CIH-CR SEXO, GESTAO, MORTE, COBRANCA, NATUREZA, COD_IDADE: the tables were in the pack, windowed 200801-201012 by the kit's folder while DATASUS filed
  2011-01 to 2011-04 in it (ADR-0198). SINAN-SDTA ST_INCUB_M, MAX_ST_INC, ST_INC_ME (`1 Horas`, `2 Dias`, the notification form SDTA_FICHA.pdf) and TP_LOCAL (campo 38,
  by elimination, the table identical to campo 37's); SIFG TRATPARC, TPESQPAR, TPMOTPARC (the dictionary's campos 42-44: the docs said "not coded"); TUBE IN_VINCULA
  (the notification dictionary's `0 ou branco - Não vinculado; 1 - Vinculado`, a blank stays blank) and TRATAMENTO (campo 32, the type of entry); SNGPC CO_CID10 (ICD10);
  SNGPC-MAN DS_DCB (the record names it: 435 codes against 435 names in 333,909 rows, no code with two names, `label_from NO_PRINCIPIO_ATIVO`); SRAG PAC_COCBO
  (CBO2002; the dictionary: "Tabela ... CBO"; `XXX`, 50 of 178 filled rows, stays undecoded).
- **Not a code** (the roles' kind corrected, each with its evidence in the entry): SIM and SINASC VERSAOSIST/VERSAOSCB and FA's season strings (text); SINAN-SDTA's six
  NU_* positives (numbers, unit count: the dictionary types them numeric(4), "se negativo colocar 00") and NU_RESU_3 (text by the dictionary; its 189 non-blank values are
  the digits 0 to 9, no agent name, set aside); SINAN-SIFC ANT_IDADE (the mother's age in years, "31 Idade da mãe | Anos" on the form; the banded reading rested on a TabNet axis);
  SIASUS AP_CODEMI, CO_INE and PA_EQUIPE (organisation identifiers: institution) and SAD's PERMANEN (a number, whole 1 to 31, unit unknown as in PS's); SIH RUBRICA ("Zerado");
  BNAFAR CODIGO_CATMAT (a catalogue key: identifier); SRAG COD_IDADE (the unit digit and the age of two documented columns: 560,576 of 560,577 rows).
- **Still undecoded, with what was searched** (listed in open question 3): CIH-CR FONTE (`CNV\FONTE.CNV` is named by the DEF and absent from the kit; the layout lists no codes;
  CIHA's table is 2-digit and the column holds one digit); BNAFAR TIPO_PRODUTO (`S`, `B`, `O`: the DEMAS swagger names the filter and does not expand it; a web search found no dictionary);
  SIA NACION_PAC (RAAS layout: a 3-digit table of PT/MS/SAS 205/96; the column is CHAR (2) holding 01 to 10); SIA AP_MNDIF on six APAC sub-layouts (documented 0/1 and N/S, but AD 2012 holds
  `1` on 1,320,905 rows of which 325,688 (25 %) have two different municipalities and `0` on 45 rows, all of the same municipality (MA and SP); the samples of AM, AN, AQ, AR and ATD hold `1` alone); SINAN FLXRECEBI (an internal flag, no codes in the dictionary); SNGPC-IND TP_RECEITUARIO
  (OQ 90: `5.` until the months land again); SRAG HISTO_VGM, REINF, RES_IGG, RES_IGM, RES_IGA (the 2019-2025 dictionary, fetched into a scratch folder, names the fields and no table) and
  RAIOX_RES (its table is declared; the lake holds the float text `6.0000000000`, so it decodes after SRAG lands again, as OQ 90). Outside the 66, in older partitions:
  SIHSUS-RD 2010-2013 ESPEC (`ESPECIAL` has no window covering 2010) and CAR_INT (no table), untouched.

**What was checked in the output** (code to label, against the document): CIH-CR 2011 `3` Feminino and `1` Masculino (the layout's "1 Masculino, 3 Feminino"), MORTE `1` Com óbito, GESTAO
`M` Municipal and `E` Estadual (GESTAO.CNV lists the raw values on the right: `2,E`, `1,M`; COBRANCA `61` and `62`, 8 % of the rows, are in no CIH table and stay `(?)`); SDTA `09` Residência;
SIFG TPESQPAR `3` Penicilina G benzatina 7.200.000UI and `4` Outro esquema; TUBE TRATAMENTO `3` Reingresso após Abandono; SNGPC DS_DCB `03494` ESTOLATO DE ERITROMICINA.

**Findings.**
- "Labelled" counts that a table decoded the codes, not that it decoded them correctly. Under the 927, SIFG's TPESQUEMA labelled `2` "400.000UI 2 - Penicilina G benzatina", `3` the dose-less
  "Penicilina G benzatina" and `4` "800.000UI" (the harvest read the dictionary's two columns together, and invented a code `7`): corrected by `supplements.yml` (`drop` and the
  dictionary's four codes), TPESQPAR the same.
- Two sources disagree and both are kept (cr.yml): the CIH layout prints GESTAO as `0 / 1 / 2` where the files and GESTAO.CNV hold `M / E / D` (and 1, 2), and names NATUREZA "natureza da
  relação do hospital com o SUS" where NATUREZA.CNV lists legal forms. The earlier GESTAO entry had read the CNV's category numbering as its codes ("1 Estadual, 2 Municipal"): wrong, corrected there.
- A kit window read from a folder's name is a claim about the data in it: CIH's was four months short (ADR-0198).

**On the real catalog (same day, after the merge).** The real catalog's curation lagged the YAML (5,129 variable docs
against 5,419): `pegasus-data curate --root C:/Users/Galaxy/pegasus_core_data` (backup kept) loaded it, and the same
measurement on the real root (artifact `2026-10-23-after-curate.json`) gives the branch's figures: 949 labelled, 18 codes
left bare, 70 words as filed, 91 empty or constant, of 1,037 coded columns. Labels read against their documents: CIH-CR
SEXO 3 Feminino, 1 Masculino (CIH layout); MORTE, GESTAO; SINAN-TUBE TRATAMENTO 3 Reingresso após Abandono; SIFG TPESQUEMA
and TPESQPAR clean; SNGPC CO_CID10 by ICD-10; SRAG PAC_COCBO by CBO; CIH COBRANCA 61 visibly unlabelled.

---

## Datasets sampled from the server (branch `meta-sample`, 2026-10-24)

**Regime.** The catalog lists 154 datasets (`pegasus_core.workspace.datasets()`); the maintainer lake holds the records of 41. Of the other 113, 111 were landed one file each into a scratch home (the seed catalog, the branch's curation loaded by
`pegasus-data curate`; pegasus-core-fixes `896cfe3`) through the builder's own reader, `pegasus-data build --root HOME --family F --uf UF --years Y --limit 1`, the blob released after the decode. The file: the smallest first publication of 100 KB or more
among a dataset's four latest years; the largest of the four when all are smaller; the smallest of any year when all four are over the cap (SISCAN's national CSVs: 2013, 2022 or 2025 instead of 1.6 GB years); never over 150 MB.
Downloaded: 116 FTP fetches, 355 MB (the largest: SIHSUS-MT 1997 36 MB, SINAN-ANTR 35, SISCAN CITO_COLO_PACNT 2013 34, CITO_COLO 32, SINAN-VIOL 32), and a 0.3 MB TabWin kit read for one table.
**Skipped for size:** SIHSUS-BASE_AIH1 (its smallest publication, 11,445 MB) and DADOS_ABERTOS-DOSES_RESIDENCIA (1,117 MB). Artifacts `data/probes/decode_coverage/2026-10-24-sampled-before.json` and `-after.json`.

**Files landed.**
- CNES (13): DCSP2601, EESP1701, EFSP2601, EPPI2301, EQAM2401, GMSP2401, HBMG2601, INSP2601, LTSP2601, PFRR2301, RCMG2601, SRAM2301, STTO2301. SIASUS (7): ABSP1701, ABOSP2601, ACAC0601, ACFSP2401, AMPMG2501, BIRR2401, PARR2401.
  SIHSUS (5): CHBR2601, ERRJ2501, MTBR9701, RJGO2301, SPRR2601.
- SIM (5): DOEXT26, DOINF26, DOMAT25, DORTO92, DORIG95. SINASC (2): DNRRR1995, DNRIG1995. SISPRENATAL: PNRO1301. PNI (2): CPNIAC16, DPNIDF19. PCE: PCEBR23. RESP: RESPBR23. ESUSNOTIFICA: DCCRBR23. DADOS_ABERTOS: Cobertura_Residencia (4.9 MB).
  IBGE (9): ALF, ESCA, ESCB, IDOSO, RENDA (1991 census zips), POP24, POPSBR24, POPTBR22, PROJUF67.
- SISCAN (15): CCTO1301, CMSP1201, HCSP1301, HMSP1401, MMBA1501 and the ten exports: CITO_COLO 2013 (32 MB), CITO_COLO_PACNT 2013, CITO_MAMA 2025, CITO_MAMA_PACNT 2025, HISTO_COLO 2022, HISTO_COLO_PACNT 2025, HISTO_MAMA 2022, HISTO_MAMA_PACNT 2022, MAMOGRAFIA 2013 (25 MB), MAMOGRAFIA_PACNT 2013.
- SINAN (48 agravos, one national file each): ACBI, ACGR, AIDA, AIDC, ANIM, ANTR, BOTU, CANC, CHAG, COLE (2016: the 2021 file is 2 bytes), COQU, DCRJ, DERM, DIFT, ESPO, ESQU, EXAN, FMAC, FTIF, HANS, HANT, HEPA, HIVA, HIVC, HIVE, HIVG, IEXO,
  LEIV, LER, LERD, LTAN, MALA, MENI, MENT, NTRA, PAIR, PEST, PFAN, PNEU, RAIV, ROTA, SIFA, SRC, TETA, TETN, TRAC, VARC, VIOL.

**Counted** (the coded columns holding values, each family's latest partition, its first 20,000 records, as above):

| state | before (head curation) | after |
|---|---|---|
| labelled | 3,002 | 3,056 |
| words as filed | 50 | 50 |
| codes left bare | 596 | 350 (220 distinct columns) |
| empty or constant | 260 | 260 |
| coded columns holding values | 3,648 | 3,456 |
| labelled columns whose labels reach under 95 % of their codes | 78 | 71 |

**The measure was wrong in one place.** `decode_coverage.py` took a labelled column's share from the code column, where "(?)" never appears, so it printed 100 % for every labelled column (the sections above say so). It now reads the `<column>_label`
beside the code, null where no table held the code, and keeps the commonest `code=label` pairs in the artifact: that is how the partly labelled columns and the wrong labels below were found. The 78 are mostly codes the table does not list (0, 8, 9),
visible as such. The 40 earlier datasets were not re-measured.

**Of the 596 bare:** 55 column-datasets (33 columns) bound, 191 (186 columns) not codes, 350 (220 columns) still undecoded, with their searches in open question 3.
- **Bound** (the document named in each entry): CNES's 1-Sim/0-Não flags (DC water-treatment, dialysis, chemotherapy and hemotherapy summaries, EQ IND_NSUS, SR AMB_SUS, HOSP_SUS and HOSP_NSUS: IT_CNES_1706 §2.2, §2.5, §2.6; AP01-07CV07: the wiki and the grid's siblings);
  SINAN's ICD-10 columns (DIAG_ESP of the DRT forms, CIRC_LESAO of VIOL: the dictionaries' "CID 10"), UF_ING and UF_HOSPITA (UF_BR), TETN ESCOLMAE_N (ESCOLARNET, campo 41) and CS_OUTRAS, LER and LERD EVOL_AFAST (the numerals of "Melhora Piora 9- Ignorado" lost from the text layer; DERM and PAIR print 1, 2, 9);
  SIASUS-AC APA_TIPAPA (APAC_JUL07 campo 008) and PA_FLQT (the letter of CODOCO's two-character keys: all five (PA_CODOCO, PA_FLQT) pairs of the PA RR 2024 file are keys of the table); SISPRENATAL's three S/N flags (the kit's simnao.CNV and the ficha); IBGE ESCOLARID (TabNet escadescr.htm).
- **Not codes** (the kind corrected, evidence in each entry): CNES-DC's 51 room and equipment counts (NUMBER and NUMERIC in §2.2) and PORTARIA (free text); the SISCAN legacy files' 115 columns that the kits' DEFs list as `I` (incremento) lines, which the tabulator sums (CColo4, HColo4, CMAMA4, HMAMA4, MMAMA4.def);
  SINAN ANTR DOSES, ESQU AN_QUANT and CHAG's titres; ESUSNOTIFICA's relatives and nifurtimox counts; SIASUS-ACF ACF_FREMIT (a 1-4 grade) and AMP's four laboratory values; PCE ID_LOC (a 12-character geocode); SIM and SINASC CRITICA ("dado para controle interno"); RESP CRITERIO (seven positional S/N flags).
- **Undecoded:** SISCAN's ten exports (about 150 columns: no dictionary), the legacy files' columns no DEF names, CNES's regionalisation codes and one conflict (ESFERA_A), SIASUS AMP's codes, SIHSUS-MT, the 1979-95 SIM and SINASC fields, SINAN's leftovers, IBGE's census bands, SISPRENATAL's three.

**Labels that did not say what their codes mean** (found by reading `code=label` pairs; fixed with the source named in the entry):
- SINAN ID_UNIDADE (every agravo): bound to five tabulator selection lists beside the name tables. AB (50,625 CNES codes, all "Sim") and the NHE lists labelled 7,259 of the 8,318 labelled cells of ANTR 2025 "Sim", the others by the rank of a hospital epidemiology nucleus. Now UNIDANET and CADGERBR (the dictionary names the CNES table).
- SINAN TP_AFAST (DRT forms): the unit of the leave (1 hora, 2 dias, 3 meses, 4 anos: PAIR and LER/DORT dictionaries) was labelled by EVOL_AFAST's Melhora/Piora list: DERM's 2 read "Piora".
- ESUSNOTIFICA's 17 Sim/Não columns: "Sim" had no row (Sim_nao.cnv labels it; the pack lost it), so 30 % of AC_NOT's answers were labelled.
- RESP CRITERIO: seven positional flags decoded token by token against a table with no S or N ("N (?) | N (?) | ...").
- SINAN PFAN CLI_BICD_N and EVOR_S_MIE: the dictionary prints their lists with repeated numerals ("1- Diminuído 1. Ausente 2. Normal"), and the harvest kept them (code 1 labelled "Diminuído 1. Ausente"). The file holds the siblings' five codes
  (BICD: 89, 39, 243, 6, 161 against the triceps' 88, 37, 250, 6, 163), so the siblings' scale is restored in `supplements.yml`.
- Dictionary line wraps and a dropped capital in 36 SINAN labels ("Reagente/Reage nte" on ten hepatitis markers, "Creche/escol a", "Toxoplamas mose", "9: gnorado"), corrected.
- Read and left: SISCAN MONEXT gives codes 1 and 2 one label (its CNV says `1-2`); PNI FXET's several codes per age (the CNV's); SIM-DOR's CAUSABAS reads the ICD-9 groups of the Basic Tabulation List (pre-1996, low priority); HIVE's CS_ESCOL_N holds 2-digit codes against a 1-digit table.

**Findings.**
- Landing needed no new mechanism: `build --family --uf --years --limit 1` lands one publication, `curate` and `decode_coverage.py` measure it; 111 datasets in about 20 minutes and 355 MB. One file could not be decoded (COLE 2021, 2 bytes; the 2016 file was used).
- Roles generated from a layout's names had typed whole blocks of counts and flags as categories (CNES-DC 51, SISCAN 115): the kind was the defect, not a table.
- A sibling's definition is not evidence for a file the document does not list: SIASUS AMP's ACEVAS, SEAPTO and SITTRA carry the dialysis homonyms' documented codes (1-3, 1-4) while the file holds 0/1, S/N/I and N/R. They stay undecoded.
