# ADR-0162: one declared intake for the sources that are not on the FTP

**Date:** 2026-10-10. **Status:** accepted.

**Context.** The author asked that pegasus_data integrate what the DEMAS API exposes: through DEMAS where it serves the
original's full breadth, otherwise through the original (the Portal de Dados Abertos' bulk files) with DEMAS as fallback.
Separate agents had each written their own fetch, cache and reduction (`sources/bnafar.py`, SISAGUA, SI-PNI), and each
reduced to a thin aggregate and dropped the records.

**Decision.** One module, `intake.py`, reads `curation/intake.yml`; a source adds a declaration, not code.
- **Declared:** origin (an API endpoint, or files, with the other route as `compare`), the columns with the role and code
  list the source's own dictionary gives, the place and period a context is keyed by, and the measures (sums and counts).
- **Records first.** The records go to the lake as Parquet with every column: the raw value under the source's name and,
  where the declaration types a column, the typed value under that name and the raw beside it (`<NAME>__RAW`). DuckDB
  streams the conversion (`all_varchar` CSV to zstd Parquet; the raw file is deleted). The dataset is registered as a
  catalog family (one publication per file and year), the ontology and the curation loader read its system, series, columns
  and code lists from the same declaration, so `query("FA-HUM")` and `info()` serve it like an FTP dataset. A source that is
  itself an aggregate has the aggregate as its record.
- **Fields second.** Context fields are derived from the lake records and written to `<lake>/fields/`, where `load_field`
  reads them. A place outside the IBGE universe is kept in the records and counted as unallocated; no date means year 0; an
  absent place and period is absent, not zero.
- **API reading.** At most one request a second per host, a browser User-Agent, backoff, an empty page as the end. A table
  that is not stable under offset paging (BNAFAR) is read by partitioning the filter (state, then municipality) until it
  fits one page. A current-state endpoint (`snapshot: true`) lands every fresh read with its read day.
- **Verdicts are tested, not assumed.** `check_source` sets the used origin against `compare` row by row on the key
  columns. Where the two disagree the original wins.

**Evidence.** BNAFAR's TOXO programme read by offset returned 3,862 rows of which 2,572 and 2,807 were distinct in two
reads; split by state, 3,862 distinct and identical on re-reading (so the earlier medicines counts from `program()` were
wrong). DEMAS' yellow-fever cases hold the Portal file's 2,911 rows plus a copy of the first, and its epizootics lack the
month of 13 rows: the Portal is used for both.

**Consequences.** `sources/bnafar.py` keeps only its domain logic (CATMAT items, units, the monthly grouping). The
SISAGUA and SI-PNI branches port onto this declaration when they merge. The existing INMET, S2iD, ANS and INEP readers
reduce without keeping records; they are the next to move.
