# Storage: what filled the disk, what was freed, what compresses (2026-10-10)

Disk C: had 16 GB free of 931 GB. Measured with `du` per tree. The projects held about 160 GB: the two data
homes' blobs (pegasus_data_home 37.3 GB, PegaSUS's root 25.6 GB), PegaSUS's lake (37.5 GB, of which the modelled
population account was 17.4 GB), the maintainer catalog (12.6 GB), PegaSUS's store (14.8 GB) and probe data (15.2 GB).
Regime: branch `pegasus-core-fixes` at 4f719eb plus this change; roots `pegasus_data_home` and
`C:/Users/Galaxy/pegasus_core_data`.

## Freed (16 GB free → 68 GB)

| step | freed |
|---|---|
| `pip cache purge`, `conda clean --all` | 9.4 GB |
| stale partial downloads (`BlobStore.sweep_staging`; partials never resume across runs) | 1.2 GB |
| `prune` on PegaSUS's root: blobs whose every partition is verified in its lake | 19.2 GB (7,095 blobs) |
| hard links between the two homes' identical blobs (content-addressed; 673 left after the prune) | 1.4 GB |
| PegaSUS store: blockdata under superseded assembly versions; `event_counts` keyed before `declared` | 7.3 GB |
| unreferenced forecast pickles of the 2026-10-05 exposure study (pegasus_project `data/agent_migration`) | 12.2 GB |
| the population account rewritten with `BYTE_STREAM_SPLIT` floats (`reencode-modelled`, versions 2-6) | 4.7 GB (17.96 → 13.23 GB) |

## What compresses

`data/probes/compression_options.py`, log `data/probes/compression_options.log`. Each real file is rewritten. Size is
relative to the file as stored; write seconds are given for the level-19 rewrite.

| file (2019) | rewritten, zstd 1 | zstd 9 | zstd 19 | rows sorted, zstd 19 | `_record_key` as 16 bytes, zstd 9 |
|---|---|---|---|---|---|
| SIM-DO BR (82.7 MB) | 0.94 | 0.92 | 0.87 (61 s) | 0.89 | 0.88 |
| SINASC-DN BR (123.7 MB) | 0.98 | 0.98 | 0.91 (79 s) | 1.08 | 0.92 |
| SIH-RD SP (153.9 MB) | 0.92 | 0.90 | 0.82 (131 s) | 0.84 | — |
| population-account-6, one year (147 MB) | — | 1.00 | — | — | BYTE_STREAM_SPLIT, zstd 9: **0.77** |

- **The source tables are near their floor.**
  - Level 19 gains 9-18% at 5-7× the write time.
  - Sorting rows by their low-cardinality columns never helps: SINASC grows by 7-15%.
  - The lake is not recompressed. Builds stay at zstd's default level.
- **The modelled floats compressed poorly until now.**
  - Their low bits are model noise, so zstd alone stored the account at 0.94 of its raw size.
  - BYTE_STREAM_SPLIT is lossless and faster to write. `write_modelled` now uses it for every float column, and
    `reencode` rewrote the versions already written. Each row group was checked equal before its file was replaced.
- **`_record_key` is the largest single column.**
  - It is the MD5 of the record's own fields: 30% of a SIM partition and 68% of a CIHA link side
    (`lake/roles/CIHA`, 335 of 495 MB a year).
  - Hex text compresses to about 17 bytes a row; 16 raw bytes saves only 6-8%.
  - It cannot be recomputed from the lake. `normalize.engine.record_keys` over SIM 2019's stored columns reproduced
    0 of its 1,349,801 keys, because the key hashes the record as it was before the lake stored it.
  - So the lake must keep it. Only a shorter key would save more, and that changes record identity.
- **The maintainer catalog (13.2 GB) is mostly the dictionary and its indexes.** By dbstat:
  - `dictionary` is 4.2 GB with 5 GB of indexes.
  - `ix_dict_source` alone is 2.3 GB, over `source_ref`. That column runs about 88 characters a row and is nearly
    unique per row (3.6 M distinct in 22 M rows).
  - Free pages are 0.23 GB, so a VACUUM gains nothing.
  - Normalising `source_ref` (file, member, line) is the remaining lever.

**Not kept: folding versions into one another.** Account-3 and -4 match account-6 in census years and the forecast,
but not in the intercensal years. Version 6 carried the intercensal residual along the cohorts, by up to 4,447 people
a cell in 2016. They are different estimates. A first check on two years (2010, 2025) had suggested they were copies.
