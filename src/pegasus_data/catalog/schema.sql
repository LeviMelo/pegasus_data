-- pegasus_data catalog schema.
--
-- One SQLite database holding everything discovered, decided, or left open.
-- It is the module's memory and ships alongside the lake.
--
-- Design notes that matter:
--   * Nothing here is ever silently overwritten with a guess. Where a fact is
--     unknown it is absent or explicitly marked, never invented (see §13 of the
--     architecture brief).
--   * Unreachable paths are rows in `coverage_gaps`, not log lines, so coverage
--     is a queryable property of the artifact.
--   * `families` are keyed by schema signature, not by container format, so the
--     same logical dataset published four ways is one family with four
--     `representations`.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (
  version     INTEGER NOT NULL,
  applied_at  TEXT    NOT NULL
);

-- ---------------------------------------------------------------- L0 discovery

-- `path` is where a file currently sits, which is not the same as what it is.
-- DATASUS reorganises: directories get renamed, series move between trees. A
-- catalog keyed only on location reports such a move as one deletion and one
-- unrelated arrival, and every stratum and family derived from it starts over.
-- `logical_id` is derived from the *filename* — system, series, geo, competencia
-- — so identity survives a move and the move itself becomes observable.
--
-- It is a GROUPING key, not a unique one: many paths share one logical_id. The
-- same competencia is republished in several containers (.dbc, .dbf, .csv, .xml),
-- and every one of them is `SIHSUS|RD|AC|2401` because every one of them IS that
-- month of that series for that state. That is the correct answer for grouping
-- representations of one publication, and the wrong answer for a primary key.
-- `path` remains the unique key here. Anything joining on logical_id must expect
-- multiple rows back.
CREATE TABLE IF NOT EXISTS files (
  path            TEXT PRIMARY KEY,
  logical_id      TEXT,              -- filename-derived identity; MANY paths per id
  directory       TEXT NOT NULL,
  filename        TEXT NOT NULL,
  extension       TEXT,
  size            INTEGER,
  modified        TEXT,              -- ISO-8601 UTC where the server supplies it
  listing_method  TEXT,              -- which FTP verb served this row (D4)
  change_signal   TEXT,              -- 'mtime' | 'size' | 'content_hash'
  first_seen      TEXT NOT NULL,
  last_seen       TEXT NOT NULL,
  gone_at         TEXT               -- set ONLY when a successful listing omitted it
);
CREATE INDEX IF NOT EXISTS ix_files_directory ON files (directory);
CREATE INDEX IF NOT EXISTS ix_files_extension ON files (extension);
CREATE INDEX IF NOT EXISTS ix_files_logical ON files (logical_id);

-- A file seen at a new path whose fingerprint matches one that just disappeared
-- from a successfully-listed directory. Recorded rather than inferred silently,
-- because a move and a coincidence look identical from one crawl.
CREATE TABLE IF NOT EXISTS file_moves (
  logical_id   TEXT,
  from_path    TEXT NOT NULL,
  to_path      TEXT NOT NULL,
  size         INTEGER,
  modified     TEXT,
  evidence     TEXT,                 -- which fields matched
  confidence   TEXT,                 -- 'high' (filename stable) | 'low' (renamed)
  renamed_from TEXT,                 -- old filename, when the name itself changed
  renamed_to   TEXT,
  run_id       TEXT,
  detected_at  TEXT,
  PRIMARY KEY (from_path, to_path)
);

-- What the filename says a file belongs to, learned from a healthy crawl and
-- then held. This is what lets system inference stop depending on where a file
-- sits: once `RD -> SIHSUS` is known, a directory rename cannot re-label it.
CREATE TABLE IF NOT EXISTS prefix_systems (
  series_prefix  TEXT PRIMARY KEY,
  system         TEXT NOT NULL,
  file_count     INTEGER NOT NULL,
  agreement      REAL NOT NULL,      -- share of files whose path agreed
  learned_at     TEXT NOT NULL
);

-- A file whose filename and whose path disagree about which system it belongs
-- to. A finding, not an error: it is either a reorganisation in progress or a
-- prefix genuinely shared by two systems.
CREATE TABLE IF NOT EXISTS system_disagreements (
  path            TEXT PRIMARY KEY,
  series_prefix   TEXT,
  system_by_name  TEXT,
  system_by_path  TEXT,
  resolved_to     TEXT,
  noted_at        TEXT
);

CREATE TABLE IF NOT EXISTS directories (
  path             TEXT PRIMARY KEY,
  parent           TEXT,
  listing_method   TEXT,
  entry_count      INTEGER,
  file_count       INTEGER,
  dir_count        INTEGER,
  last_listed_at   TEXT,
  date_convention  TEXT               -- 'monthly' | 'annual' | 'mixed' | NULL (§5.2)
);

CREATE TABLE IF NOT EXISTS coverage_gaps (   -- D6: unreachable paths are data
  path           TEXT PRIMARY KEY,
  kind           TEXT NOT NULL DEFAULT 'listing',  -- 'listing' | 'fetch' | 'decode'
  attempts       INTEGER NOT NULL DEFAULT 0,
  methods_tried  TEXT,
  last_error     TEXT,
  last_attempt   TEXT,
  resolved       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS crawl_runs (
  run_id           TEXT PRIMARY KEY,
  host             TEXT,
  base_path        TEXT,
  started_at       TEXT,
  finished_at      TEXT,
  directories      INTEGER,
  files            INTEGER,
  gaps             INTEGER,
  connections      INTEGER,
  -- Reconciliation against the previous crawl, so a change in the tree is a
  -- reported number rather than something a later stage trips over.
  files_new        INTEGER,
  files_unchanged  INTEGER,
  files_changed    INTEGER,
  files_moved      INTEGER,
  files_gone       INTEGER,
  files_unresolved INTEGER,
  notes            TEXT
);

-- ---------------------------------------------------- L1 inventory / strata

CREATE TABLE IF NOT EXISTS file_facts (      -- parsed filename grammar (§5.2)
  path             TEXT PRIMARY KEY,
  system           TEXT,
  series_prefix    TEXT,
  geo_code         TEXT,
  date_code        TEXT,
  date_format      TEXT,               -- 'YYYYMM' | 'YYMM' | 'YYYY' | 'YY'
  normalized_date  INTEGER,            -- YYYYMM as integer; YYYY00 for annual
  year             INTEGER,
  grammar          TEXT,               -- which naming grammar matched
  container_format TEXT,               -- probe-independent hint from suffix
  role             TEXT,               -- 'data' | 'dictionary' | 'documentation' | 'auxiliary' | 'unknown'
  logical_id       TEXT,               -- filename-derived identity, stable across moves
  FOREIGN KEY (path) REFERENCES files (path) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ix_file_facts_system ON file_facts (system, series_prefix, year);

CREATE TABLE IF NOT EXISTS strata (          -- D2: unit of schema sampling
  stratum_id        TEXT PRIMARY KEY,
  system            TEXT NOT NULL,
  series            TEXT,
  year              INTEGER,
  file_count        INTEGER NOT NULL DEFAULT 0,
  sampled_path      TEXT,
  sampled_member    TEXT,               -- archive member, when the sample is nested
  schema_signature  TEXT,
  field_count       INTEGER,
  sample_status     TEXT,               -- 'pending' | 'ok' | 'failed'
  sample_error      TEXT
);
CREATE INDEX IF NOT EXISTS ix_strata_system ON strata (system, series, year);

CREATE TABLE IF NOT EXISTS stratum_members (
  stratum_id  TEXT NOT NULL,
  path        TEXT NOT NULL,
  PRIMARY KEY (stratum_id, path)
);

CREATE TABLE IF NOT EXISTS schemas (         -- the field list behind a signature
  schema_signature  TEXT PRIMARY KEY,
  field_count       INTEGER NOT NULL,
  fields_json       TEXT NOT NULL,      -- ordered list of field names
  first_seen        TEXT
);

CREATE TABLE IF NOT EXISTS families (        -- D3: keyed by schema, not format
  family_id         TEXT PRIMARY KEY,
  system            TEXT NOT NULL,
  series            TEXT,
  schema_signature  TEXT,
  field_count       INTEGER,
  time_min          INTEGER,
  time_max          INTEGER,
  geo_coverage      TEXT,
  file_count        INTEGER NOT NULL DEFAULT 0,
  stratum_count     INTEGER NOT NULL DEFAULT 0,
  -- How this family's schema was learned: 'profile' (a file was decoded and its
  -- values read) or 'header' (the census read the column list from a few hundred
  -- bytes). Both give the SAME schema_signature -- that is asserted in the census
  -- tests -- so both are legitimate grounds for a family. They are NOT the same
  -- grounds for talking about values, and recording which is what keeps
  -- "we know the columns" from being mistaken for "we know what is in them".
  --
  -- Families were built from profiled strata only, which is why 16 of 20 systems
  -- had none: the census catalogued 2,971 strata across 14 systems and nothing
  -- downstream would look at them, so SINAN, SINASC, CNES and thirteen others
  -- could not be built or fetched at all.
  schema_source     TEXT,
  label             TEXT,
  notes             TEXT
);

CREATE TABLE IF NOT EXISTS representations ( -- D3: same family, other containers
  family_id         TEXT NOT NULL,
  container_format  TEXT NOT NULL,
  path_glob         TEXT,
  file_count        INTEGER NOT NULL DEFAULT 0,
  decode_cost_rank  INTEGER,
  reader            TEXT,
  PRIMARY KEY (family_id, container_format)
);

CREATE TABLE IF NOT EXISTS family_files (
  family_id  TEXT NOT NULL,
  path       TEXT NOT NULL,
  member     TEXT,                     -- archive member name where applicable
  PRIMARY KEY (family_id, path, member)
);
CREATE INDEX IF NOT EXISTS ix_family_files_path ON family_files (path);

-- ------------------------------------------------------- L2 acquisition (CAS)

CREATE TABLE IF NOT EXISTS blobs (
  sha256          TEXT PRIMARY KEY,
  byte_size       INTEGER NOT NULL,
  first_fetched_at TEXT NOT NULL,
  fetch_count     INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS fetches (         -- append-only fetch history
  id              INTEGER PRIMARY KEY AUTOINCREMENT,
  source_path     TEXT NOT NULL,
  sha256          TEXT NOT NULL,
  byte_size       INTEGER,
  fetched_at      TEXT NOT NULL,
  serving_method  TEXT,
  elapsed_ms      REAL
);
CREATE INDEX IF NOT EXISTS ix_fetches_path ON fetches (source_path);
CREATE INDEX IF NOT EXISTS ix_fetches_sha ON fetches (sha256);

-- ------------------------------------------------------- L3 decode outcomes

CREATE TABLE IF NOT EXISTS decode_attempts (
  path         TEXT NOT NULL,
  member       TEXT NOT NULL DEFAULT '',
  reader       TEXT NOT NULL,
  ok           INTEGER NOT NULL,
  rows_read    INTEGER,
  field_count  INTEGER,
  error        TEXT,
  attempted_at TEXT,
  PRIMARY KEY (path, member, reader)
);

CREATE TABLE IF NOT EXISTS archive_members (  -- D1/D7: kits expose every member
  archive_path  TEXT NOT NULL,
  member        TEXT NOT NULL,
  member_size   INTEGER,
  member_role   TEXT,                  -- 'data' | 'cnv' | 'def' | 'lookup' | 'doc' | 'binary'
  container     TEXT,                  -- 'zip' | 'lha_sfx' | 'rar' | 'gzip' | '7z'
  PRIMARY KEY (archive_path, member)
);

-- ------------------------------------------------------------- L4 profiling

CREATE TABLE IF NOT EXISTS variable_profiles (
  family_id           TEXT NOT NULL,
  field_name          TEXT NOT NULL,
  schema_signature    TEXT NOT NULL,
  source_path         TEXT,
  field_order         INTEGER,
  physical_type       TEXT,
  width               INTEGER,
  decimals            INTEGER,
  non_null            INTEGER,
  nulls               INTEGER,
  distinct_count      INTEGER,
  distinct_truncated  INTEGER NOT NULL DEFAULT 0,
  semantic_type       TEXT,
  semantic_confidence REAL,
  semantic_evidence   TEXT,            -- JSON: the statistics that produced the verdict (D5)
  stats_json          TEXT,
  PRIMARY KEY (family_id, field_name, schema_signature)
);

CREATE TABLE IF NOT EXISTS value_frequencies (
  family_id         TEXT NOT NULL,
  field_name        TEXT NOT NULL,
  schema_signature  TEXT NOT NULL,
  value             TEXT NOT NULL,
  count             INTEGER NOT NULL,
  percent           REAL,
  rank              INTEGER
);
CREATE INDEX IF NOT EXISTS ix_valfreq_field
  ON value_frequencies (family_id, field_name, schema_signature);

CREATE TABLE IF NOT EXISTS schema_presence (
  schema_signature TEXT NOT NULL,
  field_name       TEXT NOT NULL,
  field_order      INTEGER,
  PRIMARY KEY (schema_signature, field_name)
);

CREATE TABLE IF NOT EXISTS schema_drift (    -- D2: never report 'stable' at n=1
  system                TEXT NOT NULL,
  series                TEXT NOT NULL,
  observed_strata       INTEGER,
  schema_signature_count INTEGER,
  signatures_json       TEXT,
  union_field_count     INTEGER,
  always_present_json   TEXT,
  sometimes_present_json TEXT,
  drift_status          TEXT,          -- 'stable' | 'drifting' | 'insufficient_evidence'
  PRIMARY KEY (system, series)
);

CREATE TABLE IF NOT EXISTS field_renames (   -- silent traps: DIAG_SECUN → DIAGSEC1..9
  system      TEXT NOT NULL,
  series      TEXT NOT NULL,
  field_name  TEXT NOT NULL,
  present_in  TEXT,                    -- JSON list of schema signatures
  absent_in   TEXT,
  first_year  INTEGER,
  last_year   INTEGER,
  PRIMARY KEY (system, series, field_name)
);

-- ------------------------------------------------------------- L5 semantics

CREATE TABLE IF NOT EXISTS dictionary (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  system                 TEXT,
  family_id              TEXT,
  field_name             TEXT,
  schema_signature_scope TEXT,
  value_raw              TEXT,
  value_label            TEXT,
  value_group            TEXT,
  source                 TEXT NOT NULL,  -- 'cnv'|'def'|'dbf_lookup'|'pdf'|'demas_api'|'inferred'|'manual'
  source_ref             TEXT NOT NULL,  -- exact file path + archive member + line, or URL
  confidence             REAL NOT NULL,
  valid_from             TEXT,
  valid_to               TEXT
);
CREATE INDEX IF NOT EXISTS ix_dict_lookup ON dictionary (system, value_group, value_raw);
CREATE INDEX IF NOT EXISTS ix_dict_field ON dictionary (system, field_name, value_raw);
CREATE INDEX IF NOT EXISTS ix_dict_family ON dictionary (family_id, field_name);
-- `is_hierarchical` counts distinct labels for one codelist, and the lookup
-- index above starts with `system`, so that count could not seek and scanned
-- all 19.9M rows -- 5.4 seconds per call, ~60 calls to plan a single family.
CREATE INDEX IF NOT EXISTS ix_dict_group_label ON dictionary (value_group, value_label);

-- A .CNV is a *codelist*, not a column: SEXO.CNV maps 1→Masculino without
-- saying which column uses it, and several columns legitimately share one
-- codelist (MUNICBR decodes both MUNIC_RES and MUNIC_MOV). Keeping the codes in
-- `dictionary` keyed by codelist and the field attachment here avoids two
-- errors: duplicating 5,600 municipality rows per column, and reporting a
-- "conflict" every time two unrelated codelists both define the code '1'.
CREATE TABLE IF NOT EXISTS field_codelists (
  system      TEXT,
  family_id   TEXT,
  field_name  TEXT NOT NULL,
  codelist    TEXT NOT NULL,
  source      TEXT NOT NULL,       -- 'def' | 'manual' | 'name_match'
  source_ref  TEXT NOT NULL,
  confidence  REAL NOT NULL,
  -- What share of the column's OBSERVED values this codelist actually decodes.
  -- NULL means not measured (the column has never been profiled), which is not
  -- the same as zero and must not be read as one.
  --
  -- A binding is a claim that a codelist explains a column, and .DEF makes that
  -- claim for tabulation axes too: "Ano/mes de internacao, DT_INTER, ANOMES.CNV"
  -- declares an axis DERIVED FROM the column, and the binder attaches it to the
  -- raw column. Measured across the catalog, 35.2% of checkable bindings decode
  -- none of their column's observed values, and 35 columns had every binding
  -- dead while being reported as decodable. The claim is kept -- .DEF really did
  -- say it -- and the measurement is recorded beside it, because resolving a
  -- source conflict silently is exactly what this project does not do.
  decodes_observed REAL,
  measured_at TEXT,
  PRIMARY KEY (system, family_id, field_name, codelist)
);
CREATE INDEX IF NOT EXISTS ix_field_codelists_field ON field_codelists (field_name);

CREATE TABLE IF NOT EXISTS dictionary_rules (  -- ranges that could not be expanded
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  system       TEXT,
  field_name   TEXT,
  expression   TEXT NOT NULL,          -- e.g. 'A00-B99' or '100-312,400'
  value_label  TEXT,
  source       TEXT NOT NULL,
  source_ref   TEXT NOT NULL,
  confidence   REAL NOT NULL,
  reason       TEXT                    -- why it stayed a rule
);

CREATE TABLE IF NOT EXISTS dictionary_conflicts (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  system     TEXT,
  field_name TEXT,
  value_raw  TEXT,
  claim_a    TEXT,
  source_a   TEXT,
  claim_b    TEXT,
  source_b   TEXT,
  noted_at   TEXT
);

CREATE TABLE IF NOT EXISTS code_tables (       -- kit lookup tables, kept whole
  table_id     TEXT NOT NULL,          -- e.g. 'CID10' | 'TPROC10' | 'TCNESBR'
  source_ref   TEXT NOT NULL,
  code         TEXT NOT NULL,
  label        TEXT,
  extra_json   TEXT,
  PRIMARY KEY (table_id, code, source_ref)
);

CREATE TABLE IF NOT EXISTS tab_kits (
  kit_path      TEXT PRIMARY KEY,
  system        TEXT,
  container     TEXT,
  member_count  INTEGER,
  def_count     INTEGER,
  cnv_count     INTEGER,
  dbf_count     INTEGER,
  ingested_at   TEXT,
  sha256        TEXT
);

CREATE TABLE IF NOT EXISTS def_variables (     -- what a column is officially called
  def_path      TEXT NOT NULL,         -- kit path + member
  system        TEXT,
  usage         TEXT NOT NULL,         -- 'L'|'C'|'S'|'X'|'I'
  display_name  TEXT NOT NULL,
  field_name    TEXT NOT NULL,
  category_arg  TEXT,
  lookup_ref    TEXT,                  -- CNV or DBF member that decodes it
  line_no       INTEGER,
  PRIMARY KEY (def_path, usage, display_name, field_name)
);
CREATE INDEX IF NOT EXISTS ix_defvars_field ON def_variables (system, field_name);

CREATE TABLE IF NOT EXISTS def_datasets (      -- the A-line: which files a DEF describes
  def_path     TEXT PRIMARY KEY,
  system       TEXT,
  data_glob    TEXT,
  help_ref     TEXT,
  title        TEXT
);

-- What a column is called *in its own record layout*, as opposed to what TabNet
-- calls a tabulation axis built on it. `.DEF` cannot answer this for many fields:
-- it names DIAG_PRINC only as "Diag CID10 (capit)", "Diag CID10 (grupo)" and so
-- on, because those are the axes it offers. The Instrucao Tecnica documents under
-- each system's Doc/ tree carry the real thing:
--   41 DIAG_PRINC char(4) Codigo do diagnostico principal (CID10).
CREATE TABLE IF NOT EXISTS field_documentation (
  system       TEXT,
  field_name   TEXT NOT NULL,
  description  TEXT NOT NULL,
  official_name TEXT,               -- the form's own wording, where stated apart
                                    -- from the description (Estrutura_* dialect)
  declared_type TEXT,
  declared_width INTEGER,
  declared_decimals INTEGER,
  source       TEXT NOT NULL,       -- 'layout_doc' | 'demas_api' | 'manual'
  source_ref   TEXT NOT NULL,
  confidence   REAL NOT NULL,
  PRIMARY KEY (system, field_name, source_ref)
);
CREATE INDEX IF NOT EXISTS ix_field_doc_field ON field_documentation (field_name);

CREATE TABLE IF NOT EXISTS ledger (
  system                 TEXT NOT NULL,
  family_id              TEXT NOT NULL,
  field_name             TEXT NOT NULL,
  schema_signature_scope TEXT NOT NULL,
  official_name          TEXT,          -- from .DEF, the only authoritative source
  semantic_type          TEXT,
  semantic_confidence    REAL,
  semantic_evidence      TEXT,
  unit                   TEXT,
  aggregation            TEXT,          -- 'additive' | 'mean' | 'non_summable'
  sentinel_values        TEXT,          -- JSON list, per field, never global (§13)
  first_seen             INTEGER,
  last_seen              INTEGER,
  dictionary_coverage    REAL,          -- THE headline metric (§6.2)
  distinct_observed      INTEGER,
  distinct_decoded       INTEGER,
  provenance             TEXT,
  open_questions         TEXT,
  PRIMARY KEY (system, family_id, field_name, schema_signature_scope)
);

CREATE TABLE IF NOT EXISTS open_questions (
  id                     INTEGER PRIMARY KEY AUTOINCREMENT,
  key                    TEXT UNIQUE,
  area                   TEXT,
  question               TEXT NOT NULL,
  verification_procedure TEXT,
  blocking               TEXT,
  status                 TEXT NOT NULL DEFAULT 'open',  -- 'open'|'resolved'|'wontfix'
  resolution             TEXT,
  evidence               TEXT,
  noted_at               TEXT,
  resolved_at            TEXT
);

-- --------------------------------------------------------------- L7 the lake

-- Every family a build SELECTED, and what came of it. The zero-row bug — a
-- family pointing at files whose schema it did not have, normalising nothing and
-- reporting success — passed the whole suite because nothing recorded the
-- difference between "built 0 rows" and "was never asked to build". A family that
-- produces no rows must now say why, and `verify` fails on any that cannot.
-- ------------------------------------------------- curated variable dictionary
--
-- What a variable MEANS, as opposed to what values it takes. The extracted
-- dictionary (millions of code->label rows) stays in SQLite because it is
-- machine output; this table is the human half, loaded from version-controlled
-- YAML under curation/ so that an assertion has an author, a date and a diff.
--
-- Three times the design created a slot for human judgement with no way to write
-- into it: SOURCE_AUTHORITY['manual'] with nothing emitting a manual entry,
-- 'layout_doc' declared authoritative before anything produced one, and a prefix
-- contradiction only a person could settle with no way to record the settlement.
-- This table plus curation/ is that door.
CREATE TABLE IF NOT EXISTS variable_docs (
  system          TEXT NOT NULL,
  field_name      TEXT NOT NULL,
  official_name   TEXT,              -- Portuguese, as the record layout names it
  translated_name TEXT,              -- English, for docs and export ONLY
  description     TEXT,
  code_system     TEXT,              -- 'external' | 'internal' | 'none'
  codelist        TEXT,              -- reference table this field draws on
  multi_valued    INTEGER DEFAULT 0,
  token_rule      TEXT,              -- JSON: {"width": 4} or {"delimiter": ";"}
  depends_on      TEXT,              -- JSON array of field names
  modifies        TEXT,              -- field whose meaning this one changes
  derived         TEXT,              -- JSON array of derived-column recipes
  notes           TEXT,
  vintage_note    TEXT,              -- when the classification itself changed, and how
                                     -- the right one is selected for a given row
  source          TEXT NOT NULL,     -- 'manual' | 'layout_doc' | 'def' | 'web' | 'inferred'
  source_ref      TEXT,
  asserted_by     TEXT,
  asserted_at     TEXT,
  reasoning       TEXT,              -- required when source='inferred'
  PRIMARY KEY (system, field_name)
);
CREATE INDEX IF NOT EXISTS ix_variable_docs_source ON variable_docs (source);

-- Dataset-level prose: what one row IS, and what will mislead you about it.
-- None of this is derivable from the bytes.
CREATE TABLE IF NOT EXISTS dataset_docs (
  dataset_id      TEXT PRIMARY KEY,  -- e.g. SIHSUS_RD
  system          TEXT,
  series          TEXT,
  what_one_row_is TEXT,
  unit_of_analysis TEXT,
  known_biases    TEXT,
  gotchas         TEXT,              -- JSON array
  source          TEXT NOT NULL,
  source_ref      TEXT,
  asserted_by     TEXT,
  asserted_at     TEXT
);

-- What a file's own header states about its shape, read WITHOUT decoding it.
-- Kept apart from variable_profiles on purpose: a profile has read the data and
-- can speak about values, and this has read a few hundred bytes and can speak
-- only about columns. Merging them would let "we know this column exists" be
-- mistaken for "we know what is in it".
CREATE TABLE IF NOT EXISTS schema_header_facts (
  schema_signature  TEXT NOT NULL,
  path              TEXT NOT NULL,     -- the file the header was read from
  field_name        TEXT NOT NULL,
  field_order       INTEGER NOT NULL,
  type_code         TEXT,              -- DBF type: C, N, D, L, F, M...
  width             INTEGER,
  decimals          INTEGER,
  declared_records  INTEGER,           -- what the header CLAIMS; unverified
  record_length     INTEGER,
  widths_consistent INTEGER,           -- do field widths sum to record_length?
  read_at           TEXT,
  PRIMARY KEY (schema_signature, field_name)
);
CREATE INDEX IF NOT EXISTS ix_header_facts_field ON schema_header_facts (field_name);

CREATE TABLE IF NOT EXISTS build_outcomes (
  run_id           TEXT NOT NULL,
  family_id        TEXT NOT NULL,
  system           TEXT,
  files_selected   INTEGER NOT NULL DEFAULT 0,
  files_decoded    INTEGER NOT NULL DEFAULT 0,
  rows_written     INTEGER NOT NULL DEFAULT 0,
  partitions       INTEGER NOT NULL DEFAULT 0,
  reason           TEXT,              -- NULL when rows_written > 0
  recorded_at      TEXT,
  PRIMARY KEY (run_id, family_id)
);
CREATE INDEX IF NOT EXISTS ix_build_outcomes_family ON build_outcomes (family_id);

CREATE TABLE IF NOT EXISTS lake_partitions (
  family_id        TEXT NOT NULL,
  schema_signature TEXT NOT NULL,
  uf               TEXT NOT NULL,
  year             INTEGER NOT NULL,
  relative_path    TEXT NOT NULL,
  row_count        INTEGER,
  byte_size        INTEGER,
  source_paths     TEXT,
  written_at       TEXT,
  PRIMARY KEY (family_id, schema_signature, uf, year, relative_path)
);

CREATE TABLE IF NOT EXISTS lake_datasets (     -- what DuckDB views get registered
  dataset      TEXT PRIMARY KEY,        -- e.g. 'sih_rd'
  system       TEXT,
  series       TEXT,
  family_ids   TEXT,
  description  TEXT
);

-- ------------------------------------------------------- L8/L9 other sources

CREATE TABLE IF NOT EXISTS population_series (
  series             TEXT PRIMARY KEY,   -- 'POPSVS' | 'POPTCU' | 'POP' | 'projpop' | 'censo'
  authority          TEXT,
  year_min           INTEGER,
  year_max           INTEGER,
  stratifications    TEXT,               -- JSON list, e.g. ["municipality","year","sex","age"]
  age_standardizable INTEGER NOT NULL DEFAULT 0,
  file_count         INTEGER,
  notes              TEXT
);

CREATE TABLE IF NOT EXISTS api_endpoints (
  path         TEXT PRIMARY KEY,
  method       TEXT,
  summary      TEXT,
  tags         TEXT,
  params_json  TEXT,
  schema_json  TEXT,
  spec_version TEXT,
  fetched_at   TEXT
);

CREATE TABLE IF NOT EXISTS api_ingests (
  path        TEXT NOT NULL,
  params      TEXT NOT NULL,
  rows        INTEGER,
  lake_path   TEXT,
  fetched_at  TEXT,
  PRIMARY KEY (path, params)
);

-- ------------------------------------------------------------- diagnostics

CREATE TABLE IF NOT EXISTS events (            -- append-only run history
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id     TEXT,
  stage      TEXT,
  level      TEXT,
  path       TEXT,
  message    TEXT,
  detail     TEXT,
  noted_at   TEXT
);
CREATE INDEX IF NOT EXISTS ix_events_stage ON events (stage, level);
