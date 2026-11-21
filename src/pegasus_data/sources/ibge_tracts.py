"""The Census 2022 by tract: who lives in each census tract, by sex and age, as IBGE publishes it (ADR-0203).

**The product** (IBGE, *Agregados por Setores Censitários*, ``SOURCE``; dictionary of 2026-05-20): one CSV per theme
for Brazil's 472,780 tracts. Two are read:

* **básico** (Windows-1252; "." is "not applicable", read as null): the tract's identity (``CD_SETOR``, 15 digits whose first 7 are the municipality; urban or
  rural situation ``SITUACAO``/``CD_SIT``, type, area in km², district, subdistrict, neighbourhood, urban nucleus,
  agglomeration, intermediate and immediate regions, urban concentration) and its counts ``v0001`` (residents) to
  ``v0009`` (households by kind; ``v0005`` and ``v0006`` are a mean and a share and are not stored);
* **demografia** (458,772 tracts, the ones with residents): ``V01006`` residents, ``V01007``/``V01008`` men and women,
  ``V01009``-``V01019`` men and ``V01020``-``V01030`` women in eleven bands (0-4, 5-9, 10-14, 15-19, 20-24, 25-29,
  30-39, 40-49, 50-59, 60-69, 70 or more).

**Disclosure.** IBGE suppresses a count that could identify someone and writes ``X``; it is a missing value with its
reason (``suppressed``), never a zero, and never filled from the tract's other counts (CLAUDE.md §6). IBGE's own municipal
file of the theme is the sum of the same published cells, so it falls short too; the tract's residents in the basic file
(``v0001``) are never suppressed, and the people the bands leave out are measured against them (`municipal_check`) and
reported, not spread.

**Stored** once per data home in ``registries/ibge_tracts/``: the zips, ``tracts_2022.parquet`` (identity and counts)
and ``tract_population_2022.parquet`` (long: tract, sex, band, people, suppressed). The tract polygons are IBGE's tract
mesh with the basic counts, ``registries/ibge_points/tracts.gpkg`` (`tract_mesh`), where the points pack had kept it.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ..semantics.curation import declared

SOURCE = "https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/"
FILES = {"basico": declared("published_tables.yml", "ibge_tracts", "basic_file"),
         "demografia": "Agregados_por_Setor_csv/Agregados_por_setores_demografia_BR.zip",
         "municipios_demografia": "Agregados_por_Municipio_csv/Agregados_por_municipios_demografia_BR.zip"}
MESH = "malha_com_atributos/setores/gpkg/BR/BR_setores_CD2022.gpkg"
#: The eleven bands of the demography file, as (from, to) in years; None is open
BANDS = ((0, 4), (5, 9), (10, 14), (15, 19), (20, 24), (25, 29), (30, 39), (40, 49), (50, 59), (60, 69), (70, None))
#: The variables of each sex's bands, in BANDS order (declared with the dictionary's source in ``curation/published_tables.yml``)
SEX_BANDS = declared("published_tables.yml", "ibge_tracts", "sex_band_variables")
COUNTS = ("v0001", "v0002", "v0003", "v0004", "v0007", "v0008", "v0009")
IDENTITY = ("CD_SETOR", "SITUACAO", "CD_SIT", "CD_TIPO", "AREA_KM2", "CD_MUN", "NM_MUN", "CD_DIST", "NM_DIST", "CD_SUBDIST",
            "NM_SUBDIST", "CD_BAIRRO", "NM_BAIRRO", "CD_NU", "NM_NU", "CD_AGLOM", "NM_AGLOM", "CD_RGINT", "NM_RGINT",
            "CD_RGI", "NM_RGI", "CD_CONCURB", "NM_CONCURB")

__all__ = ["BANDS", "build", "tract_mesh", "tract_population", "tracts"]


def _directory(root: str | Path | None) -> Path:
    from ..config import load_settings

    return load_settings(root=root).registry_dir("ibge_tracts")


def _csv(zip_path: Path, encoding: str) -> Any:
    """The one CSV of an IBGE zip as strings (a pyarrow table), every value kept as written."""
    import zipfile

    import pyarrow as pa
    import pyarrow.csv as pacsv

    with zipfile.ZipFile(zip_path) as archive:
        member = next(n for n in archive.namelist() if n.lower().endswith(".csv"))
        with archive.open(member) as handle:
            table = pacsv.read_csv(handle, read_options=pacsv.ReadOptions(encoding=encoding),
                                   parse_options=pacsv.ParseOptions(delimiter=";"),
                                   convert_options=pacsv.ConvertOptions(column_types={}, strings_can_be_null=False,
                                                                        auto_dict_encode=False, quoted_strings_can_be_null=False))
    return table.cast(pa.schema([pa.field(n, pa.string()) for n in table.column_names]))


def _count(column: Any) -> tuple[Any, Any]:
    """An IBGE count column as (int64 with nulls, suppressed flag): ``X`` is suppressed; any other non-number raises."""
    import pyarrow as pa
    import pyarrow.compute as pc

    suppressed = pc.equal(column, "X")
    numeric = pc.match_substring_regex(column, r"^[0-9]+$")
    odd = pc.invert(pc.or_(suppressed, numeric))
    if pc.any(odd).as_py():
        raise ValueError(f"unexpected values in an IBGE count: {pc.unique(pc.filter(column, odd)).to_pylist()[:5]}")
    value = pc.cast(pc.if_else(numeric, column, pa.scalar(None, pa.string())), pa.int64())
    return value, suppressed


def build(root: str | Path | None = None) -> dict[str, Any]:
    """Download the basic and demography files (once) and write the two tables. Returns the tracts, the residents in
    each file, the suppressed cells and the check of the tracts' sums against IBGE's municipal file."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    from ..transport import download

    directory = _directory(root)
    directory.mkdir(parents=True, exist_ok=True)
    paths = {k: download(SOURCE + v, directory / Path(v).name, timeout=3600) for k, v in FILES.items()}

    basic = _csv(paths["basico"], "cp1252")
    columns: dict[str, Any] = {"tract": basic.column("CD_SETOR"), "municipality7": pc.utf8_slice_codeunits(basic.column("CD_SETOR"), 0, 7)}
    for name in IDENTITY[1:]:          # "." is IBGE's "not applicable" (a tract in no urban nucleus, a lagoon's municipality)
        column = basic.column(name)
        columns[name.lower()] = pc.if_else(pc.equal(column, "."), pa.scalar(None, pa.string()), column)
    columns["area_km2"] = pc.cast(pc.replace_substring(basic.column("AREA_KM2"), ",", "."), pa.float64())
    suppressed_basic = 0
    for name in COUNTS:
        value, suppressed = _count(basic.column(name))
        columns[name] = value
        suppressed_basic += int(pc.sum(suppressed).as_py() or 0)
    identity = pa.table(columns)
    # a tract code begins with its municipality's; the two lagoons (4300001, 4300002: no municipality) have none
    if pc.any(pc.fill_null(pc.not_equal(identity.column("municipality7"), identity.column("cd_mun")), False)).as_py():
        raise ValueError("a tract code does not begin with its municipality's")

    demo = _csv(paths["demografia"], "utf8")
    tract = demo.column("CD_setor")
    parts, suppressed_cells = [], 0
    for sex, names in SEX_BANDS.items():
        for (low, high), name in zip(BANDS, names, strict=True):
            value, suppressed = _count(demo.column(name))
            suppressed_cells += int(pc.sum(suppressed).as_py() or 0)
            n = len(tract)
            parts.append(pa.table({"tract": tract, "municipality7": pc.utf8_slice_codeunits(tract, 0, 7),
                                   "sex": pa.array([sex] * n), "age_from": pa.array([low] * n, pa.int16()),
                                   "age_to": pa.array([high] * n, pa.int16()), "people": pc.cast(value, pa.int32()),
                                   "suppressed": suppressed}))
    population = pa.concat_tables(parts).sort_by([("tract", "ascending"), ("sex", "ascending"), ("age_from", "ascending")])
    residents, residents_suppressed = _count(demo.column("V01006"))
    for table, name in ((identity, "tracts_2022.parquet"), (population, "tract_population_2022.parquet")):
        tmp = directory / f"_{name}.{os.getpid()}.tmp"
        try:
            pq.write_table(table, tmp, compression="zstd")
            os.replace(tmp, directory / name)
        finally:
            tmp.unlink(missing_ok=True)
    return {"tracts": identity.num_rows, "tracts_with_demography": len(tract),
            "residents_basic": int(pc.sum(identity.column("v0001")).as_py()),
            "residents_demography_unsuppressed": int(pc.sum(residents).as_py()),
            "tracts_residents_suppressed": int(pc.sum(residents_suppressed).as_py()),
            "sex_band_cells": population.num_rows, "sex_band_cells_suppressed": suppressed_cells,
            "basic_counts_suppressed": suppressed_basic, "municipal_check": municipal_check(root)}


def municipal_check(root: str | Path | None = None) -> dict[str, Any]:
    """What suppression leaves out, measured two ways. IBGE's municipal demography file against the tracts' unsuppressed
    sums (it is built from the same cells, so a difference would be a reading error), and the tracts' residents
    (``v0001`` of the basic file, never suppressed) against the sum of their published sex-band cells: per municipality the
    people the bands leave out. Reported, never spread back."""
    import duckdb

    from ..transport import download

    directory = _directory(root)
    path = download(SOURCE + FILES["municipios_demografia"], directory / Path(FILES["municipios_demografia"]).name)
    con = duckdb.connect()
    con.register("m", _csv(path, "cp1252"))
    population = (directory / "tract_population_2022.parquet").as_posix()
    identity = (directory / "tracts_2022.parquet").as_posix()
    long = " UNION ALL ".join(f"SELECT CD_MUN AS municipality7, '{sex}' AS sex, {low} AS age_from, TRY_CAST({name} AS BIGINT) AS people FROM m"
                              for sex, names in SEX_BANDS.items() for (low, _), name in zip(BANDS, names, strict=True))
    file_row = con.execute(f"""WITH pub AS ({long}),
        tr AS (SELECT municipality7, sex, age_from, sum(people) AS people FROM read_parquet('{population}') GROUP BY ALL)
        SELECT sum(pub.people), sum(coalesce(tr.people, 0)), count(*) FILTER (WHERE pub.people <> coalesce(tr.people, 0))
        FROM pub LEFT JOIN tr USING (municipality7, sex, age_from)""").fetchone()
    short = con.execute(f"""WITH r AS (SELECT municipality7, sum(v0001) AS residents FROM read_parquet('{identity}')
                                       WHERE municipality7 NOT IN ('4300001', '4300002') GROUP BY 1),
        b AS (SELECT municipality7, sum(people) AS banded FROM read_parquet('{population}') GROUP BY 1)
        SELECT sum(residents), sum(coalesce(banded, 0)), count(*) FILTER (WHERE residents > coalesce(banded, 0)),
               count(*) FILTER (WHERE residents > 0 AND 1 - coalesce(banded, 0) / residents > 0.05),
               max(1 - coalesce(banded, 0) / residents) FILTER (WHERE residents > 0)
        FROM r LEFT JOIN b USING (municipality7)""").fetchone()
    return {"municipal_file_people": file_row[0], "tracts_unsuppressed_people": file_row[1], "cells_differing": file_row[2],  # type: ignore[index]  # duckdb stub: fetchone is Optional; an aggregate returns one row
            "residents": short[0], "residents_in_published_bands": short[1], "municipalities_short": short[2],  # type: ignore[index]  # duckdb stub: fetchone is Optional; an aggregate returns one row
            "municipalities_short_over_5pct": short[3], "largest_share_short": round(float(short[4] or 0), 4)}  # type: ignore[index]  # duckdb stub: fetchone is Optional; an aggregate returns one row


def _where(municipality: Any, uf: Any) -> str:
    clauses = []
    if municipality is not None:
        values = [str(v).strip() for v in ([municipality] if isinstance(municipality, (str, int)) else municipality)]
        from ..geography import place_municipalities

        placed = place_municipalities(values)
        if None in placed:
            raise ValueError(f"not municipality codes (6 or 7 digits naming a municipality): "
                             f"{[v for v, p in zip(values, placed, strict=True) if p is None]}")
        clauses.append("municipality7 IN (" + ",".join(repr(str(p)) for p in sorted(set(placed))) + ")")
    if uf is not None:
        states = [str(s).strip() for s in ([uf] if isinstance(uf, (str, int)) else uf)]
        clauses.append("substr(municipality7, 1, 2) IN (" + ",".join(repr(s) for s in states) + ")")
    return ("WHERE " + " AND ".join(clauses)) if clauses else ""


def _read(name: str, municipality: Any, uf: Any, root: str | Path | None) -> Any:
    import duckdb

    path = _directory(root) / name
    if not path.is_file():
        raise FileNotFoundError(f"the tract tables are not built in {path.parent}; run `pegasus-data tracts`")
    return duckdb.connect().execute(f"SELECT * FROM read_parquet('{path.as_posix()}') {_where(municipality, uf)}").to_arrow_table()


def tracts(*, municipality: Any = None, uf: Any = None, root: str | Path | None = None) -> Any:
    """The Census 2022 tracts (a pyarrow table): identity, urban/rural situation, area, the places they belong to and the
    basic counts (``v0001`` residents …), a suppressed count null."""
    return _read("tracts_2022.parquet", municipality, uf, root)


def tract_population(*, municipality: Any = None, uf: Any = None, root: str | Path | None = None) -> Any:
    """Residents of each tract by sex (``1`` men, ``2`` women) and age band (``age_from``, ``age_to``; 70+ open), long; a
    count IBGE suppressed is null with ``suppressed`` true, never 0."""
    return _read("tract_population_2022.parquet", municipality, uf, root)


def tract_mesh(*, municipality: Any = None, uf: Any = None, root: str | Path | None = None) -> Any:
    """IBGE's 2022 tract polygons (a GeoDataFrame, SIRGAS 2000), one row per tract (a tract in several pieces is merged:
    the file repeats its counts on each piece), from ``registries/ibge_points/tracts.gpkg`` (downloaded once)."""
    import geopandas as gpd

    from ..config import load_settings
    from ..transport import download

    path = download(SOURCE + MESH, load_settings(root=root).registry_dir("ibge_points", "tracts.gpkg"),
                    timeout=7200)
    where = _where(municipality, uf).replace("WHERE ", "").replace("municipality7", "CD_MUN") or None
    frame = gpd.read_file(path, where=where, columns=["CD_SETOR", "CD_MUN", "SITUACAO"])
    return frame.dissolve(by="CD_SETOR", aggfunc="first").reset_index()


#: The public names (`pegasus_data.tract_population`, `census_tracts`)
census_tracts = tracts
