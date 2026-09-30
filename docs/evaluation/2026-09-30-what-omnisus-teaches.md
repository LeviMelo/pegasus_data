# What omnisus teaches: a survey of a neighbouring project, with each finding checked against ours

**Date:** 2026-09-30. **Regime:** omnisus at commit `478b0b5` (github.com/raphaelfh/omnisus,
MIT, v0.1, created 2026-09-26), cloned read-only; pegasus_data at `redesign` after
`7e5d3f1`. Survey by four read-only agents plus direct reading; every
"already have" below was checked against our code or documents.

**What omnisus is.** A Python toolkit (≈8,400 lines, optional Rust DBF
decoder) that imports ~50 curated DATASUS/IBGE/CNES datasets into a DuckLake
lake with hash-pinned publications and `cite()`, per-dataset YAML dictionaries
(2,654 fields, 578 with code maps; 453 claims `verified_in_source`, 179
`conflicting`) and research notebooks, including a deterministic record-linkage
study with negative controls. It is researcher-facing and curated-subset; we
are whole-tree and meaning-first. Where the two overlap, each is ahead
somewhere.

**Why this is measured, not just read.** A finding from another project is a
claim; it enters our documentation only after our own check. This entry records
the checks done now and routes the rest to the linkage plan (`docs/plans/linkage.md`,
workstream B).

## Checked now

| finding (omnisus) | our check | result |
|---|---|---|
| DBC decompression silently truncates 1–2% of records (RDAC2401 −1.8%, PAAC2401 −1.0%; `dbf_contract.py:25-32`) | downloaded both files; decompressed with our `decode/_native` and with `datasus_dbc`; header record count vs bytes | **Not our defect.** Ours: RDAC2401 declares 4,315 and holds 4,315; PAAC2401 105,836 and 105,836; output byte-identical to `datasus_dbc`. Their truncation was in their pipeline. Our header-vs-bytes mismatch report (`decode/dbf.py`, 16 of 132 payloads) stays as is. |
| `TP_DROGA` combination codes (`AO`, `A O`, `CA`…) | SIA-PS SP 2023-01, raw values | `AO` 15,221, `A O` 7; no `CA` in that month. Curated (ADR-0106, amended). |
| `GESTOR_TP` labels without a source (their issue #10) | SIH-RD AC + SP 2023-01 | 1 exactly when `GESTOR_CPF` is filled (ADR-0106). |
| `TPDISEC` 0 "coincides with an empty secondary diagnosis, not a source" | measured 214,390 admissions | Settled by measurement (ADR-0105): we accept an exact, exceptionless co-occurrence as evidence; they do not. A difference of rule, recorded here. |
| `KOTELCHUCK` 9 labelled from the kit | ours | Both claims kept (layout 6, kit 9; ADR-0106). |
| SIH `IDENT` labelled "Outras/ignorado" for 2–4, 6–9 | ours | **Same defect in ours**: the kit's IDENT.CNV is a TabWin grouping, not the layout's meaning. Routed to workstream B. |
| establishment names by per-code API (`apidadosabertos…/cnes/estabelecimentos/{cnes}`) | `DATA_SOURCES.md` CADGER section | Already have, in bulk and offline (692,004 establishments). Skip. |
| SIGTAP from `ftp2.datasus.gov.br/public/sistemas/tup/downloads` | `DATA_SOURCES.md` §4 | Already have, identical. Skip. |
| DEMAS/Hórus stock endpoint; their note that `offset` is a page number | `sources/demas_api.py`, `DATA_SOURCES.md` §5; live: `codigo_uf=12&limit=5` at `offset` 0, 1, 5 | **Not confirmed.** `offset=1` returns rows 2–6 of `offset=0`'s window and `offset=5` starts at row 6 (2026-09-30): a row offset, as our client (`offset += page_size`) assumes. |
| age: completed years, months floored | ADR-0070 | Ours keeps fractional years (18 months = 1.5). Keep ours. |
| municipality codes are 6 digits; never pad to 7 | `DATA_SOURCES.md` | Already have. |

## Routed to the linkage plan (workstream B), each to be checked before use

- **Linkage method** (`notebooks/linkage.py:933-1090`):
  - 1:1 joins on keys unique on both sides;
  - passes from strictest to loosest over the remaining records;
  - a negative control per pass (birth date +7 days, age +2 years, birth year +1; for exact identifiers the neighbouring identifier in sort order);
  - held-out validation;
  - a verdict fixed in advance (≤5% chance and ≥90% validation viable; ≤20% and ≥75% caution).
  
  Adopted as the deterministic baseline (plan A3).
- **Facts to verify:**
  - SIM DOINF/DOMAT/DOEXT are copies of DO rows;
  - SIH-SP ⊂ SIH-RD by AIH;
  - SINAN FINAIS/PRELIM split per agravo without overlap;
  - SINAN-TB file year follows `DT_DIAG`;
  - truncated `id_agravo` (`A16.`, `A50.`);
  - AIDABR24 half-empty;
  - `LERBR19`/`LERDBR19` same size;
  - CADMUN (0,0) coordinates and missing post-2011 municipalities;
  - countries table with duplicated codes;
  - hanseníase `classi_fin` set by the system;
  - SIM age-unit documentation conflict;
  - SINASC `CODESTAB`/`CODANOMAL` width drift;
  - CNES `turno_at` `'  -99'`;
  - unlabelled `ESPEC` 17, `FINANC` 00, `HOMONIMO` 2, `CO_ERRO` outside `MOTERRO` (8,048 of 14,656,815 rows), `FINALID` 7, bare `TPIDADEPAC`/`AP_COIDADE`;
  - incomplete months (RR June 2022);
  - impossible dates (years 2222, 1366);
  - `TIPPRE  ` column name with trailing spaces (PSRR2401);
  - ER's own `ANO`/`MES` equal to the file's period (4,931 files);
  - no public dispensation-event source (BNAFAR REDFM not public).
- **Mechanisms to evaluate:**
  - catch-all CNV ranges (`00-99` → "Ignorado") masking undocumented codes;
  - a per-table `check_columns()` for a person in Python;
  - a per-label claim status with document locator, and a SHA-256 registry of `sources/`;
  - `cite()` from blob hashes;
  - IBGE `/v3/agregados` 202/4714/6579 population editions against OQ-12;
  - FTP: two clocks, skip counts as a returned field, pre-flight byte reservation for split months;
  - all-null column typed from the DBF header, not the dictionary;
  - refusing a file whose own partition-named column disagrees with its scope.

## What omnisus does better, as a matter of direction

- Linkage with negative controls: none in ours before this branch.
- A machine-readable status on every code map.
- Citation of results by content hash and snapshot.

Each is in the linkage plan. The artifacts are the omnisus clone, read in the
session scratchpad, and the DBC check script, whose output is quoted above.
