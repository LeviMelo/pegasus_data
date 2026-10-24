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
