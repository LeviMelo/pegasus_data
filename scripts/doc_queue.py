"""The work queue for describing columns: small units, and it never repeats one.

Three waves of documentation were run as a dozen agents each holding 100-130
columns. Each wrote its file once, at the end of a twenty-minute turn. When the
session limit landed mid-turn, twelve agents' work vanished together — 2 million
tokens, no output, twice. The batches were the problem, not the agents.

So the unit is small — a couple of dozen columns — and every unit writes its own
file the moment it is done. A limit costs whatever was in flight and nothing
else.

The second half of that is this queue being **idempotent**. Units are built from
the columns that are still undescribed *right now*, and named by the columns
they contain rather than by an offset into a list that shifts as work lands. So
re-running after an interruption simply produces fewer units, and nothing is
described twice.

Usage::

    python scripts/doc_queue.py CATALOG --size 25            # every system
    python scripts/doc_queue.py CATALOG --system SINAN       # one of them
    python scripts/doc_queue.py CATALOG --summary            # how much is left
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import sqlite3
import sys

#: Columns per unit. Small enough that a unit finishes well inside a turn and
#: writes before anything can interrupt it; large enough that the fixed cost of
#: reading a layout document is shared across several columns.
DEFAULT_SIZE = 25

DESCRIBED = """
SELECT system, field_name FROM field_documentation
 WHERE description IS NOT NULL AND TRIM(description) <> ''
UNION
SELECT system, field_name FROM variable_docs
 WHERE description IS NOT NULL AND TRIM(description) <> ''
"""


def remaining(conn: sqlite3.Connection, system: str | None) -> dict[str, list[tuple[str, int]]]:
    """Undescribed columns per system, most-carried first."""
    described: set[tuple[str, str]] = {
        (str(r[0]), str(r[1])) for r in conn.execute(DESCRIBED)
    }
    clause = " AND s.system = ?" if system else ""
    params = (system.upper(),) if system else ()
    out: dict[str, list[tuple[str, int]]] = {}
    for row in conn.execute(
        f"""
        SELECT s.system AS system, sp.field_name AS field_name,
               SUM(s.file_count) AS files
          FROM schema_presence sp
          JOIN strata s ON s.schema_signature = sp.schema_signature
         WHERE s.system IS NOT NULL{clause}
         GROUP BY s.system, sp.field_name
        """,
        params,
    ):
        key = (str(row[0]), str(row[1]))
        if key in described:
            continue
        out.setdefault(str(row[0]), []).append((str(row[1]), int(row[2] or 0)))
    for fields in out.values():
        fields.sort(key=lambda f: (-f[1], f[0]))
    return out


def _by_dataset(
    conn: sqlite3.Connection, system: str, names: list[str]
) -> list[tuple[str, list[str]]]:
    """Group undescribed columns by the dataset that carries them.

    **A unit must be a coherent form, not a slice of an alphabet.** In SINAN,
    79% of columns belong to exactly one agravo, and among the columns still
    undescribed it is 98.6%. Those columns are siblings on one notification
    form and are only interpretable as a set: ``STSIMETRIC``, ``STVENTILA``,
    ``STVISAO``, ``STVOMITO`` are unguessable in isolation and obvious as the
    botulism form — symmetric descending paralysis, respiratory failure,
    blurred vision.

    A previous wave chunked the flat name-sorted list, which worked only by
    accident: columns of one form often share a prefix, so sorting clustered
    them. A round-robin split destroyed that accident and scattered one form
    across four workers. Grouping explicitly makes the property intentional
    rather than lucky.

    A column carried by many datasets is generic (``DT_NOTIFIC``,
    ``ID_MUNICIP``) and goes in a ``*shared*`` unit, where describing it once
    against the whole system is the right frame.
    """
    from pegasus_data.ontology import Ontology

    try:
        onto = Ontology.load()
    except Exception:  # pragma: no cover - the queue must work without curation
        return [("", sorted(names))]

    wanted = set(names)
    carriers: dict[str, set[str]] = {}
    for field_name, series in conn.execute(
        "SELECT sp.field_name, s.series FROM schema_presence sp "
        "JOIN strata s ON s.schema_signature = sp.schema_signature "
        "WHERE s.system = ?",
        (system,),
    ):
        if str(field_name) not in wanted:
            continue
        bound = onto.bind(system, str(series))
        if bound.dataset:
            carriers.setdefault(str(field_name), set()).add(bound.dataset)

    groups: dict[str, list[str]] = {}
    for name in names:
        owners = carriers.get(name, set())
        key = next(iter(owners)) if len(owners) == 1 else "*shared*"
        groups.setdefault(key, []).append(name)
    # Single-dataset groups first and largest first: a whole form in one unit is
    # the most useful thing a worker can be handed.
    return sorted(
        ((k, sorted(v)) for k, v in groups.items()),
        key=lambda kv: (kv[0] == "*shared*", -len(kv[1]), kv[0]),
    )


def units(
    conn: sqlite3.Connection, *, system: str | None, size: int, limit: int | None
) -> list[dict[str, object]]:
    """Chunk what is left into units named by their contents.

    Units are grouped by dataset first (see :func:`_by_dataset`), so a worker is
    handed one coherent form rather than an arbitrary slice of an alphabet.

    The slug is a hash of the column names, so the same unit gets the same name
    on every run and a half-finished wave can be re-run without renaming
    anything. An offset would not survive: describing one column shifts every
    unit after it.
    """
    out: list[dict[str, object]] = []
    for sys_name, fields in sorted(remaining(conn, system).items()):
        counts = dict(fields)
        for dataset, names in _by_dataset(conn, sys_name, [f for f, _ in fields]):
            for start in range(0, len(names), size):
                chunk = names[start : start + size]
                digest = hashlib.sha1("|".join(chunk).encode("utf-8")).hexdigest()[:8]
                out.append(
                    {
                        "system": sys_name,
                        "dataset": dataset,
                        "slug": f"{sys_name.lower()}_{digest}",
                        "columns": chunk,
                        "files": sum(counts.get(f, 0) for f in chunk),
                    }
                )
    # Most-carried columns first, so an interrupted run has done the work that
    # matters most rather than whatever sorted first alphabetically.
    out.sort(key=lambda u: -int(u["files"]))
    return out[:limit] if limit else out


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("catalog")
    parser.add_argument("--system")
    parser.add_argument("--size", type=int, default=DEFAULT_SIZE)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()

    conn = sqlite3.connect(f"file:{args.catalog}?mode=ro", uri=True)
    try:
        if args.summary:
            left = remaining(conn, args.system)
            total = sum(len(v) for v in left.values())
            print(f"{total:,} columns still undescribed")
            for name, fields in sorted(left.items(), key=lambda kv: -len(kv[1])):
                print(f"  {name:18s} {len(fields):5d}")
            print(f"\n-> {-(-total // args.size)} units of {args.size}")
            return
        print(json.dumps(units(conn, system=args.system, size=args.size, limit=args.limit)))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
