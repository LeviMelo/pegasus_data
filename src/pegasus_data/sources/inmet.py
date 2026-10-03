"""INMET weather stations as a municipality-month field, measured where a station stands.

The source is a CC-BY-4.0 mirror of INMET's own releases on Zenodo (record
14925215: "A mirror dataset designed for hydrometeorological time series
analysis in Brazil"). It covers automatic stations hourly from 2000 and
conventional stations daily. INMET's portal was unreachable from here on
2026-10-03.

A station is placed in the municipality whose IBGE boundary contains it (a
geopandas spatial join over IBGE's municipal mesh). Nothing is interpolated: a
municipality without a station has no climate row, and a reading belongs to
the municipality it was taken in.

Stored per station and month, as sums, counts and extremes, never finished
means (CLAUDE.md §6):
- precipitation: sum, and the readings counted;
- temperature: sum and count of readings, maximum and minimum.

A mean is computed at use.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Any

RECORD = "https://zenodo.org/api/records/14925215/files/{name}/content"
#: NOAA's station history: coordinates for WMO-numbered stations (USAF = WMO x 10),
#: which places the conventional stations the mirror's 2025 catalog no longer lists.
ISD_HISTORY = "https://www.ncei.noaa.gov/pub/data/noaa/isd-history.csv"
MESH = ("https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR?formato=application/vnd.geo%2Bjson"
        "&qualidade=intermediaria&intrarregiao=municipio")
#: How far outside the mesh a coastal station may stand and still be placed.
COAST_TOLERANCE_M = 2000
#: (catalog, database, kind) for the two station networks.
NETWORKS = (("inmet_autoh_catalog.csv", "inmet_autoh_db.parquet", "automatic_hourly"),
            ("inmet_convd_catalog.csv", "inmet_convd_db.parquet", "conventional_daily"))

__all__ = ["COAST_TOLERANCE_M", "MESH", "NETWORKS", "RECORD", "fetch", "monthly", "stations"]


def fetch(name: str, cache_dir: str | Path, *, timeout: float = 3000.0) -> Path:
    """One file of the mirror (or IBGE's mesh, ``name="mesh.json"``), cached."""
    target = Path(cache_dir) / name
    if target.is_file():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    url = (MESH if name == "mesh.json" else ISD_HISTORY if name == "isd-history.csv"
           else RECORD.format(name=name))
    with urllib.request.urlopen(url, timeout=timeout) as response:
        data = response.read()
    if data[:2] == bytes((0x1F, 0x8B)):   # IBGE sends gzip without saying so
        import gzip

        data = gzip.decompress(data)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(target)
    return target


def stations(cache_dir: str | Path) -> list[dict[str, Any]]:
    """Every station of both networks, with the municipality it stands in.

    A spatial join against IBGE's municipal mesh: the municipality that
    contains the station. A station the mesh's simplified coastline leaves at
    sea (a lighthouse, an island) takes the nearest municipality within
    ``COAST_TOLERANCE_M``. ``placed_by`` says which, and a station farther
    out stays unplaced.
    """
    import geopandas as gpd
    import pandas as pd

    frames = []
    for catalog, _db, kind in NETWORKS:
        frame = pd.read_csv(fetch(catalog, cache_dir), sep=";", dtype={"station_id": str})
        frame["network"] = kind
        frame["coordinates_from"] = "zenodo catalog"
        frames.append(frame)
    listed = pd.concat(frames, ignore_index=True)
    # Conventional stations closed before 2025 are absent from the mirror's
    # catalog but present in its data; NOAA's history gives their position.
    import duckdb

    db = fetch(NETWORKS[1][1], cache_dir).as_posix()
    seen = {str(r[0]) for r in duckdb.sql(f"SELECT DISTINCT CAST(station_id AS VARCHAR) FROM read_parquet('{db}')").fetchall()}
    isd = pd.read_csv(fetch("isd-history.csv", cache_dir), dtype=str)
    isd = isd[(isd["CTRY"] == "BR") & isd["USAF"].str.endswith("0")]
    isd["station_id"] = isd["USAF"].str[:5]
    isd = isd[isd["station_id"].isin(seen - set(listed["station_id"]))].drop_duplicates("station_id", keep="last")
    extra = pd.DataFrame({"station_id": isd["station_id"], "station_name": isd["STATION NAME"],
                          "station_x": pd.to_numeric(isd["LON"], errors="coerce"),
                          "station_y": pd.to_numeric(isd["LAT"], errors="coerce"),
                          "state_alias": "", "network": NETWORKS[1][2], "coordinates_from": "NOAA ISD history"})
    table = pd.concat([listed, extra], ignore_index=True).dropna(subset=["station_x", "station_y"])
    points = gpd.GeoDataFrame(table, geometry=gpd.points_from_xy(table.station_x, table.station_y), crs="EPSG:4674")
    mesh = gpd.read_file(fetch("mesh.json", cache_dir))[["codarea", "geometry"]].set_crs("EPSG:4674", allow_override=True)
    within = gpd.sjoin(points, mesh, how="left", predicate="within").drop(columns="index_right")
    within["placed_by"] = within["codarea"].where(within["codarea"].isna(), "within")
    missing = within["codarea"].isna()
    if missing.any():
        # Distances in metres: SIRGAS 2000 / Brazil Polyconic.
        near = gpd.sjoin_nearest(points[missing].to_crs("EPSG:5880"), mesh.to_crs("EPSG:5880"),
                                 how="left", max_distance=COAST_TOLERANCE_M)
        near = near[~near.index.duplicated()]
        within.loc[missing, "codarea"] = near["codarea"]
        within.loc[missing & within["codarea"].notna(), "placed_by"] = f"nearest within {COAST_TOLERANCE_M} m"
    within = within[~within.index.duplicated()]
    return [{"station_id": row.station_id, "station_name": row.station_name, "network": row.network,
             "state": row.state_alias, "lon": float(row.station_x), "lat": float(row.station_y),
             "municipality7": None if pd.isna(row.codarea) else str(row.codarea),
             "placed_by": None if pd.isna(row.placed_by) else str(row.placed_by),
             "coordinates_from": row.coordinates_from}
            for row in within.itertuples()]


def monthly(cache_dir: str | Path, years: list[int] | None = None) -> Any:
    """Station-month sums, counts and extremes of both networks (a pyarrow table)."""
    import duckdb

    con = duckdb.connect()
    where = f"WHERE year(datetime) IN ({','.join(str(y) for y in years)})" if years else ""
    parts = []
    for _catalog, db, kind in NETWORKS:
        path = fetch(db, cache_dir).as_posix()
        temp, tmax, tmin = (("temp_db", "temp_db", "temp_db") if kind == "automatic_hourly"
                            else ("temp_mean", "temp_max", "temp_min"))
        parts.append(f"""
            SELECT CAST(station_id AS VARCHAR) AS station_id, '{kind}' AS network, year(datetime) AS year, month(datetime) AS month,
                   sum(p) AS precipitation_mm_sum, count(p) AS precipitation_readings,
                   sum({temp}) AS temperature_c_sum, count({temp}) AS temperature_readings,
                   max({tmax}) AS temperature_c_max, min({tmin}) AS temperature_c_min
              FROM read_parquet('{path}') {where}
             GROUP BY ALL""")
    return con.execute(" UNION ALL ".join(parts)).fetch_arrow_table()
