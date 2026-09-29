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

It also writes the BRIDGE across the 2008 change of classification
(ADR-0101): the official Tabela Unificada ships ``tb_sia_sih`` (8,293 of the
pre-2008 SIA and SIH procedure codes, with their names) and
``rl_procedimento_sia_sih`` (which SIGTAP procedure replaced each one). From a
local copy of that zip (``sources/sigtap/new.zip``, competence 2026-08).

    python scripts/build_sigtap.py [catalog] [tabela-unificada.zip]
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "src" / "pegasus_data" / "resources" / "sigtap.parquet"
BRIDGE = ROOT / "src" / "pegasus_data" / "resources" / "sigtap_bridge.parquet"
TUP = ROOT / "sources" / "sigtap" / "new.zip"
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
    tup = Path(sys.argv[2]) if len(sys.argv) > 2 else TUP
    if tup.is_file():
        write_bridge(tup)
    return 0


def write_bridge(tup: Path) -> None:
    """Old SIA/SIH procedure -> the SIGTAP procedure(s) that replaced it."""
    import zipfile

    with zipfile.ZipFile(tup) as z:
        names = {
            line[0:10].strip(): (line[10:110].strip(), line[110:111])
            for line in z.read("tb_sia_sih.txt").decode("latin-1").splitlines() if line.strip()
        }
        rows = []
        for line in z.read("rl_procedimento_sia_sih.txt").decode("latin-1").splitlines():
            if not line.strip():
                continue
            new, old, kind, competence = line[0:10].strip(), line[10:20].strip(), line[20:21], line[21:27]
            rows.append((old, kind, names.get(old, ("", ""))[0] or None, new, competence))
    rows.sort()
    pq.write_table(pa.table({
        "old_code": [r[0] for r in rows], "old_system": [r[1] for r in rows],
        "old_label": [r[2] for r in rows], "sigtap_code": [r[3] for r in rows],
        "competence": [r[4] for r in rows],
    }), BRIDGE, compression="zstd")
    print(f"wrote {BRIDGE.relative_to(ROOT)}: {len(rows)} links from {len({r[0] for r in rows})} old codes")


if __name__ == "__main__":
    sys.exit(main())
