"""Did IBGE's regions ever place a municipality differently from today? (OQ-11)

Usage: python scripts/ibge_dtb_vintages.py

IBGE's Localidades API answers with today's division only, and the
membership pack takes its IBGE rows from it with empty validity windows. The
yearly territorial division files (DTB) on ``geoftp.ibge.gov.br`` state the
division as of each year:
- **mesoregions and microregions:** 1994, 2000 and 2005–2022. IBGE stopped
  publishing them after the 2022 file.
- **immediate and intermediate regions:** 2019–2025. The division was
  created in 2017, but its columns first appear in the 2019 file.

2001–2002 are not published. The 2003 and 2004 files list municipalities
without regions. Formats vary by year:
- 1994: fixed-width text;
- 2000: one row per level, with a level code;
- 2005 on: .xls, read with ``xlrd``, which is not a package dependency.

Each year's region codes are compared with the pack's current IBGE rows.
Writes data/probes/geography/ibge_dtb_vintages.json; archives are cached
under sources/ibge_dtb/.
"""

from __future__ import annotations

import io
import re
import unicodedata
import urllib.request
import zipfile
from pathlib import Path

BASE = "https://geoftp.ibge.gov.br/organizacao_do_territorio/estrutura_territorial/divisao_territorial"

#: Years whose file carries at least one region below the state.
YEARS: tuple[int, ...] = (1994, 2000, *range(2005, 2026))

#: classification -> (code width as IBGE writes the full code)
CLASSIFICATIONS = {
    "ibge_mesoregion": 4,
    "ibge_microregion": 5,
    "ibge_intermediate_region": 4,
    "ibge_immediate_region": 6,
}

def fetch(year: int, cache_dir: str | Path, *, timeout: float = 300.0) -> Path:
    """The year's DTB archive (the national municipality file), cached."""
    cache = Path(cache_dir)
    found = sorted(cache.glob(f"{year}_*.zip"))
    if found:
        return found[0]
    with urllib.request.urlopen(f"{BASE}/{year}/", timeout=timeout) as response:
        listing = response.read().decode("latin-1")
    names = re.findall(r'href="([^"?/][^"]*\.zip)"', listing)
    if year == 1994:
        names = [n for n in names if n.lower() == "brasil.zip"]
    else:
        names = [n for n in names if n.lower().startswith("dtb") and "distrito" not in n.lower()
                 and "nome" not in n.lower()]
    if not names:
        raise FileNotFoundError(f"IBGE publishes no national DTB archive for {year}")
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f"{year}_{names[0]}"
    with urllib.request.urlopen(f"{BASE}/{year}/{names[0]}", timeout=timeout) as response:
        data = response.read()
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(target)
    return target


def divisions(path: str | Path, year: int) -> dict[str, dict[str, tuple[str, str]]]:
    """``{code7: {classification: (member code, member label)}}`` for one year."""
    archive = zipfile.ZipFile(path)
    if year == 1994:
        return _fixed_width(archive)
    members = [n for n in archive.namelist() if n.lower().endswith(".xls")
               and "distrito" not in n.lower()]
    if not members:
        raise FileNotFoundError(f"{path}: no .xls member")
    member = sorted(members, key=lambda n: ("munic" not in n.lower(), n))[0]
    import xlrd

    sheet = xlrd.open_workbook(file_contents=archive.read(member), logfile=io.StringIO()).sheet_by_index(0)
    rows = [[_text(cell.value) for cell in sheet.row(r)] for r in range(sheet.nrows)]
    header = next(i for i, row in enumerate(rows[:12]) if any("munic" in _fold(c) for c in row))
    names = [_fold(c) for c in rows[header]]
    if "nivel" in names:
        return _by_level(names, rows[header + 1:])
    return _tabular(names, rows[header + 1:])


def _fixed_width(archive: zipfile.ZipFile) -> dict[str, dict[str, tuple[str, str]]]:
    # UF(2) meso(2) micro(3) municipality(5, with check digit) district(2)
    # subdistrict(2) name; the name belongs to the last non-zero code.
    meso: dict[str, str] = {}
    micro: dict[str, str] = {}
    out: dict[str, dict[str, tuple[str, str]]] = {}
    text = archive.read(archive.namelist()[0]).decode("latin-1")
    for line in text.splitlines():
        if len(line) < 17 or not line[:16].isdigit():
            continue
        uf, me, mi, mu, name = line[:2], line[2:4], line[4:7], line[7:12], line[16:].strip()
        if me != "00" and mi == "000":
            meso[uf + me] = name
        elif mi != "000" and mu == "00000":
            micro[uf + me + mi] = name
        elif mu != "00000" and line[12:16] == "0000":
            out[uf + mu] = {
                "ibge_mesoregion": (uf + me, meso.get(uf + me, "")),
                "ibge_microregion": (uf + mi, micro.get(uf + me + mi, "")),
            }
    return out


def _by_level(names: list[str], rows: list[list[str]]) -> dict[str, dict[str, tuple[str, str]]]:
    # 2000: level 8 is a mesoregion, 9 a microregion, 5 a municipality.
    at = {n: i for i, n in enumerate(names)}
    uf_i, me_i, mi_i, mu_i = at["uf"], at["mesorregiao"], at["microrregiao"], at["municipio com dv"]
    name_i = next(i for n, i in at.items() if n.startswith("nome"))
    meso: dict[str, str] = {}
    micro: dict[str, str] = {}
    out: dict[str, dict[str, tuple[str, str]]] = {}
    for row in rows:
        if not row or not row[0]:
            continue
        level, uf = row[0], row[uf_i].zfill(2)
        me, mi = row[me_i].zfill(2), row[mi_i].zfill(3)
        if level == "8":
            meso[uf + me] = row[name_i]
        elif level == "9":
            micro[uf + mi] = row[name_i]
        elif level == "5":
            out[uf + row[mu_i].zfill(5)] = {
                "ibge_mesoregion": (uf + me, meso.get(uf + me, "")),
                "ibge_microregion": (uf + mi, micro.get(uf + mi, "")),
            }
    return out


def _tabular(names: list[str], rows: list[list[str]]) -> dict[str, dict[str, tuple[str, str]]]:
    def column(*need: str, named: bool) -> int | None:
        for i, n in enumerate(names):
            if all(k in n for k in need) and (("nome" in n) == named):
                return i
        return None

    uf_i = names.index("uf")
    full_i = column("completo", named=False)
    mu_i = column("munic", named=False)
    keys = {
        "ibge_mesoregion": "meso",
        "ibge_microregion": "micro",
        "ibge_intermediate_region": "intermedi",
        "ibge_immediate_region": "imediat",
    }
    found = {cls: (column(key, named=False), column(key, named=True), CLASSIFICATIONS[cls])
             for cls, key in keys.items()}
    out: dict[str, dict[str, tuple[str, str]]] = {}
    for row in rows:
        if len(row) <= uf_i or not row[uf_i].isdigit():
            continue
        uf = row[uf_i].zfill(2)
        code7 = row[full_i] if full_i is not None and row[full_i] else row[mu_i]
        if len(code7) <= 5:
            code7 = uf + code7.zfill(5)
        if not (code7.isdigit() and len(code7) == 7) or code7 in out:
            continue
        entry: dict[str, tuple[str, str]] = {}
        for cls, (code_i, name_i, width) in found.items():
            if code_i is None or not row[code_i]:
                continue
            code = row[code_i]
            # Some years write meso and micro within the state (``02``,
            # ``006``), others in full (``1102``); the full code prefixes the
            # state.
            if len(code) < width:
                code = uf + code.zfill(width - 2)
            entry[cls] = (code, row[name_i] if name_i is not None else "")
        out[code7] = entry
    return out


def _text(value: object) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _fold(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c)).lower().strip()


def main() -> None:
    import collections
    import json

    import duckdb

    pack = "src/pegasus_data/resources/geography.parquet"
    current = {(m, c): code for m, c, code in duckdb.sql(
        f"SELECT municipality, classification, member_code FROM '{pack}' WHERE authority = 'ibge'").fetchall()}
    municipalities_now = {m for m, _ in current}
    years = {}
    for year in YEARS:
        division = divisions(fetch(year, "sources/ibge_dtb"), year)
        published = collections.Counter(c for v in division.values() for c in v)
        differs = collections.Counter(
            c for m, v in division.items() for c, (code, _) in v.items()
            if (m[:6], c) in current and current[(m[:6], c)] != code)
        years[year] = {"municipalities": len(division), "published": dict(published),
                       "differs_from_current": dict(differs),
                       "not_current": sorted(m for m in division if m[:6] not in municipalities_now)}
    out = Path("data/probes/geography/ibge_dtb_vintages.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(years, ensure_ascii=False, indent=1), encoding="utf-8")
    for year, body in years.items():
        print(year, body["municipalities"], body["published"], "differs:", body["differs_from_current"],
              "not current:", len(body["not_current"]))


if __name__ == "__main__":
    main()
