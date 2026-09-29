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
OUT_DIR = ROOT / "src" / "pegasus_data" / "curation" / "codes"

#: Other systems' dictionaries in the same tabular layout: file -> (system, series).
OTHER_DICTIONARIES: dict[str, tuple[str, tuple[str, ...]]] = {
    "sources/DIC_DADOS_RESP.pdf": ("RESP", ("RESP",)),
    # svs.aids.gov.br/daent/cgiae/coesv/sistemas-informacao/sim/documentacao/
    "sources/dicionario-de-dados-SIM-tabela-DO.pdf": (
        "SIM", ("DO", "DOEXT", "DOFET", "DOINF", "DOMAT", "DOR", "DOREXT", "DORIG"),
    ),
}

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
    # Older editions, read after the v5 dictionaries (a field only they carry is added).
    "iexo_dic": ("IEXO",),
    "dic_lv": ("LEIV",),
    "dic_dengue_online": ("DENG",),
    "acbi_dic": ("ACBI",),
    "dermatoses_dic": ("DERM",),
    "lerdort_dic": ("LERD", "LER"),
}

_WIDTH = re.compile(r"(?:varchar2?|char|caractere|num[eé]rico)\s*\(\s*(\d+)\s*\)", re.I)
#: "1 – Sim", "1-Sim", "1. Sim", "9-" (label wrapped to the next line).
_CODE = re.compile(
    r"^\s*(?:([0-9]{1,3})\s*(?:[–\-—=.]\s*|\s+)|([A-Z]{1,2})\s*[–\-—=.]\s*)(.*?)\s*$"
)  # "1 Sim" (IEXO v6) has no separator; a letter code always has one
_DBF = re.compile(r"^[A-Z][A-Z0-9_]{1,10}$")


#: "M,1 – masculino" (SIM): several codes, one label.
_ALIASES = re.compile(r"^\s*((?:[0-9A-Z]{1,3},)+[0-9A-Z]{1,3})\s*[–\-—=]\s*(.*?)\s*$")


def _categories(cell: str) -> dict[str, str]:
    codes: dict[str, str] = {}
    aliases: dict[str, list[str]] = {}
    last: str | None = None
    # "1-Sim; 2-Não; 9-Ignorado" on one line is several codes, and the PDF
    # text sometimes glues the next code to a label ("epidemiológico 3Clínico",
    # "domicílio 4 – via pública").
    cell = re.sub(r"(\b\d{1,2})\s*\n\s*([–—-])", r"\1 \2", cell)  # "4\n– via pública"
    cell = re.sub(r"(?<=[a-zà-ú)])\s*(\d{1,2})(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ][a-zà-ú])", r"\n\1 ", cell)
    cell = re.sub(r"(?<=[a-zà-ú)])\s+(\d{1,2})\s*[–—]\s+", r"\n\1 – ", cell)
    for raw in re.split(r"\n|;", cell):
        line = raw.strip()
        if not line:
            continue
        a = _ALIASES.match(line)
        if a:
            names = a.group(1).split(",")
            last = names[0]
            codes[last] = a.group(2)
            aliases[last] = names[1:]
            continue
        m = _CODE.match(line)
        code = (m.group(1) or m.group(2)) if m else None
        if m and code not in codes:
            last = code
            codes[last] = m.group(3)
        elif last is not None:
            joiner = "" if codes[last].endswith("/") or not codes[last] else " "
            codes[last] = f"{codes[last]}{joiner}{line}"
        else:
            return {}  # prose before any code: not a code list
    out = {k: re.sub(r"\s+", " ", v).strip(" .;") for k, v in codes.items()}
    for first, others in aliases.items():
        for other in others:
            out.setdefault(other, out[first])
    return out if all(out.values()) else {}


def _rows(pdf_path: Path):
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for row in table:
                    yield [(c or "").strip() for c in row]


def _parse_row(row: list[str]) -> tuple[str, dict[str, str]] | None:
    """One dictionary row: the width cell, the first non-empty cell after it
    (the categories), and the DBF name at either end of the row.

    SINAN NET puts the DBF name last (``| 44. Reflexos | tp_... | varchar(1) |
    categories | ... | TPNEURO |``); RESP and PCE put it first, with empty spacer
    cells (``| SEXO | | | Caractere (1) | | | 1-Masculino ... |``).
    """
    cells = [c.replace("\n", " ").strip() for c in row]
    # SIM's dictionary: | 12- Situação Conjugal | ESTCIV | Caracter | 1 | categories | … |
    # (type and width in separate cells, the DBF name just before the type).
    for i, cell in enumerate(cells[:-2]):
        if cell.lower() in ("caracter", "caractere", "numérico", "numerico", "char") and cells[i + 1].isdigit():
            width = int(cells[i + 1])
            name = cells[i - 1] if i > 0 else ""
            following = [row[k] for k in range(i + 2, len(row)) if row[k].strip()]
            if not following or not _DBF.fullmatch(name):
                return None
            codes = _categories(following[0])
            if len(codes) < 2 or any(len(c) > width for c in codes):
                return None
            return name, codes
    for i, cell in enumerate(cells):
        m = _WIDTH.search(cell) if len(cell) < 25 else None
        if not m:
            continue
        width = int(m.group(1))
        following = [row[k] for k in range(i + 1, len(row)) if row[k].strip()]
        if not following:
            return None
        codes = _categories(following[0])
        ends = [cells[0].split()[0] if cells[0] else "", cells[-1].split()[-1] if cells[-1] else ""]
        name = next((n for n in reversed(ends) if _DBF.fullmatch(n)), "")
        if not name or len(codes) < 2 or any(len(c) > width for c in codes):
            return None
        return name, codes
    return None


def _read(pdf: Path, series: tuple[str, ...], into: dict[str, dict[str, dict]]) -> None:
    for row in _rows(pdf):
        parsed = _parse_row(row)
        if not parsed:
            continue
        name, codes = parsed
        for s in series:
            # Two dictionaries for one series (older and newer editions): the
            # first parsed is kept, and a later one only adds fields.
            into[s].setdefault(name, {"codes": codes, "source_ref": pdf.name})


def harvest() -> tuple[dict[str, dict[str, dict[str, dict]]], list[str]]:
    """``system -> series -> field -> {codes, source_ref}``, and unmapped PDFs."""
    out: dict[str, dict[str, dict[str, dict]]] = defaultdict(lambda: defaultdict(dict))
    unmapped: list[str] = []
    for pdf in sorted(PDFS.glob("*.pdf")):
        series = next((s for key, s in DICTIONARIES.items() if key in pdf.name), None)
        if series is None:
            if "DIC" in pdf.name.upper():
                unmapped.append(pdf.name)
            continue
        _read(pdf, series, out["SINAN"])
    for rel, (system, series) in OTHER_DICTIONARIES.items():
        if (ROOT / rel).exists():
            _read(ROOT / rel, series, out[system])
    return {k: dict(v) for k, v in out.items()}, unmapped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    systems, unmapped = harvest()
    for system, tables in sorted(systems.items()):
        count = sum(len(v) for v in tables.values())
        fields = Counter(f for v in tables.values() for f in v)
        print(f"{system}: {count} code tables over {len(tables)} series; {len(fields)} distinct fields")
    if unmapped:
        print("dictionaries with no series mapping:", unmapped)
    if args.dry_run:
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for system, tables in sorted(systems.items()):
        header = (
            f"# GENERATED by scripts/harvest_codes.py from the official {system} data\n"
            "# dictionaries. Do not edit by hand: a variable's own codes:/codelist: wins\n"
            "# over this file (ADR-0079). Keyed by series, because the same column name\n"
            "# carries different codes on different forms (EVOLUCAO, CLASSI_FIN).\n"
        )
        body = {"system": system, "series": {s: dict(sorted(t.items())) for s, t in sorted(tables.items())}}
        out = OUT_DIR / f"{system.lower()}.yml"
        out.write_text(header + yaml.safe_dump(body, allow_unicode=True, sort_keys=False, width=100), encoding="utf-8")
        print(f"wrote {out.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
