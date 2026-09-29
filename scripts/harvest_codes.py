"""Harvest SINAN code tables from the official data dictionaries (ADR-0079).

Every SINAN NET "Dicionário de Dados" is a PDF table with one row per field:

    | 44. Reflexos Neurológicos | tp_reflexo_neurologico | varchar(1) |
    | 1 – Normais / 2 – Aumentados / 3 – Reduzidos/Ausentes / 9 – Ignorado |
    | Informar os reflexos ... | Campo essencial | TPNEURO |

This reads those tables with pdfplumber and writes the code lists to
``curation/codes/sinan.yml``, keyed by the FORM (the agravo series). This file
is GENERATED. EVOLUCAO and CLASSI_FIN measurably carry different codes on
different forms, so a table belongs to the series whose dictionary printed it.
It is not a property of the column name.

A list is kept only when:
- every code fits the field's declared width;
- it has at least two codes;
- each code is a short digit or letter run.

Hand curation (``codes:`` or ``codelist:`` on a variable) wins over this file.

    python scripts/harvest_codes.py [--dry-run]
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pdfplumber
import yaml

ROOT = Path(__file__).resolve().parent.parent
PDFS = ROOT / "sources" / "pdfs"
OUT = ROOT / "src" / "pegasus_data" / "curation" / "codes" / "sinan.yml"

#: Dictionary PDF (a substring of its file name) -> the SINAN series it documents.
DICTIONARIES: dict[str, tuple[str, ...]] = {
    "Animais_Pedonhentos": ("ANIM",),
    "Aids_adulto": ("AIDA",),
    "Aids_crianca": ("AIDC",),
    "anti_rabico": ("ANTR",),
    "Botulismo": ("BOTU",),
    "chikungunya__DIC": ("CHIK",),
    "Colera": ("COLE",),
    "Coqueluche_v5": ("COQU",),
    "dengue__DIC": ("DENG",),
    "Difteria_v5": ("DIFT",),
    "Chagas_v5": ("CHAG",),
    "Acidente_Trabalho_grave": ("ACGR",),
    "DRT_Cancer": ("CANC",),
    "DRT_Dermatoses": ("DERM",),
    "Acidente_Trabalho_Biologico": ("ACBI",),
    "DRT_LERDORT": ("LERD", "LER"),
    "DRT_PAIR": ("PAIR",),
    "DRT_Pneumoconioses": ("PNEU",),
    "DRT_TranstornosMentais": ("MENT",),
    "Esquistossomose_v5": ("ESQU",),
    "Febre_Maculosa": ("FMAC",),
    "Febre_Tifoide": ("FTIF",),
    "Gestante_HIV": ("HIVG",),
    "Hanseniase": ("HANS",),
    "Hantavirose_v5": ("HANT",),
    "Hepatite_v5": ("HEPA",),
    "Intoxicacao_Exogena": ("IEXO",),
    "DIC_DADOS_LTA": ("LTAN",),
    "DIC_DADOS_LV": ("LEIV",),
    "Leptospirose": ("LEPT",),
    "Malaria": ("MALA",),
    "Meningite_v5": ("MENI",),
    "Raiva_v5": ("RAIV",),
    "ROTA_NET": ("ROTA",),
    "Sifilis_Congenita": ("SIFC",),
    "sindrome-da-rubeola-congenita__DIC_DADOS_SRC": ("SRC",),
    "Tetano_Acidental": ("TETA",),
    "Tetano_NeoNatal": ("TETN",),
    "Tuberculose": ("TUBE",),
    "Violencias": ("VIOL",),
}

_WIDTH = re.compile(r"(?:varchar2?|char)\s*\(\s*(\d+)\s*\)", re.I)
#: "1 – Sim", "1-Sim", "1. Sim", "9-" (label wrapped to the next line).
_CODE = re.compile(r"^\s*([0-9]{1,3}|[A-Z]{1,2})\s*[–\-—=.]\s*(.*?)\s*$")
_DBF = re.compile(r"^[A-Z][A-Z0-9_]{1,10}$")


def _categories(cell: str) -> dict[str, str]:
    codes: dict[str, str] = {}
    last: str | None = None
    # "1-Sim; 2-Não; 9-Ignorado" on one line is several codes.
    for raw in re.split(r"\n|;", cell):
        line = raw.strip()
        if not line:
            continue
        m = _CODE.match(line)
        if m and m.group(1) not in codes:
            last = m.group(1)
            codes[last] = m.group(2)
        elif last is not None:
            joiner = "" if codes[last].endswith("/") or not codes[last] else " "
            codes[last] = f"{codes[last]}{joiner}{line}"
        else:
            return {}  # prose before any code: not a code list
    out = {k: re.sub(r"\s+", " ", v).strip(" .;") for k, v in codes.items()}
    return out if all(out.values()) else {}


def _rows(pdf_path: Path):
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    yield [(c or "").strip() for c in row]


def _parse_row(row: list[str]) -> tuple[str, dict[str, str]] | None:
    for i, cell in enumerate(row):
        m = _WIDTH.fullmatch(cell.replace("\n", " ").strip()) or (
            _WIDTH.search(cell) if len(cell) < 20 else None
        )
        if not m:
            continue
        width = int(m.group(1))
        if i + 1 >= len(row):
            return None
        codes = _categories(row[i + 1])
        name = row[-1].replace("\n", " ").split()[-1] if row[-1].strip() else ""
        if not _DBF.match(name) or len(codes) < 2 or any(len(c) > width for c in codes):
            return None
        return name, codes
    return None


def harvest() -> tuple[dict[str, dict], list[str]]:
    per_series: dict[str, dict[str, dict]] = defaultdict(dict)
    unmapped: list[str] = []
    for pdf in sorted(PDFS.glob("*.pdf")):
        series = next((s for key, s in DICTIONARIES.items() if key in pdf.name), None)
        if series is None:
            if "DIC" in pdf.name.upper():
                unmapped.append(pdf.name)
            continue
        for row in _rows(pdf):
            parsed = _parse_row(row)
            if not parsed:
                continue
            name, codes = parsed
            for s in series:
                # Two dictionaries for one series (older and newer editions):
                # the first parsed is kept, and a later one only adds fields.
                per_series[s].setdefault(name, {"codes": codes, "source_ref": pdf.name})
    return dict(per_series), unmapped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    tables, unmapped = harvest()
    count = sum(len(v) for v in tables.values())
    fields = Counter(f for v in tables.values() for f in v)
    print(f"{count} code tables over {len(tables)} series; {len(fields)} distinct fields")
    if unmapped:
        print("dictionaries with no series mapping:", unmapped)
    if args.dry_run:
        for s in sorted(tables):
            print(f"  {s}: {len(tables[s])}")
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# GENERATED by scripts/harvest_codes.py from the SINAN NET data dictionaries\n"
        "# (sources/pdfs). Do not edit by hand: a variable's own codes:/codelist: wins\n"
        "# over this file (ADR-0079). Keyed by series, because the same column name\n"
        "# carries different codes on different forms (EVOLUCAO, CLASSI_FIN).\n"
    )
    body = {"system": "SINAN", "series": {s: dict(sorted(t.items())) for s, t in sorted(tables.items())}}
    OUT.write_text(header + yaml.safe_dump(body, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
