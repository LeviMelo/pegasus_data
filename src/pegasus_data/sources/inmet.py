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

**Read** by a context consumer as one value per municipality and year
(`municipality_years`), numerator and denominator as two fields (``over``):
- *Coverage* of a station-month is its days observed over the days of the month
  (an hourly station's readings / 24, a daily station's readings), at most 1.
- A *municipality-month* is the mean of its stations' months weighted by their
  coverage (no station counts more for being hourly); its own coverage is its
  best station's.
- A *municipality-year* is the sum over months of coverage and of coverage times
  the month's value: ``months`` observed (0 to 12) is the denominator of every
  temperature field, so the mean at use is a coverage-weighted mean of the months
  held, and a year with gaps is flagged ``partial_year``, never a quiet mean of
  the wrong months (a missing winter reads as a warm year).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from . import download

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

#: Readings a station of each network makes in a day: the unit that turns a count of readings into days observed.
READINGS_PER_DAY = {"automatic_hourly": 24, "conventional_daily": 1}

__all__ = ["COAST_TOLERANCE_M", "MESH", "NETWORKS", "READINGS_PER_DAY", "MEASURES", "RECORD", "fetch", "min_months",
           "monthly", "municipality_years", "stations"]


def fetch(name: str, cache_dir: str | Path, *, timeout: float = 3000.0) -> Path:
    """One source file (mirror, INMET API, NOAA history or IBGE mesh), cached."""
    target = Path(cache_dir) / name
    if target.is_file():
        return target
    # streamed to disk (the mirror's database is 1.4 GB), under a name no reader takes for the finished file
    got = download(_SOURCES.get(name) or RECORD.format(name=name), target.with_name(target.name + ".dl"), timeout=timeout, agent=USER_AGENT)
    with got.open("rb") as handle:
        gzipped = handle.read(2) == bytes((0x1F, 0x8B))
    if gzipped:                            # IBGE sends gzip without saying so: decompressed file to file
        import gzip
        import shutil

        tmp = target.with_name(target.name + ".tmp")
        with gzip.open(got, "rb") as src, tmp.open("wb") as out:
            shutil.copyfileobj(src, out, 1 << 24)
        got.unlink()
        tmp.replace(target)
    else:
        got.replace(target)
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


#: The measures of `municipality_years` (its columns) and the variable each belongs to. A variable has one
#: denominator, ``<variable>_months``, and one status: ``ok`` when it has `min_months` observed.
MEASURES = {
    "temperature_months": "temperature", "air_temperature": "temperature",
    "air_temperature_monthly_max": "temperature", "air_temperature_monthly_min": "temperature",
    "precipitation_months": "precipitation", "precipitation_mm": "precipitation",
}


def min_months() -> float:
    """The months of a year a variable must have observed for its year to be ``ok`` (``inmet: min_months`` in
    ``curation/fields.yml``, with the measurement that chose it)."""
    from ..config import curation_root
    from ..ontology import _read_yaml

    return float(((_read_yaml(curation_root() / "fields.yml") or {})["inmet"])["min_months"])


def municipality_years(table: Any) -> Any:
    """One row per municipality and year from placed station-months (a pyarrow table of `monthly` with
    ``municipality`` and ``municipality7``): the sums a mean is made of, per variable, and what they rest on.

    Columns, for the variable ``temperature`` (readings of air temperature) and ``precipitation``:
    - ``<variable>_months``: months observed, the sum over months of the best station's coverage (0 to 12);
    - ``air_temperature`` (°C × months), ``air_temperature_monthly_max`` and ``..._min`` (the stations' mean of the
      month's extreme, × months), ``precipitation_mm`` (the stations' mean month total, mm × months): over the
      variable's months they are the coverage-weighted means of the months held;
    - ``<variable>_stations`` and ``<variable>_automatic_share`` (share of the coverage that came from automatic
      stations: the two networks differ in what a maximum and a minimum are).
    A variable a municipality-year has no reading of is null: missing is not zero.
    """
    import duckdb
    import pyarrow as pa

    networks = table.column("network").to_pylist()
    unknown = sorted({n for n in networks if n not in READINGS_PER_DAY})
    if unknown:
        raise KeyError(f"networks {unknown} have no declared readings per day: {sorted(READINGS_PER_DAY)}")
    table = table.append_column("per_day", pa.array([READINGS_PER_DAY[n] for n in networks], pa.int32()))
    con = duckdb.connect()
    con.register("sm", table)
    return con.execute("""
        WITH base AS (
            SELECT *, date_diff('day', make_date(CAST(year AS INTEGER), CAST(month AS INTEGER), 1),
                                make_date(CAST(year AS INTEGER), CAST(month AS INTEGER), 1) + INTERVAL 1 MONTH) AS days,
                   (network = 'automatic_hourly') AS auto
            FROM sm),
        t AS (          -- one municipality-month of temperature: stations averaged by coverage
            SELECT municipality, year, month, max(cov) AS cov, sum(cov * mean) / sum(cov) AS mean,
                   sum(cov * tmax) FILTER (WHERE tmax IS NOT NULL) / sum(cov) FILTER (WHERE tmax IS NOT NULL) AS tmax,
                   sum(cov * tmin) FILTER (WHERE tmin IS NOT NULL) / sum(cov) FILTER (WHERE tmin IS NOT NULL) AS tmin,
                   sum(cov * CAST(auto AS INTEGER)) AS auto_cov, sum(cov) AS all_cov, list(DISTINCT station_id) AS stations
            FROM (SELECT municipality, year, month, station_id, auto,
                         least(1.0, temperature_readings / per_day / days) AS cov,
                         temperature_c_sum / temperature_readings AS mean,
                         temperature_c_max AS tmax, temperature_c_min AS tmin
                  FROM base WHERE temperature_readings > 0)
            GROUP BY municipality, year, month),
        ty AS (
            SELECT municipality, year, sum(cov) AS temperature_months, sum(cov * mean) AS air_temperature,
                   sum(cov * tmax) AS air_temperature_monthly_max, sum(cov * tmin) AS air_temperature_monthly_min,
                   len(list_distinct(flatten(list(stations)))) AS temperature_stations,
                   sum(auto_cov) / sum(all_cov) AS temperature_automatic_share
            FROM t GROUP BY municipality, year),
        p AS (          -- one municipality-month of precipitation: the stations' total, per unit of coverage
            SELECT municipality, year, month, max(cov) AS cov, sum(total) / sum(cov) AS mm,
                   sum(cov * CAST(auto AS INTEGER)) AS auto_cov, sum(cov) AS all_cov, list(DISTINCT station_id) AS stations
            FROM (SELECT municipality, year, month, station_id, auto,
                         least(1.0, precipitation_readings / per_day / days) AS cov, precipitation_mm_sum AS total
                  FROM base WHERE precipitation_readings > 0)
            GROUP BY municipality, year, month),
        py AS (
            SELECT municipality, year, sum(cov) AS precipitation_months, sum(cov * mm) AS precipitation_mm,
                   len(list_distinct(flatten(list(stations)))) AS precipitation_stations,
                   sum(auto_cov) / sum(all_cov) AS precipitation_automatic_share
            FROM p GROUP BY municipality, year),
        places AS (SELECT municipality, any_value(municipality7) AS municipality7 FROM base GROUP BY municipality)
        SELECT municipality, places.municipality7, CAST(year AS INTEGER) AS year,
               temperature_months, air_temperature, air_temperature_monthly_max, air_temperature_monthly_min,
               temperature_stations, temperature_automatic_share,
               precipitation_months, precipitation_mm, precipitation_stations, precipitation_automatic_share
        FROM ty FULL JOIN py USING (municipality, year) JOIN places USING (municipality)
        ORDER BY municipality, year""").to_arrow_table()
