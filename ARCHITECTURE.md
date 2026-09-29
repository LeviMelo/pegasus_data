# ARCHITECTURE.md

**The map of the code.** Read the code, not older documents, when the two
disagree, and then correct this file. Written 2026-09-28 from a survey of
`src/pegasus_data` (imports, call sites, `scripts/codehealth.py`) and from live
runs. `HOW_IT_WORKS.md` is the prose companion and `DECISIONS.md` indexes why.
The previous architecture document (129 KB) is
`docs/history/pegasus_data_ARCHITECTURE.md`; code comments citing "§N" point
there.

Contents: 1 the shape · 2 the runtime paths · 3 persistent objects · 4 how a
label is chosen today · 5 what overlaps, and what becomes of it · 6 the module
map · invariants.

---

## 1. The shape

About 45,000 lines in 120 modules under `src/pegasus_data`, plus data that is
reviewed like code: `curation/` (180 YAML files) and `resources/` (the shipped
snapshot, 41 MB).

```text
 entry      cli.py (pegasus-data …)      serve/ (HTTP /api/v1, for ../pegasus_view)
              │                                │
 public API __init__.py: 66 lazily exported names
              │
 read       query() ─► _query_engine/ (plan, execute) ─► retrieve.fetch() ─┐
            load()/scan() (api.py) ─► lake ─────────────────────────────────┤
                                                    render_groups ─► view.render_table
 metadata   info (_info) · explore (_explore) · availability (_availability)
            describe (api) · DataDictionary (_dictionary) · search (_search) · dictionary (docsgen)
            compendium (_compendium) · gaps/questions (_unknowns) · translate (_translate)
 aggregate  aggregate() (_aggregate) · measures · capabilities · suggest
              │
 build      pipeline.Pipeline: crawl → inventory → semantics → sample → profile → families
            build.py: lake, population, DEMAS
            labelpack.py / bundle.py: the shipped snapshot and the portable bundle
              │
 layers     discovery/ → acquire/ → decode/ → normalize/ → persist/
            inventory/  profile/  semantics/  sources/  catalog/ (SQLite, the memory)
```

The **ingest half** (discovery → acquire → decode → normalize → persist, with
the catalog as memory) is coherent: one job per subpackage, one decode entry
point (`decode/service.py`). The **read and metadata half** grew a new
top-level door for each question and re-implements orchestration in several
of them (§5).

---

## 2. The runtime paths

### 2.1 Crawl and inventory (maintainer, or on demand)

`Pipeline.crawl` → `discovery/crawler.py` (concurrent, resumable) over
`discovery/ftp_client.py` (picks the listing verb per directory), parsed by
`discovery/listing.py`, diffed against the catalog by `discovery/reconcile.py`
(moves, disappearances; a crawl that would withdraw a large share fails).
`inventory/build.py` then derives each file's (system, series, UF, date) from
its name (`inventory/naming.py`, `inventory/systems.py`), groups files into
strata, reads each stratum's schema from the DBF header by a ranged fetch
(`inventory/schemas.py`, `decode/header.py`: the header census), and groups
schemas into families (`inventory/families.py`).

A fresh install does not crawl: its catalog starts as a copy of the shipped
seed (`catalog/seed.py`, ADR-0067), which carries the maintainer's crawl,
strata, schemas and families. `fetch()` still runs a **targeted** crawl of one
system's directory when the catalog has never seen that system
(`retrieve._discover`).

### 2.2 A read: `query()` → `fetch()`

1. `query()` (`_query_engine/executor.py`) builds a `QuerySpec`, plans it
   (`_query_engine/planner.py`): lake, fetch, or a year-level hybrid, after
   checking every expected source unit is covered.
2. A fetch plan calls `retrieve.fetch()`:
   - resolve the dataset through the ontology (`ontology.py`,
     `curation/ontology.yml`);
   - discover if needed; select files by UF/year/month (`_select_files`);
     refuse unbounded or oversized requests (`RequestTooLarge`);
   - acquire blobs (`acquire/fetcher.py` into `acquire/cache.py`,
     content-addressed);
   - decode in a killable subprocess (`decode/isolation.py`, `decode/_worker.py`,
     `decode/registry.py` probing content, not suffix);
   - normalise (`normalize/engine.py`) and union schema generations with
     structural nulls;
   - re-apply curation when the shipped YAML changed since the catalog was
     built (`_ensure_reference_tables`);
   - render labels (`render_groups.py` → `view.render_table`, §4).
3. Back in the executor: `_query_engine/semantics.py` applies dimensions
   (`MUNIC_RES.health_region`) and enrichments (CNES↔CNPJ, `crosswalk.py`), and
   assembles a `QueryReport`. Labels are the renderer's, unfiltered (ADR-0061).

`load()` and `scan()` (`api.py`) read the lake instead and render through the
same `render_groups`.

### 2.3 The semantic build (maintainer)

`Pipeline.semantics` harvests meaning, ranked by authority
(`semantics/dictionary.py`):
1. TAB kits (`semantics/tabkit.py`) containing `.CNV` codelists
   (`semantics/cnv_parser.py`) and `.DEF` tabulation definitions
   (`semantics/def_parser.py`, `semantics/defnames.py`);
2. SIGTAP (`sources/sigtap.py`), lookup DBFs, the DEMAS API
   (`sources/demas_api.py`);
3. layout PDFs (`semantics/pdf_harvest.py`);
4. community transcriptions (`sources/community.py`);
5. curation (`semantics/curation.py` loading `curation/variables/**`), the
   manual authority.

A `.DEF` binds a column to every tabulation axis that mentions it, so bindings
(`semantics/bindings.py`, catalog `field_codelists`) are many per field: 114 for
SIH `DIAG_PRINC`, 36 for `MUNIC_RES`. `semantics/ledger.py` holds per-field
aggregation rules; `semantics/relations.py` typed relations (`label_of`,
`rollup_to`, `attribute_of`, `crosswalk_to`) and the adjudication queue;
`semantics/gaps.py` what is not known. `labelpack.py` distils the result into
`resources/` (§3).

### 2.4 Aggregates and the frontend

A recipe (`curation/aggregates/*.yml`, 62 of them) is parsed into an
`AggregateSpec`. `_aggregate.build_aggregate` calls `fetch()` state by state,
lifts rows into mergeable accumulator states (`measures.py`: COUNT, SUM, MEAN,
RATIO, MIN, MAX as monoids) and writes a base cuboid; `aggregate()` rolls it up
through the geography graph (`geography.py`, compiled from the label pack).
`capabilities.py` describes a built artifact to a client; `serve/` exposes
artifacts, capabilities, population, geography memberships and (behind
`--allow-records`) microdata over HTTP. `suggest.py` proposes recipes.

---

## 3. Persistent objects

**The data home** (`config.py`, `locate.py`: five layers decide it; `pegasus-data
where` says which won):

```text
<home>/_catalog/catalog.sqlite   the catalog (catalog/schema.sql, catalog/store.py)
<home>/blobs/sha256/..           downloaded files, content-addressed
<home>/lake/<sys>/<family>/schema_signature=/uf=/year=/   the Parquet lake
<home>/lake/reference/           version-scoped code tables (persist/reference.py)
<home>/lake/population/ …        IBGE series
<home>/aggregates/ …             built aggregate artifacts
```

**The catalog** holds what the tree contains (`files`, `file_facts`,
`strata`, `schemas`, `families`, `family_files`, `schema_presence`), what
things mean (`field_codelists`, `variable_docs`, `dataset_docs`,
`dictionary`, `code_tables`, `semantic_relations`, `open_questions`), and
local state (`blobs`, `fetches`, `lake_partitions`, `build_outcomes`,
`adjudication_items`). 47 tables.

**The shipped snapshot** (`resources/`, in the wheel; 56.6 MB, budget 64 MiB):

| file | what | read by |
|---|---|---|
| `catalog_seed.sqlite.gz` (18.8 MB) | the maintainer catalog's tree and meaning tables; a fresh catalog starts as a copy (ADR-0067) | `catalog/seed.py` from `Catalog.__init__` |
| `labels.parquet` (30 MB) | 3.65M codelist rows as code ranges, by system and vintage | `labelpack.py`, `persist/reference.py` fallback, `geography.py` |
| `labels_crosswalk.parquet` (10 MB) | temporal CNES↔CNPJ | `crosswalk.py` |
| `geography.parquet`, `municipalities.parquet` | health-region memberships | `geography.py`, `_aggregate.py` |
| `query_capabilities.json`, `manifest.json` | compiled capabilities; the resource manifest with checksums | `_query_engine/capabilities.py`, `_resources.py`, `serve/` |

Built by `scripts/build_resources.py` (the seed and the manifest) and the
`labelpack` command (labels).

---

## 4. How a label is chosen today

`view._select_codelists`, per column, per file:

1. a curated `codelist`/`codelists` in `curation/variables` decides;
2. else a single catalog `label_of` relation decides;
3. else one bound codelist: used, with a warning if it is a rollup;
4. else more than twelve bound: **refused** ("arbitrarily capped");
5. else up to twelve are weighed against the file's distinct values
   (`_choose_binding`): the best decode share wins, ties to the finest grain;
   below 50% the column is left unlabelled.

Every read path applies this one policy (ADR-0061). The default render
profile keeps every raw code and adds a `<field>_label` companion (ADR-0063).
Weighing happens per file at read time, so two files of one dataset can be
labelled from different tables. Compiling one binding per field ahead of time
is M2.

---

## 5. What overlaps, and what becomes of it

Each row is a second mechanism for one job (CLAUDE.md §4). The plan column is
the milestone that removes the duplicate; an ADR is written when it is done.

| Job | Mechanisms today | Plan |
|---|---|---|
| read a dataset | `query` (wraps `fetch`), `fetch`, `load`, `scan`, `open_lake`; two dataset spellings (`"SIHSUS","RD"` vs `"SIH-RD"`) | M3: `query` is the engine; the others are thin forms of it; one identifier |
| decide a column's codelist | read-time weighing (`view.py`), curation, catalog relations; ~~the query-time gate~~ removed (ADR-0061) | M2: one compiled binding per field, applied identically everywhere |
| bootstrap a fresh catalog | ~~inside `fetch`, `_translate.py` separately, `tree.parquet` for `explore`, nothing for `info`~~ | **done** (ADR-0067): `Catalog.__init__` installs the seed |
| export the semantic layer | `labelpack.py`, `bundle.py`, `docsgen.py` (`docs/dictionary.sqlite`), `_compendium.py` (another SQLite), `persist/reference.py` | M3: one snapshot and one dictionary database |
| describe a thing | `info`, `describe`, `explore`, `DataDictionary`, `compendium`, `search`, `availability` | M3: kept as questions, backed by one catalog |
| decide a file's system | `inventory/naming.py`, `inventory/systems.py`, `ontology.py` | examined in M3 |
| convert an age | ~~`view._derive_age_years`~~ | **done** (ADR-0064): `_age.years_column` only |
| query capabilities | `capabilities.py` (aggregate artifacts) and `_query_engine/capabilities.py` (publication coverage) | rename in M3 |
| a `Catalog` | `api.Catalog` (public facade) and `catalog/store.Catalog` | rename in M3 |
| re-export the query engine | `_query.py` → `_query_engine/__init__.py` → `_query_engine/core.py` | M3: one module |
| stock time reducers | refused in `measures.py`, implemented in `tools/export_workbook.py` | M4: into `measures.py` |

Also known, not duplicates:
- `decode/_native/` compiles a C decompressor at runtime with a hardcoded
  Visual Studio path and writes the DLL into the package directory. A Python
  fallback exists.
- `ontology.py` hardcodes `CURATION`, so `PEGASUS_CURATION_DIR` is ignored by
  every `Ontology.load()` call.
- Rendering writes adjudication rows into the catalog, with failures silenced
  (`view.py`, `representations.py`).

---

## 5a. The public surface

`__init__.py` exports 68 names (`_EXPORTS`, resolved lazily). Grouped by the
question they answer; the overlap is §5's first rows.

| Question | Functions | Types and errors |
|---|---|---|
| give me data | `query`, `plan`, `fetch`, `load`, `scan`, `open_lake`, `translate` | `QuerySpec`, `QueryPlan`, `QueryReport`, `Period`, `Geography`, `FetchReport`, `LakeScan`, `RenderReport`, `PROFILES`, `DatasetUnknown`, `NothingPublished`, `FilterHasNoAxis`, `MissingColumnError`, `LabelUnavailable`, `TranslationImpossible`; warnings `TimeResolutionWarning`, `StructuralSchemaWarning`, `SemanticFallbackWarning`, `CrosswalkAmbiguityWarning` |
| attach more to it | `enrichment`, `memberships` | `EnrichmentRequest`, `MembershipSet`, `Membership` |
| what is this | `info`, `explore`, `describe`, `availability`, `field_available`, `field_coverage`, `search`, `compendium`, `gaps`, `questions`, `DataDictionary`, `Ontology` | `Info`, `Exploration`, `FieldDescription`, `Availability`, `FieldWindow`, `CompendiumReport`, `Gaps`, `OpenQuestions` |
| aggregate it | `aggregate`, `build_aggregate` | `AggregateSpec`, `AggregateReport` |
| reference data | `load_population`, `load_reference`, `export` | |
| the local store | `Catalog`, `resource_manager`, `pack`, `unpack`, `read_manifest`, `Settings`, `load_settings` | `ResourceManager`, `ResourceStatus`, `BundleError` |

---

## 6. The module map

Every module is named here; `scripts/check_docs.py` fails when one is not.

### top level

- `__init__.py`: the public names, resolved lazily.
- `api.py`: `Catalog` facade, `describe`, `load`, `scan`, `export`, `open_lake`,
  `write_table`, `load_population`, `load_reference`.
- `retrieve.py`: `fetch()`, DATASUS to a table in one call; the de facto read engine.
- `_query.py`: compatibility facade over `_query_engine/`.
- `view.py`: rendering: codelist selection, labels, profiles, derived columns.
- `render_groups.py`: groups files by vintage and system before rendering.
- `representations.py`: deduplicates the same publication delivered twice.
- `_aggregate.py`: recipes, `build_aggregate`, `aggregate()`.
- `measures.py`: the measure algebra (accumulator states).
- `capabilities.py`: what a client may do with a built aggregate.
- `suggest.py`: recipe suggestions.
- `geography.py`: health-region memberships and the geography graph.
- `crosswalk.py`: CNES↔CNPJ enrichment.
- `providers.py`: optional attribute providers (CNES names).
- `_age.py`: vectorised age in years and age bands.
- `_vintage.py`: vintage resolution helpers.
- `_explore.py`: `explore()`, what is on DATASUS.
- `_info.py`: `info()`, what a node of the ontology is.
- `_availability.py`: `availability()`/`field_coverage`, when a column existed.
- `_dictionary.py`: `DataDictionary`, the dictionary of a fetched table.
- `_translate.py`: `translate()`, labels for a user's own files.
- `_unknowns.py`: `gaps()`, `questions()`.
- `_compendium.py`: `compendium()`, the map of DATASUS as a SQLite file.
- `docsgen.py`: `docs/dictionary.sqlite` and its page reader.
- `_search.py`: `search()`, over the catalog's docs and the shipped label pack (ADR-0069).
- `_resources.py`: resource status, validation, `ensure`, `build`.
- `labelpack.py`: distils the catalog's labels into `resources/labels.parquet`.
- `bundle.py`: `pack`/`unpack` of the catalog's semantic tables.
- `ontology.py`: the declared systems and datasets, bound to crawl evidence.
- `pipeline.py`: `Pipeline`, the build stages.
- `build.py`: the stages that write data (lake, population, DEMAS).
- `progress.py`: deadlines and heartbeat.
- `config.py`, `locate.py`: settings and where the data home is.
- `textenc.py`: codepage detection.
- `verify.py`: runnable regression assertions (`pegasus-data verify`).
- `cli.py`: the Typer CLI.

### `_query_engine/`

- `_query_engine/core.py`: re-exports.
- `_query_engine/model.py`: `QuerySpec`, `QueryPlan`, `QueryReport`, warnings.
- `_query_engine/planner.py`: `plan()`.
- `_query_engine/executor.py`: `query()`.
- `_query_engine/filters.py`: publication-period filters.
- `_query_engine/semantics.py`: dimensions, enrichments, the `label_of` gate.
- `_query_engine/capabilities.py`: which datasets `query` can serve.

### `acquire/`

- `acquire/cache.py`: the content-addressed blob store.
- `acquire/fetcher.py`: bounded-concurrency downloads, skipping unchanged files.

### `catalog/`

- `catalog/store.py`: the SQLite catalog: migrations, upserts, history.
- `catalog/seed.py`: exports the seed from a maintainer catalog and installs it into a fresh one.

### `decode/`

- `decode/service.py`: `decode_source`, the one entry point.
- `decode/registry.py`: reader dispatch by content probe.
- `decode/base.py`: the reader interface.
- `decode/dbc.py`, `decode/dbf.py`, `decode/lha.py`, `decode/archives.py`,
  `decode/duckdb_.py`, `decode/text_.py`: readers.
- `decode/header.py`: DBF header parsing for the census.
- `decode/isolation.py`, `decode/_worker.py`: killable subprocess decoding.
- `decode/_native/`: the PKWare DCL decompressor (C, compiled on demand; Python fallback).

### `discovery/`

- `discovery/ftp_client.py`, `discovery/crawler.py`, `discovery/listing.py`,
  `discovery/reconcile.py`: §2.1.
- `discovery/https_client.py`: probes for an HTTPS mirror (none exists).

### `inventory/`

- `inventory/build.py`, `inventory/naming.py`, `inventory/systems.py`,
  `inventory/strata.py`, `inventory/schemas.py`, `inventory/families.py`: §2.1.

### `normalize/`

- `normalize/engine.py`: vectorised normalisation driven by the ledger.
- `normalize/geo.py`: 6- vs 7-digit municipality codes.
- `normalize/time.py`: competência and epidemiological weeks.
- `normalize/types.py`: type coercion.

### `persist/`

- `persist/lake.py`: writes the lake.
- `persist/duck.py`: DuckDB views over it.
- `persist/reference.py`: version-scoped code tables, with the label pack as fallback.
- `persist/staging.py`: atomic publish.
- `persist/decisions.py`: records of label substitutions.

### `profile/`

- `profile/accumulators.py`, `profile/detectors.py`, `profile/drift.py`,
  `profile/runner.py`: streaming per-field profiles, semantic detectors, schema drift.

### `semantics/`

- `semantics/tabkit.py`, `semantics/cnv_parser.py`, `semantics/def_parser.py`,
  `semantics/defnames.py`, `semantics/pdf_harvest.py`: harvesting (§2.3).
- `semantics/dictionary.py`: merges sources by authority.
- `semantics/curation.py`: loads `curation/`.
- `semantics/bindings.py`: field→codelist bindings.
- `semantics/ledger.py`: per-field aggregation rules.
- `semantics/relations.py`: typed relations and the adjudication queue.
- `semantics/reference.py`: reference-table helpers.
- `semantics/icd.py`: CID-9/CID-10 structure.
- `semantics/gaps.py`: what is not known.

### `serve/`

- `serve/__init__.py`: the HTTP server and routes.
- `serve/__main__.py`: `python -m pegasus_data.serve`.
- `serve/_payload.py`: response shaping.

### `sources/`

- `sources/sigtap.py`, `sources/demas_api.py`, `sources/ibge.py`,
  `sources/ibge_localidades.py`, `sources/community.py`: secondary sources.

---

## Invariants

The semantic non-negotiables are in `CLAUDE.md` §6. Structural ones:

- The catalog is the only memory; everything else is derived and rebuildable.
- A file's identity is its filename-derived `logical_id`, not its path.
- Blobs are content-addressed and immutable; a changed file is a new blob.
- Every decode runs where it can be killed; a timeout ends the work.
- Writes to the lake are staged and published atomically.
- `resources/` is a snapshot of a maintainer's catalog; nothing at runtime
  writes into the package directory (violated by `decode/_native/`, §5).
- A fresh catalog is the seed (ADR-0067); every door reads the catalog, never
  a shipped file directly, except the label pack and the geography packs.
