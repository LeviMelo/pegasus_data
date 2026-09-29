## ADR-0090: A record can name its own code; a label's inputs survive a narrow select

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0087, ADR-0088.

**Context.** A scan of all 13 CNES datasets (live home, Acre, 2023-01) after
ADR-0086 to ADR-0089 left these gaps:
- **Team identifiers with no current table.** CNES-EP files `IDEQUIPE`,
  `ID_AREA` and `ID_SEGM` whose codes are too new or too local for the kit.
  The same row carries their names in `NOME_EQP`, `NOMEAREA` and `DESCSEGM`
  (IT_CNES_1706). The kit table answered only for old codes.
- **Documented flags with no table.** The CNES technical note documents
  `LEITHOSP`, `CENTRCIR`, `QUILOMBO`, `ASSENTAD`, `POPGERAL` and the other
  indicator fields as "1-sim 0-não". The curation bound some to tables that do
  not match 0/1 (`AMB_NSUS` to `AMB_HOSP`), and bound others to nothing.
- **Bank codes.** `CO_BANCO` holds Banco Central compensation codes that no
  DATASUS table carries.
- **A narrow `select=` lost labels.** `fetch` narrowed a decoded table to the
  requested columns BEFORE rendering. So `select=["CLASS_SR"]` lost its key
  part `SERV_ESP`, `select=["ID_SEGM"]` lost `DESCSEGM`, and both came back
  undecoded.
- **SIA's "not informed" filler.** SIA ICD fields hold `0000` in most rows
  (88,592 of 95,414 in SIA-PA AC 2023-01). SIA's own `S_CID` table defines it
  as "CID NAO INFORMADO", but ADR-0087's rebinding had dropped `S_CID`.

**Decision.**
- **`label_from:`** A variable may name a sibling column that names its code.
  Its label is then that column's value in the same row: exact per record,
  current, and never a guess (`view.py`). Set on CNES-EP `IDEQUIPE`,
  `ID_AREA` and `ID_SEGM`.
- **Documented flags as inline codes.** CNES flags get inline `codes:` citing
  the technical note's "1-sim 0-não".
- **`BANCO_BR` is a canonical classification.** It is built from the Banco
  Central's "Participantes do STR" (`scripts/build_banks.py`, 464 banks) and
  bound to `CO_BANCO`. It is the current register, so a closed bank's code
  stays visibly undecoded.
- **A label's inputs survive a narrow select.** A selected column's key parts,
  naming sibling and units are loaded, kept through rendering, and dropped
  after it (`retrieve._keep_columns`, `fetch`).
- **SIA falls back to `S_CID`.** SIA's 33 ICD fields bind `ICD10` then `S_CID`;
  the canonical table decodes real codes, and SIA's own table only its
  fillers.

**Result, 2026-09-29, live home.**
- CNES-EP AC 2023-01, under `select=`:
  - `IDEQUIPE` reads "ESB ZULMIRA GARCIA (120001000102280795)", 0 undecoded;
  - `ID_SEGM` reads "ZONA URBANA (12002001)"; 4 rows of the placeholder
    `12999999` stay `(?)`.
- CNES-ST: `CO_BANCO` reads "Banco do Brasil S.A. (001)"; `LEITHOSP` reads
  "Não (0)".
- CNES-SR: `CLASS_SR` decodes under `select=`; 0 problems in the service
  file.
- SIA-PA AC 2023-01: `PA_CIDPRI` and `PA_CIDSEC` have 0 undecoded, e.g. "CID
  NAO INFORMADO (0000)" and "Transtornos globais não especificados do
  desenvolvimento (F849)".

**Still open in CNES.**
- `DT_DESAT` = `900001` (483 rows) is an undocumented sentinel in a year-month
  field, shown as `(?)`.
- Two `CO_BANCO` codes (`71X`, `002`) are not in the current register.
- One `VINCULAC` code (`080701`) and four `SGRUPHAB` habilitations are newer
  than the kit.
