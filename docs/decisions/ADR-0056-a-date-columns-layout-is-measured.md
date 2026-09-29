## ADR-0056: A date column's layout is measured from its values, not declared per system

**Date:** 2026-08-29. **Status:** active.

**Context.** `build_aggregate("sim_do_municipality_month", years=[2022])`
produced 62,040 cells from 75,707 rows, with periods named `0101` to `3112`
(`docs/history/FINDINGS.md` §3s). `_competencia_column` took the first six
characters of a packed time field, which is right for a competence (`AP_CMP` is
`202201`) and wrong for a record date. DATASUS does not use one date format:
SIH's `DT_INTER` is `AAAAMMDD` (`20211227`); SIM's `DTOBITO` and SINASC's
`DTNASC` are `DDMMAAAA` (`07052022`). Nineteen `(system, field)` pairs declared
a `date` encoding and none had ever been built; both existing specs used a
competence. Fixed in `100830f` (2026-08-29).

**Decision.**
- The layout is decided from the column. Year-first requires `text[0:4]` to be
  a plausible year and `text[4:6]` ≤ 12; day-first requires `text[4:8]` to be
  a plausible year and `text[2:4]` ≤ 12. The two are disjoint for every real
  date after 1900, so a sample of a few thousand values settles it exactly.
- `_date_layout()` returns None when neither hypothesis dominates, and the
  build reports a skipped year naming the fields. A column that cannot be read
  is refused, not bucketed under a period that means nothing.

**Alternatives.** A table of nineteen declared formats. Rejected: nineteen
things to maintain and get wrong, growing with every binding.

**What would reverse it.** A date encoding that is not eight digits, or a
column mixing layouts. Both would be refused by the dominance test.
