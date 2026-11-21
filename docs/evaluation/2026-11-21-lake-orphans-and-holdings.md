# Lake partitions held twice, and what the map said was held (2026-11-21)

**Regime.** `master` at 41b0355 plus this change; home `C:\Users\Galaxy\pegasus_core_data`. Found while mapping the
data for a neurosurgery study: a raw scan of `lake/SIM` gave 2,206,176 deaths for 2009 and 1,974,612 for 2012.

**What was wrong.** 40 Parquet partitions (218 MB) sat in the lake without a catalog row: SIM-DO 2009 an unlisted
`DOBR2009` beside its 27 listed state partitions, SIM-DO 2012 ten unlisted state partitions beside the listed
`DOBR2012`, SIA-AN 28 partitions of a superseded family (December 2011, one of April 2014), SINASC-DN 2013 the whole
year under a family name the catalog no longer uses. `query()` plans from the catalog and read each year once
(the SIM aggregate read 18,878,605 rows for 2010-2023, one reading), but `info` counted the footers on disk:
SIM-DO "held 24,944,830 rows" for 23,048,296.

**What changed.**
- `prune` also deletes a lake partition whose records the catalogued reading of its dataset-year holds, or, for an
  unlisted one, whose year has a catalogued reading and whose source files are still listed on the server
  (`persist.lake.drop_redundant_partitions`). Removed 39 partitions, 1,983,739 rows, 95 MB; the same run released
  962 downloads (2.68 GB) whose partitions were verified.
- SINASC-DN 2013 rebuilt under its current family, so the catalog lists it and the unlisted copy is replaced.
- The map counts one reading per year (`national_or_states`), and reports datasets held as downloads: CNES's
  registers (ST 828 files, PF 446, LT 516, EP 434, EQ 433, SR 326, HB 325) were "none held"; the CNES context
  fields read "none held" and now give their December years (2008-2023, beds to 2025).
- `search` gives code labels the slots other kinds leave empty, and lets a word inside a label fill them:
  "neurocirurgia" hid the `HABILITA` accreditations 1606-1618 and "neurocirurgiao" found no CBO.

**Checked.** `pegasus-data info`: SIM.DO 23,048,296 rows; CNES lines as above. `search trombectomia` returns
`HABILITA` 1618 and SIGTAP 0403070171. Found on the way, left open: SIM's national and state files differ in the
cause lines (OPEN_QUESTIONS #94), and SIGTAP labels have no validity window (#95).

**Same day: a partition of mixed schemas.** Building SIA-AQ 2013-2015 raised `Table schema does not match schema used
to create file` for state partitions whose monthly files differ by a column. The writer now opens the next part file
when a batch's schema changes and registers each file with its own row count: 2014 is written as 3 part files per
state (81 files, 2,937,694 rows) and `query("SIA.AQ", period="2014", geography="AC")` returns its 5,491 rows.
