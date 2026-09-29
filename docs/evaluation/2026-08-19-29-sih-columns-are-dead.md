## 2026-08-19 — 29 SIH columns are dead in the current generation

*Split from docs/history/FINDINGS.md §3d on 2026-09-28; text unchanged.*

### 29 SIH columns are dead in the current generation

Testing for sentinel-only content in the **newest** generation rather than across a column's whole
history flagged 29 columns, not 13. Among them `DIAG_SECUN` (the known case), `CID_ASSO`,
`CID_MORTE`, `SP_CIDSEC`, and the `UTI_MES_*` and `TPDISEC*` families. A column that is still
emitted and carries only `'0000'` is worse than an absent one, because absence is visible.
