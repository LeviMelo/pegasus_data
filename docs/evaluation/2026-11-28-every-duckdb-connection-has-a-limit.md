# Every DuckDB connection has a limit; one home per job, counted (2026-11-28)

Regime: the working tree on 17b780ff, the one home read only, Windows 11, 32 GB. ADR-0245, ADR-0246.

**What was counted, and why.** How many connections could take 80% of the machine, and whether giving each a limit
changes any answer.

| Step | Result |
|---|---|
| `duckdb.connect` in the package before | 39 sites in 23 modules; 10 with a memory limit; 29 on DuckDB's defaults |
| After | 1 site (`duckdb_session.connect`); a default connection reports `memory_limit` 2.0 GiB and the home's `work/duckdb_spill/<pid>`; 100 GB asked gives 12.0 GiB (40% of the RAM) |
| Fields through the changed paths, each in its own process | `ans_beneficiaries` 2025: 362,857 rows, 1.81 GB; `sisagua_control_counts` 2019: 1,428,419, 2.40 GB; `senatran_fleet_total` 2019: 66,840, 1.10 GB; `gdp`, `households`, `population_white`: 5,570 each; rows as the sweep of 2026-11-27 |
| `query("SIM-DO", 2022, "AL")`, `search`, `census_tracts` (Maceió) | 23,122 rows; 16 hits; 1,620 tracts |
| Tests that touch a connection (`-k` duck, lake, intake, sidra, link...) | 338 pass; one failed, the same on 04990c91: `test_compendium ... test_columns_total_agrees_with_the_link_table`. Not the deleted stray home, as first written here, but a defect it had hidden: `fields._landed` asked the process's catalog whether a source had landed, whatever home the caller described. `intake_cube`, `rows_view` and `margins_view` now take the settings; `tests/test_compendium.py` passes (found by the platform session) |
| `scripts/homes.py`, first run | 9 jobs, 32 second implementations owed: archives 13, spreadsheets 7, free-memory probes 5, file replacements 5, HTTP 1, text fold 1 |
| `scripts/layers.py` | six unplaced modules placed; 0 module-level upward imports |

Not measured: the maintainer builds that had no limit (Grade Estatística, CNEFE, CPTEC, INMET, BRDWGD, the 2010
commuting matrix, the population tensor) under the new 2 GB.
