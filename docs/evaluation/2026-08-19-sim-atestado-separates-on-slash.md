## 2026-08-19 — SIM's ATESTADO separates on /, not *

*Split from docs/history/FINDINGS.md §3d on 2026-09-28; text unchanged.*

### SIM's `ATESTADO` separates on `/`, not `*`

The causal-chain fields `LINHAA`–`LINHAD` and `LINHAII` are `*`-delimited four-character codes —
confirmed independently by measurement (10,196 of ~12,000 inter-`*` segments are exactly 4
characters) and by curation. `ATESTADO` is not: it uses `/` (`T71/X700`, `S069/X954`). The delimiter
is now chosen by measured coverage rather than by position in a candidate list, which took
`ATESTADO`'s multi-code detection from 66 to 2,031 values and its malformed count from 2,526 to 486.
