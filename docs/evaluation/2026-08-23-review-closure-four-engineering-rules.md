## 2026-08-23 — Review closure exposed four reusable engineering rules

*Split from docs/history/FINDINGS.md §3l on 2026-09-28; text unchanged.*

## 3l. Review closure exposed four reusable engineering rules (2026-08-23)

The second external review mostly found software defects, recorded formally in
`DEFECTS.md`. Four conclusions belong here because they generalise beyond the
individual fixes and consolidate the durable parts of `HANDOFF.md`:

1. **Semantic provenance may be hidden from the result, never from the
   operation.** `_source_path` and `_competencia` are internal columns used to
   choose a family and a month-exact codelist window. Projection may remove them
   only after rendering. A provenance column is not optional merely because the
   caller did not ask to see it.
2. **A resource cap cannot decide meaning.** Loading twelve of 145 candidate
   codelists is a valid cost limit and an invalid evidence rule. Uncurated sets
   above the cap are now refused; a declared codelist bypasses ranking.
3. **System independence is positive evidence.** A `system = NULL` row in the
   shipped pack means every observed system agrees and can be shared. The
   absence of one system's table does not mean a neighbour's table is safe.
   Foreign-system borrowing is therefore opt-in and reported.
4. **The transaction unit is the unit readers observe.** A state-year lake
   partition, a population series and a DEMAS endpoint are directories, not
   individual Parquet files. Staging one file and sweeping siblings later still
   exposes mixed generations. Complete trees are built aside and swapped.

`HANDOFF.md`'s ranking incident, output-inspection warning, settled PII policy
and operational cautions are otherwise already represented in §3j–§3k and the
architecture; duplicating them here would create a second, drifting bookkeeper.
