"""Reconciling a crawl against what the catalog already knew.

DATASUS republishes, reorganises and occasionally withdraws. A crawler that only
adds rows reports none of that: a moved file looks like one deletion and one
unrelated arrival, and a withdrawn file looks like nothing at all.

Two rules make the difference between a reconciliation and a guess:

* **Absence is only evidence when the listing succeeded.** A directory that
  failed to list tells us nothing about its contents. Marking its files gone
  would turn one network error into a mass deletion — and the crawl *does* hit
  transient failures routinely, so this is the normal case, not the edge case.

* **A move is a claim, so it needs evidence.** Same filename, same byte size and
  same mtime, gone from one directory and appeared in another within one crawl,
  is strong. It is still recorded as a detected move with the matching fields
  named, rather than silently rewriting the file's history.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from ..catalog.store import Catalog, utcnow


@dataclass(slots=True)
class FileState:
    """What the catalog knew about one path before this crawl."""

    path: str
    size: int | None
    modified: str | None
    logical_id: str | None


@dataclass(slots=True)
class Reconciliation:
    """The difference this crawl made, as counts and as detail."""

    new: int = 0
    unchanged: int = 0
    changed: int = 0
    moved: int = 0
    gone: int = 0
    unresolved: int = 0
    moves: list[tuple[str, str, str]] = field(default_factory=list)
    gone_paths: list[str] = field(default_factory=list)
    changed_paths: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "new": self.new,
            "unchanged": self.unchanged,
            "content_changed": self.changed,
            "moved": self.moved,
            "gone": self.gone,
            "unresolved": self.unresolved,
            "example_moves": [
                {"from": a, "to": b, "evidence": e} for a, b, e in self.moves[:10]
            ],
            "example_gone": self.gone_paths[:10],
        }

    @property
    def quiet(self) -> bool:
        return not (self.new or self.changed or self.moved or self.gone)


def snapshot(catalog: Catalog, prefixes: Sequence[str] | None = None) -> dict[str, FileState]:
    """What the catalog knows now, to compare the crawl against."""
    if prefixes:
        rows = []
        for prefix in prefixes:
            rows.extend(
                catalog.query(
                    "SELECT path, size, modified, logical_id FROM files WHERE path LIKE ? AND gone_at IS NULL",
                    (f"{prefix}%",),
                )
            )
    else:
        rows = catalog.query(
            "SELECT path, size, modified, logical_id FROM files WHERE gone_at IS NULL"
        )
    return {
        str(r["path"]): FileState(
            path=str(r["path"]),
            size=r["size"],
            modified=r["modified"],
            logical_id=r["logical_id"],
        )
        for r in rows
    }


def classify(before: FileState | None, size: int | None, modified: str | None) -> str:
    """``new`` | ``unchanged`` | ``changed`` | ``unresolved`` for one sighting."""
    if before is None:
        return "new"
    if size is None and modified is None:
        # The listing gave no change signal, so we cannot say. Content addressing
        # settles it at fetch time; until then "unresolved" is the honest label.
        return "unresolved"
    if before.size is None and before.modified is None:
        return "unresolved"
    if size is not None and before.size is not None and size != before.size:
        return "changed"
    if modified is not None and before.modified is not None and modified != before.modified:
        return "changed"
    return "unchanged"


def mark_gone(catalog: Catalog, directory: str, seen_paths: set[str]) -> list[str]:
    """Mark files absent from a **successfully listed** directory as gone.

    Only ever called on a directory whose listing succeeded — that is the whole
    safety property. Returns the paths marked, so the caller can look for them
    turning up elsewhere.
    """
    known = [
        str(r["path"])
        for r in catalog.query(
            "SELECT path FROM files WHERE directory = ? AND gone_at IS NULL", (directory,)
        )
    ]
    missing = [p for p in known if p not in seen_paths]
    if missing:
        catalog.executemany(
            "UPDATE files SET gone_at = ? WHERE path = ?", [(utcnow(), p) for p in missing]
        )
    return missing


def detect_moves(
    catalog: Catalog, gone_paths: Sequence[str], run_id: str
) -> list[tuple[str, str, str]]:
    """Match files that vanished against files that appeared, by fingerprint.

    Filename, byte size and mtime together are a strong fingerprint on this tree:
    DATASUS filenames already encode system, series, state and competência, so a
    collision would require two genuinely identical publications.
    """
    if not gone_paths:
        return []
    moves: list[tuple[str, str, str]] = []
    rows: list[tuple[object, ...]] = []
    for path in gone_paths:
        prior = catalog.query(
            "SELECT filename, size, modified, logical_id FROM files WHERE path = ?", (path,)
        )
        if not prior:
            continue
        p = prior[0]
        candidates = catalog.query(
            """
            SELECT path, logical_id FROM files
             WHERE filename = ? AND path != ? AND gone_at IS NULL
               AND (size IS ? OR ? IS NULL)
               AND (modified IS ? OR ? IS NULL)
            """,
            (p["filename"], path, p["size"], p["size"], p["modified"], p["modified"]),
        )
        if len(candidates) != 1:
            # Zero means it really went; more than one means the fingerprint does
            # not identify it, and guessing between them would be worse than
            # leaving the move unrecorded.
            continue
        target = str(candidates[0]["path"])
        evidence = "filename+size+mtime" if p["modified"] else "filename+size"
        moves.append((path, target, evidence))
        rows.append(
            (p["logical_id"], path, target, p["size"], p["modified"], evidence, run_id, utcnow())
        )
    catalog.executemany(
        """
        INSERT INTO file_moves (logical_id, from_path, to_path, size, modified, evidence, run_id, detected_at)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(from_path, to_path) DO UPDATE SET
            evidence=excluded.evidence, run_id=excluded.run_id, detected_at=excluded.detected_at
        """,
        rows,
    )
    return moves


def persist_reconciliation(catalog: Catalog, run_id: str, report: Reconciliation) -> None:
    catalog.execute(
        """
        UPDATE crawl_runs
           SET files_new = ?, files_unchanged = ?, files_changed = ?,
               files_moved = ?, files_gone = ?, files_unresolved = ?
         WHERE run_id = ?
        """,
        (
            report.new, report.unchanged, report.changed,
            report.moved, report.gone, report.unresolved, run_id,
        ),
    )
    catalog.conn.commit()


def recent_reconciliations(catalog: Catalog, limit: int = 10) -> list[dict[str, object]]:
    return [
        dict(r)
        for r in catalog.query(
            """
            SELECT run_id, started_at, files, files_new, files_unchanged, files_changed,
                   files_moved, files_gone, files_unresolved, gaps
              FROM crawl_runs ORDER BY started_at DESC LIMIT ?
            """,
            (limit,),
        )
    ]
