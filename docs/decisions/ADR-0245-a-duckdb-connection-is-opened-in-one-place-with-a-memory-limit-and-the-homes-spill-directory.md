## ADR-0245: A DuckDB connection is opened in one place, with a memory limit and the home's spill directory

**Date:** 2026-11-28. **Status:** active. **Request:** the author, 2026-11-27, after the machine was taken down
twice in one evening: "take over these OOM issues and whatever code is related and solve it"; the audit's row C15
(abnc2027_neuro `papers/REVIEW_compute_audit.md`): "make the cap the library's own default connection factory".

**Context.** DuckDB's defaults suit a machine it has to itself: a connection takes up to 80% of the RAM before it
spills, and an in-memory one spills into `.tmp` under the folder the process started in. The package called
`duckdb.connect` at 39 sites in 23 modules. Ten set a memory limit, each its own (1, 1.5, 2 GB, a share of the
machine); three modules had grown a private `connect` helper (`linkage.identity`, `persist.versions`,
`sources.ibge_cnefe`); 29 sites ran on the defaults. Two such connections in two sessions are the machine paging
(2026-11-22, 2026-11-27).

**Decision.** `duckdb_session.connect(database, *, read_only, memory_gb, threads, ordered, spill_gb, settings)` is
the one opener. Every connection gets a memory limit (2 GB unless the caller names one; `PEGASUS_DUCKDB_MEMORY_GB`
overrides the default; never above 40% of the RAM), this process's own spill directory under the home's work folder
(`Settings.duckdb_spill`), and no progress bar. The 39 sites call it; the ten that set a limit pass the same value
as an argument; the three private helpers are one call each. `scripts/homes.py` (ADR-0246) fails on a
`duckdb.connect` or a `memory_limit` written anywhere else.

**Consequences.** A query that cannot spill and does not fit now fails with DuckDB's out-of-memory error naming the
limit, where before it could take the machine: the caller passes `memory_gb` for that job, measured. Checked: fields
through the changed paths return the rows of the 2026-11-27 sweep at the same peaks (`ans_beneficiaries` 362,857 at
1.81 GB; `sisagua_control_counts` 1,428,419 at 2.40 GB; `senatran_fleet_total` 66,840; three SIDRA fields 5,570);
`query`, `search` and a census-tract read answer; the tests that touch a connection pass but one that fails the same
on 04990c91 (it reads the deleted default home). Not rerun: the maintainer builds that had no limit (the Grade
Estatística, CNEFE's joins beyond its own helper, CPTEC's daily means, INMET, the population tensor, the 2010
commuting matrix, BRDWGD): each now runs under 2 GB with a spill directory, and the first that needs more will say
so by name.
