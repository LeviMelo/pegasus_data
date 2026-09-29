"""Build the canonical naturality/country table (ADR-0093).

DATASUS codes a person's naturality in 3 digits: 800 = Brasil, 8xx = a Brazilian
state (812 Acre), any other = a country (105 GUYANA). The full list is SIM's
TabWin table TABPAIS. SINASC's own NATURAL table is a tabulation grouping, not
a code list: it keeps Brasil and the states and maps every foreign country to
"Ignorado", which would call a foreign-born mother's birthplace unknown.

Source: the maintainer catalog's dictionary (SIM kit, TABPAIS).

    python scripts/build_countries.py [catalog]
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "pegasus_data" / "resources" / "countries.parquet"
CATALOG = ROOT / "pegasus_data_home" / "_catalog" / "catalog.sqlite"


def main() -> int:
    catalog = Path(sys.argv[1]) if len(sys.argv) > 1 else CATALOG
    con = sqlite3.connect(f"file:{catalog}?mode=ro", uri=True)
    table: dict[str, str] = {}
    for code, label in con.execute(
        "SELECT value_raw, value_label FROM dictionary WHERE value_group = 'TABPAIS' AND system = 'SIM'"
    ):
        code = str(code).strip()
        if len(code) == 3 and code.isdigit() and label:
            table[code] = str(label).strip().title()
    codes = sorted(table)
    pq.write_table(pa.table({"code": codes, "label": [table[c] for c in codes]}), OUT, compression="zstd")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(codes)} codes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
