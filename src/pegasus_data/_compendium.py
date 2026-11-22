"""``compendium()`` — a portable map of DATASUS, as one SQLite file.

The question this answers is **"what does DATASUS actually have, and can I
answer my question with it?"** — asked before any data is downloaded, usually
while writing a protocol or a grant application. Answering it today means
crawling an FTP server for hours. It should mean opening a file.

So the shape is driven by the questions a researcher actually asks:

===========================================================  ====================
"what systems exist, and what is each one?"                  ``systems``
"what datasets does SIH publish, and what is a row?"         ``datasets``
"which years and states does SIA-PA cover?"                  ``coverage``
"did the columns change over the period I need?"             ``schema_generations``
"what columns are there, and what do they mean?"             ``variables``
"which datasets carry DIAG_PRINC?"                           ``dataset_variables``
"what do the codes mean?"                                    ``codes`` *(opt-in)*
"what values actually occur?"                                ``value_frequencies`` *(opt-in)*
===========================================================  ====================

**Everything else is left out on purpose.** The artefact this replaces was 57 MB,
and most of it was weight a planner cannot use: 124,810 rows of raw file listing,
and per-file percentiles (``p01``…``p99``, ``mean``, ``std``) for every column of
every file. It also carried ``system_guess`` and ``semantic_guess`` — guesses
presented as data, with no provenance and no way to tell a good one from a bad
one. It labelled a CNES establishment code ``municipality_code_candidate``, which
is simply wrong, and nothing in the file said how much to trust that.

Here, the core is small enough to ship and everything heavy is opt-in, because
the honest default for "what does DATASUS have" is a few megabytes:

    compendium("datasus.sqlite")                    # core: the map      ~5 MB
    compendium("datasus.sqlite", codes=True)        # + DATASUS's own codes
    compendium("datasus.sqlite", codes="bound")     # + CID, CBO, geography  large
    compendium("datasus.sqlite", codes="all")       # + every codelist     larger
    compendium("datasus.sqlite", values=True)       # + observed value frequencies
    compendium("datasus.sqlite", files=True)        # + the raw file listing
    compendium("datasus.sqlite", systems=["SIH"])   # scope it

Measured on SIH: the core is 0.8 MB, ``codes=True`` takes it to 4.8 MB, and
``codes="bound"`` to **425 MB** — because twelve geography and CID-10 tables are
62% of the codes bound to it. That gap is the whole reason the toggle exists.

Provenance is recorded rather than assumed: ``meta`` carries when the file was
built, which crawl it reflects, and which options were passed, so a compendium
someone emails you can be placed in time.
"""

from __future__ import annotations

import json
import os
import sqlite3
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC
from pathlib import Path
from typing import Any, Literal

from .catalog.store import CatalogStore as _Store
from .config import Settings, curation_root, load_settings
from .ontology import Ontology
from .semantics.epoch import curation_epoch

CodesOption = Literal["none", "internal", "bound", "all"] | bool

SCHEMA = """
-- What exists, as the institution declares it -----------------------------
CREATE TABLE systems (
  code            TEXT PRIMARY KEY,   -- SIH
  official_name   TEXT,               -- Sistema de Informações Hospitalares
  translated_name TEXT,
  kind            TEXT,               -- data | reference | tooling
  status          TEXT,
  authority       TEXT,
  what_it_is      TEXT,
  datasets        INTEGER,
  files           INTEGER,
  year_min        INTEGER,
  year_max        INTEGER
);

CREATE TABLE datasets (
  code             TEXT PRIMARY KEY,  -- SIH.RD
  system           TEXT REFERENCES systems(code),
  short_code       TEXT,              -- RD
  official_name    TEXT,
  translated_name  TEXT,
  what_it_is       TEXT,
  what_one_row_is  TEXT,
  unit_of_analysis TEXT,
  known_biases     TEXT,
  gotchas          TEXT,              -- JSON array
  status           TEXT,
  confidence       TEXT,
  files            INTEGER,
  year_min         INTEGER,
  year_max         INTEGER,
  ufs              INTEGER,
  generations      INTEGER,
  columns_total    INTEGER,
  columns_described INTEGER,
  -- How the FILES are split, which is not the same as what the rows contain.
  -- SIM.DOFET is national: it has a state column but no per-state file, so
  -- "give me AC" is answerable only after loading, never by picking files.
  split_by         TEXT,              -- JSON array, e.g. ["uf","year","month"]
  split_by_uf      REAL,              -- fraction of files carrying each axis
  split_by_year    REAL,
  split_by_month   REAL,
  -- What this install HOLDS, which is not what the server publishes: rows in
  -- the lake, read from the Parquet footers when the map was built.
  query_as         TEXT,              -- the identifier query() takes
  rows_held        INTEGER,
  year_min_held    INTEGER,
  year_max_held    INTEGER,
  -- Downloaded and not built into the lake: published files whose bytes the
  -- blob store holds (CNES's registers are read from them, never built), so
  -- query() reads them without the network.
  files_downloaded INTEGER,
  year_min_downloaded INTEGER,
  year_max_downloaded INTEGER,
  months_downloaded TEXT              -- which months of which years, e.g. "12 of 2008-2023; 01-12 of 2025"
);
CREATE INDEX ix_datasets_system ON datasets(system);

-- Can I answer my question with this? --------------------------------------
CREATE TABLE coverage (
  dataset TEXT REFERENCES datasets(code),
  year    INTEGER,
  uf      TEXT,
  files   INTEGER,                    -- files on the server
  rows_held INTEGER,                  -- rows in the lake (NULL: none held)
  PRIMARY KEY (dataset, year, uf)
);
CREATE INDEX ix_coverage_year ON coverage(year);
CREATE INDEX ix_coverage_uf ON coverage(uf);

-- Did the columns change under me? -----------------------------------------
CREATE TABLE schema_generations (
  dataset      TEXT REFERENCES datasets(code),
  signature    TEXT,
  field_count  INTEGER,
  year_min     INTEGER,
  year_max     INTEGER,
  files        INTEGER,
  added        TEXT,                  -- JSON array, vs the previous generation
  dropped      TEXT,                  -- JSON array
  PRIMARY KEY (dataset, signature, year_min)
);

-- What is in a row ----------------------------------------------------------
CREATE TABLE variables (
  system          TEXT,
  name            TEXT,
  official_name   TEXT,
  translated_name TEXT,
  description     TEXT,
  code_system     TEXT,               -- internal | external | none
  codelist        TEXT,
  source          TEXT,               -- the rung of evidence
  source_ref      TEXT,
  reasoning       TEXT,
  physical_type   TEXT,
  width           INTEGER,
  PRIMARY KEY (system, name)
);

CREATE TABLE dataset_variables (
  dataset TEXT REFERENCES datasets(code),
  system  TEXT,
  name    TEXT,
  -- The codelist a query labels the column with, as decided and stored per
  -- schema family (catalog.label_bindings): one JSON list, oldest family first.
  -- `label_basis` is curated | measured | none, of the newest family.
  codelists   TEXT,
  label_basis TEXT,
  label_share REAL,                   -- observed codes the newest decision decodes
  -- Non-null share of the rows held, from the lake's Parquet statistics. NULL
  -- when nothing is held: unmeasured, never zero.
  filled      REAL,
  rows_held   INTEGER,
  PRIMARY KEY (dataset, name)
);
CREATE INDEX ix_dsvar_name ON dataset_variables(system, name);

-- When each column EXISTED, which is not when it was filled in.
--
-- SIH.RD's nine secondary-diagnosis fields do not appear before 2014, so a
-- query for DIAGSEC4 in 2007 returns nothing for a STRUCTURAL reason. Read as
-- clinical missingness it corrupts any estimate spanning the boundary, and
-- schema_generations records the fact only implicitly.
--
-- `state` is deliberately three-valued. `absent` is a positive claim: a decoded
-- schema for that year exists and does not carry the column. `unknown` means
-- nothing has been decoded for that year and no claim is being made — which an
-- interval of valid_from/valid_to cannot express without inventing one.
CREATE TABLE field_validity (
  dataset    TEXT REFERENCES datasets(code),
  field      TEXT,
  year_from  INTEGER,          -- one row per contiguous run
  year_to    INTEGER,
  current    INTEGER,          -- 1 when the run reaches the newest decoded year
  bridged    TEXT,             -- JSON array of years inside the run with no data
  PRIMARY KEY (dataset, field, year_from)
);
CREATE INDEX ix_validity_field ON field_validity(field);

-- How many VINTAGES a codelist has, and over what windows.
--
-- The same MUNICBR code carries different labels in the 1992-1997 kit and the
-- current one, because municipalities were created, merged and renamed in
-- between. Decoding a 1998 extract against today's table is silently wrong, and
-- the wrongness is invisible: every code still resolves, to the wrong name.
--
-- This is a SUMMARY and always present, because the full `codes` table is
-- optional and large (425 MB bound). A consumer needs to know a codelist is
-- versioned even when they have not asked for the codes themselves. NULL
-- window bounds mean the current, open-ended kit — not an unknown one.
CREATE TABLE codelist_vintages (
  codelist   TEXT,
  system     TEXT,
  vintages   INTEGER,        -- distinct (valid_from, valid_to) windows
  window_min TEXT,           -- earliest competence, YYYYMM; NULL if only current
  window_max TEXT,
  has_current INTEGER,       -- 1 when an open-ended (current) vintage exists
  codes      INTEGER,        -- distinct codes across all vintages
  PRIMARY KEY (codelist, system)
);
CREATE INDEX ix_vintages_n ON codelist_vintages(vintages DESC);

-- How datasets join, as keys rather than pairs.
--
-- `rows_per_key` is the field that prevents the expensive mistake: SIH.RD is one
-- row per AIH and SIH.SP is many, so joining them and counting rows counts
-- professional acts while looking like it counts admissions.
--
-- `as_of` marks a key whose target is versioned in time. Joining a 2015
-- admission to today's CNES answers "what is this hospital now", not "what was
-- it when the patient was treated" — and it answers silently.
CREATE TABLE join_keys (
  name     TEXT PRIMARY KEY,
  what     TEXT,
  as_of    TEXT,              -- e.g. 'competence'; NULL when the key is stable
  caveats  TEXT               -- JSON array
);
CREATE TABLE join_key_members (
  key          TEXT REFERENCES join_keys(name),
  dataset      TEXT REFERENCES datasets(code),
  column_name  TEXT,
  rows_per_key TEXT,          -- one | many | unmeasured
  note         TEXT,
  PRIMARY KEY (key, dataset)
);
CREATE INDEX ix_keymember_dataset ON join_key_members(dataset);

-- Joins people ask for that have no key shown to work. Recorded rather than
-- omitted: a join that silently matches the wrong rows produces a cohort, not
-- an error, so "we checked and there is no key" is the more useful answer.
CREATE TABLE joins_not_established (
  want         TEXT,
  proposed_key TEXT,
  finding      TEXT
);

-- What is NOT known, stated rather than filled in ---------------------------
CREATE TABLE open_questions (
  key      TEXT PRIMARY KEY,
  area     TEXT,
  question TEXT,
  blocking TEXT
);

-- Context fields: a property of a place and a period that is not a health
-- event (GDP, rainfall, beds per specialty, water supplied), sums and counts
-- stored per municipality and year (fields.py, intake.py).
CREATE TABLE fields (
  name        TEXT PRIMARY KEY,
  label       TEXT,
  what        TEXT,
  unit        TEXT,
  source      TEXT,                   -- sidra | intake | cnes | brdwgd | inmet | series
  origin      TEXT,                   -- the SIDRA table, the intake source, the CNES measure
  over        TEXT,                   -- the denominator a rate is taken over
  by          TEXT,                   -- JSON: the breakdowns, if any
  years       TEXT,                   -- as declared
  years_held  TEXT,                   -- JSON list of years built in this install
  verified    TEXT                    -- JSON: the check its total passed
);

-- What each column STATES, as a typed role, and what a row becomes.
CREATE TABLE roles (
  dataset    TEXT,
  column_name TEXT,
  role       TEXT,                    -- entity.property
  entity     TEXT,
  property   TEXT,
  kind       TEXT,
  model      TEXT,
  first_year INTEGER,
  last_year  INTEGER,
  PRIMARY KEY (dataset, column_name, role)
);
CREATE INDEX ix_roles_role ON roles(role);
CREATE TABLE events (
  dataset     TEXT,
  name        TEXT,
  kind        TEXT,
  grain       TEXT,
  classifiers TEXT,                   -- JSON
  PRIMARY KEY (dataset, name)
);

-- Record linkage across datasets (curation/links.yml), and the runs held.
CREATE TABLE links (
  name        TEXT PRIMARY KEY,
  description TEXT,
  left_dataset  TEXT,
  right_dataset TEXT,
  same_event  INTEGER,
  runs_held   INTEGER                 -- stored runs in the lake (lake/links/<name>)
);

-- Declared aggregates (curation/aggregates) and whether this install built them.
CREATE TABLE aggregates (
  id      TEXT PRIMARY KEY,
  dataset TEXT,
  label   TEXT,
  built   INTEGER
);

-- IBGE SIDRA's catalogue as the registry holds it (sidra scan).
CREATE TABLE sidra_tables (
  id           INTEGER PRIMARY KEY,
  name         TEXT,
  research     TEXT,
  subject      TEXT,
  frequency    TEXT,
  first_period TEXT,
  last_period  TEXT,
  levels       TEXT,
  variables    INTEGER,
  curated      TEXT                   -- the author's compendium group, if any
);

-- What the package serves besides datasets and fields (curation/products.yml): layers, geometries,
-- reference tables, indices, modelled products; `held` of `stores` exist in this install.
CREATE TABLE products (
  id      TEXT PRIMARY KEY,
  label   TEXT,
  kind    TEXT,
  source  TEXT,
  what    TEXT,
  grain   TEXT,
  period  TEXT,
  call    TEXT,
  stores  TEXT,                       -- JSON: paths under the home (or resources/)
  held    INTEGER,
  stores_declared INTEGER
);
-- The members of the two product families declared in their own files: population series
-- (populations.yml) and geography memberships (geography.yml).
CREATE TABLE product_members (
  product TEXT,
  name    TEXT,
  what    TEXT,
  detail  TEXT,
  call    TEXT
);
-- Store folders of the home that no dataset, field, link, intake source or product describes.
CREATE TABLE unclaimed_stores (
  path  TEXT PRIMARY KEY,
  bytes INTEGER
);

-- What pegasus_data can DO: every public function and command.
CREATE TABLE operations (
  name    TEXT,
  kind    TEXT,                       -- function | command
  area    TEXT,
  summary TEXT,
  usage   TEXT,
  PRIMARY KEY (kind, name)
);

-- One row per thing a reader can look up, with the call that gets it: the
-- index search() reads. `folded` is name and prose without accents or case.
CREATE TABLE entries (
  kind    TEXT,                       -- dataset | variable | field | product | role | event | link | aggregate | operation | sidra
  system  TEXT,
  name    TEXT,
  title   TEXT,
  prose   TEXT,
  how     TEXT,
  folded_name TEXT,
  folded  TEXT
);
CREATE INDEX ix_entries_kind ON entries(kind);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);

CREATE VIEW dataset_columns AS
  SELECT dv.dataset, v.system, v.name, v.translated_name, v.description,
         v.code_system, v.codelist, v.physical_type, v.width
    FROM dataset_variables dv
    JOIN variables v ON v.system = dv.system AND v.name = dv.name;
"""

OPTIONAL_SCHEMA = {
    "codes": """
CREATE TABLE codelists (
  id      TEXT PRIMARY KEY,
  system  TEXT,
  codes   INTEGER
);
CREATE TABLE codes (
  codelist   TEXT REFERENCES codelists(id),
  system     TEXT,
  code       TEXT,
  label      TEXT,
  valid_from TEXT,
  valid_to   TEXT
);
CREATE INDEX ix_codes_codelist ON codes(codelist);
CREATE INDEX ix_codes_code ON codes(code);
""",
    "values": """
CREATE TABLE value_frequencies (
  dataset TEXT,
  name    TEXT,
  value   TEXT,
  n       INTEGER
);
CREATE INDEX ix_valfreq ON value_frequencies(dataset, name);
""",
    "files": """
CREATE TABLE files (
  path    TEXT PRIMARY KEY,
  dataset TEXT,
  uf      TEXT,
  year    INTEGER,
  bytes   INTEGER
);
CREATE INDEX ix_files_dataset ON files(dataset);
""",
}


@dataclass
class CompendiumReport:
    """What went in, so the caller can see it rather than infer it."""

    path: str = ""
    megabytes: float = 0.0
    rows: dict[str, int] = field(default_factory=dict)
    options: dict[str, Any] = field(default_factory=dict)
    skipped: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "megabytes": self.megabytes,
            "rows": self.rows,
            "options": self.options,
            "skipped": self.skipped,
        }

    def __repr__(self) -> str:  # pragma: no cover - presentation
        out = [f"compendium: {self.path} ({self.megabytes:.1f} MB)"]
        for table, n in self.rows.items():
            out.append(f"  {table:<20} {n:>9,}")
        if self.skipped:
            out.append("  not included: " + ", ".join(self.skipped))
        return "\n".join(out)


def compendium(
    out: str | Path | None = None,
    *,
    systems: Sequence[str] | None = None,
    codes: CodesOption = "none",
    max_codes: int = 1000,
    values: bool = False,
    files: bool = False,
    descriptions: bool = True,
    root: str | Path | None = None,
    settings: Settings | None = None,
) -> CompendiumReport:
    """Write a portable map of DATASUS to ``out``.

    ``codes`` decides how much of the value dictionary comes along, and it is the
    option that decides the file size:

    * ``"none"`` *(default)* — no code meanings. A few megabytes.
    * ``"internal"`` (also ``codes=True``) — DATASUS's own enumerations, the
      ones you cannot get anywhere else: SIM_NAO, ESP_LEIT, the severity and
      result scales. Codelists larger than ``max_codes`` are left out as
      externally-maintained classifications, and which ones is recorded in the
      report rather than left to be guessed at.
    * ``"bound"`` — every codelist bound to an included column, CID-10, CBO and
      the municipality tables included. Measured at 425 MB for SIH alone.
    * ``"all"`` — every codelist on the tree, 19.9M rows.

    ``values`` adds observed value frequencies, ``files`` the raw path listing.
    ``descriptions=False`` drops the prose and keeps the structure, for a caller
    who wants the smallest possible index.
    """
    cfg = settings or load_settings(root=Path(root) if root else None)
    store = _Store(cfg.catalog_path, read_only=True)
    onto = Ontology.load()

    codes_mode = _normalise_codes(codes)
    target = Path(out) if out is not None else default_path(cfg)
    target.parent.mkdir(parents=True, exist_ok=True)
    # STAGED. Both of these unlinked the existing database and then built its
    # replacement in place, so a failure anywhere in the build left the user
    # with no artifact at all — the previous one deleted and the new one never
    # finished. The rule every other derived artifact here follows: a file is
    # replaced only by a file that already exists in full.
    staged = target.with_name(f".{target.name}.staging.{uuid.uuid4().hex[:10]}")
    staged.unlink(missing_ok=True)

    report = CompendiumReport(
        path=str(target),
        options={
            "systems": list(systems) if systems else "all",
            "codes": codes_mode,
            "max_codes": max_codes,
            "values": values,
            "files": files,
            "descriptions": descriptions,
        },
    )
    for name, flag in (("codes", codes_mode != "none"), ("values", values), ("files", files)):
        if not flag:
            report.skipped.append(name)

    db = sqlite3.connect(staged)
    installed = False
    try:
        db.executescript(SCHEMA)
        for name, enabled in (
            ("codes", codes_mode != "none"),
            ("values", values),
            ("files", files),
        ):
            if enabled:
                db.executescript(OPTIONAL_SCHEMA[name])

        wanted = _wanted_datasets(onto, systems)
        binding = _bindings(store, onto, wanted)
        held = _held(store, onto, wanted, cfg.lake_dir, cfg.blobs_dir)
        _write_core(db, store, onto, wanted, binding, held, report, descriptions)
        _write_holdings(db, store, onto, wanted, cfg, report)
        _write_entries(db, report)
        if codes_mode != "none":
            _write_codes(db, store, wanted, binding, report, codes_mode, max_codes)
        if values:
            _write_values(db, store, binding, report)
        if files:
            _write_files(db, store, binding, report)
        _write_meta(db, store, report)
        db.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('fingerprint', ?)",
                   (fingerprint(cfg, report.options),))
        db.commit()
        db.executescript("ANALYZE; VACUUM;")
        installed = True
    finally:
        db.close()
        store.close()
        if not installed:
            # Closed first: Windows refuses to unlink a file still open.
            staged.unlink(missing_ok=True)
    os.replace(staged, target)

    report.megabytes = round(target.stat().st_size / 2**20, 2)
    return report


def default_path(settings: Settings) -> Path:
    """Where the home keeps its own map: beside the catalog it is built from."""
    return settings.catalog_dir / "compendium.sqlite"


def fingerprint(settings: Settings, options: dict[str, Any] | None = None) -> str:
    """What the map was built from: the catalog, the curation, every lake partition folder, the context fields,
    the links, the SIDRA registry, the options and this module. Any change makes a stored map stale."""
    import hashlib

    digest = hashlib.blake2b(digest_size=16)

    def stamp(path: Path) -> None:
        try:
            st = path.stat()
        except OSError:
            digest.update(f"{path}:absent".encode())
            return
        digest.update(f"{path.as_posix()}:{st.st_size}:{st.st_mtime_ns}".encode())

    for path in (settings.catalog_path, Path(f"{settings.catalog_path}-wal"),
                 settings.registry_dir("sidra", "registry.sqlite"), Path(__file__)):
        stamp(path)
    digest.update(curation_epoch()[1].encode())
    lake = settings.lake_dir
    if lake.is_dir():
        for folder in sorted(lake.glob("*/*/schema_signature=*/uf=*/year=*")):
            stamp(folder)
        for folder in sorted([*lake.glob("fields/*/year=*"), *lake.glob("links/*")]):
            stamp(folder)
    digest.update(json.dumps(options or _DEFAULT_OPTIONS, sort_keys=True, default=str).encode())
    return digest.hexdigest()


#: The options of a default build, which is what :func:`current` keeps.
_DEFAULT_OPTIONS = {"systems": "all", "codes": "none", "max_codes": 1000, "values": False, "files": False,
                    "descriptions": True}


def current(*, settings: Settings | None = None, root: str | Path | None = None, wait: bool = False) -> Path:
    """The home's map (``search()`` and ``info()`` read it). Built here when there is none. When anything it describes
    has changed, it is rebuilt by one detached ``pegasus-data compendium`` and served meanwhile as it was, saying so
    (`rebuilding`): a reader is never held for the rebuild. Every write to the catalog makes the map stale, so while a
    job wrote it (a header census, a build) every `info` and `search` call rebuilt the whole map inside itself, 52 s
    to 11 min (OQ #100). ``wait=True`` rebuilds a stale map here."""
    cfg = settings or load_settings(root=Path(root) if root else None)
    target = default_path(cfg)
    stored = None
    if target.is_file():
        try:
            con = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
            try:
                stored = con.execute("SELECT value FROM meta WHERE key = 'fingerprint'").fetchone()
            finally:
                con.close()
        except sqlite3.Error:
            stored = None
        if stored and stored[0] == fingerprint(cfg):
            return target
    if stored and not wait:
        _rebuild_detached(cfg)
        return target
    compendium(target, settings=cfg)
    return target


def _lock_path(cfg: Settings) -> Path:
    return cfg.catalog_dir / "compendium.rebuilding"


def rebuilding(cfg: Settings) -> int | None:
    """The process rebuilding the home's map in the background, or None."""
    import psutil

    try:
        pid = int(_lock_path(cfg).read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None
    return pid if psutil.pid_exists(pid) else None


def _rebuild_detached(cfg: Settings) -> None:
    """Start one detached rebuild of the home's map unless one is running. It writes beside the map and replaces it in
    one rename (`compendium`), so a reader sees the old map or the new one."""
    import subprocess
    import sys

    if rebuilding(cfg) is not None:
        return
    log = cfg.work_dir / "compendium_rebuild.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PEGASUS_DATA_HOME": str(cfg.catalog_dir.parent), "PYTHONUTF8": "1"}
    flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
    with log.open("ab") as out:
        child = subprocess.Popen([sys.executable, "-m", "pegasus_data.cli", "compendium"], stdout=out, stderr=out,
                                 stdin=subprocess.DEVNULL, env=env, creationflags=flags, close_fds=True)
    _lock_path(cfg).write_text(str(child.pid), encoding="utf-8")


def overview(*, settings: Settings | None = None, root: str | Path | None = None) -> str:
    """Everything the install holds and can do, in one text a person or an agent can read whole (a few hundred
    lines): every dataset with its years on the server and its rows held, every context field, link, aggregate and
    operation, with the call that gets each. ``info()`` with no target prints it; ``search`` finds within it."""
    path = current(settings=settings, root=root)
    con = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        q = con.execute
        built = (q("SELECT value FROM meta WHERE key = 'generated_at'").fetchone() or ["?"])[0]
        cfg = settings or load_settings(root=Path(root) if root else None)
        moving = rebuilding(cfg)
        out = [f"pegasus_data: what this install holds and can do (map of {built})."
               + (f" The home has changed since; a new map is being built (process {moving})." if moving else ""),
               "  search <words> finds anything below, and every column, role, SIDRA table and code;",
               "  info <dataset> / info <dataset>.<COLUMN> describes one. Rows held are in this install's lake.", ""]

        datasets = q("SELECT d.code, d.translated_name, d.year_min, d.year_max, d.rows_held, d.year_min_held,"
                     " d.year_max_held, d.columns_total, s.kind, d.files_downloaded, d.year_min_downloaded,"
                     " d.year_max_downloaded, d.months_downloaded FROM datasets d LEFT JOIN systems s ON s.code = d.system"
                     " ORDER BY d.system, d.code").fetchall()
        data = [d for d in datasets if d[8] != "tooling"]
        out.append(f"RECORD DATASETS ({len(data)}): query(\"<code>\", period=..., geography=...)")
        for code, name, y0, y1, held, h0, h1, cols, _, files, _f0, _f1, spans in data:
            server = f"{y0}-{y1}" if y0 else "-"
            kept = f"held {held:,} rows {h0}-{h1}" if held else (
                f"downloaded {files:,} files (months {spans}), not built" if files else "none held")
            out.append(f"  {code:<30} {str(name or '')[:46]:<46} {cols or 0:>4} cols  server {server:<9}  {kept}")

        fields = q("SELECT name, label, source, years, years_held FROM fields ORDER BY source, name").fetchall()
        out += ["", f"CONTEXT FIELDS ({len(fields)}), per municipality and year: load_field(\"<name>\")"]
        for name, label, source, years, held in fields:
            got = json.loads(held or "[]")
            kept = f"held {got[0]}-{got[-1]}" if got else "none held"
            out.append(f"  [{source or '?'}] {name:<44} {str(label or '')[:52]:<52} {years or ''}  {kept}")

        products = q("SELECT id, label, kind, source, period, call, held, stores_declared FROM products"
                     " ORDER BY kind, id").fetchall()
        out += ["", f"LAYERS, GEOMETRIES, REFERENCE TABLES AND MODELLED PRODUCTS ({len(products)}), by kind"]
        for pid, label, kind, source, period, call, held, declared in products:
            kept = "held" if declared and held == declared else (f"{held}/{declared} stores held" if declared else "")
            out.append(f"  [{kind or '?'}] {pid:<34} {str(label or '')[:50]:<50} {period or '':<10} {call or ''}"
                       f"  {kept}  ({str(source or '')[:60]})")
        for product, names in q("SELECT product, GROUP_CONCAT(name, ', ') FROM product_members GROUP BY product").fetchall():
            out.append(f"  {product} members: {names}")
        unclaimed = q("SELECT path, bytes FROM unclaimed_stores ORDER BY bytes DESC").fetchall()
        if unclaimed:
            out += ["", f"UNDESCRIBED STORES ({len(unclaimed)}): data in the home that nothing above describes (a defect)"]
            out += [f"  {path}  {bytes_ / 2**20:,.0f} MB" for path, bytes_ in unclaimed]

        links = q("SELECT name, left_dataset, right_dataset, runs_held, description FROM links ORDER BY name").fetchall()
        out += ["", f"RECORD LINKS ({len(links)}): info <name> describes one and its runs; link(<name>, ...) runs it"]
        for name, left, right, runs, what in links:
            first = str(what or "").split(". ")[0][:80]
            out.append(f"  {name:<40} {left} -> {right}  ({runs} runs held)  {first}")

        aggs = q("SELECT id, built FROM aggregates ORDER BY id").fetchall()
        out += ["", f"AGGREGATES ({len(aggs)}, * built): aggregate(\"<id>\")",
                "  " + ", ".join(f"{a}{'*' if b else ''}" for a, b in aggs)]

        n_roles, n_ds = q("SELECT COUNT(*), COUNT(DISTINCT dataset) FROM roles").fetchone()
        n_events = q("SELECT COUNT(*) FROM events").fetchone()[0]
        n_sidra = q("SELECT COUNT(*) FROM sidra_tables").fetchone()[0]
        out += ["", f"ROLES: {n_roles:,} columns of {n_ds} datasets typed as entity.property: roles(\"<dataset>\");"
                    f" EVENT TYPES: {n_events}: event_types(\"<dataset>\"), count_events(...)",
                f"SIDRA (IBGE): {n_sidra:,} tables in the registry: pegasus-data sidra search <words>"]

        out += ["", "OPERATIONS: Python functions (pegasus_data.<name>) and commands, by area"]
        for area, names in q("SELECT area, GROUP_CONCAT(name, ', ') FROM (SELECT area, name FROM operations"
                             " WHERE kind = 'function' ORDER BY name) GROUP BY area ORDER BY area").fetchall():
            out.append(f"  {area}: {names}")
        commands = [r[0].removeprefix("pegasus-data ") for r in
                    q("SELECT name FROM operations WHERE kind = 'command' ORDER BY name").fetchall()]
        out.append("  commands: pegasus-data " + ", ".join(commands))
        n_open = q("SELECT COUNT(*) FROM open_questions").fetchone()[0]
        out += ["", f"OPEN QUESTIONS in the catalog: {n_open} (the project's are in OPEN_QUESTIONS.md)."]
        return "\n".join(out)
    finally:
        con.close()


# ------------------------------------------------------------------ internals


def _normalise_codes(codes: CodesOption) -> str:
    if codes is True:
        return "internal"
    if codes is False or codes is None:
        return "none"
    text = str(codes).lower()
    if text not in {"none", "internal", "bound", "all"}:
        raise ValueError(f"codes must be none, internal, bound or all (got {codes!r})")
    return text


def _wanted_datasets(onto: Ontology, systems: Sequence[str] | None) -> set[str]:
    if not systems:
        return set(onto.datasets)
    keep: set[str] = set()
    for name in systems:
        found = onto.resolve(str(name))
        if found is None:
            near = onto.suggest(str(name))
            hint = f" Did you mean: {', '.join(near)}?" if near else ""
            raise ValueError(f"{name!r} is not a declared system or dataset.{hint}")
        kind, node = found
        if kind == "system":
            keep.update(d.code for d in onto.datasets_of(node.code))
        else:
            keep.add(node.code)
    return keep


@dataclass
class _Binding:
    """The crawl, indexed the way the writers need it."""

    dataset_of_pair: dict[tuple[str, str], str] = field(default_factory=dict)
    crawled_systems: dict[str, set[str]] = field(default_factory=dict)
    signatures: dict[str, set[str]] = field(default_factory=dict)


def _bindings(store: _Store, onto: Ontology, wanted: set[str]) -> _Binding:
    out = _Binding()
    for row in store.query(
        "SELECT DISTINCT system, series, schema_signature FROM strata "
        "WHERE system IS NOT NULL AND series IS NOT NULL"
    ):
        system, series = str(row["system"]), str(row["series"])
        code = onto.bind(system, series).dataset
        if not code or code not in wanted:
            continue
        out.dataset_of_pair[(system, series)] = code
        out.crawled_systems.setdefault(code, set()).add(system)
        if row["schema_signature"]:
            out.signatures.setdefault(code, set()).add(str(row["schema_signature"]))
    return out


def _write_field_validity(
    db: sqlite3.Connection,
    store: _Store,
    onto: Ontology,
    wanted: set[str],
    report: CompendiumReport,
) -> None:
    """When each column existed, one row per contiguous run (§14.7)."""
    from ._availability import _read as _read_availability

    rows = []
    for code in sorted(wanted):
        try:
            found = _read_availability(store.conn, onto, code)
        except Exception:  # noqa: BLE001 - a dataset with nothing decoded yet
            continue
        for window in found.fields.values():
            for lo, hi in window.intervals:
                bridged = [y for y in window.bridged_years() if lo <= y <= hi]
                rows.append(
                    (
                        code,
                        window.field,
                        lo,
                        hi,
                        1 if (window.current and hi == found.decoded_years[-1]) else 0,
                        json.dumps(bridged) if bridged else None,
                    )
                )
    db.executemany(
        "INSERT OR REPLACE INTO field_validity (dataset, field, year_from, year_to,"
        " current, bridged) VALUES (?,?,?,?,?,?)",
        rows,
    )
    report.rows["field_validity"] = db.execute(
        "SELECT COUNT(*) FROM field_validity"
    ).fetchone()[0]


def _write_codelist_vintages(
    db: sqlite3.Connection, store: _Store, report: CompendiumReport
) -> None:
    """How many vintages each codelist has, and over what competence windows.

    Always written, however large the optional `codes` table would be: a caller
    needs to know a codelist is versioned even when they have not asked for the
    codes themselves.
    """
    rows = [
        (
            str(r["value_group"]),
            r["system"],
            int(r["vintages"] or 0),
            r["window_min"],
            r["window_max"],
            1 if int(r["open_ended"] or 0) else 0,
            int(r["codes"] or 0),
        )
        for r in store.query(
            """
            SELECT value_group, system,
                   COUNT(DISTINCT COALESCE(valid_from, '') || '..' ||
                                  COALESCE(valid_to, '')) AS vintages,
                   MIN(valid_from) AS window_min,
                   MAX(valid_to)   AS window_max,
                   MAX(CASE WHEN valid_from IS NULL THEN 1 ELSE 0 END) AS open_ended,
                   COUNT(DISTINCT value_raw) AS codes
              FROM dictionary
             WHERE value_group IS NOT NULL
             GROUP BY value_group, system
            """
        )
    ]
    db.executemany(
        "INSERT OR REPLACE INTO codelist_vintages (codelist, system, vintages,"
        " window_min, window_max, has_current, codes) VALUES (?,?,?,?,?,?,?)",
        rows,
    )
    report.rows["codelist_vintages"] = db.execute(
        "SELECT COUNT(*) FROM codelist_vintages"
    ).fetchone()[0]


def _write_join_keys(
    db: sqlite3.Connection,
    onto: Ontology,
    wanted: set[str],
    report: CompendiumReport,
) -> None:
    """Declared join keys, their members, and the joins known NOT to exist (§14.8)."""
    db.executemany(
        "INSERT OR REPLACE INTO join_keys (name, what, as_of, caveats) VALUES (?,?,?,?)",
        [
            (k.name, k.what, k.as_of, json.dumps(list(k.caveats)) if k.caveats else None)
            for k in onto.keys.values()
        ],
    )
    db.executemany(
        "INSERT OR REPLACE INTO join_key_members (key, dataset, column_name,"
        " rows_per_key, note) VALUES (?,?,?,?,?)",
        [
            (k.name, m.dataset, m.column, m.rows_per_key, m.note)
            for k in onto.keys.values()
            for m in k.members
            if m.dataset in wanted
        ],
    )
    db.executemany(
        "INSERT INTO joins_not_established (want, proposed_key, finding) VALUES (?,?,?)",
        [(u.want, u.proposed_key, u.finding) for u in onto.unestablished],
    )
    report.rows["join_key_members"] = db.execute(
        "SELECT COUNT(*) FROM join_key_members"
    ).fetchone()[0]


def _write_core(
    db: sqlite3.Connection,
    store: _Store,
    onto: Ontology,
    wanted: set[str],
    binding: _Binding,
    held: _Held,
    report: CompendiumReport,
    descriptions: bool,
) -> None:
    """Coverage, variables and their links, generations, datasets, systems and open questions."""
    cover = _crawled_cover(store, onto, wanted)
    _write_coverage(db, cover, held, report)
    totals = _dataset_totals(cover, onto, wanted)

    described = _described(store)
    per_dataset_cols, col_system = _dataset_columns(store, onto, wanted, binding, held, described)
    _write_variables(db, per_dataset_cols, col_system, described, _field_meta(store), descriptions, report)
    _write_dataset_variables(
        db, store, onto, wanted, per_dataset_cols, col_system, described, held, report
    )

    _write_field_validity(db, store, onto, wanted, report)
    _write_codelist_vintages(db, store, report)
    _write_join_keys(db, onto, wanted, report)

    gens_per = _write_schema_generations(db, store, onto, wanted, binding, report)
    ds_rows = _write_datasets(
        db, store, onto, wanted, totals, per_dataset_cols, col_system, described, gens_per, held, report
    )
    _write_systems(db, onto, wanted, ds_rows, report)
    _write_open_questions(db, store, report)


def _crawled_cover(store: _Store, onto: Ontology, wanted: set[str]) -> dict[tuple[str, int, str], int]:
    """Data files the crawl lists per (dataset, year, uf)."""
    cover: dict[tuple[str, int, str], int] = {}
    for row in store.query(
        "SELECT system, series_prefix, year, geo_code, COUNT(*) AS n FROM file_facts "
        "WHERE system IS NOT NULL AND role = 'data' GROUP BY 1, 2, 3, 4"
    ):
        code = onto.bind(str(row["system"]), str(row["series_prefix"] or "")).dataset
        if not code or code not in wanted:
            continue
        year = int(row["year"]) if row["year"] is not None else 0
        uf = str(row["geo_code"] or "")
        key = (code, year, uf)
        cover[key] = cover.get(key, 0) + int(row["n"] or 0)
    return cover


def _write_coverage(
    db: sqlite3.Connection, cover: dict[tuple[str, int, str], int], held: _Held, report: CompendiumReport
) -> None:
    """The coverage table: files listed and rows held per (dataset, year, uf)."""
    db.executemany(
        "INSERT INTO coverage (dataset, year, uf, files, rows_held) VALUES (?,?,?,?,?)",
        [(d, y, u, cover.get((d, y, u), 0), held.cover.get((d, y, u)))
         for (d, y, u) in sorted(set(cover) | set(held.cover))],
    )
    report.rows["coverage"] = len(set(cover) | set(held.cover))


def _dataset_totals(
    cover: dict[tuple[str, int, str], int], onto: Ontology, wanted: set[str]
) -> dict[str, dict[str, Any]]:
    """Per dataset: files, first and last year, and the UFs seen, from the coverage."""
    totals: dict[str, dict[str, Any]] = {}
    for (code, year, uf), n in cover.items():
        slot = totals.setdefault(code, {"files": 0, "ymin": None, "ymax": None, "ufs": set()})
        slot["files"] += n
        if year:
            slot["ymin"] = year if slot["ymin"] is None else min(slot["ymin"], year)
            slot["ymax"] = year if slot["ymax"] is None else max(slot["ymax"], year)
        if uf:
            slot["ufs"].add(uf)
    # A Portal source's publications are its declaration's units (a pattern and its months, as the crawl lists FTP
    # files): the catalog knows only the ones landed, so the declared ones count where they are more.
    for code, (n, y0, y1) in _declared_publications(onto, wanted).items():
        slot = totals.setdefault(code, {"files": 0, "ymin": None, "ymax": None, "ufs": set()})
        if n > slot["files"]:
            slot.update(files=n, ymin=y0 if slot["ymin"] is None else min(slot["ymin"], y0),
                        ymax=y1 if slot["ymax"] is None else max(slot["ymax"], y1))
    return totals


def _dataset_columns(
    store: _Store,
    onto: Ontology,
    wanted: set[str],
    binding: _Binding,
    held: _Held,
    described: dict[tuple[str, str], dict[str, Any]],
) -> tuple[dict[str, set[str]], dict[tuple[str, str], str]]:
    """Each dataset's columns by name, and the system each (dataset, column) is attributed to."""
    # A dataset's columns, keyed by column name — NOT by (crawled system, name).
    #
    # This built the cross product of columns and crawled systems, so a dataset
    # published in more than one tree counted every column once per tree. SIA.AB
    # is crawled under both SIASUS and DADOS_ABERTOS and reported 116 columns; it
    # has 58. The inflated number reached `datasets.columns_total`, which is the
    # figure a reader would cite, and the duplicate rows were then silently
    # dropped by the (dataset, name) primary key — so the table said 9,237 while
    # the report said 13,281.
    #
    # Republication is exactly what the ontology exists to resolve: SIA.AB is one
    # dataset with one set of columns however many trees carry it.
    per_dataset_cols: dict[str, set[str]] = {}
    declared = _declared_columns(onto, wanted)
    #: (dataset, column) -> the system to attribute the column to. Variable docs
    #: are keyed by the crawled system, so the attribution has to be whichever
    #: one actually documents the column, with a deterministic fallback.
    col_system: dict[tuple[str, str], str] = {}
    for code in wanted:
        sigs = binding.signatures.get(code, set())
        # The columns the server's files declare, and the ones the lake holds:
        # a dataset read from the Portal or an API has no FTP header to sample,
        # and its columns are known only from the records landed.
        cols = set(held.columns.get(code, {})) | declared.get(code, set())
        if sigs:
            marks = ",".join("?" for _ in sigs)
            cols |= {
                str(r["field_name"])
                for r in store.query(
                    f"SELECT DISTINCT field_name FROM schema_presence "
                    f"WHERE schema_signature IN ({marks})",
                    tuple(sigs),
                )
            }
        if not cols:
            continue
        systems_for = sorted(binding.crawled_systems.get(code, set()))
        if not systems_for:
            systems_for = [onto.datasets[code].system]
        per_dataset_cols[code] = cols
        for name in cols:
            owner = next((s for s in systems_for if (s, name.upper()) in described), None)
            col_system[(code, name)] = owner or systems_for[0]
    return per_dataset_cols, col_system


def _write_variables(
    db: sqlite3.Connection,
    per_dataset_cols: dict[str, set[str]],
    col_system: dict[tuple[str, str], str],
    described: dict[tuple[str, str], dict[str, Any]],
    field_meta: dict[tuple[str, str], dict[str, Any]],
    descriptions: bool,
    report: CompendiumReport,
) -> None:
    """The variables table: one row per (system, column), documented where documentation exists."""
    seen_vars: set[tuple[str, str]] = {
        (col_system[(code, name)], name)
        for code, cols in per_dataset_cols.items()
        for name in cols
    }
    var_rows = []
    for system, name in sorted(seen_vars):
        doc = described.get((system, name.upper()), {})
        meta = field_meta.get((system, name), {})
        var_rows.append(
            (
                system, name,
                doc.get("official_name"), doc.get("translated_name"),
                doc.get("description") if descriptions else None,
                doc.get("code_system"), doc.get("codelist"),
                doc.get("source"), doc.get("source_ref"),
                doc.get("reasoning") if descriptions else None,
                meta.get("type"), meta.get("width"),
            )
        )
    db.executemany(
        "INSERT OR REPLACE INTO variables (system, name, official_name, translated_name,"
        " description, code_system, codelist, source, source_ref, reasoning,"
        " physical_type, width) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        var_rows,
    )
    report.rows["variables"] = len(var_rows)


def _write_dataset_variables(
    db: sqlite3.Connection,
    store: _Store,
    onto: Ontology,
    wanted: set[str],
    per_dataset_cols: dict[str, set[str]],
    col_system: dict[tuple[str, str], str],
    described: dict[tuple[str, str], dict[str, Any]],
    held: _Held,
    report: CompendiumReport,
) -> None:
    """Which datasets carry which columns, with the labelling decision and how filled the column is."""
    labels = _label_bindings(store, onto, wanted)
    link_rows = []
    for code, cols in per_dataset_cols.items():
        for name in sorted(cols):
            decided = labels.get((code, name))
            counted = held.columns.get(code, {}).get(name)
            doc = described.get((col_system[(code, name)], name.upper()), {})
            curated_list = [doc["codelist"]] if doc.get("codelist") else []
            link_rows.append((
                code, col_system[(code, name)], name,
                json.dumps(decided["codelists"] if decided else curated_list) if (decided or curated_list) else None,
                decided["basis"] if decided else ("curated" if curated_list else None),
                decided["share"] if decided else None,
                (round(counted[0] / counted[1], 4) if counted and counted[1] and counted[0] is not None else None),
                counted[1] if counted else None,
            ))
    db.executemany(
        "INSERT OR REPLACE INTO dataset_variables (dataset, system, name, codelists, label_basis,"
        " label_share, filled, rows_held) VALUES (?,?,?,?,?,?,?,?)",
        link_rows,
    )
    # Count what landed, not what was offered. Reporting the length of the input
    # list is how a row count survives being wrong: INSERT OR REPLACE collapses
    # primary-key collisions, and the report went on claiming the pre-collapse
    # number.
    report.rows["dataset_variables"] = db.execute(
        "SELECT COUNT(*) FROM dataset_variables"
    ).fetchone()[0]


def _write_schema_generations(
    db: sqlite3.Connection,
    store: _Store,
    onto: Ontology,
    wanted: set[str],
    binding: _Binding,
    report: CompendiumReport,
) -> dict[str, int]:
    """Schema generations, with what each one changed; returns the generation count per dataset."""
    gen_rows = _generations(store, onto, wanted, binding)
    db.executemany(
        "INSERT OR REPLACE INTO schema_generations (dataset, signature, field_count,"
        " year_min, year_max, files, added, dropped) VALUES (?,?,?,?,?,?,?,?)",
        gen_rows,
    )
    report.rows["schema_generations"] = len(gen_rows)
    gens_per: dict[str, int] = {}
    for gen_row in gen_rows:
        gens_per[gen_row[0]] = gens_per.get(gen_row[0], 0) + 1
    return gens_per


def _write_datasets(
    db: sqlite3.Connection,
    store: _Store,
    onto: Ontology,
    wanted: set[str],
    totals: dict[str, dict[str, Any]],
    per_dataset_cols: dict[str, set[str]],
    col_system: dict[tuple[str, str], str],
    described: dict[tuple[str, str], dict[str, Any]],
    gens_per: dict[str, int],
    held: _Held,
    report: CompendiumReport,
) -> list[tuple]:
    """The datasets table; returns its rows for the systems table to total."""
    docs = _dataset_docs(store, onto)
    axes_by_code = onto.axes(store.conn)
    ds_rows = []
    for code in sorted(wanted):
        node = onto.datasets[code]
        t = totals.get(code, {})
        doc = docs.get(code, {})
        cols = per_dataset_cols.get(code, set())
        n_desc = sum(1 for name in cols if (col_system[(code, name)], name.upper()) in described)
        ds_rows.append(
            (
                code, node.system, node.short_code,
                node.official_name, node.translated_name, node.what_it_is,
                doc.get("what_one_row_is"), doc.get("unit_of_analysis"),
                doc.get("known_biases"), doc.get("gotchas"),
                node.status, node.confidence,
                t.get("files", 0), t.get("ymin"), t.get("ymax"),
                len(t.get("ufs", ())), gens_per.get(code, 0),
                len(cols), n_desc,
                *_axis_columns(axes_by_code.get(code)),
                code, held.rows.get(code), *held.span(code),
                *held.downloads.get(code, (None, None, None, None)),
            )
        )
    db.executemany(
        "INSERT INTO datasets (code, system, short_code, official_name, translated_name,"
        " what_it_is, what_one_row_is, unit_of_analysis, known_biases, gotchas, status,"
        " confidence, files, year_min, year_max, ufs, generations, columns_total,"
        " columns_described, split_by, split_by_uf, split_by_year, split_by_month,"
        " query_as, rows_held, year_min_held, year_max_held, files_downloaded, year_min_downloaded,"
        " year_max_downloaded, months_downloaded) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ds_rows,
    )
    report.rows["datasets"] = len(ds_rows)
    return ds_rows


def _write_systems(
    db: sqlite3.Connection,
    onto: Ontology,
    wanted: set[str],
    ds_rows: list[tuple],
    report: CompendiumReport,
) -> None:
    """The systems table, with dataset, file and year totals taken from the datasets rows."""
    sys_rows = []
    for code, sys_node in sorted(onto.systems.items()):
        mine = [r for r in ds_rows if r[1] == code]
        if not mine and systems_scoped(wanted, onto, code):
            continue
        years = [r[13] for r in mine if r[13]] + [r[14] for r in mine if r[14]]
        sys_rows.append(
            (
                code, sys_node.official_name, sys_node.translated_name, sys_node.kind, sys_node.status,
                sys_node.authority, sys_node.what_it_is, len(mine),
                sum(r[12] for r in mine), min(years) if years else None,
                max(years) if years else None,
            )
        )
    db.executemany(
        "INSERT INTO systems (code, official_name, translated_name, kind, status,"
        " authority, what_it_is, datasets, files, year_min, year_max)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        sys_rows,
    )
    report.rows["systems"] = len(sys_rows)


def _write_open_questions(db: sqlite3.Connection, store: _Store, report: CompendiumReport) -> None:
    """The catalog's open questions."""
    questions = [
        (str(r["key"]), r["area"], r["question"], r["blocking"])
        for r in store.query(
            "SELECT key, area, question, blocking FROM open_questions WHERE status = 'open'"
        )
    ]
    db.executemany(
        "INSERT OR REPLACE INTO open_questions (key, area, question, blocking)"
        " VALUES (?,?,?,?)",
        questions,
    )
    report.rows["open_questions"] = len(questions)


# ------------------------------------------------------- what this install holds


@dataclass
class _Held:
    """The lake, read from its Parquet footers: no record is read."""

    #: (dataset, year, uf) -> rows held
    cover: dict[tuple[str, int, str], int] = field(default_factory=dict)
    #: dataset -> column -> [non-null rows (None when a file carries no statistics), rows]
    columns: dict[str, dict[str, list[Any]]] = field(default_factory=dict)
    rows: dict[str, int] = field(default_factory=dict)
    #: dataset -> (published files the blob store holds, first year, last year), whether built into the lake or not
    downloads: dict[str, tuple[int, int | None, int | None, str | None]] = field(default_factory=dict)

    def span(self, code: str) -> tuple[int | None, int | None]:
        years = [y for (c, y, _), n in self.cover.items() if c == code and y and n]
        return (min(years), max(years)) if years else (None, None)


def _internal(name: str) -> bool:
    """A column the lake adds (provenance, the raw value beside a typed one), not one the source publishes."""
    return name.startswith("_") or name.endswith(("__RAW", "__FLAG"))


def _held(store: _Store, onto: Ontology, wanted: set[str], lake_dir: Path, blobs_dir: Path | None = None) -> _Held:
    from concurrent.futures import ThreadPoolExecutor

    import pyarrow.parquet as pq

    # The lake read by its own layout, <SYSTEM>/<SYSTEM>_<SERIES>_<hash>/schema_signature=…/uf=…/year=…/*.parquet:
    # the catalog's lake_partitions lists only what the FTP build wrote, and the
    # intake sources (SRAG, SISAGUA, SNGPC…) land beside it without a row there.
    # The folder is not always the system's name (SNGPC lands under lake/sngpc), so the family's own name decides.
    # A family is named by the system as crawled (SIHSUS_RD_…), which the ontology knows as an alias of SIH.
    systems = sorted({*onto.systems, *(a for n in onto.systems.values() for a in (n.crawled_as or ()))},
                     key=len, reverse=True)
    parts: list[tuple[str, int, str, Path]] = []
    for system_dir in (p for p in lake_dir.iterdir() if p.is_dir()) if lake_dir.is_dir() else ():
        for family in system_dir.iterdir():
            head, _, digest = family.name.rpartition("_")
            system = next((s for s in systems if head.startswith(f"{s}_")), None)
            if not family.is_dir() or system is None or len(digest) != 10:
                continue
            code = onto.bind(system, head[len(system) + 1:]).dataset
            if not code or code not in wanted:
                continue
            for path in family.glob("schema_signature=*/uf=*/year=*/*.parquet"):
                uf = path.parent.parent.name.split("=", 1)[1]
                year = path.parent.name.split("=", 1)[1]
                parts.append((code, int(year) if year.isdigit() else 0, uf, path))

    def footer(part: tuple[str, int, str, Path]) -> tuple[tuple[str, int, str, Path], Any]:
        try:
            return part, pq.read_metadata(part[3])
        except (OSError, ValueError):  # a partition the catalog lists and the disk no longer has
            return part, None

    # The rows held are one reading of each year, as query() reads it: a year whose national file is held beside
    # some of its state files (SIM-DO 2009 and 2012, built when states were asked) counted each death twice, 24.9 M
    # rows for 23.1 M (2026-11-21). The coverage still lists every partition, the state ones included.
    from ._query_engine.coverage import national_or_states

    by_year: dict[tuple[str, int], list[tuple[str, int, str, Path]]] = {}
    for part in parts:
        by_year.setdefault((part[0], part[1]), []).append(part)
    reading = {part[3] for items in by_year.values() for part in national_or_states(items, lambda p: p[2])}

    out = _Held()
    with ThreadPoolExecutor(max_workers=8) as pool:
        for (code, part_year, uf, path), meta in pool.map(footer, parts):
            if meta is None:
                continue
            key = (code, part_year, uf)
            out.cover[key] = out.cover.get(key, 0) + meta.num_rows
            if path not in reading:
                continue
            out.rows[code] = out.rows.get(code, 0) + meta.num_rows
            nulls: dict[str, int | None] = {}
            for g in range(meta.num_row_groups):
                group = meta.row_group(g)
                for c in range(group.num_columns):
                    chunk = group.column(c)
                    name = chunk.path_in_schema.split(".")[0]
                    if _internal(name):
                        continue
                    stats = chunk.statistics
                    seen = nulls.get(name, 0)
                    known = seen is not None and stats is not None and stats.has_null_count
                    nulls[name] = (seen + stats.null_count) if known else None
            columns = out.columns.setdefault(code, {})
            for name, n_null in nulls.items():
                slot = columns.setdefault(name, [0, 0])
                slot[0] = None if (slot[0] is None or n_null is None) else slot[0] + meta.num_rows - n_null
                slot[1] += meta.num_rows
    if blobs_dir is not None:
        out.downloads = _downloaded(store, onto, wanted, blobs_dir)
    return out


def _downloaded(store: _Store, onto: Ontology, wanted: set[str], blobs_dir: Path) -> dict[str, tuple[int, int | None, int | None, str | None]]:
    """Per dataset, the published files whose bytes the blob store holds (what a query reads without the network),
    their years and which months of them. CNES is held this way and never built into the lake (its fields are cubes over
    the downloaded registers, ADR-0217), and the map said "none held" of twelve years of every state's registers
    (2026-11-21). The months are said because a dataset can be held for some months only (CNES: December of each year)."""
    count: dict[str, int] = {}
    months: dict[str, dict[int, set[int]]] = {}
    seen: set[str] = set()
    for row in store.conn.execute(
        "SELECT DISTINCT f.sha256, f.source_path, ff.system, ff.series_prefix, ff.year, ff.normalized_date FROM fetches f"
        " JOIN file_facts ff ON ff.path = f.source_path"
    ).fetchall():
        sha, path, system, series, year, normalized = (row[0], row[1], row[2], row[3], row[4], row[5])
        if path in seen or not sha or not (blobs_dir / "sha256" / str(sha)[:2] / str(sha)).is_file():
            continue
        try:
            code = onto.bind(str(system or ""), str(series or "")).dataset
        except (KeyError, ValueError, LookupError):
            code = None
        if not code or code not in wanted:
            continue
        seen.add(path)
        count[code] = count.get(code, 0) + 1
        if year:
            month = int(str(normalized)[4:6]) if normalized and len(str(normalized)) >= 6 and str(normalized)[4:6].isdigit() else 0
            months.setdefault(code, {}).setdefault(int(year), set()).add(month)
    return {code: (n, min(months.get(code) or [0]) or None, max(months.get(code) or [0]) or None,
                   _month_spans(months.get(code) or {})) for code, n in count.items()}


def _month_spans(by_year: dict[int, set[int]]) -> str | None:
    """``{2008: {12}, ..., 2023: {12}, 2025: {1..12}}`` as "12 of 2008-2023; 01-12 of 2025": runs of years holding the same
    months; a year's file without a month (an annual file) is "year"."""
    if not by_year:
        return None

    def label(ms: set[int]) -> str:
        if ms == {0}:
            return "year"
        real = sorted(m for m in ms if m)
        if real == list(range(real[0], real[-1] + 1)) and len(real) > 2:
            return f"{real[0]:02d}-{real[-1]:02d}"
        return ",".join(f"{m:02d}" for m in real)

    runs: list[tuple[str, int, int]] = []
    for year in sorted(by_year):
        lab = label(by_year[year])
        if runs and runs[-1][0] == lab and runs[-1][2] == year - 1:
            runs[-1] = (lab, runs[-1][1], year)
        else:
            runs.append((lab, year, year))
    return "; ".join(f"{lab} of {lo}" + (f"-{hi}" if hi != lo else "") for lab, lo, hi in runs)


def _declared_columns(onto: Ontology, wanted: set[str]) -> dict[str, set[str]]:
    """The columns an intake declaration lists (``curation/intake.yml``), as they land (upper-cased): known before a
    single record is read, so a source not yet landed still says what it holds."""
    from .semantics.intake_declarations import declared_sources

    out: dict[str, set[str]] = {}
    for spec in declared_sources().values():
        if not spec.get("system") or not spec.get("series") or not isinstance(spec.get("columns"), dict):
            continue
        code = onto.bind(str(spec["system"]), str(spec["series"])).dataset
        if code and code in wanted:
            out.setdefault(code, set()).update(str(c).upper() for c in spec["columns"])
    return out


def _declared_publications(onto: Ontology, wanted: set[str]) -> dict[str, tuple[int, int, int]]:
    """Per intake dataset with a files origin, the publications its declaration lists: (files, first year, last year)."""
    from .intake import _units
    from .semantics.intake_declarations import declared_sources

    out: dict[str, tuple[int, int, int]] = {}
    for spec in declared_sources().values():
        if not spec.get("system") or (spec.get("origin") or {}).get("kind") != "files":
            continue
        code = onto.bind(str(spec["system"]), str(spec["series"])).dataset
        years = [int(u["year"]) for u in _units(spec, None) if u.get("year")]
        if code and code in wanted and years:
            out[code] = (len(_units(spec, None)), min(years), max(years))
    return out


def _label_bindings(store: _Store, onto: Ontology, wanted: set[str]) -> dict[tuple[str, str], dict[str, Any]]:
    """The codelists a query labels each column with, as stored per schema family, oldest family first."""
    by_key: dict[tuple[str, str], list[tuple[str, list[str], str, Any]]] = {}
    for r in store.query(
        "SELECT f.system AS system, f.series AS series, COALESCE(f.time_max, '') AS t, b.field_name AS name,"
        " b.codelists AS codelists, b.basis AS basis, b.share AS share"
        " FROM label_bindings b JOIN families f ON f.family_id = b.family_id"
    ):
        code = onto.bind(str(r["system"]), str(r["series"])).dataset
        if not code or code not in wanted:
            continue
        try:
            lists = [str(x) for x in json.loads(r["codelists"] or "[]")]
        except ValueError:
            lists = []
        by_key.setdefault((code, str(r["name"])), []).append((str(r["t"]), lists, str(r["basis"]), r["share"]))
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for key, decisions in by_key.items():
        decisions.sort(key=lambda d: d[0])
        ordered: list[str] = []
        for _, lists, _, _ in decisions:
            ordered.extend(x for x in lists if x not in ordered)
        newest = decisions[-1]
        out[key] = {"codelists": ordered, "basis": newest[2], "share": newest[3]}
    return out


def _write_holdings(
    db: sqlite3.Connection, store: _Store, onto: Ontology, wanted: set[str], cfg: Settings, report: CompendiumReport,
) -> None:
    """Everything beyond the datasets' columns: context fields, roles and events, links, aggregates, SIDRA, and the
    operations the package offers. Each is read through the loader the package itself uses, so the map says what a
    call would find."""
    _write_fields(db, cfg, report)
    _write_products(db, cfg, report)
    _write_roles(db, report)
    _write_links(db, cfg, report)
    _write_aggregates(db, cfg, report)
    _write_sidra(db, cfg, report)
    _write_operations(db, report)


def _write_products(db: sqlite3.Connection, cfg: Settings, report: CompendiumReport) -> None:
    """What the package serves besides datasets and fields (``curation/products.yml``), with whether this install holds
    each one's stores; the population series (``populations.yml``) and geography memberships (``geography.yml``) from
    their own declarations; and every store folder of the home that nothing describes."""
    from .semantics.curation import products, read_yaml

    base = curation_root()
    declared = dict(products(base))
    rows = []
    claimed: set[str] = set()
    for pid, spec in sorted(declared.items()):
        stores = [str(s).strip("/") for s in (spec.get("stores") or [])]
        claimed.update(stores)
        held = [s for s in stores if (cfg.root / s).exists() or (Path(__file__).parent / s).exists()]
        rows.append((pid, spec.get("label"), spec.get("kind"), spec.get("source"),
                     str(spec.get("what") or "").strip() or None, spec.get("grain"),
                     None if spec.get("period") is None else str(spec["period"]), spec.get("call"),
                     json.dumps(stores), len(held), len(stores)))
    db.executemany("INSERT INTO products VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    report.rows["products"] = len(rows)

    members: list[tuple[Any, ...]] = []
    for name, spec in sorted(((read_yaml(base / "populations.yml", missing_ok=True) or {}).get("series") or {}).items()):
        what = " ".join(str(spec.get(k) or "") for k in ("kind", "authority", "notes")).strip()
        members.append(("population_series", name, what, spec.get("axes") and json.dumps(spec["axes"]),
                        f'load_population(series="{name}")'))
    geo = read_yaml(base / "geography.yml", missing_ok=True) or {}
    for section in ("classifications", "ibge_classifications", "tabnet_classifications", "ipea_classifications"):
        for name, spec in sorted((geo.get(section) or {}).items()):
            if isinstance(spec, dict):
                members.append(("geography_memberships", name, str(spec.get("what") or "").strip()[:400] or None,
                                spec.get("authority") or spec.get("source"), f'memberships("{name}")'))
    db.executemany("INSERT INTO product_members VALUES (?,?,?,?,?)", members)
    report.rows["product_members"] = len(members)

    # Every store of the home is claimed by something that describes it; what is not is listed, a visible defect.
    from .semantics.intake_declarations import declared_sources

    sources = declared_sources()
    claimed |= {f"registries/{name}" for name in sources}
    # A family of intake sources (sisagua_*) keeps its shared documents under the family's name.
    claimed |= {f"registries/{name.split('_', 1)[0]}" for name in sources if "_" in name}
    claimed |= {"lake/fields", "lake/links", "lake/sidra", "lake/cubes", "registries/sidra"}
    # A context field built from a source's raw files describes them (BR-DWGD, INMET, CNES under registries/<source>).
    claimed |= {f"registries/{src}" for (src,) in db.execute("SELECT DISTINCT source FROM fields WHERE source IS NOT NULL")}
    claimed = {c.lower() for c in claimed}  # a folder's case varies (registries/CNES, lake/sngpc)
    unclaimed = []
    for top, folder in (("registries", cfg.registries_dir), ("lake", cfg.lake_dir)):
        for path in sorted(folder.iterdir()) if folder.is_dir() else ():
            rel = f"{top}/{path.name}"
            if path.name.startswith("."):
                continue  # the home's own working folders (.staging)
            if top == "lake" and path.is_dir() and any(
                    f.is_dir() and f.name.rpartition("_")[2].isalnum() and len(f.name.rpartition("_")[2]) == 10
                    for f in path.iterdir()):
                continue  # a system folder of record datasets, described by the ontology
            low = rel.lower()
            if any(c == low or c.startswith(low + "/") or low.startswith(c + "/") for c in claimed):
                continue
            size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.is_dir() else path.stat().st_size
            unclaimed.append((rel, size))
    db.executemany("INSERT INTO unclaimed_stores VALUES (?,?)", unclaimed)
    report.rows["unclaimed_stores"] = len(unclaimed)


def _write_fields(db: sqlite3.Connection, cfg: Settings, report: CompendiumReport) -> None:
    from .fields import cnes_cube, cube_of, declared_fields, load_field

    built = cfg.lake_dir / "fields"
    rows = []
    held = _held_periods(cfg)
    for name, spec in sorted(declared_fields().items()):
        held_dir = built / name
        cnes = cnes_cube(name, spec)
        if cnes is not None:
            # A field read from records (a cube over a dataset's files at one month of each year) is held for the years
            # every file it and its support read is here, whether in the lake or downloaded (`_held_periods`); the map
            # had looked only at lake/fields and said "none held" of twelve years of CNES registers
            support = str(cnes["support"]).split(":", 1)[1].split("/", 1)[0]
            years = sorted(held(str(cnes["dataset"]), int(cnes["month"])) & held(support, int(cnes["month"])))
        elif cube_of(spec) is not None:
            # A SIDRA or series field is its cube: what is held is what the fact store answers (ADR-0217).
            try:
                years = sorted(set(load_field(name, settings=cfg).column("year").to_pylist()))
            except (LookupError, FileNotFoundError, KeyError, ValueError):
                years = []
        else:
            years = sorted(
                int(p.name.split("=", 1)[1]) for p in held_dir.glob("year=*") if p.name.split("=", 1)[1].isdigit()
            ) if held_dir.is_dir() else []
        source = str(spec.get("source") or ("series" if spec.get("series") else "sidra" if spec.get("table") else ""))
        origin = spec.get("intake") or spec.get("table") or spec.get("measure") or spec.get("series")
        rows.append((
            name, spec.get("label"), str(spec.get("what") or "").strip() or None, spec.get("unit"), source or None,
            None if origin is None else str(origin), spec.get("over"),
            json.dumps(spec["by"]) if spec.get("by") else None,
            None if spec.get("years") is None else str(spec["years"]),
            json.dumps(years), json.dumps(spec["verified"], default=str) if spec.get("verified") else None,
        ))
    db.executemany("INSERT INTO fields VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    report.rows["fields"] = len(rows)


def _held_periods(cfg: Settings) -> Any:
    """``held(dataset, month) -> {years}``: the years whose every publication of that month is on this machine,
    downloaded (its bytes in the blob store) or built (a lake partition names it among its sources). One rule for any
    dataset, by month or by year, built or only downloaded, read from the catalog in one pass per dataset: asking
    `plan()` once per dataset and year took the map from 32 s to 6.5 min (2026-11-21). A publication is a logical file:
    the copies of one file in two trees are one publication, held when any copy is."""
    import json
    from functools import cache

    from .retrieve import parse_dataset

    def present(con: sqlite3.Connection) -> set[str]:
        have = {str(r[0]) for r in con.execute("SELECT DISTINCT f.source_path, f.sha256 FROM fetches f").fetchall()
                if r[1] and (cfg.blobs_dir / "sha256" / str(r[1])[:2] / str(r[1])).is_file()}
        for (sources,) in con.execute("SELECT source_paths FROM lake_partitions").fetchall():
            have.update(json.loads(sources or "[]"))
        return have

    con = sqlite3.connect(f"file:{cfg.catalog_path.as_posix()}?mode=ro", uri=True)
    try:
        on_machine = present(con)
    finally:
        con.close()

    @cache
    def held(dataset: str, month: int) -> frozenset[int]:
        system, series = parse_dataset(dataset.replace("-", ".", 1))
        con = sqlite3.connect(f"file:{cfg.catalog_path.as_posix()}?mode=ro", uri=True)
        try:
            rows = con.execute(
                "SELECT ff.year, COALESCE(ff.logical_id, ff.path), ff.path FROM file_facts ff JOIN files f ON f.path = ff.path "
                "WHERE ff.system = ? AND ff.series_prefix = ? AND ff.role = 'data' AND f.gone_at IS NULL "
                "AND CAST(substr(CAST(ff.normalized_date AS TEXT), 5, 2) AS INTEGER) = ?",
                (system, series or system, month)).fetchall()
        finally:
            con.close()
        by_year: dict[int, dict[str, bool]] = {}
        for year, publication, path in rows:
            if year is None:
                continue
            slot = by_year.setdefault(int(year), {})
            slot[str(publication)] = slot.get(str(publication), False) or str(path) in on_machine
        return frozenset(y for y, pubs in by_year.items() if pubs and all(pubs.values()))

    return held


def _write_roles(db: sqlite3.Connection, report: CompendiumReport) -> None:
    from .semantics.column_roles import roles
    from .semantics.event_types import event_types

    role_rows, event_rows = [], []
    for path in sorted((curation_root() / "roles").glob("*.yml")):
        name = path.stem
        try:
            declared = roles(name)
        except Exception:  # noqa: BLE001 - a role file for a dataset this install does not resolve
            continue
        for r in declared:
            role_rows.append((
                name, r.get("column"), r.get("role"), r.get("entity"), r.get("property"), r.get("kind"),
                r.get("model"), r.get("first_year"), r.get("last_year"),
            ))
        try:
            events = event_types(name)
        except Exception:  # noqa: BLE001 - roles without event types
            events = []
        for e in events:
            event_rows.append((name, e.get("name"), e.get("kind"), e.get("grain"),
                               json.dumps(e.get("classifiers") or [], default=str)))
    db.executemany("INSERT OR REPLACE INTO roles VALUES (?,?,?,?,?,?,?,?,?)", role_rows)
    db.executemany("INSERT OR REPLACE INTO events VALUES (?,?,?,?,?)", event_rows)
    report.rows["roles"] = len(role_rows)
    report.rows["events"] = len(event_rows)


def _write_links(db: sqlite3.Connection, cfg: Settings, report: CompendiumReport) -> None:
    from .linkage.engine import load_links

    rows = []
    for name, spec in sorted(load_links().items()):
        held_dir = cfg.lake_dir / "links" / name
        runs = sum(1 for _ in held_dir.rglob("*.parquet")) if held_dir.is_dir() else 0
        rows.append((name, (spec.description or "").strip() or None, spec.left.dataset, spec.right.dataset,
                     1 if spec.same_event else 0, runs))
    db.executemany("INSERT INTO links VALUES (?,?,?,?,?,?)", rows)
    report.rows["links"] = len(rows)


def _write_aggregates(db: sqlite3.Connection, cfg: Settings, report: CompendiumReport) -> None:
    from .capabilities import catalogue

    rows = [(a["id"], a.get("dataset"), a.get("label"), 1 if a.get("built") else 0) for a in catalogue(settings=cfg)]
    db.executemany("INSERT INTO aggregates VALUES (?,?,?,?)", rows)
    report.rows["aggregates"] = len(rows)


def _write_sidra(db: sqlite3.Connection, cfg: Settings, report: CompendiumReport) -> None:
    path = cfg.registry_dir("sidra", "registry.sqlite")
    if not path.is_file():
        report.rows["sidra_tables"] = 0
        return
    src = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        rows = src.execute(
            "SELECT t.id, t.name, t.research, t.subject, t.frequency, t.first_period, t.last_period, t.levels,"
            " t.n_variables, c.grp FROM tab t LEFT JOIN compendium c ON c.tab = t.id"
        ).fetchall()
    finally:
        src.close()
    db.executemany("INSERT INTO sidra_tables VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
    report.rows["sidra_tables"] = len(rows)


def _write_operations(db: sqlite3.Connection, report: CompendiumReport) -> None:
    """The public functions and types (``__init__``'s exports) and every command, each with its first paragraph of
    help: what the package can do, read from the code so it cannot drift from it."""
    import inspect

    import typer

    import pegasus_data

    from .cli import app

    rows = []
    for name in sorted(pegasus_data._EXPORTS):  # noqa: SLF001 - the export table is the public surface
        obj = getattr(pegasus_data, name)
        kind = "type" if inspect.isclass(obj) else "function"
        doc = (inspect.getdoc(obj) or "").strip()
        try:
            usage = f"{name}{inspect.signature(obj)}" if kind == "function" else name
        except (TypeError, ValueError):
            usage = name
        rows.append((name, kind, str(getattr(obj, "__module__", "")).rsplit(".", 1)[-1].lstrip("_"),
                     doc.split("\n\n", 1)[0].replace("\n", " ") or None, usage))

    def walk(group: Any, prefix: str) -> None:
        for cname, cmd in sorted(group.commands.items()):
            if getattr(cmd, "hidden", False):
                continue
            full = f"{prefix} {cname}"
            if hasattr(cmd, "commands"):
                walk(cmd, full)
                continue
            text = (cmd.help or "").strip()
            rows.append((full, "command", getattr(cmd, "rich_help_panel", None) or prefix.split()[-1],
                         text.split("\n\n", 1)[0].replace("\n", " ") or None, full))

    walk(typer.main.get_command(app), "pegasus-data")
    db.executemany("INSERT OR REPLACE INTO operations VALUES (?,?,?,?,?)", rows)
    report.rows["operations"] = len(rows)


def _write_entries(db: sqlite3.Connection, report: CompendiumReport) -> None:
    """One searchable row per thing, with the call that gets it (``search()`` reads this table)."""
    from .textenc import fold

    out: list[tuple[Any, ...]] = []

    def add(kind: str, system: Any, name: Any, title: Any, prose: Any, how: str) -> None:
        name, title, prose = str(name or ""), str(title or ""), str(prose or "")
        out.append((kind, system, name, title or None, prose or None, how,
                    fold(f"{name} {title}"), fold(f"{name} {title} {prose}")))

    for r in db.execute("SELECT code, system, official_name, translated_name, what_it_is, what_one_row_is,"
                        " rows_held, year_min, year_max FROM datasets"):
        span = f"{r[7]}-{r[8]} on the server" if r[7] else "no files on the server"
        held = f", {r[6]:,} rows held" if r[6] else ", none held"
        add("dataset", r[1], r[0], " — ".join(x for x in (r[2], r[3]) if x),
            " ".join(x for x in (r[4], r[5]) if x) + f" [{span}{held}]",
            f'query("{r[0]}", period=..., geography=...)')
    for r in db.execute(
        "SELECT v.system, v.name, v.official_name, v.translated_name, v.description,"
        " GROUP_CONCAT(dv.dataset, ', ') FROM variables v"
        " JOIN dataset_variables dv ON dv.system = v.system AND dv.name = v.name GROUP BY v.system, v.name"
    ):
        first = str(r[5] or "").split(", ")[0]
        add("variable", r[0], r[1], " — ".join(x for x in (r[2], r[3]) if x),
            f"{r[4] or ''} [in {r[5]}]", f'query("{first}", select=["{r[1]}"])')
    for r in db.execute("SELECT id, label, kind, source, what, grain, period, call FROM products"):
        add("product", r[2], r[0], r[1], f"{r[4] or ''} [{r[3] or ''}; {r[5] or ''}; {r[6] or ''}]", str(r[7] or ""))
    for r in db.execute("SELECT product, name, what, detail, call FROM product_members"):
        add("product", r[0], r[1], r[3], r[2], str(r[4]))
    for r in db.execute("SELECT name, label, what, unit, source, years FROM fields"):
        add("field", r[4], r[0], r[1], f"{r[2] or ''} [{r[3] or ''}; {r[5] or ''}]", f'load_field("{r[0]}")')
    for r in db.execute("SELECT role, GROUP_CONCAT(dataset || '.' || column_name, ', ') FROM roles GROUP BY role"):
        first = str(r[1] or "").split(".")[0]
        add("role", None, r[0], str(r[0]).replace(".", " ").replace("_", " "), f"[{r[1]}]", f'roles("{first}")')
    for r in db.execute("SELECT dataset, name, kind, grain FROM events"):
        add("event", None, f"{r[0]}:{r[1]}", r[2], r[3], f'count_events("{r[0]}", ...)')
    for r in db.execute("SELECT name, description, left_dataset, right_dataset, runs_held FROM links"):
        add("link", None, r[0], f"{r[2]} -> {r[3]}", f"{r[1] or ''} [{r[4]} runs held]", f"pegasus-data link {r[0]}")
    for r in db.execute("SELECT id, dataset, label, built FROM aggregates"):
        add("aggregate", None, r[0], r[2], f"[{r[1]}; {'built' if r[3] else 'not built'}]", f'aggregate("{r[0]}")')
    for r in db.execute("SELECT name, kind, area, summary, usage FROM operations"):
        add("operation", r[2], r[0], r[1], r[3], str(r[4]))
    for r in db.execute("SELECT id, name, research, subject, first_period, last_period, levels FROM sidra_tables"):
        add("sidra", "IBGE", r[0], r[1], f"{r[2] or ''} {r[3] or ''} [{r[4]}-{r[5]}; {r[6]}]",
            f"pegasus-data sidra show {r[0]}")
    db.executemany("INSERT INTO entries VALUES (?,?,?,?,?,?,?,?)", out)
    report.rows["entries"] = len(out)


def systems_scoped(wanted: set[str], onto: Ontology, system: str) -> bool:
    """True when scoping excluded this system entirely."""
    return not any(onto.datasets[c].system == system for c in wanted)


def _described(store: _Store) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in store.query(
        "SELECT system, field_name, official_name, translated_name, description,"
        " code_system, codelist, source, source_ref, reasoning FROM variable_docs"
    ):
        out[(str(row["system"]), str(row["field_name"]).upper())] = dict(row)
    for row in store.query(
        "SELECT system, field_name, description, source FROM field_documentation"
        " WHERE description IS NOT NULL AND TRIM(description) <> ''"
        " AND description NOT LIKE 'A column DATASUS tabulates%'"
        " AND description NOT LIKE 'A quantity DATASUS tabulates%'"
    ):
        out.setdefault((str(row["system"]), str(row["field_name"]).upper()), dict(row))
    return out


def _field_meta(store: _Store) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in store.query(
        "SELECT s.system AS system, h.field_name AS f, MAX(h.type_code) AS t,"
        " MAX(h.width) AS w FROM schema_header_facts h"
        " JOIN strata s ON s.schema_signature = h.schema_signature"
        " WHERE s.system IS NOT NULL GROUP BY 1, 2"
    ):
        out[(str(row["system"]), str(row["f"]))] = {"type": row["t"], "width": row["w"]}
    return out


def _axis_columns(axes) -> tuple:
    """Flatten :class:`DatasetAxes` into the four ``datasets`` columns.

    The fractions are kept alongside the list because "93% of files carry a uf"
    is a different warning from "no file does" — the first silently drops the
    remaining 7%, the second returns nothing at all.
    """
    if axes is None:
        return (None, None, None, None)
    frac = axes.fractions()
    return (
        json.dumps(axes.names),
        frac.get("uf"),
        frac.get("year"),
        frac.get("month"),
    )


def _dataset_docs(store: _Store, onto: Ontology) -> dict[str, dict[str, Any]]:
    """``dataset_docs`` keyed by ONTOLOGY code, not by whatever the row says.

    Those rows predate the ontology and identify themselves three ways —
    ``dataset_id`` ``SIHSUS_RD``, or ``system`` SIHSUS with ``series`` RD. The
    ontology code is ``SIH.RD``, because SIH is what the Ministry calls the
    system and SIHSUS is only what the crawler files it under. Matching on the
    raw strings made the most-used dataset on the tree report itself as
    undocumented, which is exactly the kind of quiet mismatch the ontology
    exists to stop; so every key is resolved through it.
    """
    out: dict[str, dict[str, Any]] = {}
    for row in store.query(
        "SELECT dataset_id, system, series, what_one_row_is, unit_of_analysis,"
        " known_biases, gotchas FROM dataset_docs"
    ):
        body = dict(row)
        candidates = [str(row["dataset_id"] or "")]
        if row["system"] and row["series"]:
            candidates.append(f"{row['system']}.{row['series']}")
        for candidate in candidates:
            found = onto.resolve(candidate.replace("_", "."))
            if found and found[0] == "dataset":
                out.setdefault(found[1].code, body)
                break
        else:
            # Keep it reachable even when nothing resolves, rather than dropping it.
            out.setdefault(str(row["dataset_id"] or "").upper(), body)
    return out


def _generations(
    store: _Store, onto: Ontology, wanted: set[str], binding: _Binding
) -> list[tuple[Any, ...]]:
    rows: list[tuple[Any, ...]] = []
    fam = store.query(
        "SELECT system, series, schema_signature, field_count, time_min, time_max, file_count"
        " FROM families"
    )
    per: dict[str, dict[str, dict[str, Any]]] = {}
    for row in fam:
        code = onto.bind(str(row["system"]), str(row["series"])).dataset
        if not code or code not in wanted:
            continue
        sig = str(row["schema_signature"])
        slot = per.setdefault(code, {}).setdefault(
            sig,
            {"fields": row["field_count"], "files": 0, "min": None, "max": None},
        )
        slot["files"] += int(row["file_count"] or 0)
        for key, op in (("min", min), ("max", max)):
            val = row["time_min"] if key == "min" else row["time_max"]
            if val is None:
                continue
            slot[key] = val if slot[key] is None else op(slot[key], val)

    all_sigs = {s for sigs in per.values() for s in sigs}
    fields: dict[str, set[str]] = {}
    if all_sigs:
        marks = ",".join("?" for _ in all_sigs)
        for row in store.query(
            f"SELECT schema_signature, field_name FROM schema_presence"
            f" WHERE schema_signature IN ({marks})",
            tuple(all_sigs),
        ):
            fields.setdefault(str(row["schema_signature"]), set()).add(str(row["field_name"]))

    for code, sigs in per.items():
        order = sorted(
            sigs.items(), key=lambda kv: (kv[1]["min"] is None, kv[1]["min"], kv[0])
        )
        previous: set[str] | None = None
        for sig, slot in order:
            here = fields.get(sig, set())
            added = sorted(here - previous) if previous is not None else []
            dropped = sorted(previous - here) if previous is not None else []
            rows.append(
                (
                    code, sig, slot["fields"], slot["min"], slot["max"], slot["files"],
                    json.dumps(added), json.dumps(dropped),
                )
            )
            previous = here
    return rows


def _write_codes(
    db: sqlite3.Connection,
    store: _Store,
    wanted: set[str],
    binding: _Binding,
    report: CompendiumReport,
    mode: str,
    max_codes: int,
) -> None:
    keep: set[str] | None = None
    if mode in {"bound", "internal"}:
        included = {
            (str(r[0]), str(r[1]))
            for r in db.execute("SELECT system, name FROM variables")
        }
        keep = {
            str(row["codelist"])
            for row in store.query("SELECT system, field_name, codelist FROM field_codelists")
            if (str(row["system"]), str(row["field_name"])) in included
        }
        if mode == "internal":
            # Drop the big externally-maintained classifications. Measured on
            # SIH: its 324 bound codelists carry 4.6M codes and weigh 425 MB,
            # and the twelve largest — MUNICBR at 1.2M rows, the health-region
            # tables, CID-10 — are 62% of that. Those are published and
            # maintained elsewhere and a researcher already has them; what they
            # cannot get anywhere else is DATASUS's own small enumerations,
            # SIM_NAO and ESP_LEIT and the rest. Sized rather than named,
            # because a rule that depends on a curated `code_system` would go
            # wrong exactly where curation is thin.
            sizes = {
                str(row["g"]): int(row["n"] or 0)
                for row in store.query(
                    "SELECT value_group AS g, COUNT(*) AS n FROM dictionary"
                    " WHERE value_group IS NOT NULL GROUP BY value_group"
                )
            }
            big = {name for name in keep if sizes.get(name, 0) > max_codes}
            keep -= big
            report.options["codes_excluded_as_external"] = sorted(big)[:20]
            report.options["codes_excluded_count"] = len(big)
        if not keep:
            report.rows["codes"] = 0
            return

    # STREAM. ``dictionary`` holds 19.9M rows, so materialising the result into a
    # Python list exhausts memory long before it finishes — the first version of
    # this did exactly that and had to be killed. Filtering is done row by row
    # against a set rather than with an ``IN`` clause of several thousand
    # literals, which SQLite plans badly and which has a hard parameter limit.
    cursor = store.conn.execute(
        "SELECT value_group, system, value_raw, value_label, valid_from, valid_to"
        " FROM dictionary WHERE value_group IS NOT NULL"
    )
    written = 0
    batch: list[tuple[Any, ...]] = []
    insert = (
        "INSERT INTO codes (codelist, system, code, label, valid_from, valid_to)"
        " VALUES (?,?,?,?,?,?)"
    )
    while True:
        chunk = cursor.fetchmany(50_000)
        if not chunk:
            break
        for group, system, raw, label, valid_from, valid_to in chunk:
            if keep is not None and str(group) not in keep:
                continue
            batch.append((str(group), system, raw, label, valid_from, valid_to))
        if batch:
            db.executemany(insert, batch)
            written += len(batch)
            batch = []
    if batch:
        db.executemany(insert, batch)
        written += len(batch)

    db.execute(
        "INSERT INTO codelists (id, system, codes)"
        " SELECT codelist, MIN(system), COUNT(*) FROM codes GROUP BY codelist"
    )
    report.rows["codes"] = written
    report.rows["codelists"] = db.execute("SELECT COUNT(*) FROM codelists").fetchone()[0]


def _write_values(
    db: sqlite3.Connection, store: _Store, binding: _Binding, report: CompendiumReport
) -> None:
    rows = []
    for row in store.query(
        "SELECT fa.system AS system, fa.series AS series, vf.field_name AS f,"
        " vf.value AS v, SUM(vf.count) AS n FROM value_frequencies vf"
        " JOIN families fa ON fa.family_id = vf.family_id GROUP BY 1, 2, 3, 4"
    ):
        code = binding.dataset_of_pair.get((str(row["system"]), str(row["series"])))
        if code:
            rows.append((code, str(row["f"]), str(row["v"]), int(row["n"] or 0)))
    db.executemany(
        "INSERT INTO value_frequencies (dataset, name, value, n) VALUES (?,?,?,?)", rows
    )
    report.rows["value_frequencies"] = len(rows)


def _write_files(
    db: sqlite3.Connection, store: _Store, binding: _Binding, report: CompendiumReport
) -> None:
    rows = []
    for row in store.query(
        "SELECT ff.path AS path, ff.system AS system, ff.series_prefix AS series,"
        " ff.geo_code AS uf, ff.year AS year, f.size AS size"
        " FROM file_facts ff LEFT JOIN files f ON f.path = ff.path"
        " WHERE ff.role = 'data'"
    ):
        code = binding.dataset_of_pair.get((str(row["system"]), str(row["series"] or "")))
        if code:
            rows.append((str(row["path"]), code, row["uf"], row["year"], row["size"]))
    db.executemany(
        "INSERT OR REPLACE INTO files (path, dataset, uf, year, bytes) VALUES (?,?,?,?,?)",
        rows,
    )
    report.rows["files"] = len(rows)


def _write_meta(db: sqlite3.Connection, store: _Store, report: CompendiumReport) -> None:
    from datetime import datetime

    crawled = store.query("SELECT MAX(last_seen) AS t FROM files")
    meta = {
        "generator": "pegasus_data.compendium",
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "crawl_last_seen": (crawled[0]["t"] if crawled else None),
        "options": json.dumps(report.options),
        "rows": json.dumps(report.rows),
        "note": (
            "A map of what DATASUS publishes, down to the variable. "
            "Code meanings and value frequencies are optional and may be absent; "
            "see the options key for what this file was built with."
        ),
    }
    db.executemany(
        "INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)",
        [(k, None if v is None else str(v)) for k, v in meta.items()],
    )
