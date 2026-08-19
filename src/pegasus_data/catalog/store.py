"""SQLite access for the catalog: migrations, upserts, append-only history.

The catalog is the module's memory. Every layer writes here before returning, so
that any command can be interrupted and resumed from whatever the catalog knows.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2


def utcnow() -> str:
    """ISO-8601 UTC timestamp, second precision, used for every catalog stamp."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _schema_sql() -> str:
    return resources.files("pegasus_data.catalog").joinpath("schema.sql").read_text(encoding="utf-8")


_CREATE_TABLE = re.compile(
    r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)\s*\((.*?)\n\);", re.S | re.I
)
#: Line-leading words that start a table constraint rather than a column.
_CONSTRAINT_WORDS = {"primary", "foreign", "unique", "check", "constraint"}


def _declared_columns(schema: str) -> dict[str, dict[str, str]]:
    """``table -> {column: type declaration}`` as the shipped schema declares it."""
    out: dict[str, dict[str, str]] = {}
    for table, body in _CREATE_TABLE.findall(schema):
        columns: dict[str, str] = {}
        for raw in body.splitlines():
            line = raw.split("--", 1)[0].strip().rstrip(",")
            if not line:
                continue
            parts = line.split()
            if not parts or parts[0].lower() in _CONSTRAINT_WORDS:
                continue
            name = parts[0].strip('"')
            if not name.isidentifier():
                continue
            columns[name] = " ".join(parts[1:]) or "TEXT"
        out[table] = columns
    return out


class CatalogSchemaError(RuntimeError):
    """The catalog on disk cannot be brought to the shipped schema.

    Raised rather than opened. The alternative — carrying on against a database
    whose shape does not match what the code expects — is the failure mode this
    module has already hit twice: ``CREATE TABLE IF NOT EXISTS`` silently kept an
    old table, and every query written against the new one failed far away from
    the cause. A mismatch that additive migration cannot close is not something
    to work around at runtime.
    """


def _structural_mismatches(conn: sqlite3.Connection, schema: str) -> list[str]:
    """Differences additive migration cannot fix, described for a human.

    Additive column migration handles the only change this schema has ever made:
    gaining a nullable column. Anything else — a changed primary key, a column
    whose declared type no longer matches, a table the shipped schema no longer
    declares the same way — needs a deliberate rebuild, and pretending otherwise
    is how a catalog quietly diverges from the code that reads it.
    """
    problems: list[str] = []
    declared = _declared_columns(schema)
    existing_tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    for table, columns in declared.items():
        if table not in existing_tables:
            continue
        actual = {r[1]: (r[2] or "").upper() for r in conn.execute(f"PRAGMA table_info({table})")}
        actual_pk = [
            r[1] for r in conn.execute(f"PRAGMA table_info({table})") if r[5]
        ]
        for name, decl in columns.items():
            if name not in actual:
                continue
            want = decl.split()[0].upper() if decl.split() else "TEXT"
            have = actual[name]
            if have and want and have != want:
                problems.append(
                    f"{table}.{name}: catalog has {have}, shipped schema declares {want}"
                )
        want_pk = [
            name
            for name, decl in columns.items()
            if "PRIMARY KEY" in decl.upper()
        ]
        if want_pk and actual_pk and sorted(want_pk) != sorted(actual_pk):
            problems.append(
                f"{table}: primary key is {actual_pk}, shipped schema declares {want_pk}"
            )
    return problems


def _missing_columns(
    conn: sqlite3.Connection, schema: str
) -> list[tuple[str, str, str]]:
    """Columns the schema declares that this database does not have yet."""
    existing_tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    missing: list[tuple[str, str, str]] = []
    for table, columns in _declared_columns(schema).items():
        if table not in existing_tables:
            continue
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
        for name, decl in columns.items():
            if name in have:
                continue
            # A column added to a populated table must be nullable and unkeyed;
            # SQLite refuses anything else, and so would the data.
            clean = decl.replace("PRIMARY KEY", "").replace("NOT NULL", "").strip()
            missing.append((table, name, clean or "TEXT"))
    return missing


class Catalog:
    """A connection to the catalog database.

    Thread-safe for the access pattern the pipeline uses: many worker threads
    calling short write methods. Writes are serialised behind one lock; reads go
    through the same connection, which SQLite handles fine at this concurrency.
    """

    def __init__(
        self, path: str | Path, *, read_only: bool = False, strict_schema: bool = True
    ) -> None:
        """``strict_schema=False`` opens a catalog ``migrate`` would refuse.

        Only the repair path wants this: ``rebuild_table`` has to open a database
        whose shape is exactly the reason opening it fails. Nothing on the normal
        path should pass it.
        """
        self.path = Path(path)
        self.read_only = read_only
        self.strict_schema = strict_schema
        if not read_only:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        if read_only:
            uri = f"file:{self.path.as_posix()}?mode=ro"
            self.conn = sqlite3.connect(uri, uri=True, check_same_thread=False, timeout=30)
        else:
            self.conn = sqlite3.connect(self.path, check_same_thread=False, timeout=60)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        if not read_only:
            self.conn.execute("PRAGMA journal_mode = WAL")
            self.conn.execute("PRAGMA synchronous = NORMAL")
            self.migrate()

    # ---------------------------------------------------------------- lifecycle

    def migrate(self) -> None:
        """Create anything missing, then add columns the schema has gained.

        ``CREATE TABLE IF NOT EXISTS`` creates a table and then never touches it
        again, so a catalog written by an older build keeps its old columns and
        every query against a new one fails. The catalog ships alongside the lake
        and is meant to be re-crawled into over years, so upgrading it in place is
        a requirement, not a convenience.

        Only additive changes are applied automatically — new nullable columns —
        which is what a schema that only ever gains fields needs. Anything
        destructive would need a real migration and is deliberately not done here.

        What is *not* left silent is the case additive migration cannot reach: a
        changed type, a changed primary key, a dropped column. Those are refused,
        loudly, with :class:`CatalogSchemaError`. Rebuilding the table instead —
        automatically, at open time, without being asked — is the more dangerous
        of the two options the reviewer offered: a rebuild copies only the columns
        both schemas share, so a schema that dropped a column would delete that
        column's data on the next ordinary open, with no prompt and no backup. A
        catalog that took a full crawl to populate should not be reshaped as a
        side effect of opening it. The rebuild exists, but it is explicit:
        :meth:`rebuild_table`, reached from ``pegasus-data catalog-rebuild``.
        """
        with self._lock:
            schema = _schema_sql()
            # Columns first: the script also creates indexes over them, and an
            # index on a column the old table lacks fails before anything else
            # in the script has had a chance to run.
            for table, column, decl in _missing_columns(self.conn, schema):
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")
            # Then refuse, before the script runs, if what remains cannot be
            # closed by adding columns. Failing here points at the catalog;
            # failing later points at whichever query happened to touch it first.
            problems = _structural_mismatches(self.conn, schema) if self.strict_schema else []
            if problems:
                raise CatalogSchemaError(
                    f"catalog at {self.path} does not match the shipped schema and "
                    "cannot be migrated by adding columns:\n  "
                    + "\n  ".join(problems)
                    + "\n\nRebuild the affected tables with 'pegasus-data catalog-rebuild "
                    "--table <name>' (copies the columns both schemas share and drops "
                    "the rest), or re-crawl into a fresh catalog."
                )
            self.conn.executescript(schema)
            row = self.conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
            if row is None or row["v"] is None:
                self.conn.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, utcnow()),
                )
            self.conn.commit()

    def rebuild_table(self, table: str) -> dict[str, object]:
        """Recreate ``table`` from the shipped schema, carrying over shared columns.

        The remedy for what :meth:`migrate` refuses. It is deliberately a separate,
        explicit call rather than something ``migrate`` does on its own, because it
        is lossy in a way additive migration never is: a column the shipped schema
        no longer declares is not copied, and its data goes with the old table.
        Naming the dropped columns in the return value is the least this can do.
        """
        schema = _schema_sql()
        declared = _declared_columns(schema).get(table)
        if declared is None:
            raise CatalogSchemaError(f"the shipped schema does not declare a table named {table!r}")
        match = next(
            (m for m in _CREATE_TABLE.finditer(schema) if m.group(1) == table),
            None,
        )
        if match is None:  # pragma: no cover - _declared_columns reads the same source
            raise CatalogSchemaError(f"no CREATE TABLE statement found for {table!r}")

        with self._lock:
            existing = [r[1] for r in self.conn.execute(f"PRAGMA table_info({table})")]
            if not existing:
                raise CatalogSchemaError(f"catalog has no table named {table!r} to rebuild")
            shared = [c for c in existing if c in declared]
            dropped = [c for c in existing if c not in declared]
            added = [c for c in declared if c not in existing]
            before = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

            # legacy_alter_table keeps RENAME from rewriting references to this
            # table in other objects — we want the old rows parked, not the
            # schema rewritten around them.
            # Any pending implicit transaction has to close first: PRAGMAs do
            # not take effect inside one, and BEGIN inside one is an error.
            self.conn.commit()
            self.conn.execute("PRAGMA legacy_alter_table = ON")
            self.conn.execute("PRAGMA foreign_keys = OFF")
            try:
                self.conn.execute("BEGIN IMMEDIATE")
                self.conn.execute(f"ALTER TABLE {table} RENAME TO {table}__rebuild_old")
                self.conn.execute(match.group(0).rstrip(";"))
                if shared:
                    cols = ", ".join(shared)
                    self.conn.execute(
                        f"INSERT INTO {table} ({cols}) SELECT {cols} FROM {table}__rebuild_old"
                    )
                self.conn.execute(f"DROP TABLE {table}__rebuild_old")
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise
            finally:
                self.conn.execute("PRAGMA legacy_alter_table = OFF")
                self.conn.execute("PRAGMA foreign_keys = ON")

            # Dropping the parked table took its indexes with it; the script
            # recreates them, and anything else the rebuild disturbed.
            self.conn.executescript(schema)
            after = self.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            self.conn.commit()

        self.log_event(
            "catalog",
            f"rebuilt table {table}",
            detail=f"rows {before}->{after}; dropped={dropped}; added={added}",
        )
        return {
            "table": table,
            "rows_before": before,
            "rows_after": after,
            "columns_kept": shared,
            "columns_dropped": dropped,
            "columns_added": added,
        }

    def close(self) -> None:
        with self._lock:
            try:
                self.conn.commit()
            except sqlite3.Error:
                pass
            self.conn.close()

    def __enter__(self) -> Catalog:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------- primitives

    @contextmanager
    def write(self) -> Iterator[sqlite3.Connection]:
        """Serialised write transaction."""
        with self._lock:
            try:
                yield self.conn
                self.conn.commit()
            except Exception:
                self.conn.rollback()
                raise

    def execute(self, sql: str, params: Sequence[Any] = ()) -> sqlite3.Cursor:
        with self._lock:
            return self.conn.execute(sql, params)

    def executemany(self, sql: str, rows: Iterable[Sequence[Any]]) -> int:
        batch = list(rows)
        if not batch:
            return 0
        with self.write() as conn:
            conn.executemany(sql, batch)
        return len(batch)

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    def scalar(self, sql: str, params: Sequence[Any] = ()) -> Any:
        row = self.query(sql, params)
        if not row:
            return None
        return row[0][0]

    def count(self, table: str, where: str = "", params: Sequence[Any] = ()) -> int:
        clause = f" WHERE {where}" if where else ""
        return int(self.scalar(f"SELECT COUNT(*) FROM {table}{clause}", params) or 0)

    # ---------------------------------------------------------------- L0 files

    def upsert_files(self, rows: Iterable[dict[str, Any]]) -> int:
        """Insert or refresh file rows. `first_seen` is preserved across crawls."""
        now = utcnow()
        payload = [
            (
                r["path"], r["directory"], r["filename"], r.get("extension"),
                r.get("size"), r.get("modified"), r.get("listing_method"),
                r.get("change_signal"), now, now,
            )
            for r in rows
        ]
        if not payload:
            return 0
        with self.write() as conn:
            conn.executemany(
                """
                INSERT INTO files (path, directory, filename, extension, size, modified,
                                   listing_method, change_signal, first_seen, last_seen)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(path) DO UPDATE SET
                    directory=excluded.directory,
                    filename=excluded.filename,
                    extension=excluded.extension,
                    size=COALESCE(excluded.size, files.size),
                    modified=COALESCE(excluded.modified, files.modified),
                    listing_method=excluded.listing_method,
                    change_signal=excluded.change_signal,
                    last_seen=excluded.last_seen,
                    -- Seeing a file again clears any earlier `gone` mark: it is
                    -- back, or it never left and a listing had failed.
                    gone_at=NULL
                """,
                payload,
            )
        return len(payload)

    def upsert_directories(self, rows: Iterable[dict[str, Any]]) -> int:
        now = utcnow()
        payload = [
            (
                r["path"], r.get("parent"), r.get("listing_method"), r.get("entry_count"),
                r.get("file_count"), r.get("dir_count"), now, r.get("date_convention"),
            )
            for r in rows
        ]
        if not payload:
            return 0
        with self.write() as conn:
            conn.executemany(
                """
                INSERT INTO directories (path, parent, listing_method, entry_count,
                                         file_count, dir_count, last_listed_at, date_convention)
                VALUES (?,?,?,?,?,?,?,?)
                ON CONFLICT(path) DO UPDATE SET
                    parent=excluded.parent,
                    listing_method=excluded.listing_method,
                    entry_count=excluded.entry_count,
                    file_count=excluded.file_count,
                    dir_count=excluded.dir_count,
                    last_listed_at=excluded.last_listed_at,
                    date_convention=COALESCE(excluded.date_convention, directories.date_convention)
                """,
                payload,
            )
        return len(payload)

    def record_gap(
        self, path: str, *, kind: str = "listing", methods: Sequence[str] = (), error: str = ""
    ) -> None:
        with self.write() as conn:
            conn.execute(
                """
                INSERT INTO coverage_gaps (path, kind, attempts, methods_tried, last_error, last_attempt, resolved)
                VALUES (?,?,1,?,?,?,0)
                ON CONFLICT(path) DO UPDATE SET
                    kind=excluded.kind,
                    attempts=coverage_gaps.attempts+1,
                    methods_tried=excluded.methods_tried,
                    last_error=excluded.last_error,
                    last_attempt=excluded.last_attempt,
                    resolved=0
                """,
                (path, kind, ",".join(methods), error[:2000], utcnow()),
            )

    def resolve_gap(self, path: str) -> None:
        with self.write() as conn:
            conn.execute(
                "UPDATE coverage_gaps SET resolved=1, last_attempt=? WHERE path=?", (utcnow(), path)
            )

    def open_gaps(self, kind: str | None = None) -> list[sqlite3.Row]:
        if kind:
            return self.query("SELECT * FROM coverage_gaps WHERE resolved=0 AND kind=?", (kind,))
        return self.query("SELECT * FROM coverage_gaps WHERE resolved=0")

    # ---------------------------------------------------------------- L2 blobs

    def record_fetch(
        self,
        *,
        source_path: str,
        sha256: str,
        byte_size: int,
        serving_method: str | None = None,
        elapsed_ms: float | None = None,
    ) -> None:
        now = utcnow()
        with self.write() as conn:
            conn.execute(
                """
                INSERT INTO blobs (sha256, byte_size, first_fetched_at, fetch_count)
                VALUES (?,?,?,1)
                ON CONFLICT(sha256) DO UPDATE SET fetch_count = blobs.fetch_count + 1
                """,
                (sha256, byte_size, now),
            )
            conn.execute(
                """
                INSERT INTO fetches (source_path, sha256, byte_size, fetched_at, serving_method, elapsed_ms)
                VALUES (?,?,?,?,?,?)
                """,
                (source_path, sha256, byte_size, now, serving_method, elapsed_ms),
            )

    def latest_blob_for(self, source_path: str) -> str | None:
        row = self.query(
            "SELECT sha256 FROM fetches WHERE source_path=? ORDER BY id DESC LIMIT 1", (source_path,)
        )
        return row[0]["sha256"] if row else None

    # ------------------------------------------------------------ open questions

    def note_question(
        self,
        key: str,
        *,
        area: str,
        question: str,
        verification_procedure: str = "",
        blocking: str = "",
    ) -> None:
        with self.write() as conn:
            conn.execute(
                """
                INSERT INTO open_questions (key, area, question, verification_procedure, blocking, status, noted_at)
                VALUES (?,?,?,?,?, 'open', ?)
                ON CONFLICT(key) DO UPDATE SET
                    area=excluded.area,
                    question=excluded.question,
                    verification_procedure=excluded.verification_procedure,
                    blocking=excluded.blocking
                """,
                (key, area, question, verification_procedure, blocking, utcnow()),
            )

    def resolve_question(self, key: str, *, resolution: str, evidence: str = "") -> None:
        with self.write() as conn:
            conn.execute(
                """
                UPDATE open_questions
                   SET status='resolved', resolution=?, evidence=?, resolved_at=?
                 WHERE key=?
                """,
                (resolution, evidence, utcnow(), key),
            )

    # ------------------------------------------------------------------ events

    def log_event(
        self,
        stage: str,
        message: str,
        *,
        level: str = "info",
        path: str | None = None,
        detail: Any = None,
        run_id: str | None = None,
    ) -> None:
        payload = detail if isinstance(detail, str) or detail is None else json.dumps(detail, default=str)
        with self.write() as conn:
            conn.execute(
                """
                INSERT INTO events (run_id, stage, level, path, message, detail, noted_at)
                VALUES (?,?,?,?,?,?,?)
                """,
                (run_id, stage, level, path, message[:4000], payload, utcnow()),
            )

    # ------------------------------------------------------------------- misc

    def vacuum(self) -> None:
        with self._lock:
            self.conn.execute("VACUUM")

    def table_counts(self) -> dict[str, int]:
        names = [
            r["name"]
            for r in self.query(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        ]
        return {n: self.count(n) for n in sorted(names)}
