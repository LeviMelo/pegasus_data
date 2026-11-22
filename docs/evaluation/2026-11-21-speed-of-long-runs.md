# Why the long runs were long: an extract, the map, `info` (2026-11-21)

**Regime.** The real home (`C:\Users\Galaxy\pegasus_core_data`), commits 826e272 to 58be21a. The machine was shared with
a lake re-encode, the header census and the SIH-SP extract, so single timings vary by about 2×.

**The server.** One FTP connection to `ftp.datasus.gov.br` gives about 1.7 MB/s, and four in parallel gave 6.5 MB/s
together (curl, SIH-SP files of 2024), so the limit is per connection. The SIH-SP extract of 2015-2025 averaged
1.66 MB/s in total over 5.2 h (29.5 GiB in 18,600 s), one connection's worth, with four workers.

**The extract: CPU on rows it threw away.** It kept 21.5 M of 1.59 billion rows (1.3%). Each file was decoded,
normalised and its rows hashed for `_record_key`, and only then filtered.

| Step | µs a row |
|---|---|
| raw decode | 2.5 |
| raw filter | ~0 |
| MD5 key | 2.3 |
| full read path | 10-20 |

Each worker downloaded, then decoded, so its connection sat idle.

**The fix.** `normalize_table` now tests the row filter on the raw batch, a superset of the normalised test, which
still runs after. It normalises and hashes only what can match, and keeps each kept row's ordinal as `_row`.
`fetch(rows_join="any")` gives the extract's any-of-the-columns filters. Old and new reads agree row for row,
`_row` and `_record_key` included:

| Case | Result | Time |
|---|---|---|
| SIH-SP AL 2023-01, any-join | 623 of 159,666 rows kept | 3.5 s → 0.9 s |
| SIH-SP SE 2014-02, all-join | 73 of 52,521 rows kept | identical |
| SIM-DO SE 2019, all-join | 746 of 13,473 rows kept | identical |

An extract file took 5.6 s before and 2.8 s after, now bound by its downloads. The filter first left the manifest
counting kept rows as rows read (0bb0618). `FetchReport.rows_decoded` counts a file's records before the filter, and
the 100 entries written meanwhile were read again.

**The map.**
- A full rebuild took 11 minutes in the morning: 5.4 of them rebuilding stitched series, which any curation edit or
  SIDRA fetch invalidated (fixed in 826e272).
- It now takes 52 s: holdings and fields 12 s, of which fields 10; core 5.3 s; entries 3.7 s; the rest is catalog
  reads, ANALYZE and VACUUM.
- `info SIH.RD` took 44 s because the lake had changed and the map was rebuilt inside the call. With the map current,
  `info CNES.HB` takes 0.73 s, 0.5 s of it the staleness check, which stats the lake's 4,000 partition folders.

**Not a defect.** The SIGTAP history's micro-guidewire and microcatheter codes (0702050369, 0702050350) are open runs
from 2012-09 (`valid_to` null). A query of `max(valid_to)` skipped them and seemed to end them in 2012.

**Readers no longer wait on the map (OQ #100 resolved).** A stale map is served as it was and rebuilt by one detached `pegasus-data compendium` (a lock file holds its process), which replaces it in one rename. The overview says a new map is being built. On the real home during the re-encode, `info()` took 1.3 s and then 0.4 s, `info CNES.HB` 1.7 s, and the rebuild replaced the map about a minute later. A missing map is still built in the call, and `current(wait=True)` rebuilds in it.

**Intake units side by side (c66eeb1).** A file source's units landed one after another. For ANS TISS hospital files
(about 8,100, averaging 340 KB) that was about 3 s a unit, spent waiting on the previous unit's landing, not on the
server. Four now land at once and share the host's 1.1 s request schedule. The national landing went from about 0.33
to 0.9 units a second (126 partitions in 139 s).

**Record keys over a whole file (5eb7ed9).** Role tables read whole files, and the key computed on read (ADR-0231) cost
about 7-14 µs a row in batches. DuckDB now hashes a whole file in one pass, joined by position to the columns pyarrow
reads. SIH-RD SE, AL and PE 2019 (857,219 rows) took 3.5 s, against 11.5 s, with identical keys and types.
