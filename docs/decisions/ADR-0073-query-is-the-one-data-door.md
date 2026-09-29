## ADR-0073: `query()` is the one public door to data; one dataset identifier; one CLI verb

**Date:** 2026-09-28. **Status:** active. **Amends:** ADR-0026 (`fetch()` as
the one-call door), ADR-0043 (`query()` and publication coordinates).

**Context.**
- **Five public functions returned data.** `query` (which wraps `fetch`),
  `fetch`, `load`, `scan`, `open_lake`, plus `export` to write it, each with
  its own options. Labelling policy was already one (ADR-0061). The doors
  were not.
- **The dataset spelling depended on the door.** `info("SIH-RD")` was
  "unknown" while `query("SIH-RD")` worked. A bare `"RD"` resolved in `info`
  and became system "RD" in the planner.
- **`query()` took one state only**, where `fetch()` took a list.
- **The CLI had two verbs for getting data** (`get` = Python `fetch`, and
  `export`). Its `fetch` meant "download raw files". `normalize` was an alias
  of `build`. `query()`, the documented primary, had no command.
- **The query engine was re-exported through three layers**
  (`_query.py` → `_query_engine/__init__.py` → `_query_engine/core.py`).

**Decision.**
- **Public data door:** `query()` and `plan()`. `query()` accepts one or
  several states (`"AL"`, `"AL,SE"`, `["AL", "SE"]`) and `names="described"`
  (English column names from the curated dictionary). It returns an Arrow
  table with every raw code and its `_label`; `.to_pandas()` is native.
- **Removed from the public namespace:** `fetch`, `FetchReport`, `load`,
  `scan`, `LakeScan`, `open_lake`, `export`, the `Catalog` facade and
  `PROFILES`. They remain internal engines: `retrieve.fetch` reads the FTP
  server, `api.load` reads the lake, and the planner chooses between them.
- **One identifier resolver:** `Ontology.resolve`. `SIH.RD`, `SIH-RD`,
  `SIHSUS.RD`, `sih.rd` and a bare `RD` name the same dataset in every
  entry point; `retrieve.parse_dataset` defers to it. The canonical printed
  form is the ontology code, `SIH.RD`.
- **CLI:** `pegasus-data query DATASET --period --geo --select --out
  [--described-names] [--dictionary FILE]` replaces `get` and `export`. Raw
  caching is `download`, and `normalize` is removed.
- **The dictionary:** `_dictionary.describe_table` builds a table's
  dictionary on its DATASUS names and renames table and dictionary together.
  Built on already-renamed headers, it described nothing (live, 2026-09-28).
- The query engine is one package; `_query.py` and `_query_engine/core.py`
  are deleted.

**Measured:**
- `query("SIH.RD", period="2023-01", geography=["AL", "SE"])`: 24,006 rows
  (14,340 + 9,666) in 21.8 s.
- `pegasus-data query SIH.RD --period 2023-01 --geo AL --out q.csv
  --described-names --dictionary q.md`: 14,340 rows, 41 labelled columns, and
  a dictionary carrying each column's curated name, description, reference
  table, evidence rung and source citation.
- The public surface went from 68 names to 60.

**What would reverse it.** A use the lake-reading or source-shaped engines
serve that `query()` cannot express. The answer is then to extend `query()`,
not to reopen a second door.
