# SIH-RD 2025 republished: the lake read an older version (2026-10-25)

**Check.** nees-gt-ms found 17 fewer diabetes admissions of 2025 on 25/10 than TabNet `sih/cnv/nruf.def` and than its
own read of 23/10 (ES 3,411 → 3,406 rows; AM, MA, RN, BA, ES in September to December). Traced on `pegasus_core_data`,
branch `stale-lake` from bb32ed8 (fix abb6088), 2026-10-25. What was counted and why: each publication's fetches against
its partition's build (a lake that serves a replaced version is wrong without any sign); which partitions of the whole
lake rest on a replaced version; which lake sources lie outside their partition's family (a year that reads as
uncovered, a build that refuses).

**What happened.** DATASUS republished SIH-RD 2025-09 to 2025-12 on 2026-10-16 at the same paths (RDES2510 2,184,301 →
2,185,464 bytes, RDES2511 2,007,865 → 2,025,818, RDES2512 1,981,994 → 1,983,458; the old versions dated 2026-09-06). The
partitions were written on 2026-10-15 from the old files. The 23/10 read ran in a stray home and fetched the new files
(those fetch rows were adopted under ADR-0200); the 25/10 read in the one home found the 15/10 partition counted as
covering the year, because the planner matched it by path, and read the old records. TabNet holds the new version.

**Stale partitions.** `coverage._republished_since_build` over the 2,936 partitions: 104 sources, all SIH-RD 2025-09
to 2025-12 of 26 states (Acre's was rebuilt on 24/10 from the new files), each a real change of size; 0.4 s.

**Families.** The `families` run of the same morning (for CNES-LT) had re-placed files with no per-file signature in
`file_schemas`, which held none for SIH or SIA: 1,249 lake sources lay outside their partition's family (SIA-AR 442,
SIH-RD 378, SIA-ATD 189, SIA-PS 188, SIA-SAD 52), among them SIH-RD January and February 2025, moved into September's
family and refused by the first rebuild (54 "no representation has the columns" errors). Restored from the lake (each
source's partition signature, 28,978 sources, none with two) and families rebuilt: 0 outside.

**After.** SIH-RD 2025 rebuilt (27 partitions of September's layout, 12,352,880 rows; January-February untouched); stale
sources 0; ES, AM, MA, RN, BA and SP 2025 plan from the lake. ES 2025 from the lake equals the current files read
directly: 322,036 admissions, 2,781 with E10-E14 by hospital state (September 226, October 251, November 228, December
254). The residence counts nees-gt-ms compares with TabNet are to be re-extracted on its side.
