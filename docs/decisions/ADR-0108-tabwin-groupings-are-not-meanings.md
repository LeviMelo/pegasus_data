## ADR-0108: A TabWin grouping is not a code's meaning: SIH IDENT from the layout, and catch-all ranges measured before they are trusted

**Date:** 2026-09-30. **Status:** active (first instance; the general rule is
measured under the linkage plan, workstream B).

**Context.**
- **`.CNV` files are tabulation masks.** TabWin's `.CNV` exists to group
  codes into rows of a table, not to define them. SIH's `IDENT.CNV` labels 1
  "Normal", 5 "Longa permanência", and every other code "Outras/ignorado".
  The hospitals' input layout names the types:
  - SISAIH01, `IDENT_AIH`: "01-AIH Principal / 03-AIH de Continuação /
    05-AIH de Longa Permanencia" (`sources/Layout_SISAIH01.txt`, seq 9).
  
  A continuation AIH (3) read "Outras/ignorado". omnisus labels it the same
  way (EVALUATION 2026-09-30).
- **Catch-all ranges are common.** In the shipped label pack, 17,184 range
  rows in 140 code lists carry a residual label ("Ignorado", "Outros",
  "Não se aplica", "Não informado"). Some are genuine categories:
  - ICD-9 chapter ranges;
  - "Ignorado/Exterior" for municipality codes beginning 0000.
  
  Others turn any undocumented code into a confident answer:
  - `ETNIA` 0265–9999 "NÃO INFORMADO";
  - `NIV_HIER` 00–99 "NH não informado";
  - `COMPLEX2` 04–99 "Não se aplica".

**Decision.**
- **SIH `IDENT`** is curated from the layout: 1 AIH Principal, 3 AIH de
  Continuação, 5 AIH de Longa Permanência, at RD's one-character width. The
  kit's grouping is not kept behind it: any other code stays visibly
  undecoded.
- **Catch-all ranges** are not trusted by default. Each code list's residual
  ranges are to be measured (which codes in the data they actually capture,
  and whether a document names those codes) before deciding per list whether
  the residual label stays, becomes a named category, or gives way to
  "undecoded". Tracked in the linkage plan, workstream B.

**Result.** SIH-RD AC 2023-01: `IDENT` "AIH Principal (1)" 4,164, "AIH de
Longa Permanência (5)" 1.

**Amended 2026-09-30: the audit, and a label that was wrong.**
`scripts/catchall_audit.py` runs the sweep's slices and lists the observed
codes that no bound table names individually and that render with a
residual label only through a range. A code decoded meaningfully by another
table's range is excluded (SIH `SEXO` 3 "Feminino"), and so is the
conventional all-9 "ignorado".

Two columns remain:
- **SINASC `LOCNASC` 5 read "Ignorado"** through the kit's "5–9 Ignorado". The
  2019 structure defines 5 as *Aldeia indígena*; SIM's `LOCOCOR` numbers
  places differently (5 outros, 6 aldeia). The column is now curated from
  the structure alone, and 6–8 stay undecoded. Births the old label called
  "Ignorado": AC 2022 369, Brazil 2022 1,966.
- **CNES-PF `UFMUNRES` 000000** reads "Ignorado ou exterior". The all-zero
  residence is the conventional unknown, so it is kept.

Artifact: `data/probes/catchall_audit.json`; EVALUATION 2026-09-30, "Catch-all
ranges".
