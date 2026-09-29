## 2026-08-18 — V6: .duck storage version, handled by construction

*Split from docs/history/FINDINGS.md §1 V6 on 2026-09-28; text unchanged.*

### V6 — `.duck` storage version · **handled by construction**

DuckDB refuses to open a database written by a newer storage version. `decode/duckdb_.py` reads
the storage version straight from the file header (`DUCK` magic + LE uint64 at offset 8) and
raises a typed `DuckStorageVersionError` carrying it. The pipeline records that as an open
question with the observed version, never as a hard failure and never as a silently skipped file.
