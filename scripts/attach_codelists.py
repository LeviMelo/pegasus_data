"""Attach the catalog's codelist bindings to a curation file.

Writing ``code_system`` and ``source_ref`` by hand for a hundred columns is both
slow and unreliable, and it is the machine's job: the catalog already knows
which ``.CNV`` each column is bound to, harvested from DATASUS's own TabWin
kits. This copies that knowledge into the curation file, so the human effort
goes into the prose — which is the part that cannot be derived.

Two kinds of binding are refused:

*Date groupings.* ANOS, MESES, MESESC and TRIME are what TabNet offers when you
tabulate a date column. They are not evidence about what the column holds, and
recording one as a codelist would state something false.

*Codelists with no usable labels.* A binding whose values are all "Ign/Branco"
decodes nothing, so it is not worth citing.

Anything already carrying ``code_system`` other than ``none`` is left alone: a
human decision outranks this.

Usage::

    python scripts/attach_codelists.py CATALOG curation/variables/sinan_viol.yml
    python scripts/attach_codelists.py CATALOG FILE --dry-run
"""

from __future__ import annotations

import argparse
import collections
import io
import re
import sqlite3
import sys
from pathlib import Path

#: Groupings TabNet applies to a date. Not a codelist for the column.
SPURIOUS = {"ANOS", "MESES", "MESESC", "TRIME", "SEMANAS", "DIAS"}

_KEY = re.compile(r"^  ([A-Z][A-Z0-9_]*):\s*$")


def bindings(conn: sqlite3.Connection, system: str) -> dict[str, str]:
    """One usable codelist per column, or nothing."""
    usable: set[str] = set()
    for (group,) in conn.execute(
        "SELECT DISTINCT value_group FROM dictionary "
        "WHERE value_group IS NOT NULL AND value_label <> '' "
        "AND value_label NOT LIKE 'Ign%' AND value_raw NOT LIKE '%.CNV'"
    ):
        usable.add(str(group))

    per: dict[str, list[str]] = collections.defaultdict(list)
    for field, codelist in conn.execute(
        "SELECT field_name, codelist FROM field_codelists WHERE system = ?", (system,)
    ):
        cl = str(codelist)
        if cl in SPURIOUS or cl not in usable:
            continue
        per[str(field)].append(cl)
    # A column bound to many codelists is usually a geography column carrying one
    # per state; picking the shortest name gets the general one (MUNICBR over
    # MUNICAC) rather than an arbitrary state's.
    return {f: sorted(cls, key=lambda c: (len(c), c))[0] for f, cls in per.items() if cls}


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("catalog")
    ap.add_argument("file")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    path = Path(args.file)
    lines = path.read_text(encoding="utf-8").split("\n")

    import yaml

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    system = str(doc.get("system", "")).upper()

    conn = sqlite3.connect(f"file:{args.catalog}?mode=ro", uri=True)
    bound = bindings(conn, system)
    conn.close()

    out: list[str] = []
    current: str | None = None
    touched: list[tuple[str, str]] = []
    # Track whether this entry already declares a code_system the human set.
    entry_start: dict[str, int] = {}
    for i, line in enumerate(lines):
        mo = _KEY.match(line)
        if mo:
            current = mo.group(1)
            entry_start[current] = i
        out.append(line)

    # Second pass: rewrite the two lines inside each entry that we own.
    result: list[str] = []
    current = None
    manual = False
    for line in out:
        mo = _KEY.match(line)
        if mo:
            current = mo.group(1)
            manual = False
        cl = bound.get(current or "")
        if cl and line.strip() == "code_system: none" and not manual:
            result.append("    code_system: internal")
            touched.append((current or "", cl))
            manual = True
            continue
        if cl and manual and line.strip() == "source: inferred":
            result.append("    source: def")
            result.append(f"    source_ref: {cl}.CNV")
            continue
        result.append(line)

    if args.dry_run:
        for name, cl in touched:
            print(f"  {name:<14} -> {cl}")
        print(f"would attach a codelist to {len(touched)} columns")
        return

    path.write_text("\n".join(result), encoding="utf-8")
    print(f"attached a codelist to {len(touched)} columns in {path.name}")
    used = collections.Counter(cl for _, cl in touched)
    for cl, n in used.most_common(12):
        print(f"  {cl:<16} {n}")


if __name__ == "__main__":
    main()
