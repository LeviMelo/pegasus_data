"""What each municipality was called, year by year: IBGE's Divisão Territorial Brasileira (DTB).

A municipality's code is stable; its name is not. Embu became Embu das Artes, Campo de Santana became Tacima, Parati
is now written Paraty. A source that names a municipality instead of coding it (SENATRAN's fleet, SNGPC's sales)
writes the name of its own year, or an older one it never updated. The Localidades API (`ibge_localidades`) gives
today's name only, so a written name that is no longer current matched nothing, and each was added by hand to a list
(`geography.yml`, 43 entries by 2026-11-27) that had no years and applied to every source.

IBGE publishes the division as a zip under
``geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/divisao_territorial/<year>/`` for 1994, 2000 and
every year from 2003 (ADR-0244). Three layouts:
- **1994:** fixed-width text, one line per level; a municipality's line has its five digits and no district.
- **2000, 2003, 2004:** a spreadsheet with one row per level, the level in the first column (5: municipality).
- **2005 on:** a spreadsheet with one row per municipality (2014 on) or per subdistrict (most editions to 2013), the
  municipality as five digits within its state or as the full seven. File, sheet and header names change between
  editions, so the table is found by what it holds: the sheet whose header row starts with "UF".
"""

from __future__ import annotations

import io
import re
from collections.abc import Iterable
from pathlib import Path

from ..decode.archives import ArchiveFile
from ..decode.spreadsheet import read_table, sheets
from ..textenc import fold
from ..transport import download, get_text

__all__ = ["BASE_URL", "YEARS", "editions", "names_of_year", "year_archive"]

BASE_URL = "https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/divisao_territorial"

#: The editions IBGE publishes.
YEARS = (1994, 2000, *range(2003, 2026))

def year_archive(cache: str | Path, year: int) -> Path:
    """The year's national DTB zip, downloaded once into ``cache`` as ``<year>_<IBGE's file name>``. The year's folder
    also lists the districts' file and a read-me; the division is the ``dtb...`` zip that is neither (1994: ``brasil.zip``),
    and where IBGE corrected an edition (``..._v2``) only the correction is listed, or it sorts last and is taken."""
    cache = Path(cache)
    kept = sorted(p for p in cache.glob(f"{year}_*.zip") if _national(p.name.split("_", 1)[1], year))
    if kept:
        return kept[-1]
    listed = sorted(n for n in set(re.findall(r'href="([^"?/][^"]*\.zip)"', get_text(f"{BASE_URL}/{year}/"))) if _national(n, year))
    if not listed:
        raise LookupError(f"{BASE_URL}/{year}/ lists no national DTB archive")
    cache.mkdir(parents=True, exist_ok=True)
    return download(f"{BASE_URL}/{year}/{listed[-1]}", cache / f"{year}_{listed[-1]}")


def _national(name: str, year: int) -> bool:
    low = name.lower()
    return low == "brasil.zip" if year == 1994 else low.startswith("dtb") and "distrito" not in low and "nome" not in low


def names_of_year(cache: str | Path, year: int) -> list[tuple[str, str]]:
    """``(7-digit code, name)`` of every municipality in the year's division, in the file's order. A code is the
    state's two digits and the municipality's five where the file writes them apart. A file that names one code twice
    differently, or holds a count no division ever had, raises."""
    with ArchiveFile(year_archive(cache, year)) as archive:
        if year == 1994:
            with archive.open(archive.one()) as handle:
                lines = handle.read().decode("latin-1").splitlines()
            # UF(2) meso(2) micro(3) municipality(5) district(2) subdistrict(2) name
            pairs = [(ln[:2] + ln[7:12], ln[16:].strip()) for ln in lines
                     if len(ln) > 16 and ln[:16].isdigit() and ln[7:12] != "00000" and ln[12:16] == "0000"]
            return _checked(pairs, "DTB 1994")
        books = [n for n in archive.names() if n.lower().endswith((".xls", ".xlsx")) and "DISTRITO" not in fold(Path(n).name)]
        books = [n for n in books if "MUNIC" in fold(Path(n).name)] or books
        if len(books) != 1:
            raise ValueError(f"DTB {year}: expected one spreadsheet of municipalities, found {books}")
        with archive.open(books[0]) as handle:
            data = handle.read()
    label = f"DTB {year} {Path(books[0]).name}"
    header = r"^(UF|N.VEL)$"
    held = [name for name, cells in sheets(io.BytesIO(data)).items() if any(r and r[0] and re.match(header, r[0], re.I) for r in cells)]
    if len(held) > 1:                      # 2006: one sheet per level, and the whole
        held = [n for n in held if "MUNIC" in fold(str(n))]
    if len(held) != 1:
        raise ValueError(f"{label}: expected one sheet of municipalities, found {held}")
    table = read_table(io.BytesIO(data), header=header, sheet=held[0], label=label)
    heads = [fold(n).replace(" ", "_") for n in table.names]
    state = heads.index("UF")
    code = next((i for i, h in enumerate(heads) if "COMPLETO" in h and "MUNIC" in h), None)
    if code is None:
        code = next((i for i, h in enumerate(heads) if h in ("MUNIC", "MUNICIPIO", "MUNICIPIO_COM_DV")), None)
    by_level = heads[0] == "NIVEL"
    named = [i for i, h in enumerate(heads) if h.startswith("NOME")] if by_level else [i for i, h in enumerate(heads) if "NOME" in h and "MUNIC" in h]
    if code is None or len(named) != 1:
        raise ValueError(f"{label}: no column of municipality codes and one of their names in {table.names}")
    pairs = []
    for row in table.rows:
        if by_level and not (row[0] and row[0].isdigit() and int(row[0]) == 5 and (row[code] or "").isdigit()):
            continue                       # another level, or the legend under the table ("005 Município")
        written, name = row[code], row[named[0]]
        if not written or not name or not row[state] or not written.isdigit():
            raise ValueError(f"{label}: a row without state, code or name: {row}")
        pairs.append((written if len(written) == 7 else row[state].zfill(2) + written.zfill(5), name))
    return _checked(pairs, label)


def editions(cache: str | Path, years: Iterable[int] = YEARS) -> dict[int, list[tuple[str, str]]]:
    """``{year: [(code7, name)]}`` for every edition (what `geography.build_municipality_names` compiles)."""
    return {year: names_of_year(cache, year) for year in years}


def _checked(pairs: list[tuple[str, str]], label: str) -> list[tuple[str, str]]:
    out: dict[str, str] = {}
    for code7, name in pairs:
        if out.setdefault(code7, name) != name:
            raise ValueError(f"{label}: {code7} is named {out[code7]!r} and {name!r}")
    if not 4_900 <= len(out) <= 5_600 or any(len(c) != 7 for c in out):
        raise ValueError(f"{label}: {len(out)} municipalities read")
    return list(out.items())
