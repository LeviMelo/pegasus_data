## ADR-0076: A query states its download before anything moves, and is bounded by default

**Date:** 2026-09-28. **Status:** active.

**Context.**
- `query()` inherited `fetch()`'s guard: refuse above 4 GiB of *selected*
  bytes, cached or not.
- `plan()` said which publications would be read, but not how much they
  weigh.
- The user asked that the project never again move tens of gigabytes
  unannounced.
- On 2026-09-28 the live sweep allowed candidate files up to 300 MB. Two
  sweeps ran at once because a kill failed, and together with the binding
  compile they moved about 3.5 GB in a day.
- Also on 2026-09-28, a test query for SIH-RD's whole 2023 (1.0 GB, 324
  files) was run expecting a refusal. It was under the limit, and 814 MB
  downloaded before it was stopped (and deleted).

**Decision.**
- `plan()` computes, from the catalog alone, the compressed bytes the fetch
  would select (one representation per publication, by year, month and state)
  and how many are already in the blob cache. `explain()` prints
  `Download: X MiB new (Y selected, Z already cached)`
  (`_query_engine/capabilities.download_estimate`).
- `query(max_download=1 GiB)` refuses, before fetching, a request whose
  **new** bytes exceed the budget, and names the size and how to raise it.
  `None` lifts the limit. The fetch engine's own 4 GiB check is off under
  `query`, because the budget has been applied.
- Live runs carry hard budgets: 25 MB per file and 800 MB per sweep
  (`PEGASUS_SWEEP_MAX_MB`, `PEGASUS_SWEEP_BUDGET_MB`). A dataset whose
  cheapest publication is over the cap is recorded as skipped, not fetched.
- Working rule: no exploratory query is run without its plan first.

**What would reverse it.** Users routinely needing more than 1 GiB per call.
The default can then rise; the statement in the plan stays.
