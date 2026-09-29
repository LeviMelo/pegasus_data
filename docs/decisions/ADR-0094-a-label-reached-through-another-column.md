## ADR-0094: A label can be reached through another column of the row

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0090, ADR-0093.

**Context.**
- **The gap.** A maintainer's (mantenedora's) CNPJ is usually not itself an
  establishment, so the registry's CNPJ table (ADR-0093) cannot name it:
  5,393 rows of SIH-RD AL 2022-01 stayed `(?)` in `CNPJ_MANT`.
- **What the registry does hold.** Each establishment's maintainer by name
  (`RSOC_MAN` in `DBF/CADGER<UF>.dbf`).
- **What the layout says.** Every file that carries a maintainer CNPJ also
  carries the establishment it maintains (`CNES`, `PA_CODUNI`, …); the layouts
  define the field as "CNPJ da mantenedora" of that establishment.

**Decision.**
- **`label_via`.** A variable may declare `label_via: {column, table, field}`.
  Its label is `field` of the `table` row keyed by the same row's `column`
  (`view._label_via`). The registry keeps `maintainer` (`RSOC_MAN`) for this.
  `select=` loads the via column (`retrieve._keep_columns`).
- **Where it is set.** On SIH `CNPJ_MANT` (via `CNES`), CNES `CNPJ_MAN` (via
  `CNES`), SIA `PA_CNPJMNT` (via `PA_CODUNI`), and APAC `AP_CNPJMNT` and BI
  `CNPJMNT` (via their `CODUNI`).
- **Limit.** The registry does not store the maintainer's CNPJ, so the name
  cannot be cross-checked against the row's CNPJ. A row whose maintainer
  changed between the record and the registry's current state is named by
  the current maintainer.

**Result, 2026-09-29, live home.**
- SIH-RD AL 2022-01: `CNPJ_MANT` reads "SECRETARIA DE ESTADO DA SAUDE/FES
  (12200259000165)" and "PREFEITURA MUNICIPAL DE SANTANA DO IPANEMA
  (12250916000189)", with **0** undecoded (5,393 before).
- SIA-PA AC 2023-01: `PA_CNPJMNT` reads "SECRETARIA DE ESTADO DE SAUDE
  (04034526000143)". The 20,142 rows of `00000000000000` (no maintainer)
  stay `(?)`.
