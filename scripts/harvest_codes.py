"""Harvest SINAN code tables from the official data dictionaries (ADR-0079).

Every SINAN NET "Dicionário de Dados" is a PDF table with one row per field:

    | 44. Reflexos Neurológicos | tp_reflexo_neurologico | varchar(1) |
    | 1 – Normais / 2 – Aumentados / 3 – Reduzidos/Ausentes / 9 – Ignorado |
    | Informar os reflexos ... | Campo essencial | TPNEURO |

This reads those tables with pdfplumber and writes each field's layout (its
type, width and label as the form prints them, and a code table it names) and
its code list to ``curation/codes/sinan.yml``, keyed by the FORM (the agravo
series). The layout is what a field IS by its own documentation (a date, a
number, free text, a category); the role drafter reads it rather than guessing
from the column's name. This file is GENERATED. EVOLUCAO and CLASSI_FIN measurably carry different codes on
different forms, so a table belongs to the series whose dictionary printed it.
It is not a property of the column name.

A code list is kept only when:
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
    "DIC_DADOS_SRC_v5": ("SRC",),
    "mental_dic": ("MENT",),
}

_WIDTH = re.compile(r"(?:varchar2?|char|caractere|num[eé]rico|number)\s*\(\s*(\d+)\s*\)?", re.I)
#: A type cell: SINAN NET's ``varchar2(1)``, ``number(4)``, ``date``; SIM's ``Caracter`` with the width apart.
_TYPE = re.compile(r"^\s*(varchar2?|char|caractere?|caracter|num[eé]rico|number|date|data)\s*(?:\(\s*(\d+)\s*\)?)?\s*$",
                   re.I)


def _kind(word: str) -> str:
    """The storage type a dictionary prints, in three words: date, number, text."""
    w = word.lower()
    return "date" if w in ("date", "data") else "number" if w.startswith(("num", "number")) else "text"


def _entry(label: str, type_cell: str, width: int | None, following: list[str]) -> dict:
    """A field's layout from its row: type, width, the form's label, and what its categories cell holds (a code list
    that fits the width, or the name of a code table: 'Tabela com Código e nome dos municípios')."""
    m = re.search(r"varchar|char|caract|num[eé]rico|number|date|data", type_cell, re.I)
    entry: dict = {"type": _kind(m.group(0)) if m else "text"}
    if width:
        entry["width"] = width
    label = re.sub(r"^\s*\d+\s*[-.–]?\s*", "", label.replace("\n", " ")).strip()
    if label:
        entry["label"] = re.sub(r"\s+", " ", label)
    if following:
        cell = following[0]
        codes = _categories(cell)
        # a number-typed field's printed codes are kept: ESQU AN_QUANT (number(4), "0 (zero) / 1 (um) ou mais ovos")
        # holds 0 and 1 only in the records (2021: 1,298 and 1,096), a flag as printed, not an egg count
        if len(codes) >= 2 and _fits(codes, width or max(len(c) for c in codes)):
            entry["codes"] = codes
        elif re.match(r"^\s*tabela", cell, re.I):
            entry["table"] = re.sub(r"\s+", " ", cell).strip()
    return entry
#: "1 – Sim", "1-Sim", "1. Sim", "9-" (label wrapped to the next line).
_CODE = re.compile(
    r"^\s*(?:([0-9]{1,3})\s*(?:[–\-—=.]\s*|\s+)|([A-Z]{1,2})\s*[–\-—=.]\s*)(.*?)\s*$"
)  # "1 Sim" (IEXO v6) has no separator; a letter code always has one
_DBF = re.compile(r"^[A-Z][A-Z0-9_]{1,10}$")


#: "M,1 – masculino" (SIM): several codes, one label.
_ALIASES = re.compile(r"^\s*((?:[0-9A-Z]{1,3},)+[0-9A-Z]{1,3})\s*[–\-—=]\s*(.*?)\s*$")


#: Short words a wrapped cell may put on a line of their own.
_WORDS = {"a", "o", "e", "à", "ao", "as", "os", "da", "de", "do", "em", "na", "no", "ou", "se", "um"}
#: A Portuguese word does not end like this; a line after it finishes the word.
_CUT = r"(?:[bcdfgjkpqtvx]|[bcdfgjkpqtvx]i)$"
_TYPES = {"caracter", "caractere", "numérico", "numerico", "char"}
#: A dictionary table's own header cells, repeated at the top of a page.
_HEADER = {"nome do campo", "campo", "tipo", "categoria", "categorias", "descrição", "descricao", "características",
           "caracteristicas", "dbf"}


def _fits(codes: dict[str, str], width: int) -> bool:
    """Every code fits the declared width, or the rest form one consecutive run.

    TUBE ``SITUA_ENCE`` is declared varchar2(1) and lists 1 to 10; the kit's
    ``encerra.cnv`` agrees on 10 (2026-10-03). A parse of prose fails anyway:
    its "codes" do not count on from the ones that fit.
    """
    fitting = [c for c in codes if len(c) <= width]
    over = [c for c in codes if len(c) > width]
    if not over:
        return True
    if not fitting or not all(c.isdigit() for c in codes):
        return False
    top = max(int(c) for c in fitting)
    run = sorted(int(c) for c in over)
    # Continuing the run that fits (TUBE 1..10), or a run of its own: the
    # Sinan Online CHIK/DENG classification is declared VARCHAR(1) and lists
    # 5, then 10-13 (2026-10-03).
    return run == list(range(run[0], run[0] + len(run))) and (run[0] == top + 1 or len(run) >= 2)


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
    cell = re.sub(r"(?<=[a-zà-ú)])\s+(\d{1,2})-\s*(?=[a-zà-ú]{3})", r"\n\1 – ", cell)
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
            # A lone lowercase letter is the tail of a word the cell wrapped
            # ("Inconclusiv\no"); a trailing hyphen joins too ("clínico-\nepidemiológico").
            glued = (codes[last].endswith("/") or re.search(r"[a-zà-ú]-$", codes[last])
                     or (re.fullmatch(r"[a-zà-ú]{1,2}", line)
                         and (line not in _WORDS or re.search(_CUT, codes[last]))))
            joiner = "" if glued or not codes[last] else " "
            codes[last] = f"{codes[last]}{joiner}{line}"
        else:
            return {}  # prose before any code: not a code list
    out = {k: re.sub(r"\s+", " ", v).strip(" .;") for k, v in codes.items()}
    for first, others in aliases.items():
        for other in others:
            out.setdefault(other, out[first])
    return out if all(out.values()) else {}


def _rows(pdf_path: Path):
    """Table rows, with a row the page break split joined back together.

    A field whose code list runs past the page ends goes on as the next page's
    first row, its leading cells empty (ACBI ``TIPO_ACID`` stopped at code 04).
    A page that repeats the table's header first has the continuation after it:
    the header and empty rows are passed over (AIDA ``ANT_REL_CA`` stopped at
    "34-", the codes 34 to 90 on the next page under a repeated header).
    """
    held: list[str] | None = None
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            first = True
            for table in page.extract_tables():
                for raw in table:
                    row = [(c or "").strip() for c in raw]
                    if not any(row) or sum(c.lower() in _HEADER for c in row) >= 2:
                        continue        # a repeated header or an empty row: the continuation may follow
                    filled = next((i for i, c in enumerate(row) if c), None)
                    if (first and held is not None and filled and len(row) == len(held)
                            and held[filled] and not any(_WIDTH.search(c) or _DBF.fullmatch(c)
                                                         or c.lower() in _TYPES for c in row)):
                        held[filled] = f"{held[filled]}\n{row[filled]}"
                    else:
                        if held is not None:
                            yield held
                        held = row
                    first = False
    if held is not None:
        yield held


def _parse_row(row: list[str]) -> tuple[str, dict] | None:
    """One dictionary row: the field's layout (`_entry`) from the type cell, the
    first non-empty cell after it (the categories), and the DBF name at either
    end of the row.

    SINAN NET puts the DBF name last (``| 44. Reflexos | tp_... | varchar(1) |
    categories | ... | TPNEURO |``); RESP and PCE put it first, with empty spacer
    cells (``| SEXO | | | Caractere (1) | | | 1-Masculino ... |``).
    """
    cells = [c.replace("\n", " ").strip() for c in row]
    # SIM's dictionary: | 12- Situação Conjugal | ESTCIV | Caracter | 1 | categories | … |
    # (type and width in separate cells, the DBF name just before the type).
    for i, cell in enumerate(cells[:-2]):
        if cell.lower() in _TYPES and cells[i + 1].isdigit():
            name = cells[i - 1] if i > 0 else ""
            if not _DBF.fullmatch(name):
                return None
            following = [row[k] for k in range(i + 2, len(row)) if row[k].strip()]
            return name, _entry(cells[0] if i > 1 else "", cell, int(cells[i + 1]), following)
    for i, cell in enumerate(cells):
        m = _TYPE.match(cell) if len(cell) < 25 else None
        w = _WIDTH.search(cell) if len(cell) < 25 else None
        if not (m or w):
            continue
        ends = [cells[0].split()[0] if cells[0] else "", cells[-1].split()[-1] if cells[-1] else ""]
        name = next((n for n in reversed(ends) if _DBF.fullmatch(n)), "")
        if not name:
            return None
        following = [row[k] for k in range(i + 1, len(row)) if row[k].strip()]
        label = cells[0] if cells[0] and name != cells[0].split()[0] else ""
        width = int(m.group(2)) if m and m.group(2) else int(w.group(1)) if w else None
        return name, _entry(label, cell, width, following)
    # SINAN Online's dictionaries (dengue, chikungunya): no type or width cell, the categories in the first cell that
    # reads as codes, the DBF name last (``| 33- Sinais clínicos (Cefaleia) | | | 1 – Sim / 2 – Não | … | CEFALEIA |``);
    # an accent the DBF name cannot carry is dropped (ÁCIDO_PEPT is the column ACIDO_PEPT). Every other check holds
    import unicodedata

    last = cells[-1].split()[-1] if cells[-1] else ""
    name = unicodedata.normalize("NFKD", last).encode("ascii", "ignore").decode()
    if not _DBF.fullmatch(name):
        return None
    for k in range(1, len(row) - 1):
        if row[k].strip():
            codes = _categories(row[k])
            if len(codes) >= 2 and _fits(codes, max(len(c) for c in codes)):
                label = re.sub(r"^\s*\d+\s*[-.–]?\s*", "", cells[0]).strip()
                return name, {"codes": codes, **({"label": label} if label else {})}
            return None
    return None


def _read(pdf: Path, series: tuple[str, ...], into: dict[str, dict[str, dict]]) -> None:
    for row in _rows(pdf):
        parsed = _parse_row(row)
        if not parsed:
            continue
        name, entry = parsed
        for s in series:
            # Two dictionaries for one series (older and newer editions): the
            # first parsed is kept, and a later one only adds fields, or what
            # the first did not print (a type, a code list).
            held = into[s].setdefault(name, {**entry, "source_ref": pdf.name})
            for key, value in entry.items():
                held.setdefault(key, value)


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
    _supplement(out)
    return {k: dict(v) for k, v in out.items()}, unmapped


def _supplement(out: dict[str, dict[str, dict[str, dict]]]) -> None:
    """Merge ``curation/codes/supplements.yml``: codes a dictionary omits, cited.

    A supplement adds codes and never replaces one; a label that disagrees with
    the dictionary's is a conflict to resolve by hand, so the harvest stops.
    ``drop`` removes a code the text extraction invented, with its reason.
    """
    path = OUT_DIR / "supplements.yml"
    if not path.exists():
        return
    for system, series_map in (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).items():
        for series, fields in series_map.items():
            for field, extra in fields.items():
                entry = out[system][series].setdefault(field, {"source_ref": ""})
                entry.setdefault("codes", {})
                for code in extra.get("drop") or ():
                    # A code the PDF text invented (a glyph read as digits).
                    entry["codes"].pop(str(code), None)
                for code, label in (extra.get("codes") or {}).items():
                    known = entry["codes"].get(str(code))
                    if known is not None and known != label:
                        raise SystemExit(f"{system}.{series}.{field} {code}: dictionary {known!r}, supplement {label!r}")
                    entry["codes"].setdefault(str(code), label)
                entry["source_ref"] = "; ".join(x for x in (entry["source_ref"], extra["source_ref"]) if x)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    systems, unmapped = harvest()
    for system, tables in sorted(systems.items()):
        count = sum(1 for v in tables.values() for e in v.values() if e.get("codes"))
        typed = sum(1 for v in tables.values() for e in v.values() if e.get("type"))
        fields = Counter(f for v in tables.values() for f in v)
        print(f"{system}: {count} code tables, {typed} typed fields over {len(tables)} series; "
              f"{len(fields)} distinct fields")
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
