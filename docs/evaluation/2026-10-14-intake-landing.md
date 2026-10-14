# Intake landing: replaced units, unfinished API units, classed transport errors (2026-10-14)

Scenarios of the review's findings 8-11, 22 and 23, run before (`15c1cf7`+`a539314`) and after on synthetic units under a scratch
data home (`pegasus_data` has no network-free source with real records, and the defects are in how a re-landing treats what it
replaced). The scripts are throwaway; the counts are the evidence. Regime: this commit, Windows, DuckDB/SQLite, `file://` and loopback.

| Scenario | Before | After |
|---|---|---|
| unit `a` (3 rows) and `a-b` (2 rows) landed, then `a` re-landed after a column gained `type: integer` (new signature) | 8 rows readable (`a` twice), 2 families | 5 rows, 2 families until `a-b` follows, then 1 family; the old family folder and its catalog rows gone |
| the independent line count disagrees with the landed rows | records registered, then the error | `_LostRecords`, lake, catalog and sidecar byte-identical to before |
| API table of 5 rows read (pieces of 4), then grown to 9 | lake stays at 5 rows; the grown piece is cached as complete | 9 rows; the short last piece is `incomplete` and read again (4 requests on growth, 2 on a plain re-run) |
| an answer `{"erro": ...}` where the list `items` is expected | read as the end of the data | `ValueError` naming the keys it has |
| a month not yet published (HTTP 404) in a 3-month pattern | 195 s of retries, then the source stops | 0.02 s, recorded as `{"absent": 404}`, the other two months landed, fields derived |
| a partial download, then the server serves another version | spliced onto the new tail | `If-Range` mismatch: whole body re-read; an old `.part` with no validator is discarded |
| CNES-PF aggregate after a group gains a CBO prefix | stale, or 3.8 GB again | re-grouped from the kept (municipality, CBO) and (municipality, CBO, CNS) tables, no file read; equal to the previous aggregator on a 400-row PF file |
