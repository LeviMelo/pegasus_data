## 2026-08-19 — SP_ATOPROF and SP_PROCREA are not 8-digit

*Split from docs/history/FINDINGS.md §3d on 2026-09-28; text unchanged.*

### `SP_ATOPROF` and `SP_PROCREA` are not 8-digit

The instruction expected 8-digit codes wanting `TPROC` rather than `TPROC10`. Measured: both columns
appear at **two widths** — `SP_ATOPROF` at 398 distinct 8-character and 400 distinct 10-character
values, `SP_PROCREA` at 400 and 395. `TPROC` holds 23,151 8-character codes and `TPROC10` holds
23,136 10-character ones, so the columns span the 1994-era table and the post-2008 Tabela Unificada.
Binding either alone leaves half the history unlabelled. Both are bound, and because matching is
exact-width, merging them is safe — the width selects the era.
