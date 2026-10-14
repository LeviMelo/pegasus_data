# ADR-0164: the lake is read from the catalog's list of partitions, and a year is read once

**Date:** 2026-10-14. **Status:** accepted.

**Context.** Four defects of the read path shared one cause: the read decided what the lake held by walking its
directories and what a dataset's year was by selecting every file of it.
- Every `Lake.read` discovered the family's whole `schema_signature=/uf=/year=/part-*` tree again (0.3-0.7 s; 3 times with
  a two-column `rows=`), and read any file under it, the catalog's or not.
- A partition the catalog listed and the disk lacked was skipped: the generation contributed nothing, the table was short,
  and `_coverage` had already called the year lake-complete.
- With no state asked, SIM and SINASC (published as `DOBR2019` and as 27 state files, the same records) were selected
  twice: `plan("SIM.DO", period=2019)` planned 206 MiB where the national file is 103, and the lake path read the `uf=BR`
  and every `uf=XX` partition built.
- A column no generation carries (`select=["CODMUNRESS"]`, `rows={"NOPE": ...}`) came back as a null column with a warning;
  `rows={"CAUSABAS": []}` kept every row; a filter that matched nothing raised `NothingPublished("run build first")`.

**Decision.**
- **The list.** `lake_partitions` (written with each file) is the one answer to which files hold a family. `Lake.listed`
  returns it (remembered per ADR-0163), `load`/`scan` narrow it to the states and years asked and open exactly those files
  (`Lake.dataset_of`), `Lake.columns_of` reads a generation's columns from its first file's footer (cached). A directory is
  walked only by a lake without a catalog. `load()` and `scan()` share one resolution (`_resolve_generations`).
- **A listed file is there.** A missing one is `PartialLakeError`; the planner calls a year lake-complete only when its
  files are on disk, otherwise it plans a fetch and says so (`Adaptation("lake_partition")`).
- **One reading of a year.** With no state asked, a year published as a national file and as state files is read from the
  national file (`coverage.national_or_states`), in the plan, the download estimate and the lake read: the same as
  `geography="BR"`. `RetrievalPlan.year_geography` carries it per year.
- **Columns.** A `select=` or `rows=` column carried by no generation of the dataset raises `MissingColumnError` (a column
  some generations lack stays the recorded null-fill); the schema census falls back to `schemas.fields_json` where
  `schema_presence` holds nothing (30 of 321 signatures). An empty or blank `rows=` prefix list raises `ValueError`; a filter
  that matches nothing returns an empty table with its schema.

**Consequences.** Undated intake records (`year=0`, never a publication, unlisted by `intake.py`) are no longer reached by
`load(years=None)`. A lake rebuilt in place keeps its list exact, because `write_batches` updates it with the file. The fetch
path's own `uf=None` selection (`retrieve._select_files`) is unchanged: `query()` passes explicit states.
