## ADR-0092: SIGTAP is canonical, its hierarchy is a dimension, and derived columns can be selected

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0087, ADR-0089.

**Context.**
- **The question.** The user asked whether DATASUS data carries procedure or
  surgery codes.
- **What exists.** It does, throughout:
  - SIH `PROC_REA`, `PROC_SOLIC`, `SP_PROCREA` and `SP_ATOPROF`;
  - SIA `PA_PROC_ID`, `AP_PRIPAL` and the bariatric APACs' AIH procedures;
  - CIH and CIHA `PROC_REA`.
- **The codes.** SIGTAP (the Tabela Unificada, since 2008) is a hierarchy:
  group (2 digits; `04` = Procedimentos cirúrgicos) > subgroup (4) > form of
  organisation (6) > procedure (10). Before 2008, SIH used 8-digit codes from
  its own tables.
- **What each system had.** Its own kit copy of the procedure table,
  covering what that system bills, and group/subgroup/form tables bound as if
  they were the procedure's label.
- **What an analysis needs.** "Was this a surgery" requires the group; the
  procedure name alone does not say it.
- **Two defects found on the way.**
  - `select=` could not name a derived column (`IDADE_anos`,
    `PROC_REA_grupo`): `fetch` looked for it among the file's columns.
  - The planner upper-cases `select`, so a derived column with its own
    spelling was null-filled.

**Decision.**
- **`SIGTAP` is canonical.** It is built by `scripts/build_sigtap.py`: the
  union of the SIH and SIA kit copies at every level, the longest label per
  code, 6,217 codes. The official source (`ftp2.datasus.gov.br/pub/sistemas/tup`)
  was unreachable from this machine.
  - 14 procedure fields are bound to it.
  - SIH's pre-2008 tables (`TPROC`, `PROC`) stay after it. Exact-width
    matching keeps 8-digit and 10-digit codes apart.
  - Group, subgroup and form tables are no longer bound as a procedure's
    label.
- **Hierarchical fallback.** A 10-digit procedure missing from the table
  falls back to its form, then subgroup, then group, and the label says so
  (`view.SigtapLabels`, beside ADR-0089's ICD fallback).
- **Hierarchy levels as dimensions.** A derived-column recipe with
  `hierarchy: SIGTAP, digits: N` adds `<field>_grupo` and `<field>_subgrupo`
  to SIH `PROC_REA` and SIA `PA_PROC_ID`.
- **Derived columns can be selected.** `select=` resolves a curated derived
  name to its recipe's inputs, and the query's final projection matches names
  case-insensitively.

**Result, 2026-09-29, live home, SIH-RD Alagoas.**
- 2022-01:
  - `PROC_REA` reads "OPERACAO CESARIANA (0411010034)";
  - `PROC_REA_grupo` reads "Procedimentos cirurgicos (04)" for **5,383** of
    12,854 admissions;
  - `PROC_REA_subgrupo` reads "Cirurgia obstetrica (0411)", 1,904 admissions;
  - `IDADE_anos` works under `select=`.
- 2005-01: `PROC_REA` reads "PARTO NORMAL (35001011)", with 0 undecoded of
  17,649.
