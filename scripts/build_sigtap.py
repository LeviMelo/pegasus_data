"""Build the canonical SIGTAP table every procedure field decodes with (ADR-0092).

SIGTAP (the SUS "Tabela Unificada de Procedimentos", since 2008) is a
hierarchy: group (2 digits, ``04`` Procedimentos cirúrgicos) > subgroup (4,
``0411`` Cirurgia obstétrica) > form of organisation (6) > procedure (10,
``0411010034`` PARTO CESARIANO). The kits of SIH and SIA carry each level as
its own table (TB_GRUPO, TB_SUBGR, TB_FORMA, TB_SIGTAP / TB_SIGTAW), and each
system's copy covers the procedures that system bills. One table holds the
union, every level, the longest label seen for each code.

The official source (ftp2.datasus.gov.br/pub/sistemas/tup) was unreachable on
2026-09-29; the kit tables are DATASUS's own copies of it.

    python scripts/build_sigtap.py [catalog]
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "pegasus_data" / "resources" / "sigtap.parquet"
CATALOG = ROOT / "pegasus_data_home" / "_catalog" / "catalog.sqlite"
LEVELS = {"TB_GRUPO": ("group", 2), "TB_SUBGR": ("subgroup", 4), "TB_FORMA": ("form", 6),
          "TB_SIGTAP": ("procedure", 10), "TB_SIGTAW": ("procedure", 10)}


def main() -> int:
    catalog = Path(sys.argv[1]) if len(sys.argv) > 1 else CATALOG
    con = sqlite3.connect(f"file:{catalog}?mode=ro", uri=True)
    best: dict[str, tuple[str, str]] = {}
    marks = ",".join("?" * len(LEVELS))
    for group, code, label in con.execute(
        f"SELECT value_group, value_raw, value_label FROM dictionary WHERE value_group IN ({marks}) "
        "AND value_label IS NOT NULL",
        tuple(LEVELS),
    ):
        level, width = LEVELS[group]
        code = str(code).strip()
        if len(code) != width or not code.isdigit():
            continue
        text = str(label).strip()
        if len(text) > len(best.get(code, ("", ""))[0]):
            best[code] = (text, level)
    codes = sorted(best)
    pq.write_table(
        pa.table({"code": codes, "label": [best[c][0] for c in codes], "level": [best[c][1] for c in codes]}),
        OUT, compression="zstd",
    )
    counts: dict[str, int] = {}
    for c in codes:
        counts[best[c][1]] = counts.get(best[c][1], 0) + 1
    print(f"wrote {OUT.relative_to(ROOT)}: {len(codes)} codes {counts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
