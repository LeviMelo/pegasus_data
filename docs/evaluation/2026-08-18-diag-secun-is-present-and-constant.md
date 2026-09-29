## 2026-08-18 — DIAG_SECUN in the 113-column generation is present, not absent

*Split from docs/history/FINDINGS.md §2 on 2026-09-28; text unchanged.*

### `DIAG_SECUN` in the 113-column generation is present, not absent — and that is worse

The brief calls this "a silent trap: a query asking for `DIAG_SECUN` against a 2020 file returns
empty with no error."

Measured in `RDAC2001.dbc` (113 columns, 3,784 rows): `DIAG_SECUN` **is present**, with **3,784
non-null values, every one of them `'0000'`** — one distinct value. `DIAGSEC1` in the same file has
514 non-null values across 99 distinct codes.

So the query does not return empty. It returns 3,784 rows of `0000`, which looks like data and
will be counted. An empty result at least invites suspicion.

This produced a detector the brief does not specify: `constant_column`, which fires on any
non-null column with exactly one distinct value, flags whether that value looks like a retired
placeholder, and raises an open question asking which field superseded it.
