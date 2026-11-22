# The record key out of the lake: the real home re-encoded (2026-11-21/22)

**Regime.** `pegasus-data reencode-lake` on the real home (`C:\Users\Galaxy\pegasus_core_data`), launched on fe82489
at 2026-11-21 19:18 local and ended about 7 h later. It shared the machine with the SIH-SP extract, the header
census, the TISS landing and the science session's links, so its time says little. ADR-0231.

**Before (sweep of 2026-11-21).** 3,639 of 4,263 partition files stored `_record_key`: 15.9 GB of their 36.2 GB
(44%). In every one, recomputed from the file's own fields, the key equalled the stored key on a 3,000-row sample.
The 13 SINAN dengue and chikungunya files that seemed to differ were DuckDB's Hive `uf` read over their own `UF`.

**After.**
- 0 of the 7,798 listed files store the key, and none is missing. `reencode_lake` compares every row of a file
  before rewriting it, and kept none for a difference.
- The catalog's sizes match the disk.
- The lake's listed partitions, without the TISS files landed meanwhile, went from 42.9 GB to 27.1 GB (−15.9 GB,
  −37%), the key's measured size. Free disk went from 66 to 87 GB.
- The role tables went from 13 GB to 2.8 GB: the current ones are kept with 16-byte keys, the stale ones are removed.

**The carry stopped at its last step.** The science session rebuilt SIH-RD 2019's role table during the rewrite, which
removed the table the carry had listed. The carry raised `FileNotFoundError` there; it now passes over a table replaced
meanwhile. The stored runs were not re-stamped, but they are stale anyway under LINKAGE_VERSION 5 (c0c115b) and are
recomputed. 22 role tables that no current lake state can serve were removed (1.5 GB).

**Identities.**
- SIH-RD SE+AL 2019 (272,603 rows) and SIM-DO 2013 and SINASC-DN 2012-2013 (7.0 M role-table rows, scratch home): the
  keys computed on read equal the stored ones on every row.
- Whole files are hashed by DuckDB (5eb7ed9): 857,219 SIH-RD rows in 3.5 s against 11.5 s.
