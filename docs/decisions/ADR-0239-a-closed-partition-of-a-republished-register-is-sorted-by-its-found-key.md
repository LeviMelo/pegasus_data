## ADR-0239: A closed partition of a republished register is sorted by its found key

**Date:** 2026-11-26. **Status:** active. **Amends** ADR-0238. **Request:** the author, 2026-11-26: store CNES
compactly, by a general, mechanical procedure over the current architecture rather than beside it.

**Context.**
- CNES republishes its whole register every month, so a year's partition holds about twelve copies of each record,
  scattered. A compact form of separate tables (records once, with their months) took CNES-PF AL 2023 from 24.9 to
  2.5 MB (docs/plans/storage.md), but every reader of lake files (statistics, extracts, version deltas, row-count
  checks, DuckDB globs) would have to learn it.
- Sorted so that a record's copies sit together, the same file is 4.8-6.6 MB with the rows as rows: the dictionary and
  zstd collapse the runs. `_row` keeps each row's place in its source file (0.6 MB of the 4.8).
- Event datasets (SIH, SIM, SINASC) repeat nothing across publications; sorting them did not help (2026-10-10) and
  "the first row in file order" is a rule some joins read (`joins.yml`, SIH-RD's principal AIH).

**Decision.**
1. For each family with closed partitions, `persist.cluster.choose_order` measures on a probe file (the largest closed
   file of at most 2 M rows): columns constant within a publication (`_source_path`) are left out; if under 20% of the
   rows repeat across publications, no order. Otherwise the record key is found by greedy distinct counting within each
   publication (at most 6 columns), and each key column first, then the rest, then the publication, is written in the
   closed encoding; the smallest wins if it beats the file order by 10%.
2. The choice and its measurements are kept in `<family>/_order.json`; `reencode-lake` writes the family's closed files
   in that order (DuckDB sorts, spilling under `<lake>/.staging/duckdb`), stamps `pegasus.order`, and treats a closed
   file of another order as not current.
3. Nothing reads a lake file's physical order as meaning; file order is `ORDER BY _source_path, _row`.

**Consequences.** CNES-PF AL 2023: key `CPF_PROF, CNES, CBO, VINCULAC, PROF_SUS` found, 86% of rows repeats, 24.93 to
6.58 MB with the first candidates (CBO first), every row back (0 differences both ways). The establishment-first order
(4.80 MB in a hand test) is among the candidates now. Families of event records keep their file order.
