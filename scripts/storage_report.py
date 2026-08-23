"""Measure SQLite catalogs and packaged Parquet resources without modifying them.

Usage::

    python scripts/storage_report.py path/to/catalog.sqlite --resources src/pegasus_data/resources
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


def sqlite_report(path: Path) -> dict[str, Any]:
    """Return page, object, and table-size evidence for one SQLite database."""
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        page_count = int(conn.execute("PRAGMA page_count").fetchone()[0])
        freelist = int(conn.execute("PRAGMA freelist_count").fetchone()[0])
        objects = [
            {"name": str(row[0]), "bytes": int(row[1] or 0)}
            for row in conn.execute(
                "SELECT name, SUM(pgsize) FROM dbstat GROUP BY name ORDER BY SUM(pgsize) DESC"
            )
        ]
        tables = [
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_schema WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        rows: dict[str, int] = {}
        for table in tables:
            quoted = table.replace('"', '""')
            rows[table] = int(conn.execute(f'SELECT COUNT(*) FROM "{quoted}"').fetchone()[0])
        object_bytes = {item["name"]: item["bytes"] for item in objects}
        table_rows = [
            {
                "table": table,
                "rows": count,
                "table_bytes": object_bytes.get(table, 0),
                "table_bytes_per_row": (
                    round(object_bytes.get(table, 0) / count, 2) if count else None
                ),
            }
            for table, count in rows.items()
        ]
        table_rows.sort(key=lambda item: item["table_bytes"], reverse=True)
        return {
            "path": str(path.resolve()),
            "file_bytes": path.stat().st_size,
            "page_size": page_size,
            "page_count": page_count,
            "freelist_count": freelist,
            "allocated_bytes": page_size * page_count,
            "free_bytes": page_size * freelist,
            "objects": objects,
            "tables": table_rows,
        }
    finally:
        conn.close()


def parquet_report(root: Path) -> dict[str, Any]:
    """Return physical/schema statistics for every packaged Parquet artifact."""
    import pyarrow.parquet as pq

    files: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.parquet")):
        metadata = pq.read_metadata(path)
        schema = metadata.schema.to_arrow_schema()
        files.append(
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "rows": metadata.num_rows,
                "row_groups": metadata.num_row_groups,
                "compressed_bytes_per_row": (
                    round(path.stat().st_size / metadata.num_rows, 3)
                    if metadata.num_rows
                    else None
                ),
                "schema": [str(field) for field in schema],
            }
        )
    return {"root": str(root.resolve()), "total_bytes": sum(f["bytes"] for f in files), "files": files}


def build_report(catalog: Path, resources: Path | None = None) -> dict[str, Any]:
    report: dict[str, Any] = {"sqlite": sqlite_report(catalog)}
    if resources is not None:
        report["resources"] = parquet_report(resources)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    parser.add_argument("--resources", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build_report(args.catalog, args.resources)
    text = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        args.out.write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
