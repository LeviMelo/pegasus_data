"""Codes decoded only by a catch-all range (ADR-0108).

TabWin `.CNV` files group codes for display: a range such as "00-99 Ignorado"
or "2-4 Outras/ignorado" gives every code in it a confident label, although
no document names those codes. This audit runs the sweep's slices through
`query`, and for every coded column lists the observed codes that no bound
table names individually and that fall inside a range whose label is a
residual word (ignorado, outros, não se aplica, não informado, demais, sem
informação). Each is a code that reads as decoded and is not.

    PEGASUS_DATA_HOME=~/pegasus_fresh python scripts/catchall_audit.py [out.json]
"""

from __future__ import annotations

import json
import re
import sys
import warnings
from collections import Counter
from pathlib import Path

import pyarrow.compute as pc
import pyarrow.parquet as pq

import pegasus_data as p

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sweep_undecoded import SLICES  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
PACK = ROOT / "src" / "pegasus_data" / "resources" / "labels.parquet"
RESIDUAL = re.compile(r"(?i)ignor|outr[oa]s?\b|n[ãa]o se aplica|n[ãa]o informad|demais|sem inform|inv[áa]lid|em branco")


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "probes" / "catchall_audit.json"
    pack = pq.read_table(PACK, columns=["codelist", "code_lo", "code_hi", "label"])
    results = []
    for dataset, period, geography in SLICES:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                table, report = p.query(dataset, period=period, geography=geography, present="analysis",
                                        return_report=True)
        except Exception as exc:  # noqa: BLE001 - a slice that fails is reported, not fatal
            print(f"{dataset}: {type(exc).__name__}: {str(exc)[:120]}", flush=True)
            continue
        sources = report.source_report if isinstance(report.source_report, list) else [report.source_report]
        used: dict[str, str] = {}
        for src in sources:
            render = getattr(src, "render", None)
            used.update(getattr(render, "codelist_used", {}) or {})
        for column, lists in sorted(used.items()):
            if column not in table.column_names or lists.startswith(("column ", "CURATED")) or " via " in lists:
                continue
            names = [n for n in lists.split("+") if n and not n.startswith("CURATED")]
            rows = pack.filter(pc.is_in(pack["codelist"], value_set=__import__("pyarrow").array(names)))
            if not rows.num_rows:
                continue
            singles = {lo for lo, hi in zip(rows["code_lo"].to_pylist(), rows["code_hi"].to_pylist(), strict=True) if lo == hi}
            ranges = [(lo, hi, lab) for lo, hi, lab in zip(rows["code_lo"].to_pylist(), rows["code_hi"].to_pylist(),
                                                           rows["label"].to_pylist(), strict=True)
                      if lo != hi and lab and RESIDUAL.search(lab)]
            if not ranges:
                continue
            codes = [str(v).strip() if v is not None else "" for v in table.column(column).to_pylist()]
            label_col = f"{column}_label"
            labels = table.column(label_col).to_pylist() if label_col in table.column_names else [None] * len(codes)
            rendered = {}
            for code, lab in zip(codes, labels, strict=True):
                rendered.setdefault(code, lab)
            counts = Counter(c for c in codes if c)
            hidden = []
            for code, n in counts.items():
                # Named individually somewhere, decoded by a meaningful label
                # (a higher-priority table's range: SIH SEXO 3 "Feminino"), or
                # the conventional all-9 "ignorado": not a hidden code.
                if code in singles or set(code) == {"9"}:
                    continue
                if not (rendered.get(code) and RESIDUAL.search(str(rendered[code]))):
                    continue
                for lo, hi, lab in ranges:
                    if len(code) == len(lo) == len(hi) and lo <= code <= hi:
                        hidden.append({"code": code, "rows": n, "range": f"{lo}-{hi}", "label": lab})
                        break
            if hidden:
                hidden.sort(key=lambda h: -h["rows"])
                results.append({"dataset": dataset, "period": period, "geography": geography, "column": column,
                                "codelists": lists, "codes": len(hidden), "rows": sum(h["rows"] for h in hidden),
                                "examples": hidden[:8]})
                print(f"{dataset} {column}: {len(hidden)} codes, {sum(h['rows'] for h in hidden)} rows "
                      f"via {hidden[0]['range']} '{hidden[0]['label']}'", flush=True)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"wrote {out_path}: {len(results)} columns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
