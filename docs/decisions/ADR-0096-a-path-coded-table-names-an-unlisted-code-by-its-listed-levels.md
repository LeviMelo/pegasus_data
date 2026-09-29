## ADR-0096: A code built from levels is named by its deepest listed level when the table does not list it

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0089, ADR-0092.

**Context.**
- **How `VINCULAC` is coded.** CNES `VINCULAC` (professionals) codes the
  employment bond as three 2-digit levels: bond, type and subtype. The kit's
  `DBF/VINCULO.DBF` labels every code with its path: `080501` = "08
  INTERMEDIADO / 05 AUTONOMO / 01 PESSOA JURIDICA".
- **The gap.** Acre 2023-01 carries `080701`, which the current table does not
  list. It lists `08` under seven other codes but no type `07`, so the code
  read `(?)`.
- **The stale description.** The curation described the column as the 1-digit
  2014 `Vinculo.cnv` (contratado / autônomo / não identificado). No current
  file uses that table, and the column had no explicit codelist.
- **Precedent.** ICD-10 (ADR-0089) and SIGTAP (ADR-0092) already fall back to
  a listed parent level.

**Decision.**
- **`view.PathLabels`.** A codelist in `PATH_CODELISTS` (`VINCULO`: 2-digit
  levels) names an unlisted code by the deepest level that a listed code of
  the same width shares.
  - The levels are read from that code's own path label, never from a prefix
    alone.
  - The label says which levels are undocumented: "08 INTERMEDIADO — nível
    07 / 01 não consta da tabela VINCULO".
  - A code whose first level is unlisted stays `(?)`.
- **`VINCULAC` is bound to `VINCULO`,** and its description now reflects the
  6-digit path.
- **Limit.** A table enters `PATH_CODELISTS` only when its labels are verified
  to spell the path level by level. A prefix of a CBO or CNES code is not its
  parent (§6.2).
