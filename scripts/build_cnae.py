"""Build the canonical CNAE 2.0 table economic-activity fields decode with (ADR-0087).

Source: IBGE's CONCLA classification served by the Localidades/CNAE API
(``servicodados.ibge.gov.br/api/v2/cnae``): 673 classes (5 digits, with their
check digit) and 1,332 subclasses (7 digits). The responses are kept under
``sources/ibge_cnae/`` so a rebuild does not depend on the API.

SINAN's own kit table ``CNAENET.DBF`` holds CNAE 1.0 classes, and its records
carry both versions (ACGR 2023: 85111 "Atividades de atendimento hospitalar"
in 1.0, 41204 "Construção de edifícios" in 2.0). The two versions share no
class code (0 of 580 against 673, 2026-10-03), so both tables can decode one
column without ambiguity.

Writes ``src/pegasus_data/resources/cnae20.parquet`` (code, label, level, source).

    python scripts/build_cnae.py
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "sources" / "ibge_cnae"
OUT = ROOT / "src" / "pegasus_data" / "resources" / "cnae20.parquet"
API = "https://servicodados.ibge.gov.br/api/v2/cnae/"
LEVELS = {"classes": "class", "subclasses": "subclass"}


def _fetch(level: str) -> list[dict]:
    cached = CACHE / f"{level}.json"
    if not cached.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(API + level, headers={"Accept-Encoding": "identity"})
        with urllib.request.urlopen(request, timeout=300) as response:
            cached.write_bytes(response.read())
    return json.loads(cached.read_text(encoding="utf-8"))


def main() -> int:
    codes, labels, levels = [], [], []
    for level, name in LEVELS.items():
        for item in _fetch(level):
            codes.append(str(item["id"]))
            labels.append(" ".join(str(item["descricao"]).split()).capitalize())
            levels.append(name)
    if len(set(codes)) != len(codes):
        raise SystemExit("CNAE codes repeat across levels")
    table = pa.table({"code": codes, "label": labels, "level": levels,
                      "source": ["IBGE CONCLA CNAE 2.0 (servicodados API v2)"] * len(codes)})
    pq.write_table(table, OUT)
    print(f"wrote {OUT.name}: {sum(1 for x in levels if x == 'class')} classes, "
          f"{sum(1 for x in levels if x == 'subclass')} subclasses")
    return 0


if __name__ == "__main__":
    sys.exit(main())
