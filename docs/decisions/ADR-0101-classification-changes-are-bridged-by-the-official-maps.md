## ADR-0101: A change of classification is bridged by the official map, and only where the map is one-to-one

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0092.

**Context.**
- **The 2008 break.** In 2008 SIH and SIA moved from their own procedure
  tables (8 digits, `35001011` PARTO NORMAL) to SIGTAP (10 digits,
  `0310010039`). Both decode on their own side (SIH's kit tables, and SIGTAP
  since ADR-0092). But nothing linked them, so a procedure series stopped at
  2007: the SIGTAP group dimension (`PROC_REA_grupo`) was empty for every
  earlier record.
- **The official map.** The Tabela Unificada ships it: `tb_sia_sih` (8,293 old
  SIA `A` and SIH `H` codes with their names) and `rl_procedimento_sia_sih`
  (which SIGTAP procedure replaced each one). A local copy is
  `sources/sigtap/new.zip`, competence 2026-08. It has 5,381 links from 5,118
  old codes: 5,055 go to exactly one SIGTAP procedure, 63 go to two to five.
- **Measured on SIH-RD AC 2005-01:** 4,190 of 4,349 admissions (96.3%) have an
  old code with exactly one successor, 31 have two, and 128 have none.

**Decision.**
- **The map ships** as `resources/sigtap_bridge.parquet` (old code, `A`/`H`,
  old name, SIGTAP code, competence), written by `scripts/build_sigtap.py`
  from the Tabela Unificada zip.
- **A derived recipe may declare `bridge: A|H`** (`view.sigtap_bridged`). A
  10-digit code is itself; an old code becomes its successor only when the
  official map names exactly one, and is null otherwise. The bridge never
  chooses between successors.
- **The bridge feeds the SIGTAP hierarchy dimensions** (`PROC_REA_grupo`,
  `_subgrupo`), so they mean the same thing on both sides of 2008.
  `PROC_REA_sigtap` gives the procedure itself.
- **The record's own code is untouched.** `PROC_REA` still reads "PARTO
  NORMAL (35001011)" in 2005; the bridge is an added column.
- **Open.** SIA-PA before 2008 names its procedure column differently, so the
  bridge waits on the rename relation (OQ-57).

**Result, fresh home, SIH-RD AC.**

| | 2005-01 | 2023-01 |
|---|---|---|
| `PROC_REA` | PARTO NORMAL (35001011) | PARTO NORMAL (0310010039) |
| `PROC_REA_sigtap`, top value | PARTO NORMAL (0310010039), 769 rows (35001011 and 35025018 together) | PARTO NORMAL (0310010039), 334 |
| `PROC_REA_grupo` | Procedimentos cirurgicos (04), 873 rows; null 159 | Procedimentos cirurgicos (04), 1,928 rows; null 0 |
