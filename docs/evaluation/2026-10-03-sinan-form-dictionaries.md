# SINAN form dictionaries: page-break truncation, and coded fields marked uncoded

**Date:** 2026-10-03.
**Regime:** commit 699a178 plus this change; maintainer catalog; live query `SINAN.ACBI` 2023 BR (80,094 rows, mirror).
**Scripts:** `scripts/harvest_codes.py` (regenerated `curation/codes/sinan.yml`); scratch comparison of the stored `label_bindings` against each form's own `.DEF`.

**Does a form need its own DEF bindings (OQ-4)?** Each SINAN `.DEF` names its data files (`Acbi*.DB?`), which maps 53 of 60 DEFs to a series. Of 520 measured decisions where the family's form has its own DEF:
- **442** pick that DEF's table.
- **78** pick another:
  - most are a table of the same content under another name (`CON_AMBI` vs `AMBIENTE`, `PETEQUIAS` vs `SIM_NAO`);
  - the rest are age-band roll-ups on `NU_IDADE_N`, a column the curation marks uncoded and the renderer never labels.

Writing per-family DEF bindings would change no label, so none are written. Form-dependent meaning (`TIPO_ACID`) is carried by the form's own dictionary (ADR-0080) and by width-exact weighing.

**Harvest defects found and fixed.**
- **Page breaks.** A code list that ran past a page break was cut at the break. The next page's first row, its leading cells empty, now joins the row it continues.
- **Wrapped words.** A word the cell wrapped is joined back ("Inconclusiv o", "Meningocócic a", "clínico- epidemiológico").
- **Width.** An over-width code is kept when it continues the run that fits. TUBE `SITUA_ENCE` is declared varchar2(1) yet lists 1–10, and the kit's `encerra.cnv` agrees on 10.

Result:
- 126 codes gained over 40 tables, 3 new tables, 52 labels repaired;
- SIM and RESP unchanged.

Examples:
- `SIT_TRAB` had lost codes 05–99 on six forms.
- ACBI `TIPO_ACID` had lost 05–99, and code 04 read "Administ. de".
- MENI `CON_DIAGES` 10 read "Meningite por".

**Coded fields marked uncoded.** 197 SINAN curation entries said `code_system: none` for a field whose form dictionary publishes a code table. The renderer does not label an uncoded column, so these came out as bare codes. ACBI `ANTI_HIV` showed "2" for 63,740 rows. 193 are now `internal`; the four Chagas titres stay numeric (a1a7d92). The form's table still applies only where it decodes ≥95% of a column's rows. SIM and RESP have no such entries.

**Live check, ACBI 2023:**
- `TIPO_ACID` shows all 17 circumstances (Outros 14,240; Procedimento cirúrgico 7,519; …).
- `ANTI_HIV` reads Negativo 63,740, Não realizado 4,904, Ignorado 3,907, Positivo 432, Inconclusivo 112.
- `AGENTE` gained labels (Agulha com lúmen 43,518).

**The same contradiction in every system.** Stored decisions were scanned for an uncoded column that still decodes ≥95%. Most of the 121 hits are dates, counts and ages bound to tabulation axes, and stay uncoded. 45 are coded and are now `internal`:
- the 17 ESUSNOTIFICA (Chagas) yes/no flags;
- 26 SINAN fields, among them the meningitis final codes `CLA_ME_ASS`, `CLA_ME_ETI` and `CLA_SOROGR`;
- SIH `RUBRICA` and `SP_TP_ATO`.

Live check, MENI 2023 (26,629 rows):
- `CLA_SOROGR` reads B 219, C 193, Y 21, W135 18.
- `CLA_ME_ETI` reads Cryptococcus 551.

**Meningitis lab etiologies (OQ-59).** Quadros VII–XII are in the dictionary's own annex (`DIC_DADOS_Meningite_v5`, "ANEXOS"); the earlier searches missed it. The 18 `LAB_*` fields of item 49 now carry them as inline codes:

| Quadro | Test | Fields |
|---|---|---|
| VII | culture | CT* |
| VIII | bacterioscopy | BC* |
| IX | CIE | CI* |
| X | latex | AG* |
| XI | viral isolation | IS* |
| XII | PCR | PC* |

Files write a one-digit number both padded and unpadded ("07" and "7"). The unpadded reading was tested against the final diagnosis, MENI 2023:
- `LAB_CTLIQU` "7": 400 of 476 are pneumococcal meningitis (`CON_DIAGES` 10), as are 11 of 11 "07".
- "1": 78 of 96 are meningococcal (02/03).
- "6": 33 of 44 are Haemophilus (09).

Both spellings are listed. "0" is in no quadro and stays undecoded.

Culture of CSF reads Nenhum agente 13,182, Streptococos pneumoniae 476 + 11, Neisseria meningitidis 96 + 4.

**Other annex references.** The scan found two kinds:
- **Local tables.** Most dictionaries point to "Tabela disponibilizada pelo sistema": locality, neighbourhood and facility lists kept by municipal managers and never published.
- **PFA (polio).** Items 55 and 84 are ICD-10 in dotted notation ("G61.0"), which the ICD lookup now reads as the dotless code. `ATE_HIPOTE` is bound to ICD-10. `LAB_E_D_1` (item 70) stores the list's own text, cut to 30 characters, and stays uncoded.

Live check, PFAN 2023 (620 rows): `CON_DESCAR` reads Síndrome de Guillain-Barré (G61.0) 193, which was "G61.0 (?)" before.

**Sinan Online classification.** CHIK and DENG declare `CLASSI_FIN` as VARCHAR(1) but list 5, 10, 11, 12 and 13. The width tolerance now also accepts over-width codes that form a consecutive run of their own. The regenerated harvest adds exactly these two tables. The fresh-home sweep had CHIK 2023 `CLASSI_FIN` undecoded on 238,240 rows (13 Chikungunya on 130,196, 5 Descartado on 108,044).
