"""The seed catalog: a fresh install starts from what the maintainer knows.

A catalog holds two kinds of knowledge. What the tree *is* (every file, which
system, series, state and date it belongs to, which schema it follows, which
family) and what it *means* (bindings, curated variable and dataset docs, open
questions) are the same for everyone and expensive to learn: listing the tree
takes half a minute, but learning its schemas costs a ranged read per stratum,
twelve minutes for the whole tree (evaluation 2026-09-28). Everything else in a
catalog (blobs fetched, lake partitions written, adjudications) is local.

So the package ships the first kind as one compressed SQLite file, and a
catalog that does not exist yet starts as a copy of it (ADR-0067). Every door
then works the same on a fresh install as on a maintainer's machine: ``info()``,
``explore()``, a first ``fetch()`` that needs no discovery. A crawl the user
runs later reconciles against it like any other.

The seed is built from a maintainer catalog by :func:`export_seed`
(``scripts/build_resources.py``) and installed by :func:`install_seed`, which
:class:`~pegasus_data.catalog.store.Catalog` calls when its file is absent.
``PEGASUS_SEED=0`` disables seeding; the test suite sets it, because a test
that builds a catalog from nothing must get nothing.
"""

from __future__ import annotations

import gzip
import os
import shutil
import sqlite3
import tempfile
from importlib.resources import files
from pathlib import Path

SEED_NAME = "catalog_seed.sqlite.gz"

#: The shared knowledge. Local state (blobs, fetches, lake partitions, build
#: outcomes, events, adjudication items, decode attempts) is deliberately absent.
SEED_TABLES: tuple[str, ...] = (
    "files",
    "file_facts",
    "file_moves",
    "prefix_systems",
    "system_disagreements",
    "directories",
    "coverage_gaps",
    "crawl_runs",
    "strata",
    "stratum_members",
    "schemas",
    "families",
    "family_files",
    "representations",
    "representation_conflicts",
    "schema_presence",
    "schema_header_facts",
    "schema_drift",
    "field_renames",
    "field_codelists",
    "label_bindings",
    "variable_docs",
    "dataset_docs",
    "open_questions",
    "semantic_relations",
    "population_series",
    "curation_state",
)


def seeding_enabled() -> bool:
    return os.environ.get("PEGASUS_SEED", "1").strip().lower() not in ("0", "false", "no", "off")


def packaged_seed() -> Path | None:
    """The seed shipped in the wheel, or None when this build carries none."""
    try:
        path = Path(str(files("pegasus_data.resources") / SEED_NAME))
    except (ModuleNotFoundError, FileNotFoundError):  # pragma: no cover
        return None
    return path if path.is_file() else None


def install_seed(target: Path) -> bool:
    """Materialise the packaged seed at ``target`` if nothing is there yet.

    Written beside the target and renamed into place, so a crash or a second
    process never sees half a database. Returns whether a seed was installed.
    """
    if target.exists() or not seeding_enabled():
        return False
    seed = packaged_seed()
    if seed is None:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".seed-", suffix=".sqlite", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as sink, gzip.open(seed, "rb") as source:
            shutil.copyfileobj(source, sink, length=4 * 1024 * 1024)
        if target.exists():  # another process won the race; its copy is as good
            os.unlink(tmp)
            return False
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return True


def export_seed(source: Path, target: Path) -> dict[str, int]:
    """Write the seed from a maintainer catalog. Returns rows per table.

    The seed's schema is created by :class:`Catalog` itself, so it is always
    the current ``schema.sql`` and a user's first open needs no migration.
    Rows are copied by the columns both sides have.
    """
    from .store import Catalog

    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="pegasus_seed_") as work:
        db = Path(work) / "seed.sqlite"
        previous = os.environ.get("PEGASUS_SEED")
        os.environ["PEGASUS_SEED"] = "0"  # an empty schema, not a seeded one
        try:
            Catalog(db).close()
        finally:
            if previous is None:
                os.environ.pop("PEGASUS_SEED", None)
            else:
                os.environ["PEGASUS_SEED"] = previous
        conn = sqlite3.connect(db)
        counts: dict[str, int] = {}
        try:
            conn.execute("ATTACH DATABASE ? AS src", (f"file:{source.as_posix()}?mode=ro",))
            src_tables = {r[0] for r in conn.execute("SELECT name FROM src.sqlite_master WHERE type='table'")}
            for table in SEED_TABLES:
                if table not in src_tables:
                    continue
                mine = [r[1] for r in conn.execute(f"PRAGMA main.table_info({table})")]
                theirs = {r[1] for r in conn.execute(f"PRAGMA src.table_info({table})")}
                shared = [c for c in mine if c in theirs]
                cols = ", ".join(f'"{c}"' for c in shared)
                conn.execute(f"DELETE FROM main.{table}")
                conn.execute(f"INSERT INTO main.{table} ({cols}) SELECT {cols} FROM src.{table}")
                counts[table] = conn.execute(f"SELECT COUNT(*) FROM main.{table}").fetchone()[0]
            conn.commit()
            conn.execute("DETACH DATABASE src")
            conn.execute("PRAGMA journal_mode = DELETE")
            conn.execute("VACUUM")
        finally:
            conn.close()
        with db.open("rb") as raw, gzip.open(target, "wb", compresslevel=9) as out:
            shutil.copyfileobj(raw, out, length=4 * 1024 * 1024)
    return counts
