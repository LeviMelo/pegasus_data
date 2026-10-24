"""CPTEC/INPE's daily gridded weather, MERGE and SAMeT, as municipal means by area and by population, kept by vintage
(ADR-0203).

**The products** (``https://ftp.cptec.inpe.br/modelos/tempo/``, read 2026-10-24):

* **MERGE** (Rozante et al. 2010, doi:10.1590/S0102-77862010000100009; 2020; Rozante 2024, doi:10.3390/rs16244722): daily
  precipitation from rain gauges merged with NASA's GPM IMERG (V07B since the 2025 rebuild, which also took in the
  gauges of the ONS), 0.1° over South America (−120.05 to −20.05° E, −60.05 to 32.25° N), GRIB2, one file a day from
  1998-01-01, with the number of gauges per grid point (``NEST``). A day is the 24 hours ending at 12 UTC of its date
  (the ``.ctl``'s ``tdef 12Z``, the gauge day of the Brazilian networks).
* **SAMeT** (Rozante, Ramirez & Fernandes 2022, Int J Climatol, doi:10.1002/joc.7356): daily maximum, minimum and mean
  air temperature from INMET's stations merged with ERA5 and corrected for altitude with lapse rates estimated by region
  and season, 0.05° (about 5 km) over South America (−83 to −33° E, −56 to 13° N), NetCDF, one file per variable a day
  from 2000-01-01, with the stations per grid point (``nobs``). Its Read-me: while ERA5 is not yet out (about 5 days),
  a day is made from 24-hour observations and model forecasts, and regenerated when ERA5 arrives.

Both are one consistent product from 2000 to the day before yesterday: nothing here is spliced onto BR-DWGD, which
remains the 1961-2024 source of the yearly fields (ADR-0178) and the reference this one is validated against.

**Municipal means.** Each grid cell weighs in a municipality by the people of IBGE's Grade Estatística 2022 inside it
(``population``) and by its area inside the municipality (``area``), both from the 200 m / 1 km cells of the grade
(`ibge_grade.grid_weights`): the population-weighted mean is the weather where the people live, the area-weighted one
the weather of the territory (what BR-DWGD's zonal means are). A grid cell with no value that day (sea, outside the
domain) is left out of both sums and ``coverage`` says what share of the weight had a value. ``stations`` is the
product's count of stations or gauges in the grid cells the municipality touches: where it is 0 the value is the
satellite's or the reanalysis' alone.

**Vintages.** Every file read is kept in a manifest with the server's ``Last-Modified`` (``published``) and the time it
was read; a file that changes on the server (SAMeT's provisional days, a rebuilt MERGE year) is read again and its rows
are added beside the old ones, never over them. `daily` returns the latest vintage, or with ``as_of`` the latest
published on or before that instant, so a backtest sees what was known then. A day first read after its regeneration
has only its final vintage: its provisional value was never seen here and is not invented.

**Stored** under ``<lake>/climate_daily/<variable>/year=<y>/month=<m>/<run>.parquet``, one row per municipality, day
and vintage (``value_area``, ``value_population``, ``coverage_area``, ``coverage_population``, ``stations``,
``published``, ``file``), and the manifest beside it. A day's value is a daily mean or total; a week or month is formed at
use as a sum and a count of days (`weekly`), never a stored mean.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

BASE = "https://ftp.cptec.inpe.br/modelos/tempo/"


@dataclass(frozen=True)
class Product:
    """One daily variable: where its files are, how one is read, what its value is."""

    variable: str
    product: str
    folder: str               # under BASE, before {year}/{month}/
    name: str                 # the file name, with {ymd}
    first: dt.date
    unit: str
    kind: str                 # "grib" (MERGE) or "netcdf" (SAMeT)
    field: str                # the NetCDF variable, or the GRIB message's position
    reference: str


PRODUCTS: dict[str, Product] = {
    "precipitation": Product("precipitation", "MERGE", "MERGE/GPM/DAILY/", "MERGE_CPTEC_{ymd}.grib2", dt.date(1998, 1, 1),
                             "mm per day (the 24 h ending 12 UTC)", "grib", "0",
                             "Rozante et al. 2010, 2020; Rozante 2024 (doi:10.3390/rs16244722)"),
    "tmax": Product("tmax", "SAMeT", "SAMeT/DAILY/TMAX/", "SAMeT_CPTEC_TMAX_{ymd}.nc", dt.date(2000, 1, 1),
                    "°C, the day's maximum air temperature", "netcdf", "tmax", "Rozante, Ramirez & Fernandes 2022 (doi:10.1002/joc.7356)"),
    "tmin": Product("tmin", "SAMeT", "SAMeT/DAILY/TMIN/", "SAMeT_CPTEC_TMIN_{ymd}.nc", dt.date(2000, 1, 1),
                    "°C, the day's minimum air temperature", "netcdf", "tmin", "Rozante, Ramirez & Fernandes 2022 (doi:10.1002/joc.7356)"),
    "tmed": Product("tmed", "SAMeT", "SAMeT/DAILY/TMED/", "SAMeT_CPTEC_TMED_{ymd}.nc", dt.date(2000, 1, 1),
                    "°C, the day's mean air temperature", "netcdf", "tmed", "Rozante, Ramirez & Fernandes 2022 (doi:10.1002/joc.7356)"),
}
#: The first day a study is served by default: both products exist from here, so every variable has one source throughout
DEFAULT_START = dt.date(2000, 1, 1)
#: Seconds between two requests to CPTEC's file server, and the files read at once (a plain file server, not an API)
INTERVAL = 0.3
WORKERS = 4
MISSING = -9.99e8

__all__ = ["PRODUCTS", "daily", "grid", "listing", "read_file", "update", "weekly"]


def _store(settings: Any) -> Path:
    return Path(settings.lake_dir) / "climate_daily"


def listing(product: Product, year: int, month: int) -> list[dict[str, Any]]:
    """The product's files of one month on the server: ``date``, ``file``, ``url``, ``listed`` (the index's modification
    time, to the minute) and ``size`` (as the index rounds it). An absent month is an empty list."""
    from ..transport import SourceAbsent, get_text

    folder = f"{BASE}{product.folder}{year}/{month:02d}/"
    try:
        page = get_text(folder, interval=INTERVAL)
    except SourceAbsent:
        return []
    pattern = re.escape(product.name).replace(r"\{ymd\}", r"(\d{8})")
    out = []
    for m in re.finditer(rf'href="({pattern})">[^<]*</a></td><td[^>]*>(\d{{4}}-\d\d-\d\d \d\d:\d\d)\s*</td><td[^>]*>\s*([^<]*?)\s*<', page):
        name, ymd, listed, size = m.group(1), m.group(2), m.group(3), m.group(4)
        out.append({"date": dt.date(int(ymd[:4]), int(ymd[4:6]), int(ymd[6:])), "file": name, "url": folder + name,
                    "listed": listed, "size": size})
    return out


def _grib_messages(body: bytes) -> list[bytes]:
    """A GRIB2 file's messages (``GRIB``, then the total length as 8 bytes at offset 8)."""
    out, at = [], 0
    while (start := body.find(b"GRIB", at)) >= 0:
        length = int.from_bytes(body[start + 8:start + 16], "big")
        out.append(body[start:start + length])
        at = start + length
    return out


def read_file(product: Product, body: bytes) -> tuple[Any, Any, Any, Any]:
    """``(value, stations, lon, lat)`` of one file: the field (lat × lon, NaN where there is none), the stations per grid
    point (0 where none) and the cell-centre coordinates (both ascending)."""
    import numpy as np

    if product.kind == "grib":
        import eccodes

        messages = _grib_messages(body)
        if len(messages) != 2:
            raise ValueError(f"{product.product}: {len(messages)} GRIB messages, expected PREC and NEST")
        fields = []
        for raw in messages:
            handle = eccodes.codes_new_from_message(raw)
            try:
                ni, nj = eccodes.codes_get(handle, "Ni"), eccodes.codes_get(handle, "Nj")
                lon0 = eccodes.codes_get(handle, "longitudeOfFirstGridPointInDegrees")
                lat0 = eccodes.codes_get(handle, "latitudeOfFirstGridPointInDegrees")
                step = eccodes.codes_get(handle, "iDirectionIncrementInDegrees")
                if eccodes.codes_get(handle, "jScansPositively") != 1:
                    raise ValueError(f"{product.product}: rows scan north to south")
                missing = eccodes.codes_get(handle, "missingValue")
                values = eccodes.codes_get_values(handle).reshape(nj, ni)
            finally:
                eccodes.codes_release(handle)
            fields.append(np.where(values == missing, np.nan, values))
        lon = (lon0 - 360 if lon0 > 180 else lon0) + step * np.arange(ni)
        lat = lat0 + step * np.arange(nj)
        return fields[0], np.nan_to_num(fields[1], nan=0.0), np.round(lon, 4), np.round(lat, 4)
    import netCDF4

    with netCDF4.Dataset("in-memory.nc", memory=body) as data:
        data.set_auto_mask(True)
        value = np.ma.filled(data.variables[product.field][0].astype("float64"), np.nan)
        stations = np.ma.filled(data.variables["nobs"][0].astype("float64"), 0.0)
        lon, lat = np.asarray(data.variables["lon"][:], dtype=float), np.asarray(data.variables["lat"][:], dtype=float)
    value[value <= MISSING / 10] = np.nan
    if lat[0] > lat[-1]:
        value, stations, lat = value[::-1], stations[::-1], lat[::-1]
    return value, stations, np.round(lon, 4), np.round(lat, 4)


class _Weights:
    """A grid's municipal weights as sparse matrices (municipality × grid cell): population, area, and which cells a
    municipality touches."""

    def __init__(self, table: Any, shape: tuple[int, int]) -> None:
        import numpy as np
        from scipy import sparse

        codes = table.column("municipality7").to_numpy(zero_copy_only=False)
        self.municipalities, row = np.unique(codes, return_inverse=True)
        column = table.column("i").to_numpy() * shape[1] + table.column("j").to_numpy()
        size = (len(self.municipalities), shape[0] * shape[1])
        self.population = sparse.csr_matrix((table.column("population").to_numpy(), (row, column)), shape=size)
        self.area = sparse.csr_matrix((table.column("area_km2").to_numpy(), (row, column)), shape=size)
        self.touched = sparse.csr_matrix((np.ones(len(row)), (row, column)), shape=size)
        self.population_total = np.asarray(self.population.sum(axis=1)).ravel()
        self.area_total = np.asarray(self.area.sum(axis=1)).ravel()

    def reduce(self, value: Any, stations: Any) -> dict[str, Any]:
        import numpy as np

        flat = value.ravel()
        held = np.isfinite(flat)
        filled = np.where(held, flat, 0.0)
        out: dict[str, Any] = {}
        for name, matrix, total in (("population", self.population, self.population_total), ("area", self.area, self.area_total)):
            weight = matrix @ held.astype(float)
            with np.errstate(invalid="ignore", divide="ignore"):
                out[f"value_{name}"] = np.where(weight > 0, (matrix @ filled) / weight, np.nan)
                out[f"coverage_{name}"] = np.where(total > 0, weight / total, np.nan)
        out["stations"] = np.rint(self.touched @ stations.ravel()).astype(np.int32)
        return out


def grid(settings: Any, lon: Any, lat: Any) -> _Weights:
    """The municipal weights of a grid (cell centres ``lon``, ``lat``), from the Grade Estatística, built once per grid and
    kept beside the store as ``weights_<grid>.parquet``."""
    import pyarrow.parquet as pq

    from ..fields import write_parquet_atomic
    from . import ibge_grade

    key = f"{lon[0]:.3f}_{lat[0]:.3f}_{lon[1] - lon[0]:.3f}_{len(lon)}x{len(lat)}"
    path = _store(settings) / f"weights_{key}.parquet"
    if path.is_file():
        table = pq.read_table(path)
    else:
        table = ibge_grade.grid_weights(lon, lat, root=settings.root)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_parquet_atomic(table, path, compression="zstd")
    return _Weights(table, (len(lat), len(lon)))


def _manifest(settings: Any, variable: str) -> Any:
    """The files read so far for ``variable`` (a pyarrow table; empty when none)."""
    import duckdb

    files = sorted((_store(settings) / variable).glob("manifest/*.parquet"))
    if not files:
        return None
    paths = ", ".join(f"'{p.as_posix()}'" for p in files)
    return duckdb.connect().execute(f"SELECT * FROM read_parquet([{paths}])").to_arrow_table()


def _months(start: dt.date, end: dt.date) -> list[tuple[int, int]]:
    out, y, m = [], start.year, start.month
    while (y, m) <= (end.year, end.month):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def update(settings: Any, variables: Iterable[str] | None = None, *, start: dt.date | None = None,
           end: dt.date | None = None, log: Callable[[str], None] | None = None) -> dict[str, Any]:
    """Read every file of ``variables`` (default all) from ``start`` (default 2000-01-01) to ``end`` (default today) that
    is not held, or that the server lists with another time than the vintage held, and add its municipal means.

    Returns per variable: files listed, read (new and re-read), and the days the server does not have in the range."""


    start = start or DEFAULT_START
    end = end or dt.date.today()
    run = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return {variable: _update(settings, PRODUCTS[variable], start, end, run, log) for variable in variables or PRODUCTS}


def _update(settings: Any, product: Product, start: dt.date, end: dt.date, run: str,
            log: Callable[[str], None] | None) -> dict[str, Any]:
    """`update` for one variable."""
    import numpy as np
    import pyarrow as pa

    from ..fields import write_parquet_atomic
    from ..transport import request

    variable = product.variable
    first = max(start, product.first)
    manifest = _manifest(settings, variable)
    held = {}
    if manifest is not None:
        for row in manifest.select(["file", "listed"]).to_pylist():
            held.setdefault(row["file"], set()).add(row["listed"])
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        months = list(pool.map(lambda ym: listing(product, *ym), _months(first, end)))
    listed = [f for month in months for f in month if first <= f["date"] <= end]
    wanted = [f for f in listed if f["listed"] not in held.get(f["file"], set())]
    days = {f["date"] for f in listed}
    missing_days = [first + dt.timedelta(n) for n in range((end - first).days + 1) if first + dt.timedelta(n) not in days]
    state: dict[str, Any] = {"weights": None}

    def fetch(entry: dict[str, Any]) -> tuple[dict[str, Any], Any]:
        response = request(entry["url"], interval=INTERVAL, timeout=300)
        body = response.content
        published = response.headers.get("Last-Modified")
        entry = {**entry, "published": parsedate_to_datetime(published).astimezone(dt.UTC) if published else None,
                 "read_at": dt.datetime.now(dt.UTC), "bytes": len(body),
                 "sha256": hashlib.sha256(body).hexdigest()}
        return entry, read_file(product, body)

    by_month: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for entry in wanted:
        by_month.setdefault((entry["date"].year, entry["date"].month), []).append(entry)
    read = 0
    for (year, month), entries in sorted(by_month.items()):
        columns: dict[str, list[Any]] = {}
        entries_read = []
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            for entry, (value, stations, lon, lat) in pool.map(fetch, sorted(entries, key=lambda e: e["date"])):
                if state["weights"] is None:
                    state["weights"] = grid(settings, lon, lat)
                weights = state["weights"]
                reduced = weights.reduce(value, stations)
                n = len(weights.municipalities)
                columns.setdefault("municipality7", []).append(weights.municipalities)
                columns.setdefault("date", []).append(np.full(n, np.datetime64(entry["date"], "D")))
                for key, values in reduced.items():
                    columns.setdefault(key, []).append(values)
                columns.setdefault("published", []).append(np.full(n, np.datetime64(entry["published"].replace(tzinfo=None), "s")
                                                                    if entry["published"] else np.datetime64("NaT", "s")))
                columns.setdefault("file", []).append(np.full(n, entry["file"], dtype=object))
                entries_read.append(entry)
        table = pa.table({
            "municipality7": pa.array(np.concatenate(columns["municipality7"]).astype(str)),
            "date": pa.array(np.concatenate(columns["date"]), pa.date32()),
            **{k: pa.array(np.concatenate(columns[k]).astype("float32")) for k in
               ("value_population", "value_area", "coverage_population", "coverage_area")},
            "stations": pa.array(np.concatenate(columns["stations"]), pa.int32()),
            "published": pa.array(np.concatenate(columns["published"]), pa.timestamp("s", tz="UTC")),
            "file": pa.array(np.concatenate(columns["file"]).astype(str))})
        folder = _store(settings) / variable / f"year={year}" / f"month={month}"
        folder.mkdir(parents=True, exist_ok=True)
        write_parquet_atomic(table, folder / f"{run}.parquet", compression="zstd", use_byte_stream_split=[
            "value_population", "value_area", "coverage_population", "coverage_area"])
        manifest_dir = _store(settings) / variable / "manifest"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        write_parquet_atomic(pa.Table.from_pylist([
            {"date": e["date"], "file": e["file"], "listed": e["listed"], "published": e["published"],
             "read_at": e["read_at"], "bytes": e["bytes"], "sha256": e["sha256"], "run": run} for e in entries_read]),
            manifest_dir / f"{year}{month:02d}_{run}.parquet", compression="zstd")
        read += len(entries_read)
        if log:
            log(f"{variable} {year}-{month:02d}: {len(entries_read)} files")
    return {"product": product.product, "listed": len(listed), "read": read,
            "reread": sum(1 for f in wanted if f["file"] in held), "days_not_on_server": len(missing_days),
            "first_days_not_on_server": [d.isoformat() for d in missing_days[:10]]}


def daily(variables: str | Iterable[str] = ("precipitation", "tmax", "tmin", "tmed"), *, start: Any = None, end: Any = None,
          municipality: Any = None, uf: Any = None, weight: str = "population", as_of: Any = None,
          settings: Any = None) -> Any:
    """Daily municipal weather (a pyarrow table): ``municipality7``, ``date``, and per variable its value (``weight``
    ``population`` or ``area``), ``<variable>_coverage``, ``<variable>_stations`` and ``<variable>_published``.

    One row per municipality and day, from the latest vintage, or with ``as_of`` (a date or datetime, UTC) the latest one
    published on or before it; a day with no vintage by then has no value. ``municipality`` takes 6 or 7 digits, ``uf``
    2-digit codes. Raises when nothing is held for a variable (`update`, ``pegasus-data climate update``)."""
    import duckdb

    from ..config import load_settings

    if weight not in ("population", "area"):
        raise ValueError("weight is 'population' or 'area'")
    settings = settings or load_settings()
    names = [variables] if isinstance(variables, str) else list(variables)
    unknown = [v for v in names if v not in PRODUCTS]
    if unknown:
        raise KeyError(f"unknown variables {unknown}; known: {sorted(PRODUCTS)}")
    where = []
    if start is not None:
        where.append(f"date >= DATE '{dt.date.fromisoformat(str(start)[:10])}'")
    if end is not None:
        where.append(f"date <= DATE '{dt.date.fromisoformat(str(end)[:10])}'")
    if municipality is not None:
        values = [str(v).strip() for v in ([municipality] if isinstance(municipality, (str, int)) else municipality)]
        if any(len(v) not in (6, 7) for v in values):
            raise ValueError(f"municipality codes have 6 or 7 digits: {values}")
        where.append("substr(municipality7, 1, 6) IN (" + ",".join(repr(v[:6]) for v in values) + ")")
    if uf is not None:
        states = [str(s).strip() for s in ([uf] if isinstance(uf, (str, int)) else uf)]
        where.append("substr(municipality7, 1, 2) IN (" + ",".join(repr(s) for s in states) + ")")
    if as_of is not None:
        if isinstance(as_of, dt.datetime):
            moment = as_of
        elif isinstance(as_of, dt.date) or len(str(as_of)) == 10:       # a day: what was published by its end
            moment = dt.datetime.combine(dt.date.fromisoformat(str(as_of)), dt.time(23, 59, 59))
        else:
            moment = dt.datetime.fromisoformat(str(as_of))
        where.append(f"published <= TIMESTAMPTZ '{moment.replace(tzinfo=moment.tzinfo or dt.UTC).isoformat()}'")
    clause = ("WHERE " + " AND ".join(where)) if where else ""
    con = duckdb.connect()
    joined = None
    for name in names:
        folder = _store(settings) / name
        if not any(folder.glob("year=*/month=*/*.parquet")):
            raise FileNotFoundError(f"no {name} is held in {folder}; run `pegasus-data climate update --variable {name}`")
        con.execute(f"""CREATE OR REPLACE VIEW {name} AS
            SELECT municipality7, date, value_{weight} AS {name}, coverage_{weight} AS {name}_coverage,
                   stations AS {name}_stations, published AS {name}_published
            FROM read_parquet('{folder.as_posix()}/year=*/month=*/*.parquet', hive_partitioning = false) {clause}
            QUALIFY row_number() OVER (PARTITION BY municipality7, date ORDER BY published DESC, file DESC) = 1""")
        joined = name if joined is None else f"{joined} FULL JOIN {name} USING (municipality7, date)"
    return con.execute(f"SELECT * FROM {joined} ORDER BY municipality7, date").to_arrow_table()


def weekly(variables: str | Iterable[str] = ("precipitation", "tmax", "tmin", "tmed"), **options: Any) -> Any:
    """`daily` summed by epidemiological week (the Ministry's rule, `normalize.time.epi_week_array`): ``epi_year``,
    ``epi_week``, ``days`` (days with a value), and per variable ``<variable>_sum`` (the sum of the daily values: the week's
    rain; a mean temperature is ``_sum / _days``) and ``<variable>_days``. Sums and counts, never a stored mean."""
    import duckdb
    import pyarrow as pa

    from ..normalize.time import epi_week_array

    names = [variables] if isinstance(variables, str) else list(variables)
    table = daily(names, **options)
    epi_year, epi_week = epi_week_array(table.column("date"))
    table = table.append_column("epi_year", epi_year).append_column("epi_week", epi_week)
    con = duckdb.connect()
    con.register("d", table)
    sums = ", ".join(f"sum({n}) AS {n}_sum, count({n}) AS {n}_days" for n in names)
    out = con.execute(f"""SELECT municipality7, epi_year, epi_week, min(date) AS first_day, max(date) AS last_day, {sums}
                          FROM d GROUP BY ALL ORDER BY municipality7, epi_year, epi_week""").to_arrow_table()
    return out if isinstance(out, pa.Table) else pa.table(out)


#: The public names (`pegasus_data.climate_daily`, `climate_weekly`)
climate_daily, climate_weekly = daily, weekly
