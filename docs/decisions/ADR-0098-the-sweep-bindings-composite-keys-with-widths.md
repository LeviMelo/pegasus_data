## ADR-0098: What a live sweep of sixteen datasets bound: composite keys carry the record's widths, path tables name their levels, and twins share tables

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0088, ADR-0094, ADR-0096.

**Context.**
- **The sweep.** `scripts/sweep_undecoded.py` ran one small slice each of
  SIH-RD/SP, SIM-DO, SINASC-DN, CIHA, CNES-ST/PF/EP/SR, SIASUS-PA/AQ/AR/AM/BI/PS
  and SINAN-HANS through `query()` on the live home. 74 columns held values
  their label left undecoded
  (`data/probes/live/sweep_undecoded-1.json`). `scripts/def_evidence.py`
  listed, for each column, the `.CNV` tables the owning system's `.DEF` uses
  and how many of the codes each one names.
- **The failures fell into kinds, not one-offs:**
  - **A composite key lost the record's width.** SIH `COD_IDADE` + `IDADE`
    read `41` for a 1-year-old: the DBF holds `IDADE` (N 2) as `01`, and
    `IDADEDET` names `401`. 386 of 4,165 AC admissions stayed undecoded.
  - **Key composition was written twice**, in rendering and in the bindings
    compiler.
  - **Twins without tables.** SIH-SP `SP_COMPLEX`, `SP_FINANC` and
    `SP_CO_FAEC` are defined in IT SIH 2016-03 as RD's `COMPLEX`, `FINANC` and
    `FAEC_TP`, which decode, measured, through `COMPLEX2`, `FINANC` and
    `TP_FINAN`. In SIA, BI's `TPFIN`, `COMPLEX` and `UFDIF`/`MNDIF` are PA's
    and APAC's fields under other names.
  - **A subtype that means something only with its type.** SIA `SUBFIN`
    (`0017`) alone is nothing. `TP_FINAN` is keyed type + subtype (`040017`
    Nefrologia), and every pair in AC 2023-01 is listed.
  - **A service named only inside its classification path.** SIA-PS `PA_SRV`
    (`115`): the service list is CNES's own table, and codelists are not
    borrowed. SIA's `S_CLASSEN` spells every code as
    "115 SERVICO DE ATENCAO PSICOSSOCIAL / 002 …".
  - **One variable, two layouts.** `CNPJMNT`'s maintainer is found through
    the row's establishment, which BI calls `CODUNI` and PS `CNES_EXEC`.
  - **Canonical tables missing.** SIA-BI `PROC_ID` was bound to the old
    `TPROC10`, not SIGTAP. SIH, CIH and CIHA ICD fields could not name `0000`,
    which their own kits' `S_CID` names "CID NAO INFORMADO".

**Decision.**
- **A key part may carry its width,** `key: [COD_IDADE, "IDADE:2"]`. The part
  is rebuilt at the layout's fixed width, zero-filled, which reproduces the
  record's own bytes.
  - This applies to a quantity or a code part whose width the layout gives.
    It is not padding a code to force a match (§6.2): the whole key must still
    match exactly.
  - `view.compose_key` is the one builder. Rendering and
    `label_bindings.compile` both call it.
- **Twins share their tables,** and each binding cites the layout text that
  makes them the same field.
- **Keys:** `PA_SUBFIN` and BI `SUBFIN` → `TP_FINAN` keyed
  `[type, subtype]`; `PA_CLASS_S` → `S_CLASSEN` keyed `[PA_SRV, PA_CLASS_S]`.
- **`PathLabels` names a leading level.** A code that is a whole leading level
  of a path table is named by that level of a listed code: `115` → "115
  SERVICO DE ATENCAO PSICOSSOCIAL". `S_CLASSEN` (3-digit levels) joins
  `VINCULO` in `PATH_CODELISTS`.
- **`label_via.column` may be a list;** the first column present wins.
- **Canonical tables and the kit's own sentinel:** SIGTAP first on BI
  `PROC_ID`, and `S_CID` after ICD-10 on 31 SIH/CIH/CIHA fields.

**Result, live home, AC 2023-01.**
- SIH-RD `COD_IDADE`: 0 of 4,165 undecoded ("3 dias", "11 meses", "26 anos").
- SIASUS-BI:
  - `PROC_ID`: "ACOLHIMENTO COM CLASSIFICACAO DE RISCO (0301060118)";
  - `TPFIN`: "Média e Alta Complexidade (MAC) (06)";
  - `COMPLEX`: "Média Complexidade (2)";
  - `UFDIF`: "Não houve invasão (0)".
- SIASUS-PS:
  - `CNPJMNT`: "SECRETARIA DE ESTADO DE SAUDE (04034526000143)";
  - `PA_SRV`: "SERVICO DE ATENCAO PSICOSSOCIAL (115)";
  - `PA_CLASS_S`: "… / ATENDIMENTO PSICOSSOCIAL (002)".

**Left undecoded, because no source names them:**
- SIH `TPDISEC*` `0`, `GESTOR_TP`, `SP_DES_HOS`/`SP_DES_PAC`, `SP_U_AIH`;
- SIA `TIPPRE` `00`, `PA_CODOCO` (its `.CNV` is keyed by a two-character
  code that the column does not hold), `PA_UFDIF` `9`;
- CNES `TP_PREST` `99`, `GESPRG1E`;
- SINASC `CODPAISRES` `1`, `KOTELCHUCK` `9`, `TPDOCRESP` `0`;
- SIM `ORIGEM`.

They read `code (?)`.
