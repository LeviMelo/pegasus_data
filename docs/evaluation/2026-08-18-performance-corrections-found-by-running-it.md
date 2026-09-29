## 2026-08-18 — Performance corrections found by running it

*Split from docs/history/FINDINGS.md §3 on 2026-09-28; text unchanged.*

### Performance corrections found by running it

- **Range expansion against a code universe** was a linear scan per range. The per-chapter CID
  files carry thousands of ranges each and there are dozens per kit — roughly a billion string
  comparisons. Truncation preserves sort order, so the matching codes are always one contiguous
  slice and bisect finds it.
- **Dictionary merging** read the whole `dictionary` table into Python per call. By the third kit
  that was scanning millions of rows to check a few thousand keys. The batch now goes into a temp
  table and the rest is a join.
- **Re-profiling an archive member** re-expanded the whole archive and derived seven new member
  strata from each existing one, multiplying on every run. A stratum that names a member now
  profiles only that member.
