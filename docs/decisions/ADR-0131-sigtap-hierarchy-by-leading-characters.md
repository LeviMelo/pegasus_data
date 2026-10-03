## ADR-0131: SIGTAP hierarchy as joins.yml dimensions (withdrawn the same day: it duplicated ADR-0092)

**Date:** 2026-10-03. **Status:** withdrawn. ADR-0092 stands, amended below.

**What was done.** Nine `rollup_to` relations in `joins.yml` gave `PROC_REA`,
`SP_PROCREA` and `PA_PROC_ID` a group, subgroup and form of organisation.
They read the kits' `TB_GRUPO`, `TB_SUBGR` and `TB_FORMA` on the code's
leading characters (`source_namespace: tabwin_leading`), citing DATASUS's
definition files.

**Why it was withdrawn.** ADR-0092 already does the job, with a better
source:
- its derived-column recipes (`hierarchy: SIGTAP, digits: N`) add
  `PROC_REA_grupo` and `PROC_REA_subgrupo` from the canonical SIGTAP table;
- they bridge pre-2008 SIH codes to SIGTAP (ADR-0101).

A second mechanism for the same job is a defect (CLAUDE §4). The relations
and the leading-character reading were removed before anything depended on
them.

**What was kept, as amendments to ADR-0092:**
1. **The form of organisation** (`digits: 6`) joins the recipes:
   `PROC_REA_forma` and `PA_PROC_ID_forma`.
2. **A derived column named in `select=` is built under every
   presentation.** The codes presentation gives its code (`03`, `031001`).
   Before, `present="codes"` turned derivations off, and
   `select=["PROC_REA_grupo"]` returned an all-null column under an
   upper-cased name, as did `IDADE_anos`. That column read like data.
3. **Derived names compare case-insensitively** with the selection, since
   the planner upper-cases it.

**Evidence.** EVALUATION 2026-10-03 "Municipality and procedure
dimensions": through the recipes, SIH-RD SE 2022-01 by group, without the
51 long-stay continuation AIHs, equals TabNet's "Internações" by "Grupo
procedimento" exactly (10, 5,136, 3,293, 22). Subgroups match too (0201: 5,
0209: 1, 0211: 4, 0301: 293, 0303: 2,906).
