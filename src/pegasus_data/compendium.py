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
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .catalog.store import Catalog as _Store
from .config import Settings, load_settings
from .ontology import Ontology

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
  split_by_month   REAL
);
CREATE INDEX ix_datasets_system ON datasets(system);

-- Can I answer my question with this? --------------------------------------
CREATE TABLE coverage (
  dataset TEXT REFERENCES datasets(code),
  year    INTEGER,
  uf      TEXT,
  files   INTEGER,
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
    out: str | Path,
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
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)

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

    db = sqlite3.connect(target)
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
        _write_core(db, store, onto, wanted, binding, report, descriptions)
        if codes_mode != "none":
            _write_codes(db, store, wanted, binding, report, codes_mode, max_codes)
        if values:
            _write_values(db, store, binding, report)
        if files:
            _write_files(db, store, binding, report)
        _write_meta(db, store, report)
        db.commit()
        db.executescript("ANALYZE; VACUUM;")
    finally:
        db.close()
        store.close()

    report.megabytes = round(target.stat().st_size / 2**20, 2)
    return report


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
    from .availability import _read as _read_availability

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
    report: CompendiumReport,
    descriptions: bool,
) -> None:
    # --- coverage, and the per-dataset totals derived from it --------------
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
    db.executemany(
        "INSERT INTO coverage (dataset, year, uf, files) VALUES (?,?,?,?)",
        [(d, y, u, n) for (d, y, u), n in sorted(cover.items())],
    )
    report.rows["coverage"] = len(cover)

    totals: dict[str, dict[str, Any]] = {}
    for (code, year, uf), n in cover.items():
        slot = totals.setdefault(code, {"files": 0, "ymin": None, "ymax": None, "ufs": set()})
        slot["files"] += n
        if year:
            slot["ymin"] = year if slot["ymin"] is None else min(slot["ymin"], year)
            slot["ymax"] = year if slot["ymax"] is None else max(slot["ymax"], year)
        if uf:
            slot["ufs"].add(uf)

    # --- variables, and which datasets carry them -------------------------
    described = _described(store)
    field_meta = _field_meta(store)
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
    #: (dataset, column) -> the system to attribute the column to. Variable docs
    #: are keyed by the crawled system, so the attribution has to be whichever
    #: one actually documents the column, with a deterministic fallback.
    col_system: dict[tuple[str, str], str] = {}
    for code in wanted:
        sigs = binding.signatures.get(code, set())
        if not sigs:
            continue
        marks = ",".join("?" for _ in sigs)
        cols = {
            str(r["field_name"])
            for r in store.query(
                f"SELECT DISTINCT field_name FROM schema_presence "
                f"WHERE schema_signature IN ({marks})",
                tuple(sigs),
            )
        }
        systems_for = sorted(binding.crawled_systems.get(code, set()))
        if not systems_for:
            systems_for = [onto.datasets[code].system]
        per_dataset_cols[code] = cols
        for name in cols:
            owner = next((s for s in systems_for if (s, name) in described), None)
            col_system[(code, name)] = owner or systems_for[0]

    seen_vars: set[tuple[str, str]] = {
        (col_system[(code, name)], name)
        for code, cols in per_dataset_cols.items()
        for name in cols
    }
    var_rows = []
    for system, name in sorted(seen_vars):
        doc = described.get((system, name), {})
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

    link_rows = [
        (code, col_system[(code, name)], name)
        for code, cols in per_dataset_cols.items()
        for name in sorted(cols)
    ]
    db.executemany(
        "INSERT OR REPLACE INTO dataset_variables (dataset, system, name) VALUES (?,?,?)",
        link_rows,
    )
    # Count what landed, not what was offered. Reporting the length of the input
    # list is how a row count survives being wrong: INSERT OR REPLACE collapses
    # primary-key collisions, and the report went on claiming the pre-collapse
    # number.
    report.rows["dataset_variables"] = db.execute(
        "SELECT COUNT(*) FROM dataset_variables"
    ).fetchone()[0]

    _write_field_validity(db, store, onto, wanted, report)
    _write_codelist_vintages(db, store, report)
    _write_join_keys(db, onto, wanted, report)

    # --- schema generations, with what each one changed -------------------
    gen_rows = _generations(store, onto, wanted, binding)
    db.executemany(
        "INSERT OR REPLACE INTO schema_generations (dataset, signature, field_count,"
        " year_min, year_max, files, added, dropped) VALUES (?,?,?,?,?,?,?,?)",
        gen_rows,
    )
    report.rows["schema_generations"] = len(gen_rows)
    gens_per: dict[str, int] = {}
    for row in gen_rows:
        gens_per[row[0]] = gens_per.get(row[0], 0) + 1

    # --- datasets ---------------------------------------------------------
    docs = _dataset_docs(store, onto)
    axes_by_code = onto.axes(store.conn)
    ds_rows = []
    for code in sorted(wanted):
        node = onto.datasets[code]
        t = totals.get(code, {})
        doc = docs.get(code, {})
        cols = per_dataset_cols.get(code, set())
        n_desc = sum(1 for name in cols if (col_system[(code, name)], name) in described)
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
            )
        )
    db.executemany(
        "INSERT INTO datasets (code, system, short_code, official_name, translated_name,"
        " what_it_is, what_one_row_is, unit_of_analysis, known_biases, gotchas, status,"
        " confidence, files, year_min, year_max, ufs, generations, columns_total,"
        " columns_described, split_by, split_by_uf, split_by_year, split_by_month)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        ds_rows,
    )
    report.rows["datasets"] = len(ds_rows)

    # --- systems ----------------------------------------------------------
    sys_rows = []
    for code, node in sorted(onto.systems.items()):
        mine = [r for r in ds_rows if r[1] == code]
        if not mine and systems_scoped(wanted, onto, code):
            continue
        years = [r[13] for r in mine if r[13]] + [r[14] for r in mine if r[14]]
        sys_rows.append(
            (
                code, node.official_name, node.translated_name, node.kind, node.status,
                node.authority, node.what_it_is, len(mine),
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


def systems_scoped(wanted: set[str], onto: Ontology, system: str) -> bool:
    """True when scoping excluded this system entirely."""
    return not any(onto.datasets[c].system == system for c in wanted)


def _described(store: _Store) -> dict[tuple[str, str], dict[str, Any]]:
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for row in store.query(
        "SELECT system, field_name, official_name, translated_name, description,"
        " code_system, codelist, source, source_ref, reasoning FROM variable_docs"
    ):
        out[(str(row["system"]), str(row["field_name"]))] = dict(row)
    for row in store.query(
        "SELECT system, field_name, description, source FROM field_documentation"
        " WHERE description IS NOT NULL AND TRIM(description) <> ''"
        " AND description NOT LIKE 'A column DATASUS tabulates%'"
        " AND description NOT LIKE 'A quantity DATASUS tabulates%'"
    ):
        out.setdefault((str(row["system"]), str(row["field_name"])), dict(row))
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
    from datetime import datetime, timezone

    crawled = store.query("SELECT MAX(last_seen) AS t FROM files")
    meta = {
        "generator": "pegasus_data.compendium",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
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
