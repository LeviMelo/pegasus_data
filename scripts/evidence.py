"""Dump what the catalog knows about undescribed columns, as JSON.

Describing 4,354 columns is the largest remaining piece of work and the one that
does not automate: no source on the tree states what most of them mean. What the
catalog *can* do is put everything it has observed about a column in front of
whoever is writing the description, so the description is grounded in the data
rather than in the column's name.

For each column that is not documented yet, that is: the declared type and width
from its file header, what the detectors concluded and how confident they were,
the codelists it is bound to, the values actually seen in it with their labels
where any exist, the series and years it appears in, and how many files carry it
— which is the only honest ordering, because a column in 12,000 files matters
more than one in a single stratum.

Usage::

    python scripts/evidence.py CATALOG --system SINAN --limit 120
    python scripts/evidence.py CATALOG --plan          # what is left, per system
"""

from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys

TOP_VALUES = 12


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def plan(conn: sqlite3.Connection) -> list[dict[str, object]]:
    """How many columns each system still needs, worst first.

    Counts **both** rungs that carry a description: ``field_documentation``,
    extracted from DATASUS's own layout documents, and ``variable_docs``, written
    by hand under ``curation/``. Counting only the first is what this script did
    at the start, and it reported 5.9% coverage while 404 curated descriptions sat
    in the catalog — a measurement that understated the work already done.
    """
    rows = conn.execute(
        """
        WITH described AS (
          SELECT system, field_name FROM field_documentation
           WHERE description IS NOT NULL AND TRIM(description) <> ''
          UNION
          SELECT system, field_name FROM variable_docs
           WHERE description IS NOT NULL AND TRIM(description) <> ''
        )
        SELECT s.system AS system,
               COUNT(DISTINCT sp.field_name) AS columns,
               COUNT(DISTINCT CASE WHEN d.field_name IS NOT NULL
                                   THEN sp.field_name END) AS described
          FROM schema_presence sp
          JOIN strata s ON s.schema_signature = sp.schema_signature
          LEFT JOIN described d
                 ON d.system = s.system AND d.field_name = sp.field_name
         WHERE s.system IS NOT NULL
         GROUP BY s.system
         ORDER BY (COUNT(DISTINCT sp.field_name)
                   - COUNT(DISTINCT CASE WHEN d.field_name IS NOT NULL
                                         THEN sp.field_name END)) DESC
        """
    ).fetchall()
    return [
        {
            "system": r["system"],
            "columns": r["columns"],
            "described": r["described"],
            "remaining": r["columns"] - r["described"],
        }
        for r in rows
    ]


def _weights(conn: sqlite3.Connection, system: str) -> dict[str, int]:
    """Files carrying each column — the only honest way to order the work."""
    return {
        str(r["field_name"]): int(r["files"])
        for r in conn.execute(
            """
            SELECT sp.field_name AS field_name, SUM(st.file_count) AS files
              FROM schema_presence sp
              JOIN strata st ON st.schema_signature = sp.schema_signature
             WHERE st.system = ?
             GROUP BY sp.field_name
            """,
            (system,),
        )
    }


def _grouped(conn: sqlite3.Connection, sql: str, params: tuple, key: str) -> dict[str, list]:
    out: dict[str, list] = {}
    for row in conn.execute(sql, params):
        out.setdefault(str(row[key]), []).append(row)
    return out


def evidence(conn: sqlite3.Connection, system: str, limit: int, include_described: bool):
    """Everything the catalog observed, for the columns still lacking a description.

    Every lookup here is a grouped scan collected once and joined in Python.
    Asking per column would be one query per row of the answer, which on a
    19.9-million-row dictionary is the difference between seconds and an
    afternoon — a shape this project has paid for five separate times.
    """
    weights = _weights(conn, system)

    # Narrow to the batch BEFORE gathering evidence, not after. Collecting every
    # label in the system first and then slicing meant SIASUS pulled millions of
    # rows — MUNICBR alone is 865,801 — to describe ninety columns, and the agent
    # asking for them timed out having read nothing. The ordering is by files
    # carrying the column, which only needs `weights`.
    documented = {
        str(r["field_name"])
        for r in conn.execute(
            "SELECT DISTINCT field_name FROM field_documentation WHERE system = ?", (system,)
        )
    }
    curated = {
        str(r["field_name"])
        for r in conn.execute(
            "SELECT DISTINCT field_name FROM variable_docs "
            "WHERE system = ? AND description IS NOT NULL AND TRIM(description) <> ''",
            (system,),
        )
    }
    known = documented | curated

    names = sorted(weights, key=lambda f: (-weights[f], f))
    if not include_described:
        names = [f for f in names if f not in known]
    names = names[:limit]
    if not names:
        return []

    slots = ",".join("?" * len(names))

    headers = _grouped(
        conn,
        f"""
        SELECT h.field_name AS field_name, h.type_code, h.width, h.decimals
          FROM schema_header_facts h
          JOIN strata s ON s.schema_signature = h.schema_signature
         WHERE s.system = ? AND h.field_name IN ({slots})
         GROUP BY h.field_name, h.type_code, h.width, h.decimals
        """,
        (system, *names),
        "field_name",
    )
    ledger = _grouped(
        conn,
        "SELECT field_name, official_name, semantic_type, semantic_confidence, unit, "
        f"aggregation, sentinel_values FROM ledger WHERE system = ? AND field_name IN ({slots})",
        (system, *names),
        "field_name",
    )
    bindings = _grouped(
        conn,
        "SELECT field_name, codelist, confidence, source FROM field_codelists "
        f"WHERE system = ? AND field_name IN ({slots}) ORDER BY confidence DESC",
        (system, *names),
        "field_name",
    )
    values = _grouped(
        conn,
        f"""
        SELECT vf.field_name AS field_name, vf.value AS value, SUM(vf.count) AS n
          FROM value_frequencies vf
          JOIN families f ON f.family_id = vf.family_id
         WHERE f.system = ? AND vf.field_name IN ({slots})
         GROUP BY vf.field_name, vf.value
         ORDER BY n DESC
        """,
        (system, *names),
        "field_name",
    )
    # Labels for those values, in one scan rather than one lookup per value.
    labels: dict[tuple[str, str], str] = {}
    for row in conn.execute(
        f"""
        SELECT d.field_name AS field_name, d.value_raw AS code, d.value_label AS label
          FROM dictionary d
         WHERE d.system = ? AND d.field_name IN ({slots})
        """,
        (system, *names),
    ):
        labels.setdefault((str(row["field_name"]), str(row["code"])), str(row["label"]))
    for row in conn.execute(
        f"""
        SELECT fc.field_name AS field_name, d.value_raw AS code, d.value_label AS label
          FROM field_codelists fc
          JOIN dictionary d ON d.system = fc.system AND d.value_group = fc.codelist
         WHERE fc.system = ? AND fc.field_name IN ({slots})
        """,
        (system, *names),
    ):
        labels.setdefault((str(row["field_name"]), str(row["code"])), str(row["label"]))

    series = _grouped(
        conn,
        f"""
        SELECT sp.field_name AS field_name, s.series AS series,
               MIN(s.year) AS y0, MAX(s.year) AS y1
          FROM schema_presence sp
          JOIN strata s ON s.schema_signature = sp.schema_signature
         WHERE s.system = ? AND sp.field_name IN ({slots})
         GROUP BY sp.field_name, s.series
        """,
        (system, *names),
        "field_name",
    )

    out = []
    for name in names:
        head = headers.get(name, [])
        led = ledger.get(name, [{}])[0]
        seen = values.get(name, [])[:TOP_VALUES]
        out.append(
            {
                "field": name,
                "files": weights.get(name, 0),
                "declared": [
                    f"{h['type_code']}({h['width']},{h['decimals']})" for h in head[:3]
                ],
                "official_name": (led["official_name"] if led else None),
                "semantic_type": (led["semantic_type"] if led else None),
                "semantic_confidence": (led["semantic_confidence"] if led else None),
                "unit": (led["unit"] if led else None),
                "aggregation": (led["aggregation"] if led else None),
                "codelists": [
                    {"name": b["codelist"], "confidence": b["confidence"], "source": b["source"]}
                    for b in bindings.get(name, [])[:6]
                ],
                "top_values": [
                    {
                        "value": v["value"],
                        "n": v["n"],
                        "label": labels.get((name, str(v["value"]))),
                    }
                    for v in seen
                ],
                "series": [
                    {"series": s["series"], "years": [s["y0"], s["y1"]]}
                    for s in series.get(name, [])[:6]
                ],
                "already_described": name in known,
            }
        )
    return out


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog")
    parser.add_argument("--system")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--include-described", action="store_true")
    args = parser.parse_args()

    conn = connect(args.catalog)
    try:
        if args.plan or not args.system:
            print(json.dumps(plan(conn), indent=2, ensure_ascii=False))
            return
        rows = evidence(
            conn, args.system.upper(), args.limit + args.offset, args.include_described
        )
        print(json.dumps(rows[args.offset :], indent=2, ensure_ascii=False))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
