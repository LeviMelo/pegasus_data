## ADR-0088: A code that means something only with another column is keyed by both; labels shed the codes embedded in them

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0084, ADR-0087.

**Context.**
- **The user's complaint.** CNES decodes "point to another undecipherable
  code".
- **What CNES queries showed** (live home, Acre, 2023-01):
  - **Blank labels.** CNES-SR `CLASS_SR` `001` and `SERV_ESP` `159` got the
    label `''`: "decoded" to nothing.
  - **Split keys.** A CNES service classification is keyed by **service plus
    classification**: `S_CLASSEN` `159001` = "159 ATENCAO PRIMARIA / 001
    ATENCAO PRIMARIA". TabWin's `.DEF` concatenates the two columns for the
    lookup. The harvest bound each column to the table alone, so neither could
    match.
  - **Wrong curation.** It described `SRVUNICO` as the classification; its
    values are service codes.
  - **Codes inside labels.** DATASUS tables write codes into labels, so the
    readable form repeated codes the reader cannot use:
    - `NAT_JUR` `1244` → "24 124-4 Município";
    - `VINCULAC` → "01 VINCULO EMPREGATICIO / 01 ESTATUTARIO";
    - `TIPO_EQP` → "70-ESF";
    - SIA `GESTAO` → "16eeee AP - gestão estadual Amapá", where `eeee` is a
      TabWin range mask.

**Decision.**
- **Composite keys.** A variable may declare `key: [COL_A, COL_B]`. Its lookup
  key is then the row-wise concatenation of those columns, and its own raw code
  is still what the output shows.
  - The renderer uses the key for choosing, width checks and labelling
    (`view._lookup_key`).
  - The compile measures the key, not the column (`label_bindings._keyed_docs`).
  - The key is stored in `variable_docs.lookup_key`.
- **The CNES service fields are curated from the data and the layout note**
  (IT_CNES_1706 §2.6):
  - `SERV_ESP` and `SRVUNICO` are service codes, decoded by `SRN_ORD_N`;
  - `CLASS_SR` is decoded by `S_CLASSEN` with `key: [SERV_ESP, CLASS_SR]`.
- **Labels shed embedded codes when shown.** `presentation.clean_label`:
  - In each ` / `-separated segment, it removes a leading token that looks
    like a code (two or more digits, or containing `-` or `.`) when a
    capitalised word follows. It also removes a leading TabWin placeholder
    (`16eeee`).
  - Quantities survive: "22 a 27 semanas", "10 dias", "1 dia".
  - The canonical `_label` column keeps the table's text as it is.

**Result, 2026-09-29, live home, CNES-SR AC 2023-01.** No undecoded codes in
the fields below:
- `SERV_ESP` reads "ATENCAO PRIMARIA (159)".
- `CLASS_SR` reads "ATENCAO PRIMARIA / ESTRATEGIA DE SAUDE DA FAMILIA (004)".
- `NAT_JUR` reads "Município (1244)".
- `TP_UNID` reads "HOSPITAL GERAL (05)".

**Open.**
- Other composite codes are not yet found systematically. The TabWin `.DEF`
  files declare them, as column concatenations, and the `.DEF` parser does
  not yet read that part.
- Acronym labels ("ESF") are not expanded.
