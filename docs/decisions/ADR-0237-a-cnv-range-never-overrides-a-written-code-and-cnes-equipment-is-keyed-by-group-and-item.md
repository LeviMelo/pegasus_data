## ADR-0237: A `.CNV` range never overrides a code written out; CNES equipment is keyed by group and item

**Date:** 2026-11-25. **Status:** active. **Amends** the last-match rule of `semantics/cnv_parser.py` and ADR-0088
(composite keys). **Request:** the author, 2026-11-25: decoding is a core part of pegasus_data and cannot be left
incomplete (ABNc discussion of CNES).

**Context.** Measured on CNES, AL, 2026-11-25.
- `NIV_HIER.CNV` writes levels 01-08 one per line and closes with `NH não informado → ,00-99`. Read last-match-wins,
  every level was "NH não informado" (CNES-ST 2010-12: 2,329 rows with a level, all mislabelled). 22 of the 777
  harvested `.CNV` files put a wider expression after a narrower one; in three the change of rule changes a label
  (`NIV_HIER`, `AMB_HOSP`, `NATUREZA`'s `00`), the others are tree files and lists, which keep last-match.
- `CODEQUIP` had no codelist. TabWin reads it from `TIPEQUIP` on (`Equipamento.def`), so the code is the group
  followed by the item: `equipam2507.cnv` (3 wide) until 202507, `equipam2508.cnv` (4 wide, `TIPEQUIP` in two
  characters, group 10 created) from 202508. `TIPEQUIP` was bound by measurement to `TP_EQUIPAM` (groups 1-8), leaving
  group 9 and every code from 202508 undecoded.
- `CODLEITO`'s curation wrote three COVID-19 codes inline and named no table beside them, so the inline table was its
  only one: no specialty decoded in AL 2015-12 or 2023-12.

**Decision.**
1. In a `.CNV`, a code reached only through a range never overrides a line that writes the code out; between two
   ranges or two written codes the last wins (`CnvCategory.ranged`, `CnvFile.mapping`).
2. `CODEQUIP` is keyed `[TIPEQUIP, CODEQUIP]` with `EQUIPAM2507` then `EQUIPAM2508`, `TIPEQUIP` decoded by
   `GRP_EQPAM2507` then `GRP_EQPAM2508`: the tables share no code, so each year is decoded by the table of its width.
3. `CODLEITO` names `ESP_LEIT` behind its inline codes.
4. The shipped pack takes the corrected `NIV_HIER` and `AMB_HOSP` rows from a rebuild (35 rows in, 2 out); the rest
   of the rebuild is not shipped (OQ 114).

**Consequences.** AL, after `curate`: CNES-ST 2010-12 `NIV_HIER` labelled on 95.9% of rows (the rest null); CNES-LT
`CODLEITO` 100% in 2015-12 and 2023-12; CNES-EQ `TIPEQUIP` and `CODEQUIP` 100% in 2023-12 (12,355 rows) and
2025-12 (13,300). No ABNc paper read these labels (they filter on codes: t02's `110`), so no certified number moves.
