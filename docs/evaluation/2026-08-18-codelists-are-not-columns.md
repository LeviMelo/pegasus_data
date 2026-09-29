## 2026-08-18 — Codelists are not columns

*Split from docs/history/FINDINGS.md §3 on 2026-09-28; text unchanged.*

## 3. Design corrections the implementation required

These are not disagreements with the brief so much as places where building the thing revealed a
structure the brief left implicit.

### Codelists are not columns

Modelling `.CNV` entries as `(system, field, value) → label`, as the brief's `dictionary` DDL
suggests, produced **1,339,916 "conflicts"** on two kits. Almost all were spurious: `SEXO.CNV`,
`SIMNAO.CNV`, `REGIAO.CNV` and dozens of others all define the code `1`, and with `field_name`
NULL they collided with each other.

Codes are now stored once per **codelist** and attached to fields through a `field_codelists`
table populated from the `.DEF` declarations. Same two kits, same data: **41 conflicts**, all
genuine.

This also avoids duplicating 5,653 municipality rows once per column that uses `MUNICBR`.
