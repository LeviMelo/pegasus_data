"""Everything needed to describe one dataset's columns, on one screen.

The unit of this work is a **form**, not a column. A SINAN agravo is one
notification form whose columns are a cross-product — four limbs by three
modalities by two timepoints, or a block of exposure checkboxes — and describing
them one at a time re-derives the same context over and over. 79% of SINAN
columns belong to exactly one agravo, so the context is worth loading once and
spending across the whole form.

``brief.py`` prints one line per column for a whole *system*, which is the wrong
scope: it mixes fifty agravos together and shows value frequencies pooled across
all of them. This prints one *dataset*, and for each column gives the three
things that actually decide the description:

* the declared type and width, from the header census
* the codelist it is bound to, **with its values spelled out** — this is the
  part that is usually decisive and is usually not looked at. On the polio form
  it confirmed that ``CLI_A_F*`` is força and ``CLI_A_S*`` is sensibilidade, and
  it disproved a reading of ``LOCA_*`` that looked obvious and was wrong.
* what is already described, so a second pass does not redo it

Codelists that are artefacts of tabulating a date (ANOS, MESES, TRIME) are
marked as such rather than shown as evidence.

Usage::

    python scripts/formsheet.py CATALOG SINAN.VIOL
    python scripts/formsheet.py CATALOG SISCAN.CC --all      # described ones too
"""

from __future__ import annotations

import argparse
import collections
import io
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pegasus_data.ontology import Ontology  # noqa: E402

#: Groupings TabNet applies to a date column. Not evidence about the column.
SPURIOUS = {"ANOS", "MESES", "MESESC", "TRIME", "SEMANAS", "DIAS"}

DESCRIBED = """
SELECT system, field_name FROM field_documentation
 WHERE description IS NOT NULL AND TRIM(description) <> ''
   AND description NOT LIKE 'A column DATASUS tabulates%'
   AND description NOT LIKE 'A quantity DATASUS tabulates%'
UNION
SELECT system, field_name FROM variable_docs
 WHERE description IS NOT NULL AND TRIM(description) <> ''
"""


def main() -> None:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("catalog")
    ap.add_argument("dataset", help="ontology code, e.g. SINAN.VIOL")
    ap.add_argument("--all", action="store_true", help="include already-described columns")
    ap.add_argument("--values", type=int, default=10, help="codelist values to print")
    args = ap.parse_args()

    onto = Ontology.load()
    found = onto.resolve(args.dataset)
    if not found or found[0] != "dataset":
        print(f"{args.dataset!r} does not resolve to a dataset")
        raise SystemExit(1)
    node = found[1]

    conn = sqlite3.connect(f"file:{args.catalog}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row

    # Which crawled (system, series) pairs belong to this dataset, and their schemas.
    sigs: set[str] = set()
    systems: set[str] = set()
    for row in conn.execute(
        "SELECT DISTINCT system, series, schema_signature FROM strata "
        "WHERE system IS NOT NULL AND series IS NOT NULL AND schema_signature IS NOT NULL"
    ):
        if onto.bind(str(row["system"]), str(row["series"])).dataset == node.code:
            sigs.add(str(row["schema_signature"]))
            systems.add(str(row["system"]))
    if not sigs:
        print(f"{node.code}: no schema observed")
        raise SystemExit(0)

    marks = ",".join("?" for _ in sigs)
    cols: dict[str, tuple[str, int]] = {}
    order: dict[str, int] = {}
    for row in conn.execute(
        f"SELECT field_name, MAX(type_code) t, MAX(width) w, MIN(field_order) o "
        f"FROM schema_header_facts WHERE schema_signature IN ({marks}) GROUP BY field_name",
        tuple(sigs),
    ):
        cols[str(row["field_name"])] = (str(row["t"] or "?"), int(row["w"] or 0))
        order[str(row["field_name"])] = int(row["o"] or 0)
    for row in conn.execute(
        f"SELECT DISTINCT field_name FROM schema_presence WHERE schema_signature IN ({marks})",
        tuple(sigs),
    ):
        cols.setdefault(str(row["field_name"]), ("?", 0))

    done = {(str(a), str(b)) for a, b in conn.execute(DESCRIBED)}
    sysmarks = ",".join("?" for _ in systems)
    binds: dict[str, list[str]] = collections.defaultdict(list)
    for row in conn.execute(
        f"SELECT field_name, codelist FROM field_codelists WHERE system IN ({sysmarks})",
        tuple(systems),
    ):
        if str(row["field_name"]) in cols:
            binds[str(row["field_name"])].append(str(row["codelist"]))

    labels: dict[str, list[tuple[str, str]]] = collections.defaultdict(list)
    wanted = {c for v in binds.values() for c in v}
    if wanted:
        cmarks = ",".join("?" for _ in wanted)
        for row in conn.execute(
            f"SELECT DISTINCT value_group, value_raw, value_label FROM dictionary "
            f"WHERE value_group IN ({cmarks}) AND value_label <> '' "
            f"AND value_label NOT LIKE 'Ign%' AND value_raw NOT LIKE '%.CNV' "
            f"ORDER BY value_group, value_raw",
            tuple(wanted),
        ):
            labels[str(row["value_group"])].append(
                (str(row["value_raw"]), str(row["value_label"]))
            )

    vals: dict[str, list[str]] = collections.defaultdict(list)
    for row in conn.execute(
        f"SELECT vf.field_name f, vf.value v, SUM(vf.count) n FROM value_frequencies vf "
        f"JOIN families fa ON fa.family_id = vf.family_id WHERE fa.system IN ({sysmarks}) "
        f"GROUP BY 1,2 ORDER BY 3 DESC",
        tuple(systems),
    ):
        if str(row["f"]) in cols and len(vals[str(row["f"])]) < 6:
            vals[str(row["f"])].append(str(row["v"]).strip())
    conn.close()

    todo = [c for c in cols if (list(systems)[0], c) not in done and
            not any((s, c) in done for s in systems)]
    print(f"===== {node.code} — {node.translated_name or ''} =====")
    print(f"{node.official_name or ''}")
    if node.what_it_is:
        print(f"  {' '.join(node.what_it_is.split())}")
    print(f"  {len(cols)} columns in the family; {len(todo)} still to describe")
    print(f"  crawled as: {', '.join(sorted(systems))}; {len(sigs)} schema generations")

    # The codelists in play, spelled out once rather than per column.
    used = collections.Counter()
    for c in todo:
        for cl in binds.get(c, ()):
            if cl not in SPURIOUS and labels.get(cl):
                used[cl] += 1
    if used:
        print("\n--- codelists on this form (the decisive evidence) ---")
        for cl, n in used.most_common():
            shown = ", ".join(f"{a}={b}" for a, b in labels[cl][: args.values])
            print(f"  {cl:<14} {n:3d} cols  {shown[:150]}")

    print("\n--- columns ---")
    show = sorted(cols if args.all else todo, key=lambda c: (order.get(c, 9999), c))
    for c in show:
        t, w = cols[c]
        real = [x for x in binds.get(c, ()) if x not in SPURIOUS and labels.get(x)]
        spur = [x for x in binds.get(c, ()) if x in SPURIOUS]
        mark = "" if c in todo else "  [described]"
        bits = f"{t}({w})"
        if real:
            bits += f"  -> {','.join(real)}"
        elif spur:
            bits += f"  -> (date grouping only: {','.join(spur)})"
        if vals.get(c):
            bits += f"  seen: {', '.join(vals[c][:5])}"
        print(f"  {c:<14} {bits}{mark}")


if __name__ == "__main__":
    main()
