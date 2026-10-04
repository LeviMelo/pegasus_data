"""INMET weather stations as a municipality-month field, measured where a station stands.

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

Nothing is interpolated: a municipality without a station has no row.

**Stored** per station and month as sums, counts and extremes, never finished
means (CLAUDE.md §6). A mean is computed at use.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import fetch_url

RECORD = "https://zenodo.org/api/records/14925215/files/{name}/content"
INMET_STATIONS = "https://apitempo.inmet.gov.br/estacoes/{kind}"
ISD_HISTORY = "https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv"
MESH = ("https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?formato=application/vnd.geo%2Bjson"
        "&qualidade=maxima&intrarregiao=municipio")
#: INMET's firewall resets requests from non-browser clients.
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0"
#: How far outside the mesh a coastal station may stand and still be placed.
COAST_TOLERANCE_M = 2000
#: (mirror catalog, mirror database, INMET API kind, network) for the two station networks.
NETWORKS = (("inmet_autoh_catalog.csv", "inmet_autoh_db.parquet", "T", "automatic_hourly"),
            ("inmet_convd_catalog.csv", "inmet_convd_db.parquet", "M", "conventional_daily"))
_SOURCES = {"mesh_max.json": MESH, "isd-history.csv": ISD_HISTORY,
            "inmet_stations_T.json": INMET_STATIONS.format(kind="T"),
            "inmet_stations_M.json": INMET_STATIONS.format(kind="M")}

__all__ = ["COAST_TOLERANCE_M", "MESH", "NETWORKS", "RECORD", "fetch", "monthly", "stations"]


def fetch(name: str, cache_dir: str | Path, *, timeout: float = 3000.0) -> Path:
    """One source file (mirror, INMET API, NOAA history or IBGE mesh), cached."""
    target = Path(cache_dir) / name
    if target.is_file():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    data = fetch_url(_SOURCES.get(name) or RECORD.format(name=name), timeout=timeout, agent=USER_AGENT)
    if data[:2] == bytes((0x1F, 0x8B)):   # IBGE sends gzip without saying so
        import gzip

        data = gzip.decompress(data)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(target)
    return target


def stations(cache_dir: str | Path) -> list[dict[str, Any]]:
    """Every station with readings, its position's source, and the municipality it stands in."""
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
    mesh = gpd.read_file(fetch("mesh_max.json", cache_dir))[["codarea", "geometry"]].set_crs("EPSG:4674", allow_override=True)
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
