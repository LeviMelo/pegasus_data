"""A portable semantic bundle: translation that does not need DATASUS.

Everything this module knows how to *say* about a value — that `SEXO=3` is
Feminino, that `DIAG_PRINC` draws on CID-10, that `IDADE` is meaningless without
`COD_IDADE` — is derived from files on an FTP server that is frequently slow,
occasionally unreachable, and not under anyone's control here. A module that can
only translate while DATASUS is up is a module that cannot be relied on, and the
data it describes does not change when the server does: a 2019 admission is
coded the way it was coded whether or not ftp.datasus.gov.br answers today.

So the semantic layer is packable. A bundle is a single file holding the
codelists, the field bindings, the curated meanings and the schema catalogue —
enough to label, describe and document without a network at all. Fetching new
*data* still needs DATASUS; understanding it does not.

**What is packed and what is not.** Only codelists actually bound to a field:
19.5% of the 10,748 codelists carry 48% of the dictionary's rows, and the rest
are TabNet tabulation axes nothing decodes against. Rows are de-duplicated on
``(system, codelist, code, label)``, because the same municipality name repeats
across every validity window — SIASUS's MUNICBR alone is 865,801 rows for about
5,570 municipalities. A code whose *wording* changed still keeps both readings,
each with the span of vintages it covers; only exact repeats collapse.

**What a bundle is not.** It is not the lake and not a substitute for the
catalog. It carries no file inventory, no profiles, no row counts and no data —
only the means to interpret data someone already has.

**Why the table list is introspected rather than written out.** A bundle that
declares its own column layout drifts the first time the catalog schema gains a
column, and drifts silently: the copy still succeeds, positionally, into the
wrong slots. Reading the live schema instead means a bundle is correct by
construction or fails loudly, and never quietly mislabels.
"""

from __future__ import annotations

import json
import sqlite3
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from .catalog.store import Catalog, utcnow

#: Bumped when the packed shape changes in a way an older reader cannot handle.
BUNDLE_FORMAT = 1

#: Tables whose rows belong to one system, and which a ``--system`` pack filters.
SYSTEM_SCOPED: tuple[str, ...] = (
    "field_codelists",
    "variable_docs",
    "dataset_docs",
    "field_documentation",
    "prefix_systems",
)

#: Tables keyed on a schema signature rather than a system. A signature is shared
#: across systems by construction, so filtering these by system would drop the
#: very shape the bundle exists to explain.
SHAPE_SCOPED: tuple[str, ...] = (
    "dictionary_rules",
    "schemas",
    "schema_presence",
    "schema_header_facts",
)

#: Everything a bundle carries. ``dictionary`` is handled separately because it
#: is the only table that is filtered *and* de-duplicated.
PACKED_TABLES: tuple[str, ...] = ("dictionary", *SYSTEM_SCOPED, *SHAPE_SCOPED)

MANIFEST = "manifest.json"
PAYLOAD = "semantics.sqlite"

#: Rows moved per INSERT batch when restoring. Large enough that the per-batch
#: overhead disappears, small enough that the full 7.5-million-row dictionary
#: never exists as Python objects all at once.
RESTORE_BATCH = 50_000


class BundleError(RuntimeError):
    """A bundle cannot be read, or was produced by an incompatible version."""


@dataclass(slots=True)
class BundleManifest:
    format: int
    created_at: str
    systems: list[str]
    counts: dict[str, int]
    source_note: str = ""
    dictionary_deduplicated: int = 0
    dictionary_original: int = 0
    bound_only: bool = True
    #: Codelists left out because they exceeded ``max_codelist_rows``. Named,
    #: not merely counted: a reader who finds MUNICBR unlabelled needs to know
    #: it was omitted rather than unknown.
    codelists_omitted: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "format": self.format,
            "created_at": self.created_at,
            "systems": self.systems,
            "counts": self.counts,
            "source_note": self.source_note,
            "dictionary_deduplicated": self.dictionary_deduplicated,
            "dictionary_original": self.dictionary_original,
            "bound_only": self.bound_only,
            "codelists_omitted": self.codelists_omitted,
        }


@dataclass(slots=True)
class BundleReport:
    path: Path
    manifest: BundleManifest
    bytes_written: int = 0
    tables: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "megabytes": round(self.bytes_written / 2**20, 2),
            "systems": self.manifest.systems or ["<all>"],
            "tables": self.tables,
            "dictionary_rows": self.manifest.dictionary_deduplicated,
            "dictionary_rows_before_dedup": self.manifest.dictionary_original,
            "codelists_omitted": self.manifest.codelists_omitted,
        }


def _columns(catalog: Catalog, table: str) -> list[str]:
    return [str(r["name"]) for r in catalog.query(f"PRAGMA table_info({table})")]


def _system_clause(
    systems: Sequence[str] | None, column: str = "system"
) -> tuple[str, list[object]]:
    if not systems:
        return "", []
    slots = ",".join("?" * len(systems))
    return f" AND {column} IN ({slots})", [s.upper() for s in systems]


def _create_like(source_columns: Sequence[str], table: str) -> str:
    """A staging table shaped like the catalog's, with no constraints.

    Deliberately untyped and unconstrained: the bundle is a transport format,
    the catalog it is restored into holds the real keys, and a PRIMARY KEY here
    would reject rows the source catalog legitimately holds.
    """
    body = ", ".join(f'"{c}"' for c in source_columns)
    return f"CREATE TABLE {table} ({body})"


def pack(
    catalog: Catalog,
    out_path: str | Path,
    *,
    systems: Sequence[str] | None = None,
    bound_only: bool = True,
    max_codelist_rows: int | None = None,
    note: str = "",
) -> BundleReport:
    """Write a portable semantic bundle.

    ``bound_only`` keeps the bundle to codelists some field actually decodes
    against. Turning it off packs every TabNet tabulation axis as well, roughly
    doubling the size to carry tables nothing joins to.

    ``max_codelist_rows`` drops the very large geographic roll-ups — MUNICBR and
    friends, which are thousands of municipalities repeated per system and carry
    most of the bytes. It exists for the small bundle that ships *inside* the
    package, where the codes a reader meets constantly (SEXO, RACACOR, the
    outcome flags) matter far more than a complete municipality list they can
    rebuild from CADMUN. Bundles built this way say so in their manifest, so a
    missing municipality name reads as "not packed" rather than "unknown".
    """
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = target.with_suffix(".staging.sqlite")
    staging.unlink(missing_ok=True)

    counts: dict[str, int] = {}
    conn = sqlite3.connect(staging)
    try:
        conn.execute("PRAGMA journal_mode = OFF")
        conn.execute("PRAGMA synchronous = OFF")

        original, packed, dropped = _pack_dictionary(
            catalog,
            conn,
            systems=systems,
            bound_only=bound_only,
            max_codelist_rows=max_codelist_rows,
        )
        counts["dictionary"] = packed

        for table in (*SYSTEM_SCOPED, *SHAPE_SCOPED):
            columns = _columns(catalog, table)
            if not columns:
                continue
            conn.execute(_create_like(columns, table))
            where, params = (
                _system_clause(systems) if table in SYSTEM_SCOPED else ("", [])
            )
            names = ", ".join(f'"{c}"' for c in columns)
            rows = [
                tuple(r[c] for c in columns)
                for r in catalog.query(
                    f"SELECT {names} FROM {table} WHERE 1=1{where}", params
                )
            ]
            if rows:
                slots = ",".join("?" * len(columns))
                conn.executemany(f"INSERT INTO {table} VALUES ({slots})", rows)
            counts[table] = len(rows)
        conn.commit()
    finally:
        conn.close()

    manifest = BundleManifest(
        format=BUNDLE_FORMAT,
        created_at=utcnow(),
        systems=[s.upper() for s in (systems or [])],
        counts=counts,
        source_note=note or "packed from a pegasus_data catalog",
        dictionary_deduplicated=packed,
        dictionary_original=original,
        bound_only=bound_only,
        codelists_omitted=dropped,
    )
    with zipfile.ZipFile(
        target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9
    ) as archive:
        archive.writestr(
            MANIFEST, json.dumps(manifest.as_dict(), indent=2, ensure_ascii=False)
        )
        archive.write(staging, PAYLOAD)
    staging.unlink(missing_ok=True)

    return BundleReport(
        path=target,
        manifest=manifest,
        bytes_written=target.stat().st_size,
        tables=counts,
    )


def _pack_dictionary(
    catalog: Catalog,
    conn: sqlite3.Connection,
    *,
    systems: Sequence[str] | None,
    bound_only: bool,
    max_codelist_rows: int | None = None,
) -> tuple[int, int, list[str]]:
    """Copy the dictionary, filtered to bound codelists and de-duplicated.

    Returns ``(rows_considered, rows_packed, codelists_omitted)`` so the manifest
    can state what the de-duplication actually bought rather than asserting it.
    """
    columns = _columns(catalog, "dictionary")
    conn.execute(_create_like(columns, "dictionary"))

    where, params = _system_clause(systems, "d.system")
    join = (
        " JOIN (SELECT DISTINCT system, codelist FROM field_codelists) fc"
        "   ON fc.system = d.system AND fc.codelist = d.value_group"
        if bound_only
        else ""
    )
    original = int(
        catalog.scalar(
            f"SELECT COUNT(*) FROM dictionary d{join} WHERE 1=1{where}", params
        )
        or 0
    )

    omitted: list[str] = []
    if max_codelist_rows:
        # One grouped scan, not a size query per codelist. The dictionary is
        # 19.9M rows and asking it 10,748 times is the difference between
        # seconds and an afternoon.
        oversized = catalog.query(
            f"SELECT d.system, d.value_group, COUNT(*) AS n FROM dictionary d{join} "
            f"WHERE 1=1{where} GROUP BY d.system, d.value_group HAVING n > ?",
            [*params, int(max_codelist_rows)],
        )
        for row in oversized:
            omitted.append(f"{row['system']}.{row['value_group']}")
            where += " AND NOT (d.system = ? AND d.value_group = ?)"
            params = [*params, row["system"], row["value_group"]]

    # The identity of a *meaning* is the code and the words it maps to; the
    # window is an attribute of that meaning, not part of it. So group on the
    # identity and take the span across the rows that share it. A relabelled
    # code keeps both readings and both spans; an unchanged one collapses from
    # one row per vintage to one row.
    identity = ["system", "value_group", "field_name", "value_raw", "value_label"]
    identity = [c for c in identity if c in columns]
    aggregates = {"valid_from": "MIN", "valid_to": "MAX", "confidence": "MAX"}
    selected = []
    for column in columns:
        if column in identity:
            selected.append(f'd."{column}"')
        elif column in aggregates:
            selected.append(f'{aggregates[column]}(d."{column}") AS "{column}"')
        else:
            selected.append(f'MIN(d."{column}") AS "{column}"')
    group_by = ", ".join(f'd."{c}"' for c in identity)

    rows = catalog.query(
        f"SELECT {', '.join(selected)} FROM dictionary d{join} "
        f"WHERE 1=1{where} GROUP BY {group_by}",
        params,
    )
    payload = [tuple(r[c] for c in columns) for r in rows]
    if payload:
        slots = ",".join("?" * len(columns))
        conn.executemany(f"INSERT INTO dictionary VALUES ({slots})", payload)
    return original, len(payload), sorted(omitted)


def read_manifest(bundle_path: str | Path) -> BundleManifest:
    path = Path(bundle_path)
    try:
        archive = zipfile.ZipFile(path)
    except (OSError, zipfile.BadZipFile) as exc:
        raise BundleError(f"{path} is not a readable bundle: {exc}") from exc
    with archive:
        try:
            raw = json.loads(archive.read(MANIFEST).decode("utf-8"))
        except KeyError as exc:
            raise BundleError(
                f"{path} has no {MANIFEST}; not a pegasus_data bundle"
            ) from exc
    if int(raw.get("format", 0)) > BUNDLE_FORMAT:
        raise BundleError(
            f"bundle format {raw.get('format')} is newer than this build understands "
            f"({BUNDLE_FORMAT}); upgrade pegasus_data"
        )
    return BundleManifest(
        format=int(raw["format"]),
        created_at=str(raw.get("created_at", "")),
        systems=list(raw.get("systems") or []),
        counts=dict(raw.get("counts") or {}),
        source_note=str(raw.get("source_note", "")),
        dictionary_deduplicated=int(raw.get("dictionary_deduplicated", 0)),
        dictionary_original=int(raw.get("dictionary_original", 0)),
        bound_only=bool(raw.get("bound_only", True)),
        codelists_omitted=list(raw.get("codelists_omitted") or []),
    )


def unpack(
    catalog: Catalog, bundle_path: str | Path, *, replace: bool = False
) -> dict[str, object]:
    """Load a bundle into a catalog.

    Additive by default. A local catalog was built by reading the files
    themselves; a bundle is a copy of someone else's reading of them, so it
    fills gaps rather than overruling first-hand evidence. ``replace=True``
    clears the packed tables first, for the case where the bundle genuinely *is*
    the source of truth — a fresh machine with no crawl behind it.

    Columns are matched by name, and a column the local schema does not have is
    dropped rather than shifting everything after it into the wrong slot.
    """
    path = Path(bundle_path)
    manifest = read_manifest(path)
    staged = path.with_suffix(".unpacked.sqlite")
    with zipfile.ZipFile(path) as archive:
        staged.write_bytes(archive.read(PAYLOAD))

    restored: dict[str, int] = {}
    offered: dict[str, int] = {}
    skipped: dict[str, list[str]] = {}
    try:
        source = sqlite3.connect(f"file:{staged.as_posix()}?mode=ro", uri=True)
        try:
            for table in PACKED_TABLES:
                local = _columns(catalog, table)
                if not local:
                    continue
                try:
                    cursor = source.execute(f"SELECT * FROM {table}")
                except sqlite3.Error:
                    continue
                packed_columns = [d[0] for d in cursor.description]
                shared = [c for c in packed_columns if c in local]
                missing = [c for c in packed_columns if c not in local]
                if missing:
                    skipped[table] = missing
                if not shared:
                    continue
                keep = [packed_columns.index(c) for c in shared]
                if replace:
                    catalog.execute(f"DELETE FROM {table}")
                names = ", ".join(f'"{c}"' for c in shared)
                slots = ",".join("?" * len(shared))
                sql = f"INSERT OR IGNORE INTO {table} ({names}) VALUES ({slots})"
                # Streamed in batches rather than materialised. The full bundle's
                # dictionary is 7.5 million rows, and building that as one list of
                # Python tuples costs gigabytes before a single row is written —
                # and holding it in one transaction grew the write-ahead log past
                # 1.9 GB. Each batch commits.
                before = catalog.count(table)
                offered_here = 0
                while batch := cursor.fetchmany(RESTORE_BATCH):
                    offered_here += catalog.executemany(
                        sql, [tuple(row[i] for i in keep) for row in batch]
                    )
                # What landed, not what was offered. `INSERT OR IGNORE` drops a
                # row the local catalog already holds, and on an additive unpack
                # the difference is precisely what this machine already knew —
                # which is worth reporting rather than counting as new knowledge.
                restored[table] = catalog.count(table) - before
                offered[table] = offered_here
        finally:
            source.close()
    finally:
        staged.unlink(missing_ok=True)

    catalog.log_event(
        "bundle",
        "unpacked semantic bundle",
        detail=(
            f"{sum(restored.values())} rows from {path.name} "
            f"(packed {manifest.created_at})"
        ),
    )
    return {
        "bundle": str(path),
        "created_at": manifest.created_at,
        "systems": manifest.systems or ["<all>"],
        "restored": restored,
        "total_rows": sum(restored.values()),
        "already_known": sum(offered.values()) - sum(restored.values()),
        "unknown_columns": skipped,
        "replaced": replace,
    }
