# Geography from TabNet and IPEA; context fields from IBGE

**Date:** 2026-10-03.

**Regime:**
- branch `linkage`; maintainer home `pegasus_data_home`, registries cached
  under `<root>/registries/`.
- Sources over HTTP: TabNet (`/cgi/territorio/*.cnv`), IPEA geobr
  (`/geobr/data_gpkg/amc/*`), IBGE Localidades and aggregates APIs.
- `pegasus-data geography --out <scratch>` and `pegasus-data fields`.

## Geography

**Health macroregion, TabNet's `br_macsaud.cnv`** (152 lines declared in
its header):
- **5,606 codes assigned:** 5,569 of IBGE's 5,570 municipalities, plus 36
  Federal District administrative regions (5300xx), which DATASUS codes as
  municipalities.
- **124 macroregions.** The header's 152 counts lines with catch-alls.
- **Missing:** Alta Floresta D'Oeste (110001), left unassigned.
- **Examples:** Aracaju "2801 MACRO UNICA", São Paulo "3521 RRAS6",
  Fortaleza "2310 FORTALEZA", Belo Horizonte "3103 CENTRO", Manaus
  "1304 CENTRAL".

**Current health region, TabNet's `br_regsaud.cnv`:** 446 regions over the
same 5,606 codes.

**Comparable areas, IPEA geobr (Ehrl 2017):**

| period | municipalities (2010) | AMCs | largest AMC |
|---|---|---|---|
| 1980–2010 | 5,566 | 3,829 | 53 municipalities |
| 1991–2010 | 5,565 | 4,298 | 20 |
| 2000–2010 | 5,565 | 5,476 | 7 |

The PegaSUS record gives 3,830 AMCs for its 1980s-based version.

**The rebuilt pack against the shipped one** (built from the label pack
before its rebuild):
- `health_macroregion` and `health_region_current` are new (5,606 rows
  each).
- `agglomeration` grows from 2,381 to 3,325 rows and `health_colegiado`
  from 27,790 to 32,241. The shipped geography pack was older than the
  shipped label pack.
- The final pack is rebuilt after the label pack (EVALUATION 2026-10-03
  "Concept lists").

## Context fields

`pegasus-data fields --name gdp --name gross_value_added_public_administration --years 2020-2021`:
- 11,140 rows per field (5,570 municipalities × 2 years), every status
  `value`.
- **GDP 2021 sums to R$ 9,012,142,031 thousand,** Brazil's official GDP for
  2021. This checks that the municipal series adds up to the national one.
- Aracaju 2021: R$ 18,405,678 thousand.
