"""Minimum comparable areas (AMC) from IPEA's geobr, read without GIS libraries.

An AMC is the smallest set of municipalities whose combined territory is the
same at both ends of a period, so a series rolled up to AMCs is not broken by
a municipality splitting off. IPEA's geobr publishes them for any pair of
census years up to 2010, generated with the routine of Ehrl (2017), Estudos
Econômicos 47(1). Each GeoPackage is SQLite; only its attribute columns are
read: ``code_amc`` and the list of 2010 municipality codes in it.

Municipalities created after 2010 belong to no published AMC and are left
unassigned rather than given a parent.
"""

from __future__ import annotations

import sqlite3
import urllib.request
from pathlib import Path

URL = "https://www.ipea.gov.br/geobr/data_gpkg/amc/{start}/AMC_{start}_2010_simplified.gpkg"

__all__ = ["URL", "comparable_areas", "fetch"]


def fetch(start: int, cache_dir: str | Path, *, timeout: float = 300.0) -> Path:
    """IPEA's AMC GeoPackage for ``start``–2010, cached."""
    target = Path(cache_dir) / f"AMC_{start}_2010_simplified.gpkg"
    if target.is_file():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(URL.format(start=start), timeout=timeout) as response:
        data = response.read()
    if not data.startswith(b"SQLite format 3"):
        raise FileNotFoundError(f"IPEA returned no GeoPackage for AMC {start}-2010")
    tmp = target.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(target)
    return target


def comparable_areas(path: str | Path) -> list[tuple[str, str, str]]:
    """``(municipality code7, AMC code, AMC label)`` for every 2010 municipality."""
    con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
    try:
        table = con.execute("SELECT table_name FROM gpkg_contents LIMIT 1").fetchone()[0]
        rows = con.execute(
            f'SELECT code_amc, list_code_muni_2010, list_name_muni_2010 FROM "{table}"'
        ).fetchall()
    finally:
        con.close()
    out: list[tuple[str, str, str]] = []
    for code_amc, codes, _names in rows:
        amc = str(int(float(code_amc)))   # stored as a float: 1001.0
        members = [c.strip() for c in str(codes or "").replace(";", ",").split(",")]
        members = [c for c in members if c.isdigit() and len(c) == 7]
        for code in members:
            out.append((code, amc, f"AMC {amc} ({len(members)} municipalities in 2010)"))
    return out
