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
