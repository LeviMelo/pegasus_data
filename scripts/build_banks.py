"""Build the canonical bank-code table (ADR-0087): CNES's CO_BANCO and similar.

Source: Banco Central do Brasil, "Participantes do STR"
(https://www.bcb.gov.br/content/estabilidadefinanceira/str1/ParticipantesSTR.csv,
saved as ``sources/ParticipantesSTR.csv``): the 3-digit compensation code and
each institution's full name. It is the CURRENT register: a bank that closed or
merged before the download is absent, and its code stays visibly undecoded.

    python scripts/build_banks.py
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "sources" / "ParticipantesSTR.csv"
OUT = ROOT / "src" / "pegasus_data" / "resources" / "banks.parquet"


def main() -> int:
    rows = list(csv.DictReader(SOURCE.read_text(encoding="utf-8-sig").splitlines()))
    table: dict[str, str] = {}
    for r in rows:
        code = (r.get("Número_Código") or "").strip()
        name = (r.get("Nome_Extenso") or r.get("Nome_Reduzido") or "").strip()
        if code.isdigit() and name:
            table[code.zfill(3)] = name
    codes = sorted(table)
    pq.write_table(pa.table({"code": codes, "label": [table[c] for c in codes]}), OUT, compression="zstd")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(codes)} banks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
