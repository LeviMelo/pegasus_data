"""Measure temporal and directional cardinality of a compiled crosswalk."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb


def audit(path: Path) -> dict[str, int]:
    source = path.resolve().as_posix().replace("'", "''")
    relation = f"read_parquet('{source}')"
    normalized = (
        "(SELECT row_number() OVER () relation_id, source_code, target_code, lo, hi FROM ("
        "SELECT DISTINCT source_code, target_code, "
        "COALESCE(NULLIF(valid_from,''),'000000') lo, "
        "COALESCE(NULLIF(valid_to,''),'999912') hi "
        f"FROM {relation}))"
    )
    queries = {
        "rows": f"SELECT COUNT(*) FROM {relation}",
        "distinct_source_codes": f"SELECT COUNT(DISTINCT source_code) FROM {relation}",
        "distinct_target_codes": f"SELECT COUNT(DISTINCT target_code) FROM {relation}",
        "ambiguous_source_windows": (
            "SELECT COUNT(*) FROM (SELECT source_code, valid_from, valid_to, "
            f"COUNT(DISTINCT target_code) n FROM {relation} GROUP BY 1,2,3 HAVING n > 1)"
        ),
        "ambiguous_source_pairwise_overlaps": (
            "SELECT COUNT(*) FROM (SELECT DISTINCT a.source_code, "
            "GREATEST(a.lo,b.lo) overlap_from, LEAST(a.hi,b.hi) overlap_to "
            f"FROM {normalized} a JOIN {normalized} b "
            "ON a.source_code=b.source_code AND a.target_code<>b.target_code "
            "AND a.relation_id<b.relation_id AND a.lo<=b.hi AND b.lo<=a.hi)"
        ),
        "sources_changing_target": (
            "SELECT COUNT(*) FROM (SELECT source_code, COUNT(DISTINCT target_code) n "
            f"FROM {relation} GROUP BY 1 HAVING n > 1)"
        ),
        "reverse_multi_source_windows": (
            "SELECT COUNT(*) FROM (SELECT target_code, valid_from, valid_to, "
            f"COUNT(DISTINCT source_code) n FROM {relation} GROUP BY 1,2,3 HAVING n > 1)"
        ),
        "reverse_multi_source_pairwise_overlaps": (
            "SELECT COUNT(*) FROM (SELECT DISTINCT a.target_code, "
            "GREATEST(a.lo,b.lo) overlap_from, LEAST(a.hi,b.hi) overlap_to "
            f"FROM {normalized} a JOIN {normalized} b "
            "ON a.target_code=b.target_code AND a.source_code<>b.source_code "
            "AND a.relation_id<b.relation_id AND a.lo<=b.hi AND b.lo<=a.hi)"
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
