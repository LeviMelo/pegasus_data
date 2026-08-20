"""Evidence for many columns at once, in as few characters as possible.

`evidence.py` emits JSON with everything the catalog knows, which is right when
one column is being studied and wrong when sixty are being described in a
sitting — the volume of it crowds out the work. This prints one line per column:
what it is declared as, what it is bound to, and what its values actually look
like.

Usage::

    python scripts/brief.py CATALOG SISCAN --limit 60
    python scripts/brief.py CATALOG SINAN --grep DT_       # one family at a time
"""

from __future__ import annotations

import argparse
import io
import sqlite3
import sys

DESCRIBED = """
SELECT system, field_name FROM field_documentation
 WHERE description IS NOT NULL AND TRIM(description) <> ''
UNION
SELECT system, field_name FROM variable_docs
 WHERE description IS NOT NULL AND TRIM(description) <> ''
"""


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("catalog")
    ap.add_argument("system")
    ap.add_argument("--limit", type=int, default=60)
    ap.add_argument("--grep", help="only columns whose name contains this")
    ap.add_argument("--values", type=int, default=4, help="top values to show")
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{args.catalog}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    system = args.system.upper()

    done = {f for s, f in conn.execute(DESCRIBED) if s == system}
    weights = {
        str(r[0]): int(r[1] or 0)
        for r in conn.execute(
            "SELECT sp.field_name, SUM(s.file_count) FROM schema_presence sp "
            "JOIN strata s ON s.schema_signature = sp.schema_signature "
            "WHERE s.system = ? GROUP BY sp.field_name",
            (system,),
        )
    }
    names = [f for f in sorted(weights, key=lambda f: (-weights[f], f)) if f not in done]
    if args.grep:
        names = [f for f in names if args.grep.upper() in f]
    names = names[: args.limit]
    if not names:
        print(f"nothing left for {system}" + (f" matching {args.grep!r}" if args.grep else ""))
        return
    slots = ",".join("?" * len(names))

    decl: dict[str, str] = {}
    for r in conn.execute(
        f"SELECT h.field_name, h.type_code, h.width FROM schema_header_facts h "
        f"JOIN strata s ON s.schema_signature = h.schema_signature "
        f"WHERE s.system = ? AND h.field_name IN ({slots}) "
        f"GROUP BY h.field_name, h.type_code, h.width",
        (system, *names),
    ):
        key = str(r[0])
        decl.setdefault(key, f"{r[1]}{r[2]}")

    binds: dict[str, list[str]] = {}
    for r in conn.execute(
        f"SELECT field_name, codelist FROM field_codelists WHERE system = ? "
        f"AND field_name IN ({slots}) ORDER BY confidence DESC",
        (system, *names),
    ):
        binds.setdefault(str(r[0]), []).append(str(r[1]))

    vals: dict[str, list[str]] = {}
    for r in conn.execute(
        f"SELECT vf.field_name, vf.value, SUM(vf.count) n FROM value_frequencies vf "
        f"JOIN families f ON f.family_id = vf.family_id "
        f"WHERE f.system = ? AND vf.field_name IN ({slots}) "
        f"GROUP BY vf.field_name, vf.value ORDER BY n DESC",
        (system, *names),
    ):
        got = vals.setdefault(str(r[0]), [])
        if len(got) < args.values and r[1] is not None:
            got.append(str(r[1]).strip()[:14])

    official: dict[str, str] = {
        str(r[0]): str(r[1])
        for r in conn.execute(
            f"SELECT field_name, official_name FROM ledger WHERE system = ? "
            f"AND field_name IN ({slots}) AND official_name IS NOT NULL",
            (system, *names),
        )
    }
    conn.close()

    print(f"# {system}: {len(names)} columns still undescribed (of {len(weights) - len(done)})")
    for name in names:
        parts = [f"{name:<14}", f"{decl.get(name, '?'):>6}", f"{weights.get(name, 0):>7,}f"]
        if official.get(name):
            parts.append(f'"{official[name][:40]}"')
        if binds.get(name):
            parts.append("cl=" + ",".join(binds[name][:3]))
        if vals.get(name):
            parts.append("v=" + "|".join(vals[name]))
        print("  ".join(parts))


if __name__ == "__main__":
    main()
