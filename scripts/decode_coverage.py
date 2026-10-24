"""How far the coded columns decode on real records, as a reader meets them.

For every lake family, the WHOLE latest partition's coded columns (role kind category or code_tree) go through the
renderer itself (`view.render_table`, what `query` applies), eight columns at a time. The renderer's table choice weighs
the rows it is given, so all of them are given, and a code that appears late in a file is counted. The first 20,000
records had stood for the file until 2026-10-24, and missed SINAN-DENG 2024's `CLASSI_FIN` 8 (542,641 rows) and
`SOROTIPO` 0 (131,058). For each column it records:
* whether the column was labelled, and by which table;
* the share of its coded cells that got a label (the `<column>_label` beside the code, null where no table held the
  code);
* the commonest code=label pairs, to be read, and the codes left bare with their counts.

A column left unlabelled is split by its values: words as filed ("SAÍDA DO TRATAMENTO") read as they are; codes ("12",
"M") are the gaps. Read-only: the lake's files, the catalog and the reference tables.

    python scripts/decode_coverage.py --root C:/Users/Galaxy/pegasus_core_data --out data/probes/decode_coverage/DATE.json
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

import pegasus_data as pg
from pegasus_data.api import Catalog
from pegasus_data.view import render_table

GROUP = 8
WORD = re.compile(r"[A-Za-zÀ-ÿ]{3,}")


def family_sample(catalog: Catalog) -> dict[str, dict]:
    """Each lake family's latest partition on disk (its largest of that year)."""
    lake = Path(catalog.settings.lake_dir)
    rows = catalog.store.query(
        "SELECT f.family_id, f.system, f.series, p.relative_path, p.year FROM families f "
        "JOIN lake_partitions p ON p.family_id = f.family_id ORDER BY f.family_id, p.year DESC, p.row_count DESC")
    latest: dict[str, dict] = {}
    for r in rows:
        if (lake / r["relative_path"]).is_file():
            latest.setdefault(r["family_id"], dict(r))
    return latest


def measure(catalog: Catalog, family_id: str, r: dict) -> dict:
    lake = Path(catalog.settings.lake_dir)
    system, series = str(r["system"]).upper(), str(r["series"] or "").upper()
    entry = {"family": family_id, "dataset": f"{system}-{series}", "year": r["year"], "columns": []}
    roles = pg.roles(entry["dataset"], period=int(r["year"]))
    coded = {x["column"].upper() for x in roles if x.get("kind") in ("category", "code_tree")}
    parquet = pq.ParquetFile(lake / r["relative_path"])
    entry["rows"] = parquet.metadata.num_rows
    names = [n for n in parquet.schema_arrow.names if n.upper() in coded]
    for i in range(0, len(names), GROUP):
        raw = parquet.read(columns=names[i:i + GROUP])
        rendered, rep = render_table(raw, store=catalog.store, lake_root=lake, system=system, family_id=family_id,
                                     year=int(r["year"]), registries=catalog.settings.registries_dir)
        for name in raw.column_names:
            codes = [None if v is None or not str(v).strip() else str(v).strip() for v in raw.column(name).to_pylist()]
            filled = Counter(v for v in codes if v is not None)
            if not filled or name in rep.constant:
                entry["columns"].append({"column": name.upper(), "state": "empty or constant"})
                continue
            label_col = f"{name}_label"
            if name in rep.labelled and label_col in rendered.column_names:
                pairs = Counter(zip(codes, rendered.column(label_col).to_pylist(), strict=True))
                bare = Counter({code: n for (code, lab), n in pairs.items() if code is not None and lab is None})
                entry["columns"].append({"column": name.upper(), "state": "labelled", "table": rep.codelist_used.get(name),
                                         "share": round(1 - sum(bare.values()) / sum(filled.values()), 4),
                                         "bare": bare.most_common(8),
                                         "top": [f"{c}={lab}" for (c, lab), _ in pairs.most_common(6) if c is not None]})
                continue
            words = sum(n for v, n in filled.items() if WORD.search(v)) / sum(filled.values())
            entry["columns"].append({"column": name.upper(), "state": "words as filed" if words > 0.8 else "codes left bare",
                                     "distinct": len(filled), "top": [v for v, _ in filled.most_common(5)]})
    return entry


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    catalog = Catalog(root=args.root)
    out = []
    for family_id, r in sorted(family_sample(catalog).items()):
        try:
            out.append(measure(catalog, family_id, r))
        except Exception as e:  # noqa: BLE001 - a family that cannot be read is listed with why, not skipped
            out.append({"family": family_id, "dataset": f"{r['system']}-{r['series']}", "error": f"{type(e).__name__}: {e}"})
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, indent=1, default=str, ensure_ascii=False), encoding="utf-8")
    latest: dict[str, dict] = {}
    for e in out:
        if not e.get("error") and (e["dataset"] not in latest or e["year"] > latest[e["dataset"]]["year"]):
            latest[e["dataset"]] = e
    states = Counter(c["state"] for e in latest.values() for c in e["columns"])
    filled = sum(n for s, n in states.items() if s != "empty or constant")
    partial = sum(1 for e in latest.values() for c in e["columns"] if c["state"] == "labelled" and c.get("share", 1) < 0.95)
    print(f"{len(latest)} datasets, {len(out)} families ({sum(1 for e in out if e.get('error'))} unreadable); "
          f"coded columns holding values {filled}: " + ", ".join(f"{s} {n}" for s, n in states.most_common())
          + f"; labelled columns whose labels reach under 95 % of their codes: {partial}")


if __name__ == "__main__":
    main()
