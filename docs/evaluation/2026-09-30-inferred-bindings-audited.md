# The 73 inferred code-table bindings, measured

**Date:** 2026-09-30.

**Regime:**
- branch `linkage`, fresh home `~/pegasus_fresh`, live FTP;
- one slice per dataset, as named below.

**Who measured.** A sonnet agent, reporting observations apart from
interpretations. Every change below was measured again before it was made.

**Why this count.** OQ-64 asks which inferred descriptions are wrong. The
riskiest are those that also bind a code table: a wrong binding puts a label
on every value. For each binding, two things were counted:
- the share of observed values the table decodes;
- a plausibility check that a coincidental fit would fail:
  - municipality: UF prefix against the file's state;
  - ICD: code pattern and subject;
  - CNES: width.

**Counted.**
- **Supported:** high decode share and the plausibility check passes.
  - municipality: IBGE `MUNCOD` 100%, RESP `ID_MN_RESI` 99.996%, SIA-PA
    `PA_MUNAT` 100% (all `28` in SE), SIH `MUNIC_LOC`, `MUN_MOV`, `MUN_RES`;
  - SIA `*_GESTAO` (AC, CO, OP) 100%;
  - SIA-ABO comorbidity ICD codes 100%;
  - UF codes in SIH-ER, SIH-MT and SINAN.
- **Unmeasurable:** SIA-UD (31 columns), SIA-EX, PC and PF have no files in
  the catalog; two columns are never observed.
- **Suspect:** 18 columns, in the table below. None read as a wrong label;
  each read as undecoded (`code (?)`).
- **The agent's categories sum to 74 against 73 bindings** in the curation
  (recounted); the difference was not traced.

| binding | measured | action |
|---|---|---|
| SINAN `CON_MUNICI`, `CON_INF_MU`, `CLI_MUNICI`, `CONF_INF_M`, `MTRANSFU` → BR_MUNICIPALFA | 0–0.04% decoded; the values are 7-digit IBGE codes (LTAN 2003: 99.6% current IBGE codes) | **ADR-0118**: a 7-digit table chained after the 6-digit one; LTAN 28,349 of 28,715 now decode |
| SIM-DOFET `LINHAA_O`–`LINHAD_O`, `LINHAII_O` → ICD10 | 0% decoded: several codes per cell, each after `*`. The curation called the `*` ICD's asterisk notation, which it is not. | **fixed**: declared multi-valued with SIM-DO's own `*` rule; 2014: 30,831 of 30,831 (`LINHAA_O`) and 11,746 of 11,746 (`LINHAB_O`) decode; the note is corrected |
| SINAN `DS_TRANS1`–`3` → BR_MUNICIPALFA | only 2 values observed, both text ("ÔNIBUS", "Sem De") | **fixed**: binding removed; described from the observation |
| e-SUS `LAB_CNES` → CADGERBR | 21,834 of 21,834 values are `0` | description records it; `0` stays undecoded |
| SINAN `TPUNINOT` → TIPOUNIDADE | TUBE 2019: 15.8% decode. The single digits 1–7 fit CNES types without their leading zero (no 3 or 6, which CNES lacks). | OQ-61: widths are never padded |
| SIM-DOREXT `CODINST` → CODINST | 411 of 411 undecoded | OQ-61 |
| SIM-DOREXT `CODPAISRES` → PAIS | 243 of 411; the rest 1–2 digits against a 3-digit table | OQ-61 |
| SISCAN `CNPJ_MANT` → CNPJ_BR | 5–6% decoded; all well-formed 14-digit CNPJs | kept: an open namespace the table covers only in part |

**Findings.**
- **No inferred binding produced a wrong label.** Where a binding misfit, the
  values stayed undecoded: exact widths did their job.
- **Two inferred descriptions were wrong in substance:**
  - `DS_TRANS` holds text, not a municipality;
  - the DOFET `*` is SIM's separator, not ICD notation.
- **The largest decode gain was a missing table, not a wrong binding:**
  seven-digit municipality codes.
