# The ingest review: what each fault cost, measured (2026-10-14)

**Regime.** Branch `fix-ingest` (base 15c1cf7), offline: the blob store and catalog of `pegasus_core_data` read-only,
synthetic bytes for everything else; no FTP contact. Scripts were scratch (`ingest/t_*.py`); nothing was written to the data
home. Source: the review of the same day (`pegasus_project/data/handoffs/review-ingest.md`).

| Fault | Before | After |
|---|---|---|
| `.dbc` of a valid header and a random stream | DBF reader returned 331 rows (`CAUSABAS='\x1b'`) | no rows; the DBF reader refuses a body shorter than its header; failure named |
| 6,551 real blobs <= 8 MB with a DBF version byte | in a first 2,283: 3 refused by the DBC reader (2 loose DBFs, 1 empty file) | all 6,551 read (6,543 as DBC, 8 as loose DBF), 0 failures, row count = declared in every one |
| Archive of good, truncated, random-stream members | truncated and random read as "absent" | `member_verdict`: present, failed, failed; a name not in it: absent |
| Build with 1 of 3 months undecodable | counted decoded and mismatched, no gap, exit 0, never retried | error entry (exit 1), `coverage_gaps` row with the readers' text, partition fingerprint `<undecodable>:...`, retried next build |
| CSV `001;002;010`, `0301010072` | 1, 2, 10; 301010072 | text as written |
| DBF, 1,500 ASCII records then 10 with accents | `JOS╔ AÃ├O` from record 1,501 | `JOSÉ AÇÃO`, `encoding:cp1252` recorded |
| 7 MB UTF-8 text, 40 one-byte offsets | 5 read as cp1252 | 0 |
| Crawl with nothing listening | still running after 25 s | `CrawlFailed` in 2.7 s |
| Listing 100 bytes stale for one file | 4 transfers then a gap | 1 transfer, accepted when the server confirms the length |
| `profile` (read-only count on the local catalog) | 2,421 table-file strata fetched (2,620 in all), 57.3 GB of sampled files | 331 families, 1.7 GB; the 121 zip strata are read as before |
| Prefix read returning 0 bytes | stored as a permanent failure | retried on a fresh connection |
| `build` families_with_no_rows (one family, rows written) | 1 | 0 |

**Not measured here:** the overlap of download and decode in `fetch()` (needs the network; the mechanism removes the
serial phase, so wall clock becomes the download tail plus one decode), and the CRC-16 check of LHA members against a real
APAC archive (none in the blob store; the stored-member helper and the CRC-16/ARC check value 0xBB3D agree).

## Second round (branch `fix2-ingest`, base a3646a2; same regime: `pegasus_core_data` read-only, scratch lake otherwise)

| Fault | Before | After |
|---|---|---|
| Query on a family while one partition is being written (finding 9) | `BinderException: Hive partition mismatch` (a hidden staging tree is inside the family; DuckDB's `**/*.parquet` reads it) | 20 rows read: staging is under `<lake>/.staging/` |
| Swap while a reader holds the partition open, Windows (10) | `PermissionError` at once, the written staging tree left in the family, the build aborted | retried for 6.4 s, then the error with the old partition intact and no tree left; a reader releasing after 1 s: swapped in 1.57 s |
| Dates `99991231`, `00010102`, `30000101`, `21010101` in `epi_week_array` (12) | `OverflowError`, the batch lost | epi year and week null (the date and `_raw` kept); 1900-01-01 and 2100-12-31 computed; 1 M rows 0.043 s to 0.053 s; 1,003 sampled rows equal `epi_week()` |
| Implied decimals per cell (15) | `["100","100.00","5","0.5"]` as `N(14,2)` gave 1.00, 100.00, 0.05, 0.50 | 100, 100, 5, 0.5, the point-less ones counted in a warning. Real files: 278,906 values in 40 `decimals>0` columns of 14 SIH/SIASUS/SINAN/PNI blobs, none without the point |
| `fetch()` hashing a record key it drops (20) | 0.563 s per 65,536 x 113 batch | 0.027 s (`record_key=False`); the 65,536 keys, when asked, are identical (same digest). A connection per batch is 5% of the key, so none is shared |
| `fetch(uf=None)` of a year with a national file and 27 state files (retrieve) | SIM-DO 2019: 28 files, 206.2 MiB; SINASC-DN 2019: 28 files, 266.9 MiB; every record twice | 1 file, 103.4 MiB; 1 file, 133.5 MiB, with the warning; SIH-RD (324 files) and SINAN-DENG unchanged |
| `emit_labels` default (7) | built partitions: 0 current under True | 2,924 current under False (the new default), 403 landed by intake; no `_label` column in any of the 3,327 |

**Not done:** finding 6 (`_record_key` from the raw decoded batch, length-prefixed) changes every key, so `TRANSFORM_VERSION`
would make the 2,924 partitions stale (OQ-78). Finding 21 was done by the query round (`_label_array` encodes once per
distinct code).
