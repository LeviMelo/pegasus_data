## ADR-0236: One model of what the home holds: a file whole in the lake, or by predicate in its dataset's extract store

**Date:** 2026-11-24. **Status:** active. **Amends** the extracts of `extract.py` (one folder per filter, 2026-10-11)
and ADR-0234 (a partition's sources are the lake's holdings). **Request:** the author, 2026-11-24: the overlap of the
SIH-SP extracts with the full lake exposes defects of the lake's management of itself; extracts are absorbed and
managed, agglutinating as new filters arrive, and dropped only when the file is taken whole. Resolves OQ 108.

**Context.** The home held DATASUS records two ways with no shared model of coverage.
- **Lake partitions** hold whole publications. The catalog knows each partition's sources and their digests
  (`lake_partitions.source_paths`, `source_digests`, ADR-0234). Coverage already reasons per source: a year is the lake's
  when every publication of it is a source of a partition at the listed version.
- **Extracts** held the rows of a publication matching a filter, one folder per filter digest, with a manifest of their
  own. Their parts were named by state and period. The planner saw them through a special case (`plan(rows=)`).

Measured on SIH-SP, 2026-11-24:
- The lake held every file of 2010-2025 whole: 4,916 sources in `SIHSUS_SP_c275b49fe5` (17.8 GB) and 271 in
  `SIHSUS_SP_3b016b3e09`, the 2025 layout (1.4 GB).
- Five extract folders held 204,394,274 rows (6.3 GB) of those same files at the same digests: `0415` (170,206,799 rows,
  5.2 GB), `0403|040803 OR SP_ATOPROF 0702040126` (32.2 M, 1.0 GB), `0403` 2024 (300 of the year's 324 files) and two
  of 12 files each.
- The folders overlapped one another: every 0403 row is in two of them. Each new filter had downloaded the same files
  again. Nothing knew that the lake held their rows. The coverage did not show a partial holding (OQ 108). A
  republished file did not void the rows extracted from its old version.
- SIA-PA's split files (`PASP2301a`, `b`, `c`) share a state and a period, so their parts overwrote one another: see
  the migration below.

**Decision.**
1. **A holding per published file** (`persist/held.py`). Each file is held one of two ways:
   - **whole by the lake**: a partition lists the file at a recorded digest, and the server lists that version
     (`lake_whole`);
   - **partly by its dataset's extract store**: `<lake>/extracts/<SYSTEM>-<SERIES>/`, one store per dataset, its
     `holdings.sqlite` holding a row per file:
     - path, year, state and period;
     - the digest read, and the held predicate;
     - the file's rows, the rows held, the bytes;
     - the parts (disjoint) and the code version.

     A row is written as the file's part lands, so a running build can be inspected (OQ 108 (2)). A failure is a row
     of `failed`. Parts are named by the file's own name and a digest of its path, never by state and period.
2. **A predicate is a union of atoms** (`Predicate`). An atom is a column and a code prefix; `TRUE` is the whole file.
   - It is canonical: a prefix that another prefix of the same column implies is not kept.
   - An extract keeps a row that any of its filters matches, so the union of two extracts' filters is the predicate of
     both.
   - `implies` is exact for such unions.
   - A query's row filter is covered when every column is implied (`rows_join="any"`), or one column is (`"all"`).
3. **Extracts agglutinate.** `build_extract` reads only what a file lacks:
   - a file the lake holds whole is not read;
   - a file whose held predicate implies the new filter is not read;
   - any other file is read for the atoms its predicate lacks (`beyond`), and stores the rows those match and the held
     predicate does not (`new AND NOT held`). The file's predicate widens to `held OR new`;
   - a file the server lists at another version than the one held (`stale`) is read again for its whole predicate,
     and its parts are replaced. A republished file voids exactly its own rows.
4. **The lake absorbs.** A file the lake holds whole needs no store rows. `absorb` drops them when the lake holds the
   file at the same digest and the lake's rows that the predicate keeps are the store's, the same `_row` set. Every
   partition is read once for all the files it holds. A lake build absorbs the files it wrote (`Builder.build`,
   `counts["absorbed"]`).
5. **One read path.** `held_files` answers for both stores. `retrieve` reads a held file from the home instead of
   downloading it:
   - a file the lake holds whole in a year the lake does not hold whole, with the query's row filter pushed into the
     partition scan (`versions.source_rows(where=)`);
   - a store file whose predicate covers the filter.

   The planner counts both as held (`extract_bytes`). `extract_table` serves the store's rows and the lake's, in the
   old row order: year, then state, then period, then file order. Its columns are the old ones, the `year` the old
   folders gave by Hive inference included.
6. **Coverage reports partial holdings.** `lake_coverage(...)[year]["held"]` counts a year's published files:
   `whole`, `partial` (predicate -> files and rows) and `neither`. A year that only the store holds appears too.
   `pegasus-data extracts DATASET` prints this and absorbs with `--apply`.
7. **Migration** (`migrate_extracts`, `pegasus-data extracts --migrate [--apply [--remove]]`). Each file of a legacy
   folder is handled one of three ways:
   - **absorbed**: the lake holds it at its rows' digest, and the `_row` sets match;
   - **carried** into the store: only the rows it adds;
   - **short**: the folder recorded more rows than its part holds, so the file is not carried and is read again.

   `--apply` writes and deletes nothing. `--remove` deletes a folder only when every file of it was absorbed or
   carried and none mismatched.

**Rejected.**
- **Conjunctive predicates (a full DNF).** An extract is built under "any". A held conjunction would make "is this
  filter held" a containment question between DNFs on prefix sets, and would store a file's rows in pieces that one
  OR no longer describes. A query's conjunction is already answered: one column whose prefixes the holding implies is
  enough (`covers`, "all"). Reopen if a study needs a conjunction held without its wider disjunct.
- **Keeping per-filter folders and indexing them.** The overlaps stay stored twice, and every reader keeps
  choosing a folder. The old `extract_table` took the first folder whose filter covered the codes, and fell through to
  the next only when that folder lacked a file of the year.
- **Holdings in the catalog (`extract_holdings` beside `lake_partitions`).** A store that moves or is deleted with its
  folder would leave rows that claim data. The catalog's seed and schema carry the maintainer's tree, not one home's
  state. The two views meet in `held_files` and `lake_coverage`, not in one table.
- **Serving `extract_table` through `query()`.** That would be one path, but `query` renders and renames columns,
  and PegaSUS and the ABNc studies read the raw columns `extract_table` returns.
- **Re-sorting the lake on the common filter columns now** (OQ 109). See Consequences.

**Evidence.** Evaluation 2026-11-24-holdings (`data/probes/holdings/`):
- **Migration dry run.** All 10,692 files of the five SIH-SP folders were absorbed: each file's `_row` set equals the
  lake's rows that its folder's predicate keeps. That is 204,394,274 rows, 0 mismatched and 0 short. The 0415 folder's
  rows are 170,206,799: the lake holds those same rows of those same files. The brief's 170,190,960 is 15,839 fewer;
  it is no folder's count. The run took 921 s, each partition read once.
- **`extract_table`, old code at HEAD against new**, every column but `_ingested_at` hashed in order: 0403 2024
  (2,119,682 rows), 040803 2025 (534,328) and 0403 2015-2016 (3,120,698) are identical in rows, values, order and
  schema. The old ones were read from the folders, the new ones from the lake. `_ingested_at` is when each copy was
  decoded, so it differs.
- **`query("SIH.SP", rows=...)`** before and after, by state and period: see the evaluation.

**Consequences.**
- After `--remove`, SIH-SP's extracts are gone: 6.3 GB, every row held by the lake. A new SIH-SP filter downloads
  nothing.
- **Reading a filter from the lake costs a partition scan.** `extract_table` 0403 for 2024 took 58 s from the lake,
  against about 2 s from a 64 MB folder. A filtered read cannot touch less than a state-year (OQ 109). The lake is
  appended file by file, so row groups cluster by source and month, not by code. Sorting a partition's row groups on
  the common filter columns (procedure, diagnosis) would let statistics prune: one rewrite of the lake, under `_row`
  identity and the same order on read. It is OQ 109's next step, not done here.
- **Derived stores** (`lake/roles`, cubes) are current by the lake files' sizes and times (`store.carried_currency`,
  ADR-0231). They know nothing of holdings by file. Lineage by holding is OQ 111.
