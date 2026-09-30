## ADR-0104: CBO 1994 is bridged to CBO 2002 by the conversion DATASUS applied, measured, and all bridges are one resource

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0101.

**Context.**
- **CNES changed occupation classification in August 2007.** Its professional
  records moved from CBO 1994 to CBO 2002 (Portaria SAS 370/2007). §2 of that
  portaria charged DATASUS with converting the registered records. No table of
  that conversion was published: the portaria and its successor (SAS 154/2008)
  list only the provisional SUS codes (2235-C1 ENFERMEIRO SAUDE DA FAMILIA, …).
- **MTE's table does not cover CNES's codes.** The Ministry of Labour's official
  CBO-94 → CBO-2002 conversion (`sources/CBO94 - CBO2002 - Conversao.csv`, from
  mtecbo.gov.br) lacks the medical family 0-61.xx and the SUS extensions CNES
  used: `06105` MEDICOS EM GERAL, `06164` MEDICO PLANTONISTA, `57282` AGENTE
  COMUNITARIO. It bridges 46% of AC's 2006 professionals.
- **The conversion can be observed.** The same professional at the same
  establishment appears in July 2007 under the old code and in August 2007
  under the new one. `scripts/measure_cbo_conversion.py` pairs them on
  (establishment, professional). The identifier forms the pair and never
  leaves the script; the artifact holds code-to-code counts only
  (`data/probes/cbo_conversion_observed.json`). In AC, PE, BA, RJ and MG it
  found:
  - 493,609 pairs over 143 old codes;
  - 138 codes that moved to one new code for 95% or more of their
    professionals: `06105` → `223115` Médico clínico (99.7% of 17,346),
    `57282` → `515105` (99.9% of 66,728), `07112` → `2235C1` (99.9%);
  - 5 codes that genuinely split: `06310` CIRURGIAO DENTISTA → `223208` 76% /
    `2232B1` 24%, by whether the dentist was in a family-health team;
  - agreement with MTE's table on 47 of the 52 codes both cover.
- **CBO labels were glued.** The canonical CBO 2002 table took its non-MTE
  codes' labels from the longest kit label, which was glued `.CNV` text ("MEDICO
  CLINICO  CLINICO GERAL MEDICO CLINICO GERAL MEDICO" for 223115).
- **Bridges were one mechanism per classification.** ADR-0101's bridge was
  SIGTAP-only (`sigtap_bridge.parquet`, `view.sigtap_bridged`).

**Decision.**
- **One resource, `resources/bridges.parquet`,** holds every bridge as claims
  (bridge, old code, new code, strength, source), built by
  `scripts/build_bridges.py`:
  - `SIGTAP_A`/`SIGTAP_H`: the official Tabela Unificada links. Strength is
    1/number of successors.
  - `CBO94`: the observed CNES conversion for the codes CNES used (strength =
    share of professionals), then MTE's conversion for other CBO 94 codes.
- **One rule** (`view.bridged`): a code crosses when one claim holds for 95% of
  the evidence or more. A code already in the target classification is itself.
  `sigtap_bridge.parquet` and `sigtap_bridged` are removed.
- **CNES `CBO` gains `CBO_2002`** (recipe `bridge: CBO94, to: CBO2002`).
- **CBO labels:** a label from a DBF column wins over a `.CNV` label, then an
  accented spelling, then the most common. Codes MTE's current file lacks are
  marked "not in the current CBO 2002": some are SUS extensions, some earlier
  CBO 2002 codes such as 223115.

**Result, new home, CNES-PF AC.**
- **2006-01:** `CBO_2002` is null for 464 of 5,381 professionals (54% before).
  Top values: "Agente comunitário de saúde (515105)" 1,063, "Auxiliar de
  enfermagem (322230)" 1,061, "Médico clínico (223115)" 337.
- **2008-01:** `CBO_2002` equals the record's own code, 0 null.
- **SIH-RD AC 2005-01, after the refactor:** `PROC_REA_sigtap` is unchanged
  (159 null; "PARTO NORMAL (0310010039)" 769).

**Sources:**
- [Portaria SAS 370/2007](https://bvsms.saude.gov.br/bvs/saudelegis/sas/2007/prt0370_04_07_2007_comp.html);
- [Portaria SAS 154/2008](https://bvsms.saude.gov.br/bvs/saudelegis/sas/2008/prt0154_18_03_2008_comp.html);
- [MTE CBO conversion](http://www.mtecbo.gov.br/cbosite/pages/tabua/FiltroConversao_CBO2002_CBO94_CIUO88.jsf);
- [DATASUS: CNES professionals from August 2007 classified by CBO 2002](https://datasus.saude.gov.br/cnes-recursos-humanos-a-partir-de-agosto-de-2007-ocupacoes-classificadas-pela-cbo-2002/).
