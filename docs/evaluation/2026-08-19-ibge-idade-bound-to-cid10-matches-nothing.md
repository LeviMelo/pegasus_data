## 2026-08-19 — IBGE.IDADE is bound to CID10 and matches nothing

*Split from docs/history/FINDINGS.md §3d on 2026-09-28; text unchanged.*

### `IBGE.IDADE` is bound to CID10 and matches nothing

A distributional detector bound it at 0.35 confidence because age-band codes like `2559` and `1524`
have exactly the shape of an ICD-9 code. Shape is not identity. A near-zero match rate is now
reported as a *finding* rather than as poor coverage, because the two want opposite responses: one
needs a better table, the other needs the binding deleted.
