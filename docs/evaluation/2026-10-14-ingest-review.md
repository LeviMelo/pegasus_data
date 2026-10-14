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
