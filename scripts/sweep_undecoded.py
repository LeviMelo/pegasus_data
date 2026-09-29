"""Live sweep: which coded columns leave values undecoded, dataset by dataset.

Runs one small slice of each dataset through ``query`` (the user's path), and
for every column that has a label companion counts the values that stayed
undecoded ("code (?)"). The output is the worklist for "every code
translatable": each entry is a code no source has named yet, or a binding that
is wrong. Run it against a FRESH home (CLAUDE.md §5):

    PEGASUS_DATA_HOME=~/pegasus_live/home python scripts/sweep_undecoded.py [out.json]
"""

from __future__ import annotations

import json
import sys
import time
import warnings
from collections import Counter
from pathlib import Path

import pegasus_data as p

#: (dataset, period, geography). Small slices: a state-month or a state-year.
SLICES = [
    ("SIH-RD", "2023-01", "AC"),
    ("SIH-SP", "2023-01", "AC"),
    ("SIM-DO", "2022", "AC"),
    ("SINASC-DN", "2022", "AC"),
    ("CIHA", "2023-01", "AC"),
    ("CNES-ST", "2023-01", "AC"),
    ("CNES-PF", "2023-01", "AC"),
    ("CNES-EP", "2023-01", "AC"),
    ("CNES-SR", "2023-01", "AC"),
    ("SIASUS-PA", "2023-01", "AC"),
    ("SIASUS-AQ", "2023-01", "AC"),
    ("SIASUS-AR", "2023-01", "AC"),
    ("SIASUS-AM", "2023-01", "AC"),
    ("SIASUS-BI", "2023-01", "AC"),
    ("SIASUS-PS", "2023-01", "AC"),
    ("SINAN-HANS", "2022", None),
]


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/probes/live/sweep_undecoded.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    results = []
    for dataset, period, geo in SLICES:
        entry: dict[str, object] = {"dataset": dataset, "period": period, "geography": geo}
        started = time.time()
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                table = p.query(dataset, period=period, geography=geo, present="analysis",
                                allow_partial=True, max_download=300 * 2**20)
        except Exception as exc:  # noqa: BLE001 - a failed slice is a finding
            entry["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
            results.append(entry)
            print(dataset, "ERROR", entry["error"][:160], flush=True)
            continue
        entry["seconds"] = round(time.time() - started, 1)
        entry["rows"] = table.num_rows
        names = set(table.column_names)
        coded = [n for n in table.column_names if f"{n}_label" in names]
        entry["coded_columns"] = len(coded)
        undecoded: dict[str, object] = {}
        for name in coded:
            miss = Counter(
                str(v) for v, lab in zip(table.column(name).to_pylist(), table.column(f"{name}_label").to_pylist(), strict=True)
                if v not in (None, "") and str(v).strip() and lab is None
            )
            if miss:
                undecoded[name] = {"rows": sum(miss.values()), "top": miss.most_common(5)}
        entry["undecoded"] = undecoded
        results.append(entry)
        print(dataset, entry["rows"], "rows", entry["seconds"], "s;", len(coded), "coded;",
              len(undecoded), "with undecoded values", flush=True)
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("wrote", out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
