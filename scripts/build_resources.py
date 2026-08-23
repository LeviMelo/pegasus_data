"""Freeze the map of DATASUS into the package.

The most distinctive thing this module knows is not how to decode a `.dbc` — it
is **what is on the server**: 207,251 files, which system and series and year and
state each belongs to, how big it is, and which of the 273 schemas it follows.
Nobody else has that, DATASUS does not publish it, and obtaining it takes a
multi-hour crawl.

Compressed, the whole map is about **1 MB**. That is small enough to ship, which
changes what the module *is* for someone who has just installed it: instead of
"run a crawl for a few hours and then you can ask questions", ``explore()``
answers immediately, offline, on a fresh install.

What is shipped is a snapshot and says so. A crawl the user runs locally always
wins over it — the map records what the tree looked like when the package was
built, and DATASUS moves things.

Usage::

    python scripts/build_resources.py CATALOG
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

RESOURCES = Path(__file__).resolve().parents[1] / "src" / "pegasus_data" / "resources"

#: zstd at a high level, because this is written once per release and read often.
_CODEC = "zstd"
_LEVEL = 19


def _write(table: pa.Table, name: str) -> int:
    target = RESOURCES / f"{name}.parquet"
    pq.write_table(table, target, compression=_CODEC, compression_level=_LEVEL)
    return target.stat().st_size


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _table(rows: list[tuple], names: list[str]) -> pa.Table:
    if not rows:
        return pa.table({n: pa.array([], type=pa.string()) for n in names})
    columns = list(zip(*rows, strict=True))
    return pa.table(
        {n: pa.array(list(c)) for n, c in zip(names, columns, strict=True)}
    )


def build(catalog_path: str) -> dict[str, object]:
    conn = sqlite3.connect(f"file:{catalog_path}?mode=ro", uri=True)
    RESOURCES.mkdir(parents=True, exist_ok=True)
    written: dict[str, int] = {}
    try:
        # The map itself. `gone_at IS NULL` because a file the last crawl found
        # withdrawn is not on the server, and shipping it would send people
        # after paths that 404.
        files = conn.execute(
            """
            SELECT f.path, fa.system, fa.series_prefix, fa.geo_code, fa.year,
                   fa.normalized_date, f.size, fa.role, fa.container_format,
                   fa.logical_id
              FROM files f
              LEFT JOIN file_facts fa ON fa.path = f.path
             WHERE f.gone_at IS NULL
             ORDER BY f.path
            """
        ).fetchall()
        written["tree"] = _write(
            _table(
                files,
                ["path", "system", "series", "uf", "year", "yyyymm", "size", "role",
                 "format", "logical_id"],
            ),
            "tree",
        )

        # The schema catalogue: which columns each generation actually has. This
        # is what lets `explore()` answer "does 2008 have DIAG_SECUN" without a
        # byte of the data being downloaded.
        written["families"] = _write(
            _table(
                conn.execute(
                    """
                    SELECT family_id, system, series, schema_signature, field_count,
                           time_min, time_max, file_count, stratum_count
                      FROM families ORDER BY system, series, COALESCE(time_min, 0)
                    """
                ).fetchall(),
                ["family_id", "system", "series", "signature", "fields", "time_min",
                 "time_max", "files", "strata"],
            ),
            "families",
        )
        written["schema_presence"] = _write(
            _table(
                conn.execute(
                    "SELECT schema_signature, field_name, field_order FROM schema_presence "
                    "ORDER BY schema_signature, field_order"
                ).fetchall(),
                ["signature", "field", "order"],
            ),
            "schema_presence",
        )

        counts = {
            "files": len(files),
            "systems": len({r[1] for r in files if r[1]}),
            "families": conn.execute("SELECT COUNT(*) FROM families").fetchone()[0],
            "columns": conn.execute(
                "SELECT COUNT(DISTINCT field_name) FROM schema_presence"
            ).fetchone()[0],
        }
        crawled = conn.execute(
            "SELECT MAX(finished_at) FROM crawl_runs WHERE finished_at IS NOT NULL"
        ).fetchone()[0]
    finally:
        conn.close()

    old_manifest_path = RESOURCES / "manifest.json"
    old_manifest = (
        json.loads(old_manifest_path.read_text(encoding="utf-8"))
        if old_manifest_path.is_file()
        else {}
    )
    resource_entries = dict(old_manifest.get("resources") or {})
    for name in written:
        path = RESOURCES / f"{name}.parquet"
        resource_entries[name] = {
            "file": path.name,
            "tier": "A",
            "bytes": path.stat().st_size,
            "rows": pq.read_metadata(path).num_rows,
            "sha256": _sha256(path),
        }
    manifest = {
        "resource_schema_version": 2,
        "resource_content_version": datetime.now(UTC).date().isoformat(),
        "built_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_build_id": crawled,
        "crawled_at": crawled,
        "counts": counts,
        "budgets": old_manifest.get("budgets") or {
            "growth_ratio": 1.25,
            "architectural_review_bytes": 100 * 1024 * 1024,
            "aggregate_bytes": 45 * 1024 * 1024,
        },
        "resources": resource_entries,
        "note": (
            "Bundled resources are an offline runtime baseline. "
            "Local version-compatible updates take precedence."
        ),
    }
    (RESOURCES / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    return manifest


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog")
    args = parser.parse_args()
    manifest = build(args.catalog)
    total = sum(int(item.get("bytes", 0)) for item in manifest["resources"].values())
    print(json.dumps(manifest, indent=2))
    print(f"\ntotal shipped: {total / 2**20:.2f} MB")


if __name__ == "__main__":
    main()
