# SIH-RD 2014 refused as a representation conflict (2026-11-05)

**Found by** the toxoplasmosis study (`../toxoplasmose_brasil`): every 2014 month of SIH-RD raised
`RepresentationConflictError` (e.g. `SIHSUS|RD|AL|201401`).

**Cause.** Five candidates per publication: XML twice (`/SIHSUS/XML/`, `/SIHSUS/2014/XML/`), DBF (`/SIHSUS/DBF/`), DBC
twice (`/SIHSUS/MHJ_14_16/`, `/SIHSUS/200801_/Dados/`). The exports are set aside behind the natives. The two DBCs are
byte-identical (963,086 bytes for AL 2014-01); only the `Dados` copy has a census row (113 fields, `e2f7244ae509a4c0`),
while `MHJ_14_16` is in the exports' family (`2dfed3d360ebaa80`) by inference. The inferred signature was compared with
the measured one and read as a contradiction.

**Fix** (ADR-0212): only measured signatures (`file_schemas`) count. **Checked:** `query("SIH-RD", period=2014,
select=["N_AIH"])` = 11,612,715 rows, the lake's count (`read_parquet` of the 324 partitions, all from `200801_/Dados`);
B58/P37.1/O98.6 as principal diagnosis = 1,987, as read from the partitions before the fix.

Regime: branch `pegasus-core-fixes` over `cfb0e0b`, data home `C:/Users/Galaxy/pegasus_core_data`.

## The same day: SIA-PA's extract listed every copy of a publication

`extract._files` listed the catalog's data files without choosing a representation, so Paraná 2024-08..2025-06 was
listed twice, from `/SIASUS/teste/` (trial copies, 2025-09-24) and `200801_/Dados`. The trial copies failed
(`NothingPublished`: `fetch(_only_paths=)` resolves the publication to its `Dados` copy), and `extract_table` refused
2024 and 2025 whole. `_files` now applies `choose_representations`, as a query does. **Checked:** `_files(SIASUS-PA,
2024, PR)` lists 12 files, all `Dados`; `extract_table(SIASUS-PA, PA_PROC_ID, toxoplasma IgG/IgM, 2024)` returns
475,971 rows, 34,344 of them from Paraná establishments.
