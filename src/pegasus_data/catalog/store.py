"""SQLite access for the catalog: migrations, upserts, append-only history.

The catalog is the module's memory. Every layer writes here before returning, so
that any command can be interrupted and resumed from whatever the catalog knows.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import resources
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1


def utcnow() -> str:
    """ISO-8601 UTC timestamp, second precision, used for every catalog stamp."""
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _schema_sql() -> str:
    return resources.files("pegasus_data.catalog").joinpath("schema.sql").read_text(encoding="utf-8")


class Catalog:
    """A connection to the catalog database.

    Thread-safe for the access pattern the pipeline uses: many worker threads
    calling short write methods. Writes are serialised behind one lock; reads go
    through the same connection, which SQLite handles fine at this concurrency.
    """

    def __init__(self, path: str | Path, *, read_only: bool = False) -> None:
        self.path = Path(path)
        self.read_only = read_only
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
        with self._lock:
            self.conn.executescript(_schema_sql())
            row = self.conn.execute("SELECT MAX(version) AS v FROM schema_version").fetchone()
            if row is None or row["v"] is None:
                self.conn.execute(
                    "INSERT INTO schema_version (version, applied_at) VALUES (?, ?)",
                    (SCHEMA_VERSION, utcnow()),
                )
            self.conn.commit()

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
