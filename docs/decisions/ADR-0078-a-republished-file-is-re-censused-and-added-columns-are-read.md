## ADR-0078: A republished file is re-censused, and a file that only gained columns is read, not refused

**Date:** 2026-09-28. **Status:** active. **Amends:** the family rule "a file
whose columns differ belongs to a different generation" (build._matches_schema).

**Context.**
- **What happened.** DATASUS rewrote all of SIA-PA on 2026-09-17 with one more
  column, `PA_VL_CRD`. Every older column kept its name.
- **Why it broke.** The catalog had censused the 2026 stratum in August, with
  61 fields. Retrieval accepts a file only if its schema signature equals its
  family's, so every 2026 SIA-PA file was refused. The live sweep reported "2
  did not match their family's schema": a year of data read as nothing.
- **The census blind spot.** It re-read only strata without a signature, so a
  republication was invisible to it. 101 strata had samples modified after
  they were first catalogued: SINAN 72, SIA 15, SIM 7, SIH 6, SINASC 1.

**Decision.**
- **Superset files are read.** A file carrying **every** catalogued column plus
  new ones is read, with the new columns kept, and warns once per file
  ("republished with column(s) … re-run `schemas`"). This is
  `build.schema_fit`; `NormalizePlan.columns` carries the family's catalogued
  columns. A file that **lost** a column is still refused.
- **Republished strata are re-read.** `strata.censused_at` records when a
  stratum's header was read. The census re-reads any stratum whose sampled
  file's `modified` is later than `censused_at` (or than `first_seen`, for
  strata censused before the column existed). A re-read replaces the stored
  signature, where before it kept the old one.

**Result, 2026-09-28:**
- `query("SIA-PA", period="2026-01", geography="RR")` returns 25,329 rows,
  including `PA_VL_CRD`.
- The re-census read 101 strata (0.8 MB). SIA-PA 2026 became its own 62-column
  family; no other signature changed.

**What would reverse it.** A republication that keeps a column's name but
changes its meaning. Only a curated drift note could catch that, not a schema
rule.
