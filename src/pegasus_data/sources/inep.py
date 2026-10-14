"""INEP's school census: basic-education enrolments by municipality, as published margins.

Since the 2021 release the open microdata are one row per school
(``microdados_ed_basica_<year>.csv``) with enrolment counts by sex, by
colour/race and by age band (0-3, 4-5, 6-10, 11-14, 15-17, 18+), each a
separate margin; the crossing age x sex x race is not published (handoff
§7.1 asked for it; it does not exist openly). Summed here to the school's
municipality: where the school is, not where the student lives, and an
enrolment is not a person.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pyarrow as pa

from . import download

BASE = "https://download.inep.gov.br/dados_abertos/microdados_censo_escolar_{year}.zip"
MARGINS = {
    "total": ["QT_MAT_BAS"],
    "sex": ["QT_MAT_BAS_FEM", "QT_MAT_BAS_MASC"],
    "race": ["QT_MAT_BAS_BRANCA", "QT_MAT_BAS_PRETA", "QT_MAT_BAS_PARDA", "QT_MAT_BAS_AMARELA",
             "QT_MAT_BAS_INDIGENA", "QT_MAT_BAS_ND"],
    "age_band": ["QT_MAT_BAS_0_3", "QT_MAT_BAS_4_5", "QT_MAT_BAS_6_10", "QT_MAT_BAS_11_14",
                 "QT_MAT_BAS_15_17", "QT_MAT_BAS_18_MAIS"],
}


def fetch(year: int, cache_dir: str | Path, *, timeout: float = 3600.0) -> Path:
    return download(BASE.format(year=year), Path(cache_dir) / f"microdados_censo_escolar_{year}.zip", timeout=timeout)


def enrolments(year: int, cache_dir: str | Path) -> pa.Table:
    """``(municipality7, margin, category, value)``: each published margin summed per municipality.

    ``QT_MAT_BAS_ND`` is colour/race not declared; sex has no such column.
    Each margin sums to ``total`` (2023: 47,304,632 in 5,570 municipalities).
    """
    import pyarrow.compute as pc
    import pyarrow.csv as pacsv

    with zipfile.ZipFile(fetch(year, cache_dir)) as zf:
        name = next(n for n in zf.namelist() if n.lower().endswith(f"microdados_ed_basica_{year}.csv"))
        raw = zf.read(name)
    columns = sorted({c for cs in MARGINS.values() for c in cs})
    table = pacsv.read_csv(
        io.BytesIO(raw),
        read_options=pacsv.ReadOptions(encoding="latin-1"),
        parse_options=pacsv.ParseOptions(delimiter=";"),
        convert_options=pacsv.ConvertOptions(
            include_columns=["CO_MUNICIPIO", *columns],
            column_types={"CO_MUNICIPIO": pa.string(), **{c: pa.float64() for c in columns}}),
    )
    summed = table.group_by("CO_MUNICIPIO").aggregate([(c, "sum") for c in columns])
    parts = []
    for margin, cols in MARGINS.items():
        for column in cols:
            category = "not declared" if column.endswith("_ND") else column.removeprefix("QT_MAT_BAS").lstrip("_").lower() or "all"
            n = summed.num_rows
            parts.append(pa.table({
                "municipality7": summed.column("CO_MUNICIPIO"),
                "margin": pa.array([margin] * n, pa.string()),
                "category": pa.array([category] * n, pa.string()),
                "value": pc.fill_null(summed.column(f"{column}_sum"), 0.0),
            }))
    return pa.concat_tables(parts)
