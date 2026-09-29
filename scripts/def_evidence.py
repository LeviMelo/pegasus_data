"""For undecoded columns, what the kits' own .DEF files bind them to, and whether it fits.

Reads a sweep (``scripts/sweep_undecoded.py``) and, for each column with
undecoded values, lists the ``.CNV`` tables the owning system's ``.DEF`` files
tabulate that field with, and how many of the column's undecoded codes each
table names. A table that names them all is the evidence for a curated
binding; none naming them means the codes are unpublished (or the column is
not a code at all).

    python scripts/def_evidence.py data/probes/live/sweep_undecoded.json [catalog]
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

SYSTEM_OF = {"SIH": "SIHSUS", "SIM": "SIM", "SINASC": "SINASC", "CIHA": "CIHA", "CNES": "CNES",
             "SIASUS": "SIASUS", "SINAN": "SINAN"}


def main() -> int:
    sweep = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    catalog = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("pegasus_data_home/_catalog/catalog.sqlite")
    con = sqlite3.connect(f"file:{catalog}?mode=ro", uri=True, timeout=120)
    for entry in sweep:
        system = SYSTEM_OF.get(str(entry["dataset"]).split("-")[0], str(entry["dataset"]).split("-")[0])
        for field, found in (entry.get("undecoded") or {}).items():
            codes = [c for c, _ in found["top"]]
            refs = sorted({
                str(r[0]).replace("\\", "/").rsplit("/", 1)[-1].rsplit(".", 1)[0].upper()
                for r in con.execute(
                    "SELECT DISTINCT lookup_ref FROM def_variables WHERE system=? AND upper(field_name)=? "
                    "AND lookup_ref IS NOT NULL", (system, field.upper()))
            })
            fits = []
            for ref in refs:
                named = con.execute(
                    f"SELECT value_raw, value_label FROM dictionary WHERE system=? AND value_group=? "
                    f"AND value_raw IN ({','.join('?' * len(codes))})", (system, ref, *codes)).fetchall()
                fits.append((ref, len({v for v, _ in named}), dict(named)))
            print(f"{entry['dataset']} {field} rows={found['rows']} codes={codes}")
            for ref, n, named in fits:
                print(f"    {ref}: names {n}/{len(codes)} {str(named)[:160]}")
            if not refs:
                print("    (no .DEF binds this field)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
