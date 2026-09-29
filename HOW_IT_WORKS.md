# How pegasus_data works

What runs today, in the order the work moves. `ARCHITECTURE.md` maps the
modules, `DECISIONS.md` indexes why each piece is as it is, and `STATUS.md`
says what is being changed. Written 2026-09-28.

---

## 0. The shape

There are two halves.

- **What the tree is and means** is built once, by a maintainer, and shipped
  as the seed catalog. It covers every file, its schema family, and which
  codelist labels each column.
- **Your data** is read on demand from the FTP server, or from a lake you
  built, and labelled with that knowledge.

```text
 maintainer                                   user
 ──────────                                   ────
 crawl → inventory → schemas → families       query("SIH.RD", period, geography)
   → curate → bindings                          → plan: which publications
   → build_resources: seed + label pack         → fetch: download, decode, normalise
                      │                         → render: labels, derived columns
                      └── ships in the wheel ──→ an Arrow table + a report
```

---

## 1. The map: crawl, inventory, census, families

- **Crawl** (`discovery/`). Lists every directory of
  `ftp.datasus.gov.br/dissemin/publicos`: 367 directories and 208,095 files in
  about 30 s. The listing verb is chosen per directory, because the server
  answers differently in different places. A crawl is reconciled against the
  catalog: new, changed, moved, gone. One that would withdraw a large share of
  the catalog is refused as a fault.
- **Inventory** (`inventory/`). Reads each filename for its system, series,
  state, date and part (`PASP2301a` = SIA, PA, SP, 2023-01, part A). The date
  convention (`YYMM` or `YYYY`) is decided per directory. Files are grouped
  into strata, one per (system, series, year).
- **Census.** Reads each stratum's column list from the first few hundred
  bytes of one file: a ranged read, so the whole tree's schemas cost about
  2 MB, not a decode of 991 GiB.
- **Families.** Group strata by schema signature: a family is one generation
  of one dataset.
- **Ontology.** Each family is bound to a declared dataset
  (`curation/ontology.yml`), so `SIH.RD` finds its files wherever DATASUS
  put them.

## 2. Meaning: harvest, curation, bindings

- **Harvest** (`semantics/`). Codelists come from the TabNet kits (`.CNV`
  code tables and `.DEF` tabulation definitions), SIGTAP, lookup DBFs, the
  DEMAS API, layout PDFs and, lowest, community transcriptions. They are
  merged by an authority ladder and keyed by system and validity window.
- **Curation** (`curation/variables/**`). 4,534 columns, each with its
  official and English name, description, code system, evidence rung and
  source. A curated codelist decides without measurement.
- **Bindings** (`semantics/label_bindings.py`, `pegasus-data bindings`). A
  `.DEF` binds a column to every table that mentions it, so the compile
  decides which one labels it. For every family it samples small real files,
  reads them through the same path a user's query uses, and weighs every bound
  table against the observed codes:
  - per-state slices of a national table are set aside;
  - rollups, which name a group rather than the code, are excluded;
  - the table decoding the most wins, the finer one on a tie;
  - below half, nothing does, and the reason is recorded.

  One row per (system, family, field) goes into `label_bindings`.
- **Build the snapshot** (`scripts/build_resources.py`). Exports the catalog's
  shared tables as `resources/catalog_seed.sqlite.gz`. The label pack
  (`labels.parquet`) is distilled separately by `labelpack`.

## 3. A query

1. **Resolve.** `"SIH.RD"`, `"SIH-RD"` and `"RD"` all go through
   `Ontology.resolve` (ADR-0073).
2. **Plan** (`_query_engine/planner.py`). The planner turns `period` and
   `geography` into publication coordinates and checks the dataset really is
   cut that way (a national SINAN file has no state axis). For each year it
   chooses the lake, if every expected publication is there, or a fetch.
   `plan(...).explain()` shows this without reading anything.
3. **Fetch** (`retrieve.fetch`, internal):
   - select the files of the dataset's families for those coordinates, and one
     representation per publication (`.dbc` over `.csv.zip`; the newest edition
     when DATASUS republished one);
   - download into the content-addressed blob cache;
   - decode in killable worker processes; normalise the types;
   - union the generations, with columns absent from a generation null
     structurally.
4. **Render** (`view.py`), per (family, year):
   - find each coded column's codelist (curation, else the family's binding,
     else a one-time weighing), read it at that year's vintage, and join it on
     the exact code;
   - add `<column>_label` beside the raw code;
   - add the curated derived columns (`IDADE_anos`).
5. **Report.** A `QueryReport` says what was planned, read, skipped,
   superseded and left unlabelled, and why. Warnings to the user are
   summarised into one.

## 4. The lake, aggregates, the frontend

- **The lake.** `pegasus-data build` writes families as partitioned Parquet
  (`lake/<system>/<family>/…/uf=/year=`). `query` uses it wherever it covers
  a request.
- **Aggregates** (`_aggregate.py`, `measures.py`, `geography.py`). A recipe
  (`curation/aggregates/*.yml`) is built once into a base cuboid of mergeable
  states (count, sum, mean as sum and count …) by municipality and period.
  `aggregate()` rolls it up through health regions, states and the country.
- **`serve/`.** Exposes built aggregates, their capabilities, population
  denominators and geography over HTTP for `../pegasus_view`.

## 5. What is kept honest, and how

- **Refusal over guessing.** An unbound, rollup-only or weakly decoding
  column stays as its raw code with a stated reason. An ambiguous
  representation, or an unbounded download, is refused.
- **Live checks.** `scripts/live.py` runs the documented uses against the
  real server on a fresh data home, and each run that changes something
  becomes an entry in `EVALUATION.md`.
