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
 entry      cli/ (pegasus-data …)        serve/ (HTTP /api/v1, for ../pegasus_view)
              │                                │
 public API __init__.py: 66 lazily exported names
              │
 read       query() ─► _query_engine/ (plan, execute) ─► retrieve.fetch() ─┐
            load()/scan() (api.py) ─► lake ─────────────────────────────────┤
                                                    render_groups ─► view.render_table
 metadata   info (_info) · explore (_explore) · availability (_availability)
            describe (api) · DataDictionary (_dictionary) · search (_search)
            compendium (_compendium) · gaps/questions (_unknowns) · translate (_translate)
 aggregate  aggregate() (_aggregate) · measures · capabilities · suggest
              │
 build      pipeline.Pipeline: crawl → inventory → semantics → sample → profile → families
            build.py: lake, population, DEMAS
            labelpack.py, catalog/seed.py: the shipped snapshot
              │
 layers     discovery/ → acquire/ → decode/ → normalize/ → persist/
            inventory/  profile/  semantics/  sources/  linkage/  catalog/ (SQLite, the memory)
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
3. Back in the executor: `_query_engine/semantics.py` applies dimensions and
   enrichments (CNES↔CNPJ, `crosswalk.py`), and assembles a `QueryReport`.
   - **Code roll-ups** (`CAUSABAS.chapter`) go through `joins.yml` relations
     to label-pack codelists.
   - **Municipality roll-ups** (`CODMUNRES.health_region_current`) go through
     the membership pack, for any column `geography.yml` lists in
     `municipality_fields` (ADR-0130). Labels are the renderer's, unfiltered (ADR-0061).

`plan()` also emits the lake read: `RetrievalPlan.lake_partitions`, the exact files of one reading of each lake year (the
national file or the states', never both; all on disk when planned), and `query` hands them to `load(partitions=)` in one
call. `load()` and `scan()` (`api.py`) read the lake and render through the same `render_groups`; both start from
`plan_lake_read` (`_query_engine/readplan.py`: dataset families, the axis refusal, the schema census, the files, the
missing-column rule), from the catalog's list of the lake (`lake_partitions`, ADR-0164) through the process's one read-only
catalog connection whose reads are remembered until the catalog changes (ADR-0163). Without a plan a caller's `uf`/`years`
narrow that list by the same one-reading rule (`coverage.one_reading`). Reference lookups are keyed by the validity window
a month falls in (`persist.reference.reference_vintage`, ADR-0185), not by the month.

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
MOMENTS, LOGMOMENTS, RATIO, MIN, MAX as monoids) and writes a base cuboid; `aggregate()` rolls it up
through the geography graph (`geography.py`, compiled from the label pack).
`capabilities.py` describes a built artifact to a client; `serve/` exposes
artifacts, capabilities, population, geography memberships and (behind
`--allow-records`) microdata over HTTP. `suggest.py` proposes recipes.

---

## 3. Persistent objects

**The data home** (`config.py`, `locate.py`: five layers decide it, and an explicit root carries its blobs, lake, work and
catalog with it, ADR-0175; `pegasus-data where` says which won):

```text
<home>/_catalog/catalog.sqlite   the catalog (catalog/schema.sql, catalog/store.py)
<home>/blobs/sha256/..           downloaded files, content-addressed
                                 (every blob named by snapshot_versions is kept, ADR-0141)
<home>/lake/<sys>/<family>/schema_signature=/uf=/year=/   the Parquet lake
<home>/lake/reference/           version-scoped code tables (persist/reference.py); `_stamps.json`: each system's dictionary fingerprint, a stale system rewritten on read
<home>/lake/population/ …        IBGE series
<home>/aggregates/ …             built aggregate artifacts
<home>/registries/sidra/         the SIDRA registry (registry.sqlite) and every IBGE response kept as received (http/)
<home>/lake/sidra/facts/table=<id>/   SIDRA observations, long, one Parquet part per request (ADR-0142)
```

**The catalog** holds what the tree contains (`files`, `file_facts`,
`strata`, `schemas`, `families`, `family_files`, `schema_presence`), what
things mean (`field_codelists`, `variable_docs`, `dataset_docs`,
`dictionary`, `code_tables`, `semantic_relations`, `open_questions`), and
local state (`blobs`, `fetches`, `snapshot_versions`, `lake_partitions`,
`build_outcomes`, `adjudication_items`). 48 tables.
`snapshot_versions` is the kept history of the files DATASUS rewrites in place
(`snapshot.py`, ADR-0141): one row per (path, content, server mtime), never
deleted, not in the seed.

**The shipped snapshot** (`resources/`, in the wheel; 61.0 MiB on 2026-10-04 after the code structures and proximity graphs, from 56.6 MB; budget 64 MiB):

| file | what | read by |
|---|---|---|
| `catalog_seed.sqlite.gz` (18.8 MB) | the maintainer catalog's tree and meaning tables; a fresh catalog starts as a copy (ADR-0067) | `catalog/seed.py` from `Catalog.__init__` |
| `labels.parquet` (30 MB) | 3.65M codelist rows as code ranges, by system and vintage | `labelpack.py`, `persist/reference.py` fallback, `geography.py` |
| `labels_crosswalk.parquet` (11 MB) | historical CNES↔CNPJ claims from older kits; the registry answers first (ADR-0100) | `crosswalk.py` |
| `icd10`, `cbo2002`, `sigtap`, `banks`, `countries` `.parquet` | canonical classifications, one table for every system (ADR-0087) | `persist/reference.py` |
| `bridges.parquet` | every classification bridge: pre-2008 SIA/SIH procedures → SIGTAP (official), CBO 1994 → CBO 2002 (CNES's measured 2007 conversion, then MTE's) (ADR-0101, ADR-0104) | `view.bridged`; built by `scripts/build_bridges.py` |
| `geography.parquet`, `municipalities.parquet` | health-region memberships | `geography.py`, `_aggregate.py` |
| `publication_coverage.json`, `manifest.json` | compiled publication coverage; the resource manifest with checksums | `_query_engine/coverage.py`, `_resources.py`, `serve/` |

Built by `scripts/build_resources.py` (the seed and the manifest) and the
`labelpack` command (labels).

---

## 3a. The data model: from a file on the server to a variable

DATASUS publishes files. A person asks for a dataset. Between the two are six
objects, each derived from the one before and each with one job.

```text
system    SIH, SIA, SINAN …           ontology.yml: what the institution calls it
 └ dataset  SIH.RD, SINAN.DENG …        ontology.yml + curation/datasets: what one row IS
    └ stratum  (system, series, year)    inventory/strata.py: the unit of sampling
       └ file     one path on the server   files, file_facts (UF, date, logical_id, part)
          └ member   a table inside an archive or a DuckDB database (archive_members)
    └ family   (system, series, schema signature)  inventory/families.py
       └ publication  logical_id = system|series|UF|date[|part]; its representations
```

- **Dataset and series.** A dataset is the ontology's name for a series:
  `SIH.RD` is the series `RD` of the system `SIHSUS`. One dataset is one kind
  of row.
- **File facts.** Parsing a file's name (`inventory/naming.py`) gives:
  - its series, its UF (or `BR`), its date and its split-publication part;
  - its **logical identity**, which uses the **normalized** date, so
    `DNRRR95.DBC` and `DNRRR1995.dbc` are one publication (ADR-0081).
- **Schema.** A file's schema is its ordered column list, hashed into a
  **signature**. Since ADR-0081 every DBC/DBF header is read (`file_schemas`,
  183,128 files, 437 MB, 2026-09-29), plus archives and DuckDB databases by
  their members (ADR-0077, ADR-0083). Nothing is inferred from a sample any
  more, except inside archives.
- **Family.** A family is one dataset in one physical layout: (system,
  series, signature). Measured 2026-09-29: **390 families**, with 77 datasets
  having more than one. Every file belongs to the family of its **own**
  header. A layout change mid-series (SIH added columns in 2008, SIA-PA gained
  `PA_VL_CRD` in 2026) is a new family, not an error.
- **Publication and representation.** One publication can exist several times:
  - in several formats (`.dbc`, `.csv.zip`, `.xml`), where the cheapest to
    decode is read;
  - in several trees (the 1994_1995/Dados and ANT folders), where byte-identical
    copies collapse;
  - as several editions (the MHJ_14_16 folder versus 200801_/Dados), where the
    newest wins;
  - in several layouts, where the majority layout wins.

  A query reads each publication **once** (`representations.py`).
- **Member.** A table inside an archive is its own publication. SIA's
  2001-2007 APAC archives each hold up to eight tables; a DuckDB database
  holds a fact table and its `dim_*` tables.

**How a query crosses layouts.**
- A query selects publications by period and UF. It decodes each file with its
  own family's normalisation plan and concatenates the results.
- A column absent from one layout is null for those rows, and
  `structural_absence` in the report says so.
- A file that gained columns since it was catalogued is read with them
  (ADR-0078). A file that lost a catalogued column is refused.

**What the model does not yet do: the variable.**
- A column is identified by its physical name. When DATASUS renames a column
  between layouts (SINASC's `CODIGO` and `CONTADOR`, 1995), the two stay two
  columns.
- Measured 2026-09-29: 1,869 fields are absent from some family of their
  dataset.
- The column position gives no reliable pairing: 1,176 same-position
  complementary pairs, most of them unrelated fields.
- A merge needs evidence, either a documented rename or matching value
  distributions. Merging silently would break the rule "never resolve a
  conflict silently". This is OQ-57.

---

## 4. How a label is chosen

One function, `semantics/label_bindings.decide()`, used by the renderer at
query time and by `compile_bindings` at build time (ADR-0082). Best evidence
first:

1. **`codes:` in the curation**: a code table written for this column, from
   a document (ADR-0079);
2. **the form's own dictionary**: a table harvested from DATASUS's official
   data-dictionary PDFs (`scripts/harvest_codes.py`, `curation/codes/`), keyed
   by series because a column name means different codes on different forms.
   It is taken when it decodes at least 95% of the column's rows (ADR-0080);
3. **a curated `codelist:`** (or, with `per_form: true`, a list of per-form
   alternatives, which become candidates for step 6);
4. **a reviewed adjudication** (`label_of` relation);
5. **the stored decision** in `label_bindings`, compiled from sample files and
   shipped in the seed (ADR-0072);
6. **measured weighing** of every table the TabWin `.DEF` files bind to the
   field. Per-state partitions are collapsed, rollups (a region for a
   municipality) are excluded, and the best identity table must decode at
   least half the values.

A code no table decodes stays raw and is reported. The presentation then shows
it as `9 (?)` (ADR-0084). `pegasus-data meaning` measures, for every field of
every family, whether it is described and whether its codes decode (ADR-0085).

---

## 5. What overlaps, and what becomes of it

Each row is a second mechanism for one job (CLAUDE.md §4). The plan column is
the milestone that removes the duplicate; an ADR is written when it is done.

| Job | Mechanisms today | Plan |
|---|---|---|
| read a dataset | ~~`fetch`, `load`, `scan`, `open_lake`, `export` as public doors~~ | **done** (ADR-0073): `query` is the one door; the engines are internal; one identifier resolver |
| decide a column's codelist | ~~read-time weighing per file, capped at 12~~; ~~the query-time gate~~ | **done** (ADR-0061, ADR-0072): curation, then one stored binding per family and field |
| bootstrap a fresh catalog | ~~inside `fetch`, `_translate.py` separately, `tree.parquet` for `explore`, nothing for `info`~~ | **done** (ADR-0067): `Catalog.__init__` installs the seed |
| export the semantic layer | ~~the bundle and the dictionary database~~ | **done** (ADR-0075): the seed and label pack ship; `compendium()` is the researcher's map; `persist/reference` the lake's tables |
| describe a thing | `info`, `describe`, `explore`, `DataDictionary`, `compendium`, `search`, `availability` | M3: kept as questions, backed by one catalog |
| decide a file's system | `inventory/naming.py`, `inventory/systems.py`, `ontology.py` | **examined** (2026-10-04): not duplicates but three layers. `naming.system_from_path` is the path's evidence; `systems.resolve_system` decides (a trustworthy learned prefix wins, the path otherwise) and the inventory stores it in `file_facts.system`; `Ontology.bind` maps that system and series to a declared dataset. `pipeline` reads documentation files' system from the path alone; it equals the stored one for all 227 non-data files (repo home) |
| convert an age | ~~`view._derive_age_years`~~ | **done** (ADR-0070): `_age.years_column` only, fractional years from measured units |
| query capabilities | ~~two modules named `capabilities`~~ | **done** (2026-10-04): `capabilities.py` is what a client may do with an aggregate; `_query_engine/coverage.py` (and `publication_coverage.json`) is what DATASUS publishes |
| a `Catalog` | ~~`api.Catalog` and `catalog/store.Catalog`~~ | **done** (2026-10-04): `Catalog` is the public door; the SQLite store is `catalog/store.CatalogStore` |
| re-export the query engine | ~~three layers~~ | **done** (ADR-0073): `_query_engine/` only |
| stock time reducers | ~~refused in `measures.py`, implemented in `tools/export_workbook.py`~~ | **done** (2026-10-04): `_aggregate` reduces a stock over time (OQ-14); the workbook (`workbook.py`, `pegasus-data workbook`) calls it |
| choose a publication's files | `Builder.build` and `retrieve._select_files` each read a family's files, filter by state, year and month, and call `choose_representations`; the retry after a refusal for columns is shared since ADR-0190 | one function that returns the selected rows of a family, called by both |

Also known, not duplicates:
- ~~`decode/_native/` compiled into the package with a hardcoded Visual
  Studio path~~: it builds into a per-user cache with discovered compilers
  (ADR-0074). Shipping it compiled in wheels awaits a publishing decision.
- ~~`ontology.py` hardcodes `CURATION`, so `PEGASUS_CURATION_DIR` is ignored by
  every `Ontology.load()` call~~: every reader resolves it through
  `config.curation_root()` (2026-10-04).
- ~~Rendering writes adjudication rows into the catalog, with failures silenced
  (`view.py`, `representations.py`)~~: a query reads stored label decisions
  without writing (`decide(persist=False)`), and representation conflicts are
  derived on every call; the `representation_conflicts` table is dropped
  (2026-10-04).

---

## 5a. The public surface

`__init__.py` exports 79 names (`_EXPORTS`, resolved lazily; the "56" written here earlier was stale, recounted 2026-10-04); the data engines (`retrieve.fetch`, `api.load`, `api.scan`) are internal (ADR-0073). Grouped by the
question they answer; the overlap is §5's first rows.

| Question | Functions | Types and errors |
|---|---|---|
| give me data | `query`, `plan`, `translate` | `QuerySpec`, `QueryPlan`, `QueryReport`, `Period`, `Geography`, `RenderReport`, `DatasetUnknown`, `NothingPublished` (and its `PublishedEmpty`: read, and published with no records), `DownloadBudgetExceeded` (over `max_download`, ADR-0076), `FilterHasNoAxis`, `MissingColumnError`, `LabelUnavailable`, `TranslationImpossible`; warnings `TimeResolutionWarning`, `StructuralSchemaWarning`, `SemanticFallbackWarning`, `CrosswalkAmbiguityWarning`, `PartialSourceWarning` (a short table accepted with `allow_partial`, ADR-0095) |
| attach more to it | `enrichment`, `memberships` | `EnrichmentRequest`, `MembershipSet`, `Membership` |
| what is this | `info`, `explore`, `describe`, `availability`, `field_available`, `field_coverage`, `field_fill`, `search`, `compendium`, `gaps`, `questions`, `DataDictionary`, `Ontology` | `Info`, `Exploration`, `FieldDescription`, `Availability`, `FieldWindow`, `CompendiumReport`, `Gaps`, `OpenQuestions` |
| what each column states, and what a row counts as | `roles` (entity.property, value kind, model role per column), `event_types`, `count_events` (status, consolidation and weight applied: a row may stand for a quantity, ADR-0155, or a grid of people by sex and age band, ADR-0156; a row may be a group with no person strata, ADR-0157) | |
| how places relate | `proximity_graph` (contiguity by border km, population-weighted distance, REGIC 2018 links), `municipality_areas`, `regic_cities`, `care_flows` (residence → place of care, birth or death, as events), `care_flow_profile`, `care_flow_catchments`, `care_flow_communities`, `compare_flow_regions` (what a flow graph says about places, derived on request, ADR-0144) | |
| how much two fields share | `field_overlap` (shared events over the smaller field) | |
| how codes are organised | `code_structures`, `code_structure` (trees as parent tables: ICD10, SIGTAP, CBO2002, CNAE20; lists as memberships: CID-BR-10, ICD-10 lists 2 and 4, avoidable causes, ICSAP, SIM's typed garbage codes); `code_bridge` (ICD-9 → ICD-10, NCHS's double-coding study); `code_attributes` (each ICD-10 code's dual role, sex restriction and cause-of-death fields in the DATASUS release; NCHS Part 11 Table G's age and sex edits, absolute or conditional; for chapter XX the NCHS matrix's mechanism and intent and the release's place of occurrence) | |
| aggregate it | `aggregate` (a classifier rolls up its code tree: `by=["CAUSABAS@category"]`; results carry `data_version`), `build_aggregate` (counts a recipe's declared `event_type`; national files read whole) | `AggregateSpec`, `AggregateReport` |
| reference data | `load_population`, `load_reference`, `load_field` | |
| places | `municipality_point`, `distance_km` (population centre by default) | |
| rates | `age_standardised_rates` (direct, WHO 2000 or Brazil 2022) | |
| how far to trust it | `race_reliability` | |
| the local store | `resource_manager`, `Settings`, `load_settings` | `ResourceManager`, `ResourceStatus` |

---

## 6. The module map

Every module is named here; `scripts/check_docs.py` fails when one is not.

### top level

- `__init__.py`: the public names, resolved lazily.
- `api.py`: `Catalog` facade, `describe`, `load`, `scan`, `export`, `open_lake`,
  `write_table`, `load_population`, `load_reference`.
- `retrieve.py`: `fetch()`, DATASUS to a table in one call; the de facto read engine.
- `_request.py`: what a request asks for, checked before a byte is fetched: the dataset spec, axis refusals, state/month/year cleaning, and the errors `fetch` raises.
- `view.py`: rendering into the canonical form: codelist selection, `_label` companions, derived columns.
- `lookups.py`: code → label maps, read per vintage, cached per table version, merged in authority order, and applied at exact width (§6.2).
- `rates.py`: crude and directly age-standardised rates of queried records over POPSVS.
- `quality.py`: where a field's values cannot be taken at face value, measured from the data: `race_reliability` (ADR-0128).
- `fields.py`: context fields, IBGE's municipal statistics declared in `curation/fields.yml`, read through `sidra/` into `<lake>/fields/` (ADR-0127, ADR-0142); an entry with `series:` is a measure of a stitched census series. Also climate: BR-DWGD's municipal zonal statistics (`sources/brdwgd.py`: the municipality-month base `climate_monthly`, and six sum fields with `over` read from it, one value per municipality and year, `partial_year` below twelve months held, ADR-0177 and ADR-0178) and INMET's station-month base `climate`, kept as observations to validate them; S2iD disasters, ANS plan beneficiaries and INEP enrolment margins (declared intake sources, ADR-0188) and CNES supply (`sources/cnes.py`: 35 `cnes_*` fields, December stocks of establishments, beds, equipment, professionals and teams by municipality, code groups in the `cnes:` block of `fields.yml`, ADR-0150; `field_rate` divides a sum field by the population account); every non-FTP byte goes through `transport.py` (ADR-0188).
- `registry.py`: registries from their owner's current TabWin kit, fetched once and cached (ADR-0086): the typed establishment registry (`CADGERBR`: names, maintainer, valid CNPJ only, inclusion/exclusion dates), `CNPJ_BR`, teams (`INE_EQUIPE_BR`, SIASUS kit) and `HUF_*` (ADR-0100). The single source of establishment identity.
- `presentation.py`: how a result reads, applied last: value and header templates, presets, language (ADR-0084).
- `render_groups.py`: groups files by vintage and system before rendering.
- `representations.py`: deduplicates the same publication delivered twice, and re-chooses after a representation was refused for its columns (`refused=`, ADR-0190).
- `_aggregate.py`: recipes, `build_aggregate`, `aggregate()`.
- `measures.py`: the measure algebra (accumulator states).
- `capabilities.py`: what a client may do with a built aggregate.
- `workbook.py`: a built aggregate as an Excel workbook, each sheet its own aggregation (`pegasus-data workbook`).
- `suggest.py`: recipe suggestions; what is structural (identifier, date, the event's own place) comes from the dataset's declared column roles, never from names.
- `geography.py`: health-region memberships and the geography graph. `mesh_file`: IBGE's mesh, downloaded once (the one definition of its URL; `mesh` reads it for maps, the points pack and INMET's station placement take the same file).
- `extract.py`: filtered extracts, `<lake>/extracts/<dataset>/<digest>/`: the records of a dataset that its filters (column → code prefixes) match, its files read, kept and released one by one; a manifest of every file's rows read and kept and the files that failed. Apart from the lake, so no query reads a filtered table as the dataset; `extract_table` serves a code set only where the extract holds its years whole. A filter column that is in no file's header (the catalog's census) is refused before the first fetch.
- `concepts.py`: the concept index: which sources hold a condition's codes (every record's own condition code by its role, SINAN's `ID_AGRAVO`; SIGTAP's procedure–ICD compatibility, label search over ICD-10 and SIGTAP), cached in `registries/concepts` (PegaSUS's scope). `dispensed`: the SIGTAP medicine procedures (group 06) of SIA's APAC AM authorised under the codes, one APAC once (the event type's rule), cached per year; `stock_by_state`: BNAFAR's stock of a drug by state and month. `treatments`: the medicines an official document gives for the codes (`curation/treatments.yml`, each substance with the declared fields that count it, their exact filter and denominator); records never name a treatment here. `captures`: the populations several systems list, for capture–recapture (`curation/captures.yml`: one definition across systems, each list's filter on its role table, its grouping into one person and its deaths; a link's side filter is written for pairing and is never a population).
- `transport.py`: the one client of every byte not on the FTP tree (ADR-0188): `request`/`get_json`/`get_text`, `read_range`, `download`; HTTP/1.1 over IPv4 with the system trust store, a browser User-Agent, one request per interval per host (shared by threads), resets/timeouts/408/425/429/5xx retried with `Retry-After`, any other 4xx `SourceAbsent` at once, a streamed download resumed with an `If-Range` validator. `intake`, `sidra/`, `sources/*` and `geography` call it; the FTP client and the S3 mirror of the FTP tree (`discovery/`, `acquire/`, `snapshot.py`) are the FTP tree's own.
- `intake.py`: the one intake for sources that are not on the FTP (ADR-0162), declared in `curation/intake.yml` (DEMAS, the Portal, S2iD, INEP, ANS): records land in the lake as Parquet (raw beside typed, DuckDB-streamed) and register as a queryable dataset (catalog family, ontology system and series, curation docs from the same declaration); context fields are derived from the records into `<lake>/fields/`; DEMAS and Portal files are read politely (API tables unstable under paging by partitioned filters), a unit is replaced whole across every schema family (staged, counted, swapped, registered; ADR-0172), and `check_source` sets the used origin against its `compare` origin.
- `sources/bnafar.py`: BNAFAR/Hórus medicine stock domain logic (CATMAT items, supply units, the monthly grouping) on `intake`; every fresh read also lands in the lake as `BNAFAR-STOCK` with its read day (the endpoint serves current positions only).
- `identifiers.py`: what a CNPJ and a CPF are (check digits), and what a label may not begin with: an identifier (ADR-0102) or TabWin's order mark (`LABEL_PREFIX`, ADR-0105).
- `linkage/`: record linkage across systems (ADR-0107; `docs/plans/linkage.md`).
- `linkage/roles.py`: records as normalised roles (`curation/roles.yml`), with their setting (ADR-0109, ADR-0123); `role_table(where=)` is the one reader: national role tables of whole years cached under `<lake>/roles/` (keyed by the dataset's role block, the label files' content and that year's lake partitions; read projected and filtered by `_uf`, multi-year periods as unions, LRU-capped by `role_cache_gb`), a state whose nation is not cached computed alone, national ones built state by state (ADR-0167, ADR-0186).
- `linkage/identity.py`: record identity (`_record_key`, numbered for exact duplicates; ADR-0124), the memory-bounded DuckDB connection every linkage module uses and the one SQL identifier quoting (`quote`).
- `linkage/engine.py`: deterministic linkage from `curation/links.yml` (a side may be `group`ed, its `latest` record standing for the group): 1:1 passes over what is left, a negative control per pass, held-out validations, `judge` (the one verdict rule) and `Report` (the result both engines extend) (ADR-0110, ADR-0186).
- `linkage/placebo.py`: the one negative control: a left key rotated round the partner's range, the reach tests of the deterministic keys and the probabilistic blocks; used by `engine`, `probabilistic` and `discover` (ADR-0186).
- `linkage/model.py`: comparisons (optionally conditioned on a right-side role, ADR-0115), evidence in bits per level, the false-match threshold (ADR-0111).
- `linkage/levels.py`: the one definition of comparison levels, on whole Arrow arrays, returned as integer codes (`Levels`; national candidate sets; ADR-0111, ADR-0115, ADR-0121).
- `linkage/store.py`: link runs kept in the lake, keyed by spec content, method and scope and served while their fingerprint (`LINKAGE_VERSION`, the role-table keys of the years read) is current, reused by `link()` (ADR-0112, ADR-0167, ADR-0186).
- `linkage/timeline.py`: one pregnancy as linked events from the spine links; served by `serve/` behind `--allow-records` (ADR-0112).
- `linkage/probabilistic.py`: probabilistic linkage: m from leave-one-field-out anchors, u from random pairs, a half-year rotation placebo (`linkage/placebo.py`), 1:1 resolution (ADR-0111, ADR-0167).
- `linkage/discover.py`: link discovery: every key from type-compatible roles counted against a week-rotated placebo (`linkage/placebo.py`); `discover_links()`, `pegasus-data link-discover` (ADR-0119).
- `linkage/entities.py`: stored links merged into persons (union-find over (record, person role), strongest evidence first, refusing merges that break a person constraint); `build_entities()`, `person_pairs()`, `pegasus-data link-entities` (docs/plans/linkage-theory.md §3.3).
- `linkage/annotators.py`: settings as annotators. Dawid–Skene EM over persons classified by several settings (a latent consensus class, a confusion matrix per setting), optionally hierarchical (a hospital shrunk toward its system); race and other clerk-recorded categories (docs/plans/linkage-theory.md §5, T4).
- `linkage/uncertainty.py`: linkage error into analyses: `p_match` weights, `link_draws()` (plausible link sets from the match probabilities), Rubin's rules (docs/plans/linkage-theory.md §6, T5).
- `crosswalk.py`: CNES↔CNPJ enrichment. Reads the registry first (windows from inclusion to exclusion), then the label pack's historical claims where the registry is silent; compares with the record's own CNPJ when the layout has one (ADR-0100).
- `providers.py`: optional attribute providers (CNES names).
- `_age.py`: age in fractional years from measured unit tables (ADR-0070), and age bands.
- `_vintage.py`: vintage resolution helpers.
- `_explore.py`: `explore()`, what is on DATASUS; `lake_coverage()`, what the lake holds by year; `publications()`, the files it holds a dataset's records from (path, server size and date, digest decoded, fetch, rows, preliminary or final; read from the lake rows' own `_source_path` and `_blob_sha256`) and the files listed but not held (ADR-0181).
- `_info.py`: `info()`, what a node of the ontology is; `dataset_facts()`, what the shipped curation documents of a dataset (row, dates, events, notes) with their sources (ADR-0181).
- `_availability.py`: `availability()`/`field_coverage`, when a column existed; `field_fill`, how much of each year it fills (presence is not fill).
- `_dictionary.py`: `DataDictionary`, the dictionary of a fetched table.
- `_translate.py`: `translate()`, labels for a user's own files.
- `_unknowns.py`: `gaps()`, `questions()`.
- `_compendium.py`: `compendium()`, the map of DATASUS as a SQLite file.
- `_search.py`: `search()`, over the catalog's docs and the shipped label pack (ADR-0069).
- `_resources.py`: resource status, validation, `ensure`, `build`.
- `labelpack.py`: distils the catalog's labels into `resources/labels.parquet`.
- `ontology.py`: the declared systems and datasets, bound to crawl evidence.
- `snapshot.py`: `pegasus-data snapshot`, the versions of preliminary and current-year files (declared in `curation/snapshots.yml`) kept as they change; `versions()` and `digests_as_of()` behind `query(as_of=)` (ADR-0141).
- `pipeline.py`: `Pipeline`, the build stages.
- `build.py`: the stages that write data (lake, population, the DEMAS OpenAPI document); `build_lake(dataset, years, root=)` builds one dataset's lake for a caller that is not the command line.
- `progress.py`: deadlines and heartbeat.
- `config.py`, `locate.py`: settings and where the data home is.
- `textenc.py`: codepage detection; `fold`, the one folding of names compared (accents, case, hyphen and apostrophe between words).
- `_lazy.py`: a module imported on its first use (`pyarrow.dataset`, which loads pandas, kept off every command's start).
- `verify.py`: runnable regression assertions (`pegasus-data verify`).
- `cli/`: the Typer CLI (`python -m pegasus_data.cli`, `cli/__main__.py`), one module per help panel: `cli/setup.py`, `cli/pipeline.py`, `cli/read.py`, `cli/audit.py`, `cli/sidra.py` (`pegasus-data sidra`); shared options and helpers in `cli/_common.py`.

### `_query_engine/`

- `_query_engine/model.py`: `QuerySpec`, `QueryPlan`, `QueryReport`, warnings.
- `_query_engine/planner.py`: `plan()`.
- `_query_engine/executor.py`: `query()`.
- `_query_engine/filters.py`: publication-period filters.
- `_query_engine/semantics.py`: dimensions, enrichments, the `label_of` gate.
- `_query_engine/coverage.py`: which datasets `query` can serve, and which years the lake holds whole (files looked at on disk); `national_or_states`: a year published nationally and per state is read once.

### `acquire/`

- `acquire/cache.py`: the content-addressed blob store.
- `acquire/fetcher.py`: bounded-concurrency downloads, skipping unchanged files.
  When an FTP transfer fails, it falls back to the mirror at the listed size,
  recorded as `mirror:<url>` (ADR-0122).

### `catalog/`

- `catalog/store.py`: the SQLite catalog: migrations, upserts, history; `shared()` / `memo()`: the read-only connection kept per process and the reads remembered until `data_version` moves (ADR-0163).
- `catalog/seed.py`: exports the seed from a maintainer catalog and installs it into a fresh one.

### `decode/`

- `decode/service.py`: `decode_source`, the one entry point.
- `decode/registry.py`: reader dispatch by content probe.
- `decode/base.py`: the reader interface.
- `decode/dbc.py`, `decode/dbf.py`, `decode/lha.py`, `decode/archives.py`,
  `decode/duckdb_.py`, `decode/text_.py`: readers.
- `decode/header.py`: DBF header parsing for the census (dBase III/IV/7).
- `decode/duckdb_remote.py`: a remote DuckDB database's tables and columns from a few ranged reads (ADR-0083).
- `decode/isolation.py`, `decode/_worker.py`: killable subprocess decoding.
- `decode/admission.py`: machine-wide decode slots (file locks) and a free-RAM floor, so
  concurrent processes cannot multiply worker pools into paging.
- `decode/_native/`: the PKWare DCL decompressor (C, built once into a user cache; Python fallback, 20× slower).

### `discovery/`

- `discovery/ftp_client.py`, `discovery/crawler.py`, `discovery/listing.py`,
  `discovery/reconcile.py`: §2.1.
- `discovery/https_client.py`: the HTTPS transport. It probes DATASUS's own
  hosts for a mirror (none exists) and serves the fetcher's fallback to the
  third-party S3 mirror (ADR-0122).

### `inventory/`

- `inventory/build.py`, `inventory/naming.py`, `inventory/systems.py`,
  `inventory/strata.py`, `inventory/schemas.py`, `inventory/families.py`: §2.1.

### `normalize/`

- `normalize/engine.py`: vectorised normalisation driven by the ledger.
  A column no profile describes still takes its container's declaration: a DBF `D` field is typed as a date (SINAN, 96 of 98 families).
- `normalize/geo.py`: 6- vs 7-digit municipality codes.
- `normalize/time.py`: competência and epidemiological weeks.
- `normalize/types.py`: type coercion.

### `persist/`

- `persist/lake.py`: writes the lake and reads it from the catalog's list of partitions (`Lake.listed`, `dataset_of`; a listed file missing is `PartialLakeError`, ADR-0164).
- `persist/duck.py`: DuckDB views over it.
- `persist/reference.py`: version-scoped code tables, with the label pack as fallback; which validity windows answer a request is `labelpack.select_windows`, the rule of both (ADR-0187). An inline curated codelist reads from the curation itself; a code written `{label, from, to}` decodes only in those years (`curation.inline_windows`, ADR-0189).
- `persist/staging.py`: atomic publish. A lake partition is staged under `<lake>/.staging/`, outside every family tree (a glob over a family would read it), and a refused rename is retried (ADR-0173).
- `persist/decisions.py`: records of label substitutions.

### `profile/`

- `profile/accumulators.py`, `profile/detectors.py`, `profile/drift.py`,
  `profile/runner.py`: streaming per-field profiles, semantic detectors, schema drift.

### `semantics/`

- `semantics/tabkit.py`, `semantics/cnv_parser.py`, `semantics/def_parser.py`,
  `semantics/defnames.py`, `semantics/pdf_harvest.py`: harvesting (§2.3).
- `semantics/dictionary.py`: merges sources by authority.
- `semantics/curation.py`: loads `curation/`.
- `semantics/epoch.py`: the curation epoch (the curation directory in use and the digest of its content, once per process) and `@curated`, the one memo for everything a process derives from the curation files (roles, event types, grids, inline codelists, the ontology, the declared fields, relations, the care flows): built once per epoch and shared, dropped together by `forget_curation()` (ADR-0187).
- `semantics/column_roles.py`: `curation/roles/<dataset>.yml`, a role for every column, validated against the linkage roles; every place states whose it is (`place_of`: the subject's, the event's or the record's; a stratum is the subject's, a `where` the event's, ADR-0187); every column a study reads as a field (categorical or not) also declares its `fact_domain` (person, clinical, process, administrative) with evidence, and `pg.roles` returns it, so a study groups by people, disease and care, never by billing fields (docs/evaluation/2026-10-11-column-domains.md); every measure declares its `unit` with the document line (or `unit_unknown` and why), an amount of money the `competence` column(s) of its month and the first month in its currency (`unit_from`), and `undeclared_units()` lists those not yet decided (ADR-0184).
- `proximity.py`: proximity graphs as edge lists (`proximity.parquet`, `municipality_areas.parquet`, `regic_cities.parquet`, built from IBGE's 2022 mesh, Census tracts and REGIC 2018) and care flows counted from records; `care_flows` is the one flow mechanism (per year, `share`, municipality or CNES destination, every event accounted for, ADR-0144); which datasets have a flow, and its columns, are derived from the column roles (`flows()`: the residence stratum to the event entity's `where` municipality, ADR-0166), not listed.
- `careflow.py`: what a care-flow graph says about places, derived from the `care_flows` table and never stored: self-sufficiency and import share, nodal catchments, Leiden flow communities (`network` extra) and their comparison with the official health regions (`pegasus-data graph --derive`, ADR-0144).
- `modelled.py`: the modelled tier (ADR-0139): products under lake/modelled/, typed, versioned, with uncertainty and validation evidence.
- `semantics/code_structures.py`: `code_trees.parquet`, `code_lists.parquet` and `code_attributes.parquet` (`scripts/build_code_structures.py`), served as data; and `garbage_codes()`, the GBD garbage-code classification declared in `curation/garbage_codes.yml` (two published editions, levels 1-4, expanded over the ICD-10 tree by sort position; ADR-0182).
- `semantics/grids.py`: a variable spread over columns as a grid of named axes (`grids:` in a role file, ADR-0158), read long by `grid_table`.
- `semantics/event_types.py`: the `event_types:` of `curation/datasets/*.yml`; counts events by their status, consolidation and weight (a column or a grid by sex and band, `grid_events`); `read_events` is the one place an event type's records are read (duplicate flag, weights, ADR-0165; `consolidate=False` reads its records, `prepare` adds a column before the rule, ADR-0187).
- `population_account.py`: the population account by municipality (or comparable area) × sex × five-year band × year, 2000 onward (modelled tier; ADR-0148). The vital cohort-component account (SIM/SINASC) opens on a corrected census; between censuses the closing census's departure is carried along the cohorts; after 2022 a regression of the previous decade's cohort net migration (SIDRA 200, 202, 5938) moves the account, with intervals calibrated cross-period (spread per √year, region multiplier, band model widened to nominal). Product `population_account` (`population-account-2`; `-1`, the Gibbs-hierarchy version, stays readable; `registration_completeness` `population-account-2` comes from `birth_registration`: the vital account's 0-4 and 5-9 cohorts against the corrected census, by state). Reads: lake CENSO, SIDRA store, POPSVS, `sources/pes.py`, the events directory.
- `population_tensor.py`: the account refined to municipality × year × sex × single age 0-100 × race (modelled tier; ADR-0151; product `population_account` `population-account-3`, and `-4` with the forecast, written as a stream of row groups through `write_modelled`). It splits comparable areas and composites into municipalities (share anchored on the earliest census that counts every member, the 2007 Contagem, half the 2010-2022 growth differential; error law calibrated on neighbour pairs), keeps the account's single-year path and splits 80+ by the state's census shape, and adds race by cohort composition between censuses (SIDRA 9606, 2093) with a state reclassification rate. `population_account.py` keeps the band-level account (`assemble`, calibration, intervals); `fields.py` and `sus_dependent.py` read `population-account-2` (band-level intervals).
- `population_backcast.py`: the account before 2000 (ADR-0151 item 6; `population-account-5`). `Pre` assembles the 1991-2010 comparable areas, the Census 1991 (SIDRA 200) with the 2000 coverage carried back, the Census 2000 corrected, SIM deaths 1991-2000 and the Contagem 1996 (SIDRA 475); `backward_path`/`retreat` run the deaths-only account backward from 2000, `settle` carries the 1991 census's departure along the cohorts; `split_shares` splits an area into its municipalities (anchors 2000, 1996 and 1991 where every member was counted); `backcast_tables` and `write_product` write 1991-1999 (`race = total`) ahead of `-4`'s rows via `population_tensor.age_cells`.
- `population_forecast.py`: the account forward from the PES-corrected 2022 census to 2030 (ADR-0151; `population-account-4`). `Trends` fits the national death rate by sex × band and births per woman log-linearly over ten non-COVID years; `project_vital` runs the Lexis account with the observed events to 2023 and projected ones after (municipal levels from the reference years); `forecast_bands` moves each band by `population_account.predict` at the horizon; `forecast_account` returns single ages and band-interval offsets (event-projection spread 0.003 a year added). Pseudo-forecasts with the same code are in the evaluation entry.
- `modelled_race.py`: the race misclassification products `race_confusion_infant` (ADR-0143) and `race_confusion_women` (ADR-0149; population `WOMEN`, reference from SIM–SINASC mother links with the false-link share in the likelihood): C(recorded in SIM | declared) from the stored links, a multinomial logit by state, region, municipal composition and age band; `reclassify` turns SIM deaths by recorded race into deaths by declared race. Fitting needs the `modelled` extra (jax, numpyro).
- `sus_dependent.py`: the population without private coverage (ADR-0146): the population account minus ANS medical-hospital links by municipality × sex × band, 2021-2023 (`sus-dependent-2`); product `population_without_private_coverage`.
- `completeness.py`: SIM and SINASC completeness by UF and year (ADR-0146): the published IDB 2012 ratio to 2011 (`resources/published_coverage_idb2012.csv`), a rolling-origin-calibrated extension, Hill's growth balance as a check; product `system_completeness` (`system-completeness-2`; its SINASC upper bound reads `registration_completeness`).
- `semantics/bindings.py`: field→codelist bindings (the candidates).
- `semantics/label_bindings.py`: the ONE label decision (`decide`, ADR-0082) and the compiled bindings per (system, family, field): `weigh`, `resolve`, `compile_bindings` (ADR-0072).
- `semantics/coverage.py`: whether every field of every family is described and decodes (`pegasus-data meaning`, ADR-0085).
- `semantics/ledger.py`: per-field aggregation rules.
- `semantics/relations.py`: typed relations and the adjudication queue.
- `semantics/reference.py`: reference-table helpers.
- `semantics/icd.py`: CID-9/CID-10 structure.
- `semantics/gaps.py`: what is not known.

### `sidra/`

The general interface to IBGE's SIDRA (aggregates API v3), ADR-0142. Every request to the server is made in `sidra/client.py` and nowhere else.

- `sidra/client.py`: the one HTTP door: paced and sequential, browser User-Agent, gzip by magic bytes, the firewall's HTML-with-200 refused, every response kept on disk with its URL, size, SHA-256 and time.
- `sidra/registry.py`: the metadata registry in SQLite (tables, variables with units and kind, classifications, categories with Total flags, periods, locality counts), built from `/agregados` and `/metadados`; the curated compendium (`curation/sidra/compendium.yml`) as an overlay.
- `sidra/planner.py`: a `Selection` checked against the registry and cut into requests under the measured limits (values, ID-list text, URL length).
- `sidra/store.py`: the long fact store: one Parquet part per request under `<lake>/sidra/facts/`, with IBGE's markers as `status` and provenance in each part's footer.
- `sidra/session.py`: `Sidra`, the registry, the client and the store behind one object: `describe`, `selection`, `plan`, `fetch`, `slice`, `labelled`.
- `sidra/series.py`: series stitched across tables and vintages (`curation/sidra/series.yml`, `axes.yml`): canonical axes, both claims kept where sources overlap, checks against each table's own totals, a declared `comparability` and `gaps` (`--report`), and `series_values`, the one door by which a series becomes a context field (census series 2000/2010/2022: sanitation, literacy, race, urban population, income bands).
- `sidra/lineage.py`: roll-ups to IPEA's minimum comparable areas across municipal creations; non-counts refused.
- `sidra/population.py`: the Census as the population series `CENSO`, a projection of the stitched series `population_age_sex`.
- `sidra/prices.py`: `price_index()`, IBGE's IPCA (table 1737, December 1993 = 100) as the series `price_index_ipca`: the monthly index, the annual mean, and the factor that deflates a nominal amount to a reference month (ADR-0183).
- `sidra/survey.py`: what SIDRA offers, scored for health inference (`pegasus-data sidra survey`, `rank`).

### `serve/`

- `serve/__init__.py`: the HTTP server and routes.
- `serve/__main__.py`: `python -m pegasus_data.serve`.
- `serve/_payload.py`: response shaping.
- `serve/_cache.py`: byte-bounded LRU with single-flight (responses, tables, payloads).
- `serve/_errors.py`: `Refused`, a status and a reason.
- `serve/_filters.py`: `dim.X` parsing and the check of each code against what the artifact holds.
- `serve/_membership.py`: `/geo/membership` body per (pack, system), with `conflicts` and an ETag.
- `serve/_population.py`: `/population`, one `code7` width, years and strata read from the files.
- `serve/_records.py`: `/records`, lake only, with the effective period and the gaps (ADR-0171).

### `sources/`

- `sources/sigtap.py`, `sources/demas_api.py`, `sources/ibge.py`,
  `sources/ibge_localidades.py`, `sources/community.py`: secondary sources. `sources/ibge.py` holds the population series as data (ADR-0188): `curation/populations.yml` declares them and `materialised` reads what their files hold (years, columns, municipality code widths).
- `sources/tabnet.py`: TabNet over HTTP. Its current territorial tables
  (health macroregion, current health regions) feed the geography pack, and
  `tabulate` asks TabNet for a published table to check a figure against.
- `sources/pes.py`: IBGE's 2022 post-enumeration survey as published rates (net error by age × sex, state, size class) and `corrected_census`, the enumerated census raked onto those margins (modelled; the margins are IBGE's, the cells an estimate).
- `sources/inmet.py`: INMET stations (readings from the Zenodo mirror, positions from INMET's API first) placed by spatial join in the municipality containing them; station-month sums, counts and extremes for the `climate` field, and `station_months`, the complete station-months the climate fields are validated against (`scripts/climate_validation.py`). Observations, not the source of the climate fields.
- `sources/brdwgd.py`: BR-DWGD's daily municipal zonal means (Saldanha et al., Zenodo concept 7824919, latest version), read as byte ranges in parallel and reduced to month sums and day counts; the source of `climate_monthly` and the six climate fields (ADR-0178).
- `sources/ipea_amc.py`: minimum comparable areas from IPEA's geobr (Ehrl 2017),
  read from the GeoPackage's attributes alone, for the geography pack.

---

## Invariants

The semantic non-negotiables are in `CLAUDE.md` §6. Structural ones:

- The catalog is the only memory; everything else is derived and rebuildable.
- A file's identity is its filename-derived `logical_id`, not its path.
- Blobs are content-addressed and immutable; a changed file is a new blob.
- Every decode runs where it can be killed; a timeout ends the work.
- Writes to the lake are staged and published atomically.
- `resources/` is a snapshot of a maintainer's catalog; nothing at runtime
  writes into the package directory (ADR-0074).
- A fresh catalog is the seed (ADR-0067); every door reads the catalog, never
  a shipped file directly, except the label pack and the geography packs.
