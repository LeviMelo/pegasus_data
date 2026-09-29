## 2026-08-18 — Parquet is not smaller than a .dbc, and that is the wrong comparison

*Split from docs/history/FINDINGS.md §3 on 2026-09-28; text unchanged.*

### Parquet is not smaller than a `.dbc` — and that is the wrong comparison

P3 calls raw DATASUS "a storage bomb" and expects Parquet to be a fraction of it.
Measured on `RDAC1901.dbc`, a 113-column modern SIH-RD file:

| form | bytes | vs `.dbc` | vs decoded |
|---|---|---|---|
| `.dbc` as published | 237,472 | 1.00× | 0.10× |
| decoded `.dbf`, row-wise | 2,309,017 | 9.73× | 1.00× |
| Parquet, labels + raw (default) | 318,163 | 1.34× | **0.14×** |
| Parquet, labels only | 240,365 | 1.01× | 0.10× |
| Parquet, raw only | 247,428 | 1.04× | 0.11× |
| Parquet, neither | 169,626 | 0.71× | 0.07× |

So the lake is **1.34× the published `.dbc`** and **0.14× the decoded form**. Both numbers are true and
only the second one means anything: a `.dbc` is itself compressed and cannot be queried at all until
it is inflated whole, which is the 2.3 MB row-wise DBF. The relevant saving is against the form you
would otherwise have to materialise, and there it is a factor of seven — before counting partition
pruning, row-group statistics and column projection, which are the actual reason a filtered read is
fast.

The gap between 1.34× and 0.71× is the cost of §7.1's rule that both the raw code and the decoded
label are kept. It is real — 215 columns instead of 129 — so `build --no-labels` exists to decline it.
Nothing is lost by declining: every code and every dictionary entry is still there, and
`load(..., labels=True)` can apply them at read time. The default keeps the brief's behaviour, and the
verify report now states which comparison it is making rather than quoting the flattering one.
