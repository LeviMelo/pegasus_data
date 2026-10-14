"""INMET weather stations: station-months, measured where a station stands.

**Readings.** A CC-BY-4.0 mirror of INMET's releases on Zenodo (record
14925215): automatic stations hourly from 2000, conventional stations daily.
Checked against INMET's own 2022 archive for Brasília A001 on 2026-10-03:
1,356.4 mm of precipitation and a 21.247 °C mean in both.

**Positions,** in order:
- INMET's station API (`apitempo.inmet.gov.br/estacoes/T|M`, current stations);
- the mirror's catalog;
- NOAA's ISD history, for conventional stations closed before both.

`coordinates_from` names which. INMET's firewall resets a request with no
browser user agent, which is not an outage.

**Placement.** A station is placed in the municipality whose IBGE boundary
contains it: a geopandas spatial join over IBGE's full-resolution municipal
mesh. A coastal station within ``COAST_TOLERANCE_M`` of the mesh takes the
nearest municipality. INMET also registers a municipality in each station's
WIGOS identifier (`0-76-0-<IBGE code>...`); it is kept beside the placement as
`inmet_municipality7`.
- The two agree for 715 of 757 stations.
- Most of the rest are stations on a border (under 1 km).
- A few are plain registry errors (Lençóis A425 registered 307 km away).

A municipality without a station has no row.

**Stored** per station and month as sums, counts and extremes, never finished
means (CLAUDE.md §6). A mean is computed at use.

**Role.** These stations are *observations*, no longer the source of the municipal climate fields: a station gives the
climate of its own site, and 8 of Alagoas's 102 municipalities have a usable station-year (ADR-0178; the fields are read
from gridded products, `climate_grid.py`). `climate` stays as the station-month base, and `station_months` gives the
complete station-months the gridded fields are validated against (docs/evaluation/2026-10-14-climate-gridded-fields.md).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..transport import download

RECORD = "https://zenodo.org/api/records/14925215/files/{name}/content"
INMET_STATIONS = "https://apitempo.inmet.gov.br/estacoes/{kind}"
ISD_HISTORY = "https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv"
#: How far outside the mesh a coastal station may stand and still be placed.
COAST_TOLERANCE_M = 2000
#: (mirror catalog, mirror database, INMET API kind, network) for the two station networks.
NETWORKS = (("inmet_autoh_catalog.csv", "inmet_autoh_db.parquet", "T", "automatic_hourly"),
            ("inmet_convd_catalog.csv", "inmet_convd_db.parquet", "M", "conventional_daily"))
_SOURCES = {"isd-history.csv": ISD_HISTORY,
            "inmet_stations_T.json": INMET_STATIONS.format(kind="T"),
            "inmet_stations_M.json": INMET_STATIONS.format(kind="M")}

__all__ = ["COAST_TOLERANCE_M", "NETWORKS", "RECORD", "fetch", "monthly", "station_months", "stations"]


def fetch(name: str, cache_dir: str | Path, *, timeout: float = 3000.0) -> Path:
    """One source file (mirror, INMET API or NOAA history), cached."""
    # streamed to disk (the mirror's database is 1.4 GB)
    return download(_SOURCES.get(name) or RECORD.format(name=name), Path(cache_dir) / name, timeout=timeout)


def stations(cache_dir: str | Path, mesh: str | Path) -> list[dict[str, Any]]:
    """Every station with readings, its position's source, and the municipality it stands in (``mesh``: IBGE's maxima
    municipal mesh, `geography.mesh_file`)."""
    import duckdb
    import geopandas as gpd
    import pandas as pd

    frames = []
    for catalog, db, kind, network in NETWORKS:
        api = pd.DataFrame(json.loads(fetch(f"inmet_stations_{kind}.json", cache_dir).read_text(encoding="utf-8")))
        api = pd.DataFrame({
            "station_id": api["CD_ESTACAO"].astype(str), "station_name": api["DC_NOME"],
            "lon": pd.to_numeric(api["VL_LONGITUDE"], errors="coerce"),
            "lat": pd.to_numeric(api["VL_LATITUDE"], errors="coerce"), "state": api["SG_ESTADO"],
            "inmet_municipality7": api["CD_WSI"].map(_wsi_municipality), "coordinates_from": "INMET API"})
        mirror = pd.read_csv(fetch(catalog, cache_dir), sep=";", dtype={"station_id": str})
        mirror = pd.DataFrame({"station_id": mirror["station_id"], "station_name": mirror["station_name"],
                               "lon": mirror["station_x"], "lat": mirror["station_y"], "state": mirror["state_alias"],
                               "inmet_municipality7": None, "coordinates_from": "Zenodo catalog"})
        seen = {str(r[0]) for r in duckdb.sql(
            f"SELECT DISTINCT CAST(station_id AS VARCHAR) FROM read_parquet('{fetch(db, cache_dir).as_posix()}')").fetchall()}
        frame = pd.concat([api, mirror], ignore_index=True).drop_duplicates("station_id")
        if network == "conventional_daily":
            # Closed before INMET's and the mirror's catalogs: NOAA's history.
            isd = pd.read_csv(fetch("isd-history.csv", cache_dir), dtype=str)
            isd = isd[(isd["CTRY"] == "BR") & isd["USAF"].str.endswith("0")].assign(station_id=lambda d: d["USAF"].str[:5])
            isd = isd[isd["station_id"].isin(seen - set(frame["station_id"]))].drop_duplicates("station_id", keep="last")
            frame = pd.concat([frame, pd.DataFrame({
                "station_id": isd["station_id"], "station_name": isd["STATION NAME"],
                "lon": pd.to_numeric(isd["LON"], errors="coerce"), "lat": pd.to_numeric(isd["LAT"], errors="coerce"),
                "state": None, "inmet_municipality7": None, "coordinates_from": "NOAA ISD history"})], ignore_index=True)
        frames.append(frame[frame["station_id"].isin(seen)].assign(network=network))
    table = pd.concat(frames, ignore_index=True).dropna(subset=["lon", "lat"]).reset_index(drop=True)
    points = gpd.GeoDataFrame(table, geometry=gpd.points_from_xy(table.lon, table.lat), crs="EPSG:4674")
    mesh = gpd.read_file(mesh)[["codarea", "geometry"]].set_crs("EPSG:4674", allow_override=True)
    placed = gpd.sjoin(points, mesh, how="left", predicate="within").drop(columns="index_right")
    placed = placed[~placed.index.duplicated()]
    placed["placed_by"] = placed["codarea"].where(placed["codarea"].isna(), "within")
    missing = placed["codarea"].isna()
    if missing.any():
        # Distances in metres: SIRGAS 2000 / Brazil Polyconic.
        near = gpd.sjoin_nearest(points[missing].to_crs("EPSG:5880"), mesh.to_crs("EPSG:5880"),
                                 how="left", max_distance=COAST_TOLERANCE_M)
        near = near[~near.index.duplicated()]
        placed.loc[missing, "codarea"] = near["codarea"]
        placed.loc[missing & placed["codarea"].notna(), "placed_by"] = f"nearest within {COAST_TOLERANCE_M} m"
    keep = ["station_id", "station_name", "network", "state", "lon", "lat", "coordinates_from",
            "inmet_municipality7", "placed_by"]
    out = placed.rename(columns={"codarea": "municipality7"})[keep + ["municipality7"]]
    return [{k: (None if pd.isna(v) else v) for k, v in row.items()} for row in out.to_dict("records")]


def monthly(cache_dir: str | Path, years: list[int] | None = None) -> Any:
    """Station-month sums, counts and extremes of both networks (a pyarrow table)."""
    import duckdb

    con = duckdb.connect()
    where = f"WHERE year(datetime) IN ({','.join(str(y) for y in years)})" if years else ""
    parts = []
    for _catalog, db, _kind, network in NETWORKS:
        path = fetch(db, cache_dir).as_posix()
        temp, tmax, tmin = (("temp_db", "temp_db", "temp_db") if network == "automatic_hourly"
                            else ("temp_mean", "temp_max", "temp_min"))
        parts.append(f"""
            SELECT CAST(station_id AS VARCHAR) AS station_id, '{network}' AS network,
                   year(datetime) AS year, month(datetime) AS month,
                   sum(p) AS precipitation_mm_sum, count(p) AS precipitation_readings,
                   sum({temp}) AS temperature_c_sum, count({temp}) AS temperature_readings,
                   max({tmax}) AS temperature_c_max, min({tmin}) AS temperature_c_min
              FROM read_parquet('{path}') {where}
             GROUP BY ALL""")
    return con.execute(" UNION ALL ".join(parts)).to_arrow_table()


def _wsi_municipality(wsi: object) -> str | None:
    """The IBGE code INMET writes into a WIGOS identifier: ``0-76-0-2900306000000688``."""
    match = re.match(r"0-76-0-(\d{7})", str(wsi or ""))
    return match.group(1) if match else None


def station_months(cache_dir: str | Path, years: list[int] | None = None, complete: float = 0.9) -> Any:
    """Station-months of both networks with the daily statistics a gridded product is validated against (a pyarrow table):
    ``temperature_mean`` (an automatic station's 24-hour mean of its hourly readings, a conventional station's INMET
    mean), ``temperature_midrange`` (the month's mean of (daily maximum + daily minimum) / 2), ``temperature_max`` and
    ``temperature_min`` (the month's means of the daily extremes), ``precipitation_mm`` (the month total).

    A day counts when it has 20 hourly readings of the variable (an automatic station) or its daily value (a
    conventional one); a month is **complete** when at least ``complete`` of its days count, and a variable of a
    month that is not complete is null, never a statistic of the days held. A precipitation total is the mean
    counted day times the days of the month. An hourly gauge that reported nothing is a null month, not a dry one.
    """
    import duckdb

    con = duckdb.connect()
    where = f"WHERE year(datetime) IN ({','.join(str(y) for y in years)})" if years else ""
    parts = []
    for _catalog, db, _kind, network in NETWORKS:
        path = fetch(db, cache_dir).as_posix()
        if network == "automatic_hourly":
            daily = f"""SELECT CAST(station_id AS VARCHAR) AS station_id, CAST(datetime AS DATE) AS day,
                               if(count(temp_db) >= 20, avg(temp_db), NULL) AS tmean, if(count(temp_db) >= 20, max(temp_db), NULL) AS tmax,
                               if(count(temp_db) >= 20, min(temp_db), NULL) AS tmin, if(count(p) >= 20, sum(p), NULL) AS p
                          FROM read_parquet('{path}') {where} GROUP BY ALL"""
        else:
            daily = f"""SELECT CAST(station_id AS VARCHAR) AS station_id, CAST(datetime AS DATE) AS day,
                               temp_mean AS tmean, temp_max AS tmax, temp_min AS tmin, p
                          FROM read_parquet('{path}') {where}"""
        parts.append(f"""
            SELECT station_id, '{network}' AS network, year(day) AS year, month(day) AS month,
                   date_diff('day', make_date(year(day), month(day), 1), make_date(year(day), month(day), 1) + INTERVAL 1 MONTH) AS days,
                   count(tmean) AS days_tmean, count(tmax) FILTER (WHERE tmin IS NOT NULL) AS days_extremes, count(p) AS days_p,
                   avg(tmean) AS tmean, avg((tmax + tmin) / 2) AS tmid, avg(tmax) FILTER (WHERE tmin IS NOT NULL) AS tmax,
                   avg(tmin) FILTER (WHERE tmax IS NOT NULL) AS tmin, avg(p) AS p_day
              FROM ({daily}) GROUP BY ALL""")
    return con.execute(f"""
        SELECT station_id, network, year, month,
               if(days_tmean >= {complete} * days, tmean, NULL) AS temperature_mean,
               if(days_extremes >= {complete} * days, tmid, NULL) AS temperature_midrange,
               if(days_extremes >= {complete} * days, tmax, NULL) AS temperature_max,
               if(days_extremes >= {complete} * days, tmin, NULL) AS temperature_min,
               if(days_p >= {complete} * days, p_day * days, NULL) AS precipitation_mm
          FROM ({' UNION ALL '.join(parts)})""").to_arrow_table()
