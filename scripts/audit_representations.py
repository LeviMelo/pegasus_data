"""Report presumptive physical-representation alternatives by logical publication."""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


def audit(path: Path) -> dict[str, Any]:
    conn = sqlite3.connect(f"file:{path.resolve().as_posix()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        summary = conn.execute(
            """
            SELECT COUNT(*) groups, COALESCE(SUM(n),0) physical_files,
                   COALESCE(SUM(n - 1),0) alternatives
              FROM (
                SELECT logical_id, COUNT(*) n
                  FROM file_facts
                 WHERE logical_id IS NOT NULL AND role='data'
                 GROUP BY logical_id HAVING COUNT(*) > 1
              )
            """
        ).fetchone()
        by_format = [
            dict(row)
            for row in conn.execute(
                """
                SELECT container_format, COUNT(*) files
                  FROM file_facts
                 WHERE logical_id IN (
                   SELECT logical_id FROM file_facts WHERE logical_id IS NOT NULL
                   GROUP BY logical_id HAVING COUNT(*) > 1
                 )
                 GROUP BY container_format ORDER BY files DESC
                """
            )
        ]
        examples = [
            dict(row)
            for row in conn.execute(
                """
                SELECT logical_id, COUNT(*) representations,
                       GROUP_CONCAT(DISTINCT container_format) formats
                  FROM file_facts
                 WHERE logical_id IS NOT NULL AND role='data'
                 GROUP BY logical_id HAVING COUNT(*) > 1
                 ORDER BY representations DESC, logical_id LIMIT 20
                """
            )
        ]
        return {
            "logical_publications_with_alternatives": int(summary["groups"] or 0),
            "physical_files_in_groups": int(summary["physical_files"] or 0),
            "files_avoided_by_preference": int(summary["alternatives"] or 0),
            "formats": by_format,
            "examples": examples,
        }
    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.catalog), indent=2))


if __name__ == "__main__":
    main()
