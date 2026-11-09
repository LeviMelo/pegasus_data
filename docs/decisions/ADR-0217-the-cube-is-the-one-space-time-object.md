# ADR-0217: The cube is the one space × time object; a SIDRA table is a cube without a declaration

2026-11-09. Status: active. Plan: `docs/plans/cubes.md`. Begins the unification of fields (ADR-0127, ADR-0142, ADR-0162),
aggregates (ADR-0050 and after) and the SIDRA fact store (ADR-0141).

## Context

Thirteen mechanisms made a place × time table (the survey in the plan, §1). Three of them did the same job three ways:
- **Context fields.** Hand-declared slices: `gdp` was SIDRA table 5938, variable 37, copied into `lake/fields/` with its
  status renamed.
- **Aggregates.** Recipes with their own place and time declaration.
- **SIDRA's fact store.** It already held any table whole: (table, variable, period, locality, one category per
  classification) → value, with IBGE's statuses and provenance.

The fields' `law: sum` and `over` were declared, and no code applied them.

## Decision

1. **A cube is one measure over place × period × strata,** in one long shape: `place` (the code at the level: a
   municipality's 7 digits, a state's 2, the country 0), `period` (the start at the grain), one column per stratum kept,
   `value`, `status` (one vocabulary), `unit` and `source`. Its manifest is in the schema. `cube(source, place=, by=,
   where=, periods=)` is the one door (`cubes.py`).
2. **A cube is named by where it comes from.**
   - **`sidra:<table>/<variable>`** is a cube as soon as the registry knows the table; nobody declares it.
   - **`series:<name>/<measure>`** is a measure of a series stitched across censuses.
   - The records, gridded, population and modelled adapters follow (plan, stages 2-4).
3. **What may be summed is the source's statement.**
   - **SIDRA's `summarização` decides** along which of period and territory a variable adds up. A state or the country
     is IBGE's own figure when held, or the sum of municipalities when IBGE says the variable sums.
   - **A roll-up that is not allowed is refused,** and one over a part without a value is `incomplete`, never a short sum.
4. **The 26 SIDRA and series fields are views of their cubes.**
   - `load_field` reads them from the fact store and returns the same rows, columns and types. Their stored copies were
     removed once that was measured: 26 of 26 equal, 0 differences.
   - A built stitched series is kept under `lake/cubes/`, keyed by the request and by the fingerprint of the facts it was
     built from (8 s to build, 0.7 s to read).
   - `pegasus-data fields` only fetches their facts.

## Consequences

- **Any SIDRA table is served** at municipality, state or country, with IBGE's statuses: table 2683 (deaths by civil
  status) and table 10381 (employed persons) were served undeclared.
- **The other 97 fields are still built apart** (CNES 43, intake 46, climate 8). They move onto cubes in stages 2-4,
  each reproduced before what it replaces is removed.
