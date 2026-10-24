"""Validate CPTEC's daily MERGE and SAMeT municipal series (ADR-0204) against BR-DWGD and INMET's stations.

Three checks, each written to ``--out`` (JSON):

1. **BR-DWGD over the overlap** (2000-01 to 2024-02, complete months of both): the area-weighted municipal monthly mean
   Tmax and Tmin and the monthly precipitation against BR-DWGD's municipal zonal means (its ``climate_monthly`` base,
   area-weighted too): bias, RMSE and r pooled, by region and by year, and the anomaly after each municipality-month's
   climatology (the part a model learns from).
2. **INMET's automatic stations, daily** (one year, ``--year``): the grid cell holding each station, read from the
   product's own files for that year, against the station's hourly record (UTC) reduced over three candidate days: the
   UTC calendar day, the local day (03 to 03 UTC) and the gauge day (the 24 h ending 12 UTC). The window that fits best is
   the product's day, tested rather than assumed. INMET's stations are among both products' inputs: a reproduction check.
3. **The store against its own files**: for the same year, the municipal means recomputed from the grids for every
   municipality equal what `update` stored (the pipeline adds nothing and loses nothing).

    python scripts/cptec_validation.py --root C:/Users/Galaxy/pegasus_core_data --year 2023 --out data/probes/climate/cptec_validation.json

Reads the data home (BR-DWGD's cached monthly sums, INMET's registry, the CPTEC store) and, for checks 2 and 3, the year's
files from CPTEC (about 1,460 files, 2.5 GB, nothing kept but the station samples).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

VARIABLES = ("precipitation", "tmax", "tmin", "tmed")


def _stats(con, value: str, reference: str, table: str, where: str = "TRUE", group: str | None = None):  # type: ignore[no-untyped-def]
    keys = f"{group}, " if group else ""
    rows = con.execute(f"""SELECT {keys} count(*), round(avg({value} - {reference}), 3), round(sqrt(avg(({value} - {reference})^2)), 3),
            round(corr({value}, {reference}), 4) FROM {table} WHERE {where} AND {value} IS NOT NULL AND {reference} IS NOT NULL
            {'GROUP BY ' + group + ' ORDER BY ' + group if group else ''}""").fetchall()
    fields = ("n", "bias", "rmse", "r")
    if group:
        return {str(r[0]): dict(zip(fields, r[1:], strict=True)) for r in rows}
    return dict(zip(fields, rows[0], strict=True))


def against_brdwgd(root: Path, settings, names=("tmax", "tmin", "precipitation")) -> dict:  # type: ignore[no-untyped-def]
    import duckdb

    from pegasus_data.sources import brdwgd, cptec

    months, release = brdwgd.municipality_months(root / "registries" / "brdwgd")
    daily = cptec.daily(list(names), start="2000-01-01", end="2024-02-29", weight="area", settings=settings)
    con = duckdb.connect()
    con.register("bm", months)
    con.register("d", daily)
    mean = {"tmax": "avg", "tmin": "avg", "precipitation": "sum"}
    aggregates = ", ".join(f"{mean[n]}({n}) AS {n}, count({n}) AS {n}_days" for n in names)
    con.execute(f"CREATE TABLE c AS SELECT municipality7, year(date) AS year, month(date) AS month, {aggregates} FROM d GROUP BY ALL")
    reference = {"tmax": "b.tmax_sum / b.days", "tmin": "b.tmin_sum / b.days", "precipitation": "b.precipitation_mm_sum"}
    complete = " AND ".join(f"c.{n}_days = b.days" for n in names)
    con.execute(f"""CREATE TABLE j AS SELECT c.*, {', '.join(f'{reference[n]} AS b_{n}' for n in names)}
        FROM c JOIN bm b USING (municipality7, year, month)
        WHERE b.days = date_diff('day', make_date(year, month, 1), make_date(year, month, 1) + INTERVAL 1 MONTH) AND {complete}""")
    out: dict = {"brdwgd_release": {k: release[k] for k in ("record", "version", "published")},
                 "municipality_months": con.execute("SELECT count(*), count(DISTINCT municipality7) FROM j").fetchone()}
    for name in names:
        value, reference = name, f"b_{name}"
        out[name] = {"pooled": _stats(con, value, reference, "j"),
                     "by_region": _stats(con, value, reference, "j", group="substr(municipality7, 1, 1)"),
                     "by_year": _stats(con, value, reference, "j", group="year")}
        row = con.execute(f"""WITH a AS (SELECT {value} - avg({value}) OVER w AS dx, {reference} - avg({reference}) OVER w AS dy FROM j
                WINDOW w AS (PARTITION BY municipality7, month)) SELECT round(corr(dx, dy), 4), round(sqrt(avg((dx - dy)^2)), 3) FROM a""").fetchone()
        out[name]["anomaly"] = {"r": row[0], "rmse": row[1]}
    return out


def _station_days(root: Path, year: int):  # type: ignore[no-untyped-def]
    """Each automatic station's day under three windows (UTC day, local day, the 24 h ending 12 UTC): Tmax, Tmin and the
    mean of the hourly readings, the precipitation total, and the hours behind each."""
    import duckdb

    con = duckdb.connect()
    path = (root / "registries" / "inmet" / "inmet_autoh_db.parquet").as_posix()
    con.execute(f"""CREATE TABLE h AS SELECT CAST(station_id AS VARCHAR) AS station_id, datetime, temp_db, p FROM read_parquet('{path}')
        WHERE datetime >= TIMESTAMP '{year - 1}-12-31' AND datetime < TIMESTAMP '{year + 1}-01-02'""")
    windows = {"utc_day": "datetime", "local_day": "datetime - INTERVAL 3 HOUR", "ends_12utc": "datetime + INTERVAL 12 HOUR"}
    parts = [f"""SELECT station_id, '{name}' AS window, CAST({shifted} AS DATE) AS date, count(temp_db) AS t_hours,
                max(temp_db) AS tmax, min(temp_db) AS tmin, avg(temp_db) AS tmed, count(p) AS p_hours, sum(p) AS precipitation
             FROM h GROUP BY ALL""" for name, shifted in windows.items()]
    return con.execute("SELECT * FROM (" + " UNION ALL ".join(parts) + f") WHERE year(date) = {year}").to_arrow_table()


def against_stations_and_store(root: Path, settings, year: int, variables=VARIABLES) -> dict:  # type: ignore[no-untyped-def]
    import duckdb
    import numpy as np
    import pandas as pd
    import pyarrow as pa

    from pegasus_data.sources import cptec
    from pegasus_data.transport import request

    catalog = pd.read_csv(root / "registries" / "inmet" / "inmet_autoh_catalog.csv", sep=";")
    lon_s, lat_s = catalog["station_x"].to_numpy(float), catalog["station_y"].to_numpy(float)
    samples, consistency = [], {}
    stored = cptec.daily(variables, start=f"{year}-01-01", end=f"{year}-12-31", weight="area", settings=settings).to_pandas()
    stored_pop = cptec.daily(variables, start=f"{year}-01-01", end=f"{year}-12-31", weight="population", settings=settings).to_pandas()
    for variable in variables:
        product = cptec.PRODUCTS[variable]
        files = [f for m in range(1, 13) for f in cptec.listing(product, year, m)]
        state: dict = {}
        worst = {"area": 0.0, "population": 0.0}

        def read(entry, product=product):  # type: ignore[no-untyped-def]
            return entry, cptec.read_file(product, request(entry["url"], interval=cptec.INTERVAL, timeout=300).content)

        stored_by_day = {w: {d: g.set_index("municipality7")[variable] for d, g in f.groupby("date")}
                         for w, f in (("area", stored), ("population", stored_pop))}
        with ThreadPoolExecutor(max_workers=cptec.WORKERS) as pool:
            for n, (entry, (value, stations, lon, lat)) in enumerate(pool.map(read, files)):
                if n % 30 == 0:
                    print(variable, entry["date"], flush=True)
                if "weights" not in state:
                    state["weights"] = cptec.grid(settings, lon, lat)
                    j = np.floor((lon_s - (lon[0] - (lon[1] - lon[0]) / 2)) / (lon[1] - lon[0])).astype(int)
                    i = np.floor((lat_s - (lat[0] - (lat[1] - lat[0]) / 2)) / (lat[1] - lat[0])).astype(int)
                    state["ij"] = (np.clip(i, 0, len(lat) - 1), np.clip(j, 0, len(lon) - 1))
                i, j = state["ij"]
                samples.append(pd.DataFrame({"station_id": catalog["station_id"], "date": entry["date"], "variable": variable,
                                             "grid": value[i, j], "grid_stations": stations[i, j]}))
                reduced = state["weights"].reduce(value, stations)
                for weight in ("area", "population"):
                    day = stored_by_day[weight][entry["date"]]
                    mine = pd.Series(reduced[f"value_{weight}"], index=state["weights"].municipalities).reindex(day.index)
                    worst[weight] = max(worst[weight], float(np.nanmax(np.abs(mine.to_numpy() - day.to_numpy()))))
        consistency[variable] = {"files": len(files), "max_abs_difference": worst}
    grid = pa.Table.from_pandas(pd.concat(samples, ignore_index=True), preserve_index=False)
    import pyarrow.parquet as pq

    cache = Path("data/probes/climate") / f"cptec_station_samples_{year}.parquet"
    cache.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(grid, cache)
    (cache.with_suffix(".consistency.json")).write_text(json.dumps(consistency, default=str), encoding="utf-8")
    station = _station_days(root, year)
    con = duckdb.connect()
    con.register("g", grid)
    con.register("s", station)
    out: dict = {"store_against_its_files": consistency, "windows": {}}
    for variable in variables:
        hours = "p_hours" if variable == "precipitation" else "t_hours"
        out["windows"][variable] = {}
        for window in ("utc_day", "local_day", "ends_12utc"):
            con.execute(f"""CREATE OR REPLACE TABLE j AS SELECT g.grid, s.{variable} AS station, g.grid_stations
                FROM g JOIN s ON s.station_id = g.station_id AND s.date = g.date AND s.window = '{window}'
                WHERE g.variable = '{variable}' AND s.{hours} = 24""")
            out["windows"][variable][window] = {"all": _stats(con, "grid", "station", "j"),
                                                "cell_without_station": _stats(con, "grid", "station", "j", "grid_stations = 0")}
    return out


def main() -> None:
    from pegasus_data.config import load_settings

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--year", type=int, default=2023)
    parser.add_argument("--skip-files", action="store_true", help="only the BR-DWGD comparison (no download)")
    parser.add_argument("--variables", default="tmax,tmin,precipitation", help="the BR-DWGD comparison's variables")
    parser.add_argument("--station-variables", default=",".join(VARIABLES), help="the station and store checks' variables")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    settings = load_settings(root=args.root)
    result = {"run": dt.datetime.now(dt.UTC).isoformat(), "brdwgd": against_brdwgd(args.root, settings, tuple(args.variables.split(",")))}
    if not args.skip_files:
        result["stations"] = against_stations_and_store(args.root, settings, args.year, tuple(args.station_variables.split(",")))
    text = json.dumps(result, indent=1, default=str)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
