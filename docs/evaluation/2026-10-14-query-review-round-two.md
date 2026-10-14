# The query review, round two (ADR-0174)

Regime: branch `fix2-query`, `pegasus_core_data` read-only (a guard refused any fetch), 2026-10-14. Scripts are scratch (`query2/m*.py`).

| Finding | Counted | Before | After |
|---|---|---|---|
| 9 label needs | SIH-RD AC 2024 (57,272 rows) `load(columns=["COD_IDADE"])`, null labels | 57,272 | 0 (1.15 s cold; projection exactly `COD_IDADE`, `COD_IDADE_label`) |
| 29 filter | `rows={"DIAG_PRINC": ["I21"]}` / `["i2.1"]` / `["I21","J18"]` on the same year | 345 / not matched / - | 345 / 345 / 1,889 |
| 21 editions | lake-complete years over all 38 datasets of the real lake | 388 | 388 (no stale edition there today); synthetic rows: old edition built = incomplete, other format and mirror = complete |
| 23 multi-valued | `_multi_valued_dimensions` on the real catalog | default home, errors hidden | SINASC-DN `CODANOMAL` yes; SINAN `CRITERIO` no |
| 15 uf basis | `_uf_basis_note` | none | SIH-RD names MUNIC_MOV vs MUNIC_RES; SIM-DO, SINASC-DN, SINAN-DENG empty |
| undated | FA.HUM holds 1 undated record in each of 2 families of 2,912 | `load(years=None)` returned 2,911 | synthetic home: 6 of 6, named years 3 and 5 |
| per-group render | warm `render_table`, 3 rows, 4 columns, SIH-RD | 4.6 ms | 1.6 ms (the adjudication lookup is asked once per catalog state) |

A read can download: `view._lookup` -> `lookups` -> `persist.reference` -> `registry.lookup` -> `registry.build` -> `Fetcher.ensure` ran
a 1-file FTP fetch (166 s, nothing kept) inside `load()` of SIH-RD, all columns, because a registry-backed table was absent. Not fixed
here (`registry.py`); it needs an explicit command to build and a refusal on the read path.
