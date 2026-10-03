## ADR-0131: SIGTAP procedure hierarchy as dimensions, matched on leading characters only where the source's definition file does so

**Date:** 2026-10-03. **Status:** active.

**Context.**
- **No roll-up existed for procedures.** SIH `PROC_REA`, SIH-SP
  `SP_PROCREA` and SIA `PA_PROC_ID` had labels (`TB_SIGTAP`) but nothing
  above them.
- **DATASUS's own definition files tabulate them by group, subgroup and
  form of organisation.** They map the ten-character procedure code through
  `TB_GRUPO.DBF` (2-character codes), `TB_SUBGR.DBF` (4) and `TB_FORMA.DBF`
  (6):
  - `TAB_SIH RD2008.DEF` lines 261–269;
  - `SP2008.DEF` ("Grupo Proc. Principal");
  - `TAB_SIA Producao_Ambulatorial.DEF` lines 80–88.
- **How TabWin reads such a table.** It matches the field's leading
  characters to the table's code width. SIGTAP's code is built that way:
  group (2), subgroup (2), form of organisation (2), sequence (3), check
  digit.
- **The project's rule:** widths are matched exactly, and a code is never
  truncated to make a join succeed.

**Decision.**
1. **Nine `rollup_to` relations** in `joins.yml`: `procedure_group`,
   `procedure_subgroup` and `procedure_form`, for `PROC_REA`, `SP_PROCREA`
   and `PA_PROC_ID`, each citing its definition file.
2. **`source_namespace: tabwin_leading`** marks a relation whose table
   holds shorter codes than the field. Only such a relation is read on the
   leading characters, and only when the table's codes have one width. Every
   other relation keeps the exact match.
   - `source_namespace` is persisted with the relation, so the catalog copy
     keeps the rule.
3. **CIHA is not declared.** It uses the same codes, but no CIHA definition
   file was read.

**Evidence.** EVALUATION 2026-10-03 "Municipality and procedure
dimensions": SIH-RD SE 2022-01, 8,512 AIH, every row resolved. Without
the 51 long-stay continuation AIHs, the group counts equal TabNet's
"Internações" by "Grupo procedimento" exactly: 10, 5,136, 3,293 and 22.

**Consequences.**
- **`dimensions=["PROC_REA.procedure_group"]`** gives "Procedimentos
  clinicos", "Procedimentos cirurgicos" and the rest.
- **The exception to exact widths is declared, cited and confined to the
  relations that carry it.**
