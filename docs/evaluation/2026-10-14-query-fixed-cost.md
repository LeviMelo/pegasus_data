# The fixed cost of a query (2026-10-14)

**Regime.** Branch `fix-query-path` against its base commit `15c1cf7`; the real root `pegasus_core_data` (catalog 261 MB,
3,327 lake partitions; read only, `max_download=0`); Python 3.11, pyarrow 23, SQLite 3.53; the same rows on both sides.
**Script.** `scripts/query_fixed_cost.py` (each side in a fresh process; 5 plans, then 6 identical queries; the first
query is cold). Review: `pegasus_project/data/handoffs/review-query.md`.

**What was counted.** Milliseconds of `plan()` and of `query()` repeated, which is the scan of the selected partitions plus
everything else a query does (dataset resolution, file axes, coverage, schema census, render lookups).

| case (2019) | rows | plan before → after | query warm before → after | first query before → after |
|---|---|---|---|---|
| SIM-DO BR, 4 columns, `CAUSABAS` I21/I22, codes | 95,757 | 22 → 4 | 190-390 → 70-90 | 1.6-4.0 s → 0.9-1.0 s |
| SIH-RD AC, 4 columns, `DIAG_PRINC` I21/I22, codes | 205 | 211-350 → 4 | 900-1,350 → 90-100 | 1.0-1.3 s → 0.17 s |
| SIH-RD AC, same, labelled | 205 | 146 → 4 | 8,800-15,700 → 210-370 | 20 s → 3.7 s |
| SIM-DO BR 2018-2019, labelled | 188,829 | 50 → 4 | 400-560 → 165-175 | 0.7 s → 0.24 s |

`plan()` over ten years (2010-2019, warm): SIH-RD BR 460 ms to 35-45, SIH-RD AL
230-400 to 4, SIA-PA AC (2015-2024) 250-470 to 11.

Where it went: the dataset's file axes and publications were recomputed from the catalog on every call (plan 0.2 s,
`_resolve_generations` 0.35 s); every lake read walked the family's directory (0.33 s); `_apply_derived` built a Python
dict of the whole MUNICBR for each of the 12 month groups (0.69 s each, 8.2 s of the labelled query); a reference table was
re-read and re-filtered in Python for every month, and one with no copy for the system was read whole to say so (110 ms,
now 0.1 ms; a month of MUNICBR 45 ms, now 3.7 ms; CID9WHO 16 ms, now 1.7 ms).

**Checks that the answers did not move.**
- `read_reference_table`, old and new code over 3,252 requests on `pegasus_data_home/lake/reference` (60 random tables and
  six named ones, every system, six year/competence asks, borrowing on and off): the rows, the borrowed and fallback notes
  and the refusals are identical in all 3,252 (a one-off digest comparison, not kept).
- `plan("SIM.DO", period=2019)`: `fetch`, 28 publications, 206.2 MiB before; `lake`, the national file, 0 bytes now.
  `SINASC-DN` the same. `geography="BR"` unchanged (103.4 MiB as the national file).
- `select=["CODMUNRESS"]` raises `MissingColumnError` (it returned 1,349,801 rows and a null column); `rows={"CAUSABAS": []}`
  raises `ValueError`; `rows={"CAUSABAS": ["ZZZ"]}` returns 0 rows with the schema (it raised `NothingPublished`);
  `rows={"NOPE": ...}` raises `MissingColumnError`.
- The 30 signatures of this catalog with no `schema_presence` rows (among them SIM 2006 and SIH 1994, 2002-2004, 2009) are
  read from `schemas.fields_json`; without it the typo check could not be proved for SIM or SIH.
