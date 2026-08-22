"""Find descriptions that do not distinguish a column from its siblings.

The failure this catches is specific and it has happened here before: an agent
handed a run of similar columns writes the same sentence for each, varying a
word. Thirty-seven CNES ``QTINST*`` columns once shared a description. It passes
every structural check — the field is present, the length is fine, the source is
declared — and it is worthless, because the reader still cannot tell the columns
apart.

Three things are measured, and they fail differently:

``duplicate``
    Two columns in one system whose descriptions are identical once normalised.
    Always wrong: if two columns really mean the same thing, say so in one and
    cross-reference from the other.

``near-duplicate``
    High token overlap. Usually a template with one noun swapped. Sometimes
    legitimate — a run of yes/no symptom flags is genuinely similar — so this is
    reported for judgement rather than as a verdict.

``boilerplate``
    A description that opens with the same stem as many others in its system.
    Catches "Sim/Não flag for ..." repeated eighty times, which is a description
    of the *encoding* rather than of the variable.

Usage::

    python scripts/audit_descriptions.py CATALOG              # every system
    python scripts/audit_descriptions.py CATALOG --system SINAN
    python scripts/audit_descriptions.py CATALOG --near 0.85  # stricter
"""

from __future__ import annotations

import argparse
import collections
import io
import re
import sqlite3
import sys

#: Words carrying no discriminating power when comparing two descriptions.
STOP = frozenset(
    ["a", "an", "the", "of", "for", "to", "in", "on", "and", "or", "is", "are", "was", "be", "been", "this", "that", "it", "its", "as", "by", "with", "from", "at", "not", "no", "yes", "one", "row", "rows", "column", "columns", "field", "value", "values", "which", "when", "whether", "where", "what", "who", "whom"]
)

DESCRIBED = """
SELECT system, field_name, description FROM variable_docs
 WHERE description IS NOT NULL AND TRIM(description) <> ''
UNION
SELECT system, field_name, description FROM field_documentation
 WHERE description IS NOT NULL AND TRIM(description) <> ''
"""


def normalise(text: str) -> str:
    return " ".join(str(text).lower().split())


def tokens(text: str) -> frozenset[str]:
    words = re.findall(r"[a-z0-9_]+", str(text).lower())
    return frozenset(w for w in words if w not in STOP and len(w) > 2)


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("catalog")
    ap.add_argument("--system")
    ap.add_argument("--near", type=float, default=0.9, help="token overlap to flag")
    ap.add_argument("--stem", type=int, default=6, help="leading words defining a stem")
    ap.add_argument("--limit", type=int, default=15)
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{args.catalog}?mode=ro", uri=True)
    rows = [
        (str(s), str(f), str(d))
        for s, f, d in conn.execute(DESCRIBED)
        if not args.system or str(s).upper() == args.system.upper()
    ]
    conn.close()

    by_system: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    for system, field, desc in rows:
        by_system[system].append((field, desc))

    grand = {"duplicate": 0, "near": 0, "boilerplate": 0, "total": len(rows)}
    for system in sorted(by_system):
        entries = by_system[system]
        print(f"\n=== {system}: {len(entries)} described ===")

        # 1. exact duplicates after normalising
        seen: dict[str, list[str]] = collections.defaultdict(list)
        for field, desc in entries:
            seen[normalise(desc)].append(field)
        dupes = {k: v for k, v in seen.items() if len(v) > 1}
        grand["duplicate"] += sum(len(v) for v in dupes.values())
        if dupes:
            print(f"  DUPLICATE descriptions: {len(dupes)} texts covering "
                  f"{sum(len(v) for v in dupes.values())} columns")
            for text, fields in sorted(dupes.items(), key=lambda kv: -len(kv[1]))[: args.limit]:
                print(f"    {len(fields):3d} columns: {', '.join(sorted(fields)[:6])}"
                      f"{' ...' if len(fields) > 6 else ''}")
                print(f"         \"{text[:110]}\"")
        else:
            print("  DUPLICATE descriptions: none")

        # 2. boilerplate openings
        stems: dict[str, list[str]] = collections.defaultdict(list)
        for field, desc in entries:
            words = normalise(desc).split()[: args.stem]
            if len(words) >= args.stem:
                stems[" ".join(words)].append(field)
        heavy = {k: v for k, v in stems.items() if len(v) >= 8}
        grand["boilerplate"] += sum(len(v) for v in heavy.values())
        if heavy:
            print(f"  BOILERPLATE openings: {len(heavy)} stems")
            for stem, fields in sorted(heavy.items(), key=lambda kv: -len(kv[1]))[: args.limit]:
                print(f"    {len(fields):3d} columns open \"{stem} ...\"")
        else:
            print("  BOILERPLATE openings: none")

        # 3. near-duplicates, compared only within a shared opening word so the
        #    comparison stays O(n * bucket) rather than O(n^2) across thousands.
        buckets: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
        for field, desc in entries:
            first = normalise(desc).split()
            buckets[first[0] if first else ""].append((field, desc))
        near: list[tuple[float, str, str]] = []
        for bucket in buckets.values():
            if len(bucket) < 2 or len(bucket) > 400:
                continue
            toks = [(f, tokens(d)) for f, d in bucket]
            for i in range(len(toks)):
                for j in range(i + 1, len(toks)):
                    score = jaccard(toks[i][1], toks[j][1])
                    if score >= args.near:
                        near.append((score, toks[i][0], toks[j][0]))
        grand["near"] += len(near)
        if near:
            near.sort(reverse=True)
            print(f"  NEAR-DUPLICATE pairs (>= {args.near:.2f} token overlap): {len(near)}")
            for score, a, b in near[: args.limit]:
                print(f"    {score:.2f}  {a}  ~  {b}")
        else:
            print("  NEAR-DUPLICATE pairs: none")

    print("\n=== totals ===")
    print(f"  described           {grand['total']}")
    print(f"  in a duplicate set  {grand['duplicate']}")
    print(f"  boilerplate opening {grand['boilerplate']}")
    print(f"  near-duplicate pairs{grand['near']:>5}")


if __name__ == "__main__":
    main()
