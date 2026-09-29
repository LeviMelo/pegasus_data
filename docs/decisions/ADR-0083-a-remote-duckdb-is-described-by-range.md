## ADR-0083: A remote DuckDB database is described by ranged reads; its tables are members

**Date:** 2026-09-29. **Status:** active. **Amends:** ADR-0077.

**Context.**
- **What DATASUS publishes.**
  - `SIHSUS/base_aih1.duck`, 12 GB.
  - Eleven zipped DuckDB exports under `Dados_Abertos/APAC_SIA/`, 38 MB to
    6.9 GB.
- **The gap.** None had a schema in the catalog, so none could be queried or
  described.
- **What the files look like inside.** A DuckDB file names its catalog's
  metadata blocks in a 12 KB header, and every 256 KB block carries a checksum.
  DuckDB's `ATTACH` reads through its own file system, not a Python one; an
  fsspec-registered FTP filesystem was tried and refused.

**Decision.**
- **Plain `.duck`.** `decode/duckdb_remote.remote_duckdb_tables` writes the
  header into a sparse local file of the database's full size and attaches it
  read-only. Each "corrupt block at location N" error names the next block
  needed, which is fetched by ranged FTP read (`REST`) before retrying.
  - Measured: 8 blocks, 2.1 MB and 99 s describe `base_aih1.duck`. It is a
    star schema: `stg_aih` holds 221,499,268 admissions in 74 columns, beside
    12 `dim_*` tables.
  - The file is extended by one write at its end. `truncate()` on Windows
    zero-fills, and the first attempt allocated all 12 GB.
- **Zipped `.duck.zip`.** Deflate cannot be read by range, and the catalog
  blocks sit deep in the file (7% and 45% of the way into `base_aih1.duck`).
  So a zipped export is described only when it is at most 64 MB, fetched
  whole: `apac_ab`, `apac_abo` and `apac_acf`, 130 MB in all. The eight larger
  ones wait for their published dictionary (OQ-54).
- **Tables are members.** Each table is recorded in `archive_members`
  (container `duckdb`): `dim_*` tables with role `reference`, the others
  `data`. The stratum reads the **fact** table, the largest non-`dim_` table.
  "The largest table" would have been `dim_cadger` (679,026 rows) rather than
  `fat_apac_ab` (306,886).
- **Queries stay bounded.** A query of these databases downloads them whole,
  so `max_download` (ADR-0076) refuses it unless it is raised.

**Open.**
- Read a DuckDB fact table by row group, by range, for filtered queries.
- Use the `dim_*` tables as code tables.
