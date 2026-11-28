## ADR-0240: A read holds bounded memory, whatever the file's order or size

**Date:** 2026-11-27. **Status:** active. **Amends** ADR-0239 (its rule 3, nothing reads physical order as meaning).
**Request:** the author's compute audit (abnc2027_neuro `papers/REVIEW_compute_audit.md`), after a field read took the
shared machine to 88.9 GB of commit and froze it twice.

**Context.**
- ADR-0239 sorts a closed register by its record key, then publication, so a file's competence alternates row by row.
  The vintage split (`render_groups._partition`) cut a table into one zero-copy slice per run of equal values, which
  assumed a file is one publication: CNES-PF AL 2023 became about 900,000 Table objects, and
  `covariates.municipal(2019)` (CNES-PF and CNES-EQ fields) went past 88 GB.
- A month's request read the whole year of a partition before its period filter (national CNES-PF 2023-12: past 10 GB).
- A records cube or field held a whole year of rows before reducing them (SNGPC sales 2019 unbounded, ANS beneficiaries
  2025 6.3 GB), and the scanner read many batches ahead (2.0 GB on SNGPC).

**Decision.**
1. The split takes each value's rows once, by a stable index sort, when the runs outnumber the values (more than
   64 + 8 per value); file-order runs remain the path for files written one publication at a time.
2. A month-precision request prunes the lake scan to its months on `_competencia` (rows with no month or a year's
   competence kept for the period filter); a cube's year is reduced batch by batch over `api.scan` and its partials
   merged; `Lake.scanner` reads two batches of one file ahead (`batch_readahead`, `fragment_readahead`).
3. A register field above 60 million values is refused with its size (`fields.FieldTooLarge`), never held.

**Consequences.** National CNES-PF 2023-12: 2.92 GB, 6.6 s, 5,690,091 rows (equal to a direct count); fresh national
cubes of neurosurgeons 1.63 GB and CT scanners 0.68 GB; `covariates.municipal(2019)` 1.52 GB, 15 s; SNGPC sales 2019
4.6 GB in 34 s; ANS beneficiaries 2025 2.5 GB; 42 records-cube fields equal whole against parts; all 189 fields
re-measured bounded, row counts unchanged. A long scan is about three times slower for a quarter of the memory. Every
records cube rebuilds once (the module's fingerprint changed). Regression tests: `test_reencode_closed`,
`test_cube_streamed`.
