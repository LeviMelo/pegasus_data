"""The code lists of the Census 2010 sample microdata, read from IBGE's own documentation workbooks.

The layout (``Layout_microdados_Amostra.xls``) prints a code list only for a small variable and names a workbook for the
places, countries, courses, occupation, activity and religion; ``Documentacao.zip`` (the registry
``census2010_microdata``) holds them under ``Anexos Auxiliares/``. `documentation_codes` reads each workbook and returns the
``series -> column -> {codes, width, source_ref}`` that ``scripts/harvest_codes.py`` writes to ``curation/codes/censo2010.yml``
(the form's harvested dictionary, served as ``CURATED.CENSO2010.<SERIES>.<COLUMN>``).

A code list lists the codes of **every level** of a hierarchy (occupation: 1, 11, 111, 1111; courses: 1, 14, 140), and a
column holds one level: only the codes of the column's own width are kept (widths are matched exactly, never padded), and the
codes of the other levels are the hierarchy the table does not carry. One exception is read from the workbook itself and
named where it is made: the military residual codes of the occupation list.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path
from typing import Any

from .census_commuting import _directory, _sheet

__all__ = ["documentation_codes"]

A = r"Anexos Auxiliares/"
#: the columns each list labels, by series (PESSOAS unless stated), with the column's width in the layout
UFS = {"PESSOAS": ("V6222", "V6252", "V6262", "V6362", "V6602")}
MUNICIPALITIES = {"PESSOAS": ("V6254", "V6264", "V6364", "V6604")}
COUNTRIES = {"PESSOAS": ("V6224", "V6256", "V6266", "V6366", "V6606"), "EMIGRACAO": ("V3061",)}


def _text(value: Any) -> str:
    return " ".join(str(value).split())


def _integer(value: Any) -> str | None:
    """A numeric cell as the digits it shows (``1100015.0`` -> ``'1100015'``), None for anything else."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return str(int(number)) if number == number and number == int(number) else None


def _add(table: dict[str, str], code: str, label: str, where: str, several: bool = False) -> None:
    """One label a code. With ``several`` (a place workbook), a code printed under several names (the United Kingdom's 8000826 is
    listed as Escócia and as Inglaterra) keeps every name, joined by `` / `` in the order printed: a list that names one code twice
    is not resolved to one of them. Anywhere else two labels are a conflict and raise."""
    if code in table and table[code] != label:
        if several:
            if label not in table[code].split(" / "):
                table[code] = f"{table[code]} / {label}"
            return
        raise ValueError(f"{where}: code {code} is both {table[code]!r} and {label!r}")
    table[code] = label


def _places(documentation: Path, pattern: str, label_column: int, code_column: int, first: int = 0, width: int = 7) -> dict[str, str]:
    """``code -> name`` of a place workbook: a row with a numeric code of ``width`` digits is a place; a row without one
    (a continent or a state heading) is not."""
    table: dict[str, str] = {}
    sheet = _sheet(documentation, pattern)
    for row in sheet.itertuples(index=False):
        code = _integer(row[code_column])
        if code and len(code) == width and _text(row[label_column]) not in ("", "nan"):
            _add(table, code, _text(row[label_column]), pattern, several=True)
    return table


def _occupation_2010(documentation: Path) -> dict[str, str]:
    """COD 2010 (``Ocupação COD 2010.xls``): the 4-digit codes. The military branch (grande grupo 0) is written with text cells
    whose leading zero is kept (``0110``) except its three residual codes, ``299``, ``599`` and ``999``, which are numeric cells
    that lost it; they are read as ``0299``, ``0599``, ``0999`` because they stand inside that branch (after the heading ``0``
    "MEMBROS DAS FORÇAS ARMADAS, POLICIAIS E BOMBEIROS MILITARES") and name military residuals, and because those three are
    exactly the 4-digit codes the microdata holds that no other row can be."""
    table: dict[str, str] = {}
    military = False
    sheet = _sheet(documentation, A + r"Ocupa.*COD 2010\.xls$")
    for row in sheet.iloc[2:].itertuples(index=False):
        cell, label = row[0], _text(row[1])
        if label in ("", "nan"):
            continue
        code = cell.strip() if isinstance(cell, str) else _integer(cell)
        if code is None:
            continue
        if not isinstance(cell, str) and code == "0":
            military = True
        elif military and not isinstance(cell, str) and len(code) < 4:
            code = code.zfill(4)
        if len(code) == 4:
            _add(table, code, label, "Ocupação COD 2010")
    return table


def _classes(documentation: Path, pattern: str, label_column: int, code_column: int, width: int) -> dict[str, str]:
    """The text codes of a sheet that are ``width`` digits (CNAE-Domiciliar classes ``01101``, activity of Census 2000)."""
    table: dict[str, str] = {}
    sheet = _sheet(documentation, pattern, **({"sheet_name": "Plan2"} if "CD2000" in pattern else {}))
    for row in sheet.itertuples(index=False):
        cell = row[code_column]
        code = cell.strip() if isinstance(cell, str) else _integer(cell)
        if code and len(code) == width and code.isdigit() and _text(row[label_column]) not in ("", "nan"):
            _add(table, code, _text(row[label_column]), pattern)
    return table


def _courses(documentation: Path, pattern: str) -> dict[str, str]:
    """The 3-digit detailed fields of a course workbook (1 digit the general area, 2 the specific, 3 the detailed field). The last
    block, general area ``0`` "NÃO SABE E NÃO ESPECIFICADO", has one detailed field written as a numeric cell that lost its leading
    zero (``85`` "NÃO SABE E SUPERIOR NÃO ESPECIFICADO", ``97`` for the master's and the doctorate); it is read as ``085`` and
    ``097`` because it stands inside area 0 (the ``85`` of area 8 "PROTEÇÃO AMBIENTAL" is a 2-digit specific area), and the
    microdata holds exactly ``085`` (33,847 persons) and ``097`` (1,969 and 628) as 3-digit codes the list otherwise lacks."""
    table: dict[str, str] = {}
    unknown_area = False
    for row in _sheet(documentation, pattern).itertuples(index=False):
        code = row[0].strip() if isinstance(row[0], str) else _integer(row[0])
        if not code or _text(row[1]) in ("", "nan"):
            continue
        if not isinstance(row[0], str) and code == "0":
            unknown_area = True
        elif unknown_area and not isinstance(row[0], str) and len(code) == 2:
            code = code.zfill(3)
        if len(code) == 3 and code.isdigit():
            _add(table, code, _text(row[1]), pattern)
    return table


def _religion(documentation: Path) -> dict[str, str]:
    """``Religião 2010.txt``: one ``<code> <label>`` line per religion (3 digits) under its 2-digit group."""
    with zipfile.ZipFile(documentation) as z:
        name = next(n for n in z.namelist() if re.search(A + r"Religi.*2010\.txt$", n))
        text = z.read(name).decode("cp1252")
    table: dict[str, str] = {}
    for line in text.splitlines():
        found = re.fullmatch(r"(\d{3}) (\S.*?)\s*", line)
        if found:
            _add(table, found.group(1), found.group(2), "Religião 2010.txt")
    return table


def _occupation_2000(documentation: Path) -> dict[str, str]:
    """The 4-digit occupations of the Census 2000 classification (``estrutura ocupação CD2000.pdf``): a code opens a line, its
    title may continue on the next lines; a line that is only a page number ends nothing."""
    import pdfplumber

    with zipfile.ZipFile(documentation) as z:
        name = next(n for n in z.namelist() if re.search(A + r"estrutura ocupa.*CD2000\.pdf$", n))
        with pdfplumber.open(io.BytesIO(z.read(name))) as pdf:
            lines = [ln for page in pdf.pages for ln in (page.extract_text(x_tolerance=3) or "").splitlines()]
    table: dict[str, str] = {}
    current = None
    for line in lines:
        found = re.fullmatch(r"(\d{4})\s+[–-]?\s*(\S.*?)\s*", line)
        if found:
            current = found.group(1)
            _add(table, current, found.group(2), "estrutura ocupação CD2000.pdf")
        elif re.fullmatch(r"\d{1,3}", line.strip()) or re.match(r"\d{1,3}\s", line):
            current = None                       # a page number or a code of another level ends the title
        elif current and line.strip() and not line.startswith(("Grande", "Grupo", "CLASSIFICA")):
            table[current] = f"{table[current]} {_text(line)}"
    return table


def documentation_codes(root: str | Path | None = None) -> dict[str, dict[str, dict[str, Any]]]:
    """``series -> column -> {"codes", "width", "source_ref"}`` of every column whose code list is a workbook of the held
    ``Documentacao.zip``. A list shared by several columns is one dict (the same object), written once."""
    documentation = _directory(root, "census2010_microdata") / "Documentacao.zip"
    out: dict[str, dict[str, dict[str, Any]]] = {}

    def bind(table: dict[str, str], columns: dict[str, tuple[str, ...]], width: int, source: str) -> None:
        for series, names in columns.items():
            for name in names:
                out.setdefault(series, {})[name] = {"width": width, "source_ref": f"Documentacao.zip, {source}", "codes": table}

    ufs = _places(documentation, A + r"Migra.*Unidades da Federa.*\.xls$", 0, 1)
    bind(ufs, UFS, 7, "Anexos Auxiliares/Migração e deslocamento _Unidades da Federação.xls")
    municipalities = _places(documentation, A + r"Migra.*_Munic.pios\.xls$", 1, 2)
    # the migration list omits two municipalities the microdata holds (1200013 Acrelândia, 1304302 Urucará); the documentation's own
    # territorial division (2010) lists them, and is written in capitals as the migration list is
    for code, name in _places(documentation, r"Divis.*Territorial.*\.xls$", 7, 6).items():
        municipalities.setdefault(code, name.upper())
    bind(municipalities, MUNICIPALITIES, 7, "Anexos Auxiliares/Migração e deslocamento _Municípios.xls; Divisão Territorial do Brasil/...municípios 2010.xls for the two it omits (1200013, 1304302)")
    # the country list is filed twice: ``Paises`` (195 codes) and ``Países`` (the same, without 8000710 ÁFRICA DO SUL and with four
    # spellings of its own: BELARUS/BIELORRUSIA, NÍGER, ZIMBÁBUE, NÃO SABE PAÍS ESTRANGEIRO). The first, complete, one is read.
    countries = _places(documentation, A + r"Migra.*Deslocamento_Paises estrangeiros\.xls$", 1, 2)
    bind(countries, COUNTRIES, 7, "Anexos Auxiliares/Migração e Deslocamento_Paises estrangeiros.xls")
    bind(_occupation_2010(documentation), {"PESSOAS": ("V6461",)}, 4, "Anexos Auxiliares/Ocupação COD 2010.xls")
    bind(_classes(documentation, A + r"Atividade CNAE_DOM 2\.0 2010\.xls$", 3, 2, 5), {"PESSOAS": ("V6471",)}, 5,
         "Anexos Auxiliares/Atividade CNAE_DOM 2.0 2010.xls")
    for column, pattern, name in (("V6352", r"Cursos Superiores_Estrutura 2010\.xls$", "Cursos Superiores_Estrutura 2010.xls"),
                                  ("V6354", r"Cursos Mestrado_Estrutura 2010\.xls$", "Cursos Mestrado_Estrutura 2010.xls"),
                                  ("V6356", r"Cursos Doutorado_Estrutura 2010\.xls$", "Cursos Doutorado_Estrutura 2010.xls")):
        bind(_courses(documentation, A + pattern), {"PESSOAS": (column,)}, 3, f"Anexos Auxiliares/{name}")
    bind(_religion(documentation), {"PESSOAS": ("V6121",)}, 3, "Anexos Auxiliares/Religião 2010.txt")
    bind(_classes(documentation, A + r"Estrutura atividade CD2000\.xls$", 1, 0, 5), {"PESSOAS": ("V6472",)}, 5,
         "Anexos Auxiliares/Estrutura atividade CD2000.xls, sheet Plan2 (Códigos do Censo 2000)")
    bind(_occupation_2000(documentation), {"PESSOAS": ("V6462",)}, 4, "Anexos Auxiliares/estrutura ocupação CD2000.pdf")
    return out
