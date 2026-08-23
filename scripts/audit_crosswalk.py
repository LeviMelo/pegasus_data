"""Measure temporal and directional cardinality of a compiled crosswalk."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def audit(path: Path) -> dict[str, int]:
    source = path.resolve().as_posix().replace("'", "''")
    relation = f"read_parquet('{source}')"
    queries = {
        "rows": f"SELECT COUNT(*) FROM {relation}",
        "distinct_source_codes": f"SELECT COUNT(DISTINCT source_code) FROM {relation}",
        "distinct_target_codes": f"SELECT COUNT(DISTINCT target_code) FROM {relation}",
        "ambiguous_source_windows": (
            "SELECT COUNT(*) FROM (SELECT source_code, valid_from, valid_to, "
            f"COUNT(DISTINCT target_code) n FROM {relation} GROUP BY 1,2,3 HAVING n > 1)"
        ),
        "sources_changing_target": (
            "SELECT COUNT(*) FROM (SELECT source_code, COUNT(DISTINCT target_code) n "
            f"FROM {relation} GROUP BY 1 HAVING n > 1)"
        ),
        "reverse_multi_source_windows": (
            "SELECT COUNT(*) FROM (SELECT target_code, valid_from, valid_to, "
            f"COUNT(DISTINCT source_code) n FROM {relation} GROUP BY 1,2,3 HAVING n > 1)"
        ),
        "max_targets_per_source_window": (
            "SELECT MAX(n) FROM (SELECT source_code, valid_from, valid_to, "
            f"COUNT(DISTINCT target_code) n FROM {relation} GROUP BY 1,2,3)"
        ),
        "max_sources_per_target_window": (
            "SELECT MAX(n) FROM (SELECT target_code, valid_from, valid_to, "
            f"COUNT(DISTINCT source_code) n FROM {relation} GROUP BY 1,2,3)"
        ),
    }
    connection = duckdb.connect()
    try:
        return {name: int(connection.execute(sql).fetchone()[0] or 0) for name, sql in queries.items()}
    finally:
        connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.path), indent=2))


if __name__ == "__main__":
    main()
