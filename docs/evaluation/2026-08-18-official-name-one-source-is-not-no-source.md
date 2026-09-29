## 2026-08-18 — official_name: one source is not "no source"

*Split from docs/history/FINDINGS.md §3b on 2026-09-28; text unchanged.*

### `official_name`: one source is not "no source"

Reporting that `DIAG_PRINC` "has no official name" was scoped to `.DEF` and stated as though it were
general. `.DEF` enumerates TabNet's tabulation axes, so of course it names only roll-ups. The record
layouts carry the real thing, and they were sitting uncrawled in the `Doc/` trees:

```
41 DIAG_PRINC char(4) Código do diagnóstico principal (CID10).
36 VAL_TOT numeric(14,2) Valor total da AIH.
```

`IT_SIHSUS_1603.pdf` yields **144 SIH fields** with official descriptions and declared types, now in
`field_documentation`. `official_name` consults the record layout first, then a `.DEF` bound to the
labelling codelist, then a `.DEF` naming the field directly — and only reports `None` when all three
miss. That same layout text is what corroborates the CID-10 binding, which is how `DIAG_PRINC` now
resolves to the full table rather than to a 529-label roll-up.
