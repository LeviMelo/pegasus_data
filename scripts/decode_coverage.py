"""How far the coded columns decode on real records, as a reader meets them.

For every lake family, the first 20,000 records of its latest partition go through the renderer itself
(`view.render_table`, what `query` applies). For each column whose role is coded (kind category or code_tree) it
records whether the column was labelled, by which table, and the share of its coded cells that got a label (the
`<column>_label` beside the code, null where no table held the code) with the commonest code=label pairs, to be read.
A column left unlabelled is split by its values: words as filed ("SAÍDA DO TRATAMENTO") read as they
are; codes ("12", "M") are the gaps. Read-only: the lake's files, the catalog and the reference tables.

    python scripts/decode_coverage.py --root C:/Users/Galaxy/pegasus_core_data --out data/probes/decode_coverage/DATE.json
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

import pegasus_data as pg
from pegasus_data.api import Catalog
from pegasus_data.view import render_table

SAMPLE = 20_000
BARE = re.compile(r"^(.*) \(\?\)$")
WORD = re.compile(r"[A-Za-zÀ-ÿ]{3,}")


def family_sample(catalog: Catalog) -> dict[str, dict]:
    """Each lake family's latest partition (its largest of that year)."""
    rows = catalog.store.query(
        "SELECT f.family_id, f.system, f.series, p.relative_path, p.year FROM families f "
        "JOIN lake_partitions p ON p.family_id = f.family_id ORDER BY f.family_id, p.year DESC, p.row_count DESC")
    latest: dict[str, dict] = {}
    for r in rows:
        latest.setdefault(r["family_id"], dict(r))
    return latest


def measure(catalog: Catalog, family_id: str, r: dict) -> dict:
    lake = Path(catalog.settings.lake_dir)
    system, series = str(r["system"]).upper(), str(r["series"] or "").upper()
    entry = {"family": family_id, "dataset": f"{system}-{series}", "year": r["year"], "columns": []}
    roles = pg.roles(entry["dataset"], period=int(r["year"]))
    coded = {x["column"].upper() for x in roles if x.get("kind") in ("category", "code_tree")}
    raw = pa.Table.from_batches([next(pq.ParquetFile(lake / r["relative_path"]).iter_batches(batch_size=SAMPLE))])
    rendered, rep = render_table(raw, store=catalog.store, lake_root=lake, system=system, family_id=family_id,
                                 year=int(r["year"]), registries=catalog.settings.registries_dir)
    raw_names = {n.upper(): n for n in raw.column_names}
    for name in rendered.column_names:
        col = name.upper()
        if col not in coded:
            continue
        cells = pc.drop_null(rendered.column(name))
        if len(cells) == 0 or name in rep.constant:
            entry["columns"].append({"column": col, "state": "empty or constant"})
            continue
        if name in rep.labelled:
            # the label sits in the column beside the code (`<name>_label`), null where no table held the code: the share
            # of the code's cells that got one (this read the code column itself, where "(?)" never appears, and so
            # reported 100 % for every column, 2026-10-23)
            label_col = f"{name}_label"
            if label_col in rendered.column_names:
                pairs = Counter(zip(rendered.column(name).to_pylist(), rendered.column(label_col).to_pylist(), strict=True))
                n_coded = sum(n for (code, _), n in pairs.items() if code is not None)
                got = sum(n for (code, lab), n in pairs.items() if code is not None and lab is not None)
                share = got / max(1, n_coded)
                top = [f"{code}={lab}" for (code, lab), _ in pairs.most_common(6) if code is not None]
            else:
                texts = Counter(cells.to_pylist())
                share = 1 - sum(n for t, n in texts.items() if BARE.match(str(t))) / len(cells)
                top = []
            entry["columns"].append({"column": col, "state": "labelled", "table": rep.codelist_used.get(name),
                                     "share": round(share, 4), "top": top})
            continue
        values = Counter(str(v).strip() for v in raw.column(raw_names.get(col, name)).to_pylist()
                         if v is not None and str(v).strip())
        words = sum(n for v, n in values.items() if WORD.search(v)) / max(1, sum(values.values()))
        entry["columns"].append({"column": col, "state": "words as filed" if words > 0.8 else "codes left bare",
                                 "distinct": len(values), "top": [v for v, _ in values.most_common(5)]})
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
