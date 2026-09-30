"""Build the canonical CBO 2002 table every occupation field decodes with (ADR-0087).

Sources, best first:

1. The official Classificação Brasileira de Ocupações 2002 structure (Ministério
   do Trabalho, ``sources/estrutura-cbo.zip``): 2,695 occupations (6 digits),
   plus the family, subgroup, principal subgroup and major group levels (4, 3,
   2 and 1 digits). SIM's own CBO table lacked common occupations (622315
   "Trabalhador na olericultura", 782510 "Motorista de caminhão"); 262 of 23,122
   deaths in Alagoas 2022 carried a code no system table decoded.
2. DATASUS's extension codes, which are not occupations in CBO but are used as
   one in its records (999993 "Aposentado/Pensionista", 999992 "Dona de
   Casa"), taken from the kit tables in the maintainer catalog's dictionary.

Writes ``src/pegasus_data/resources/cbo2002.parquet`` (code, label, level, source).

    python scripts/build_cbo.py [catalog]
"""

from __future__ import annotations

import csv
import io
import re
import sqlite3
import sys
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "sources" / "estrutura-cbo.zip"
OUT = ROOT / "src" / "pegasus_data" / "resources" / "cbo2002.parquet"
CATALOG = ROOT / "pegasus_data_home" / "_catalog" / "catalog.sqlite"
LEVELS = {
    "CBO2002 - Grande Grupo.csv": "major group",
    "CBO2002 - SubGrupo Principal.csv": "principal subgroup",
    "CBO2002 - SubGrupo.csv": "subgroup",
    "CBO2002 - Familia.csv": "family",
    "CBO2002 - Ocupacao.csv": "occupation",
}


def official() -> dict[str, tuple[str, str]]:
    out: dict[str, tuple[str, str]] = {}
    with zipfile.ZipFile(SOURCE) as zf:
        for name, level in LEVELS.items():
            text = zf.read(name).decode("latin-1")
            for row in csv.DictReader(io.StringIO(text), delimiter=";"):
                code = (row.get("CODIGO") or "").strip()
                title = re.sub(r"\s+", " ", (row.get("TITULO") or "").strip())
                if code and title:
                    out[code] = (title, level)
    return out


def extensions(catalog: Path, known: set[str]) -> dict[str, tuple[str, str]]:
    """Six-digit codes the kits carry that CBO 2002 does not (DATASUS's own)."""
    if not catalog.exists():
        return {}
    con = sqlite3.connect(f"file:{catalog}?mode=ro", uri=True)
    # Several kits name the same code; a .CNV often glues synonyms onto a
    # label ("MEDICO CLINICO  CLINICO GERAL MEDICO CLINICO GERAL MEDICO" for
    # 223115) while CNES's DBF has it as a column ("Médico clínico"). A DBF
    # label wins, then an accented one, the most common, the shorter (ADR-0104).
    from collections import Counter

    seen: dict[str, Counter] = {}
    for code, label, source in con.execute(
        "SELECT value_raw, value_label, source FROM dictionary "
        "WHERE upper(value_group) IN ('CBO', 'CBO2002', 'CBO_02', 'OCUPACAO', 'MEDIC_02') "
        "AND value_label IS NOT NULL"
    ):
        code = str(code).strip()
        # Six characters: the Ministry of Health's own occupations use letters
        # (CNES 2231F9, 5152A1) where CBO has none.
        if not re.fullmatch(r"[0-9A-Z]{6}", code) or code in known:
            continue
        text = re.sub(r"\s+", " ", re.sub(r"^\d{4}[-.]?\d{2}\s+", "", str(label).strip()))
        seen.setdefault(code, Counter())[(source == "dbf_lookup", text)] += 1
    best = {
        # ... and of two spellings of one text, the accented ("Médico clínico").
        code: max(counts.items(), key=lambda kv: (kv[0][0], not kv[0][1].isascii(), kv[1], -len(kv[0][1])))[0][1]
        for code, counts in seen.items()
    }
    return {c: (lbl, "not in the current CBO 2002") for c, lbl in best.items()}


def main() -> int:
    catalog = Path(sys.argv[1]) if len(sys.argv) > 1 else CATALOG
    table = official()
    source = dict.fromkeys(table, "cbo2002_mte")
    for code, value in extensions(catalog, set(table)).items():
        table[code] = value
        source[code] = "kit"
    codes = sorted(table)
    pq.write_table(
        pa.table({
            "code": codes,
            "label": [table[c][0] for c in codes],
            "level": [table[c][1] for c in codes],
            "source": [source[c] for c in codes],
        }),
        OUT, compression="zstd",
    )
    by: dict[str, int] = {}
    for c in codes:
        by[table[c][1]] = by.get(table[c][1], 0) + 1
    print(f"wrote {OUT.relative_to(ROOT)}: {len(codes)} codes {by}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
