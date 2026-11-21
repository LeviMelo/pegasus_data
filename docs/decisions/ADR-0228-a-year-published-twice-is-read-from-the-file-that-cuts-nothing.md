## ADR-0228: a year published twice is read from the publication that cuts nothing

**Date:** 2026-11-21. **Status:** active. **Amends** the one-reading rule of `coverage.national_or_states` (the national
file always). **Request:** the author, 2026-11-21: open problems are fixed, not left open (OPEN_QUESTIONS #94).

**Context.** SIM and SINASC publish a year as a national file and as 27 state files, the same records. `query()` read
the national file. The national file is not always the same bytes: its DBF declares a column narrower than the widest
state file, and the longer values are cut. `DOBR2012` declares `LINHAA` 10 characters, `DOES2012` 20, and 18 of ES's
21,616 deaths of 2012 lose a cause in `LINHAA` (28 in `LINHAD`). The census of every header (3,149 SIM and SINASC files,
widths per file in `file_schemas.widths_json`) finds the national file narrower than the widest state file in the
cause lines of SIM 1999-2008 and 2011-2017 (`LINHAA` 10-15 against 20, `LINHAII` 15-20 against 30) and in SINASC's
`CODANOMAL`, the congenital anomalies, in 2006-2013 (9-16 against 20). A schema signature is the column names only,
so the header facts kept per signature had hidden it.

**Decision.**
1. The census records each file's declared widths (`file_schemas.widths_json`), and re-reads the headers of years a
   dataset publishes both nationally and per state.
2. One reading of such a year is the national file unless it declares a column narrower than the widest of the 27 state
   files, none wider than every state file, and none a state file lacks; then the year is read from the state files.
   Where each cuts something, the national file is kept and the loss is recorded here: SIM 2009 (the national file
   `LINHAA` and `LINHAB`, the states `LINHAD` and `LINHAII`); SIM 2012 (ten state files, ES GO MG MS MT PR RJ RS SC SP,
   have 68 of the national file's 85 columns); SINASC 2013-2017 (state files without some columns, or narrower in
   two). The years read from the state files: SIM 1999-2008, 2011, 2013-2017; SINASC 2006-2012. The same rule decides the
   planner (`_catalog_coverage`), the read (`retrieve._one_reading`), the lake's reading (`one_reading`) and `prune`,
   which deletes a partition outside its year's reading when its records are held or its sources are still listed.
3. A width the state files only pad (`SEXO` declared 4 in some SINASC state files, 1 nationally) would move a year to the
   states at no loss: the records are the same, so the reading costs a rebuild and loses nothing.

**Evidence.** The header census of 2026-11-21 above; the ES 2012 comparison of the lake's two readings
(DATA_SOURCES 1.7). The underlying cause (`CAUSABAS`) and every other column were equal as multisets.

**Not decided.** Reading a conflicting year column by column from whichever file is wider: the rows of the two
publications are not matched by any key, so it is not done.
