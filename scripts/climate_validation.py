"""Validate the BR-DWGD municipal climate against INMET's complete station-months (ADR-0178).

Each station-month with at least 90% of its days (`inmet.station_months`) is compared with the BR-DWGD municipal value of
the municipality the station stands in (the field a consumer reads, so the spatial representativeness of a station is part
of the error). Temperature: mean daily maximum, mean daily minimum, their mid-range (what `air_temperature` is) against
the station's mid-range and against its 24-hour mean (the difference between those two is definition, not error);
precipitation: the month total. INMET's stations are among BR-DWGD's inputs: this is a reproduction check, not an
independent one.

    python scripts/climate_validation.py --root C:/Users/Galaxy/pegasus_core_data [--out data/probes/climate_validation.json]

Reads only: `<root>/registries/brdwgd` (cached monthly sums; built by `pegasus-data fields`), `<root>/registries/inmet` and
the placement of stations in `<root>/lake/fields/climate`.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

PAIRS = (("midrange", "(g.tmax + g.tmin) / 2", "temperature_midrange"), ("mid vs 24 h mean", "(g.tmax + g.tmin) / 2", "temperature_mean"),
         ("tmax", "g.tmax", "temperature_max"), ("tmin", "g.tmin", "temperature_min"),
         ("precipitation", "g.precipitation_mm", "precipitation_mm"))


def main() -> None:
    import duckdb

    from pegasus_data.sources import brdwgd, inmet

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    months, release = brdwgd.municipality_months(args.root / "registries" / "brdwgd")
    stations = inmet.station_months(args.root / "registries" / "inmet")
    con = duckdb.connect()
    con.register("bm", months)
    con.register("sm", stations)
    con.execute(f"""CREATE TABLE placed AS SELECT DISTINCT station_id, municipality7
        FROM read_parquet('{(args.root / 'lake' / 'fields' / 'climate').as_posix()}/*/*.parquet', hive_partitioning = true)""")
    # a gridded month is complete when the product holds the whole month; the last, partial month of a release is left out
    con.execute("""CREATE TABLE g AS SELECT municipality7, year, month, tmax_sum / days AS tmax, tmin_sum / days AS tmin,
            precipitation_mm_sum / days * date_diff('day', make_date(year, month, 1), make_date(year, month, 1) + INTERVAL 1 MONTH) AS precipitation_mm
        FROM bm WHERE days = date_diff('day', make_date(year, month, 1), make_date(year, month, 1) + INTERVAL 1 MONTH)""")
    con.execute("""CREATE TABLE j AS SELECT s.*, p.municipality7, g.tmax, g.tmin, g.precipitation_mm AS g_precipitation_mm
        FROM sm s JOIN placed p USING (station_id) JOIN g ON g.municipality7 = p.municipality7 AND g.year = s.year AND g.month = s.month""")
    result: dict[str, object] = {"release": {k: release[k] for k in ("record", "version", "published")}, "pooled": {}, "by_region": {}, "by_decade": {}}
    for label, expression, reference in PAIRS:
        value = expression.replace("g.precipitation_mm", "g_precipitation_mm").replace("g.", "")
        where = f"{reference} IS NOT NULL"
        row = con.execute(f"""SELECT count(*), round(avg({value} - {reference}), 3), round(sqrt(avg(({value} - {reference})^2)), 3),
                round(corr({value}, {reference}), 4), count(DISTINCT station_id) FROM j WHERE {where}""").fetchone()
        result["pooled"][label] = dict(zip(("station_months", "bias", "rmse", "r", "stations"), row, strict=True))  # type: ignore[index]
        by_region = con.execute(f"""SELECT substr(municipality7, 1, 1), count(*), round(avg({value} - {reference}), 2),
                round(sqrt(avg(({value} - {reference})^2)), 2) FROM j WHERE {where} GROUP BY 1 ORDER BY 1""").fetchall()
        result["by_region"][label] = {r[0]: {"n": r[1], "bias": r[2], "rmse": r[3]} for r in by_region}  # type: ignore[index]
        by_decade = con.execute(f"""SELECT year // 10 * 10, count(*), round(avg({value} - {reference}), 2),
                round(sqrt(avg(({value} - {reference})^2)), 2) FROM j WHERE {where} GROUP BY 1 ORDER BY 1""").fetchall()
        result["by_decade"][label] = {r[0]: {"n": r[1], "bias": r[2], "rmse": r[3]} for r in by_decade}  # type: ignore[index]
    anomaly = {}
    for label, expression, reference in (PAIRS[0], PAIRS[4]):
        value = expression.replace("g.precipitation_mm", "g_precipitation_mm").replace("g.", "")
        row = con.execute(f"""WITH a AS (SELECT station_id, month, {value} AS x, {reference} AS y FROM j WHERE {reference} IS NOT NULL),
                d AS (SELECT x - avg(x) OVER (PARTITION BY station_id, month) AS dx, y - avg(y) OVER (PARTITION BY station_id, month) AS dy FROM a)
                SELECT round(corr(dx, dy), 4), round(sqrt(avg((dx - dy)^2)), 3) FROM d""").fetchone()
        anomaly[label] = {"r": row[0], "rmse": row[1]}
    result["anomaly_after_station_month_climatology"] = anomaly
    maceio = con.execute("""SELECT month, count(*) FILTER (WHERE temperature_midrange IS NOT NULL) AS n_t,
            round(avg(temperature_mean), 2), round(avg(temperature_midrange), 2), round(avg((tmax + tmin) / 2), 2),
            count(*) FILTER (WHERE precipitation_mm IS NOT NULL) AS n_p, round(avg(precipitation_mm), 1), round(avg(g_precipitation_mm) FILTER (WHERE precipitation_mm IS NOT NULL), 1)
            FROM j WHERE station_id = 'A303' GROUP BY month ORDER BY month""").fetchall()
    result["maceio_A303_by_month"] = [dict(zip(("month", "n_temperature", "station_mean", "station_midrange", "brdwgd_midrange", "n_precipitation",
                                              "station_precipitation_mm", "brdwgd_precipitation_mm"), r, strict=True)) for r in maceio]
    failed = con.execute("""SELECT year, month, round(g_precipitation_mm, 1), round((tmax + tmin) / 2, 2) FROM j
        WHERE station_id = 'A303' AND year = 2021 AND precipitation_mm IS NULL ORDER BY month""").fetchall()
    result["maceio_A303_gauge_failed_2021"] = [{"month": r[1], "brdwgd_precipitation_mm": r[2], "brdwgd_midrange": r[3]} for r in failed]
    text = json.dumps(result, indent=1, default=str)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
