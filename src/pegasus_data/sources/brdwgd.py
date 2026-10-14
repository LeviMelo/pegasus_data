"""BR-DWGD's municipal zonal statistics: the climate of every municipality and day, computed and kept by others (ADR-0178).

A weather station gives the climate of its own site and nothing for the other municipalities (INMET's network: 8 of
Alagoas's 102 municipalities have a usable station-year, and a gauge can report nothing for months while its thermometer
works). The exposure of a municipality is a **gridded, quality-controlled product** read over its area.

**The product.** BR-DWGD (Xavier, Scanlon, King & Alves 2022, Int J Climatol 42:8390, doi:10.1002/joc.7731): daily, 0.1°
(about 11 km) over Brazil from 1961, interpolated from the Brazilian rain-gauge and weather-station networks (11,473
gauges and 1,252 stations in the paper): precipitation, maximum and minimum temperature, relative humidity, solar
radiation, wind at 2 m, evapotranspiration.

**Who computes the municipal values.** Saldanha and colleagues (Inria/Fiocruz; the R package `brclimr`) publish the
zonal statistics of every daily grid for every municipality (mean, maximum, minimum, standard deviation, sum and cell
count of the cells that intersect the municipality, `doi:10.1017/eds.2024.3`), as Parquet on Zenodo, one file per
variable, long form (`code_muni`, `date`, `name`, `value`, sorted by name, then date). This module reads the latest
version of the concept record (`CONCEPT`): v3.2.3, 1961-01-01 to 2024-03-20, IBGE's 2010 municipal mesh.
`brclimr` 0.2.0 itself reads an older copy (v1.0.0, DigitalOcean) that ends 2020-07-31.

**Reading it.** The files are 2 GB each, and Zenodo serves about 80 KB/s per connection with 133 requests a minute. The
statistic wanted (``mean``, the mean of the cells weighted by the area of each cell inside the municipality) is one sixth
of a file and sits in contiguous row groups, so each is fetched as one byte range, several at once, and reduced at once
to month sums and day counts; only that table (a few MB) is kept (`monthly`). Nothing is interpolated here.

**Stored** per municipality and month as the sum of the daily municipal means and the count of days held (CLAUDE.md §6:
sums and counts, a mean is formed at use). A day that holds no value is counted apart (``days_missing``) and is never a zero;
a municipality with no value on any day has no row.
"""

from __future__ import annotations

import io
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from ..transport import get_json, read_range

#: Zenodo's concept record of the BR-DWGD zonal statistics: its latest version is the current release.
CONCEPT = 7824919
RELEASE_URL = "https://zenodo.org/api/records/{record}/versions/latest"
FILE_URL = "https://zenodo.org/api/records/{record}/files/{name}/content"
#: Our measure and BR-DWGD's name for it (file ``<name>_<version>.parquet``, rows named ``<name>_<version>_mean``).
VARIABLES = {"precipitation_mm": "pr", "tmax": "Tmax", "tmin": "Tmin"}
#: Connections at once: Zenodo throttles per request (133 a minute), not per byte, and serves each stream slowly.
WORKERS = 16

#: The measures of `municipality_years` (its columns) and the variable each belongs to. A variable has one denominator,
#: ``<variable>_months``.
MEASURES = {
    "temperature_months": "temperature", "air_temperature": "temperature",
    "air_temperature_monthly_max": "temperature", "air_temperature_monthly_min": "temperature",
    "precipitation_months": "precipitation", "precipitation_mm": "precipitation",
}

__all__ = ["CONCEPT", "MEASURES", "VARIABLES", "latest_release", "monthly", "municipality_months", "municipality_years"]


def _try(function: Any, argument: Any) -> Any:
    """``function(argument)``, or the connection error it ended in (kept to be retried)."""
    try:
        return function(argument)
    except (ConnectionError, OSError) as exc:
        return exc


class _Pieces(io.RawIOBase):
    """A remote file held in pieces (its footer and the byte ranges fetched): reads inside them, fails outside."""

    def __init__(self, size: int, pieces: dict[int, bytes]) -> None:
        self.size, self.pieces, self.position = size, pieces, 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.position

    def seek(self, offset: int, whence: int = 0) -> int:
        self.position = offset if whence == 0 else self.position + offset if whence == 1 else self.size + offset
        return self.position

    def readinto(self, buffer: Any) -> int:
        want = min(len(buffer), self.size - self.position)
        for start, data in self.pieces.items():
            if start <= self.position and self.position + want <= start + len(data):
                buffer[:want] = data[self.position - start:self.position - start + want]
                self.position += want
                return want
        raise OSError(f"bytes {self.position}-{self.position + want} were not fetched")


def latest_release(cache_dir: str | Path | None = None) -> dict[str, Any]:
    """The current release of the concept record: ``record`` (id), ``version`` (BR-DWGD's, from the file names),
    ``published`` and the ``files`` {variable name: url}. It is kept in ``cache_dir`` as ``release.json``; when Zenodo
    cannot be asked (several tries), the release kept is returned with ``offline`` set, and with none kept the error is raised."""
    import re

    cache = Path(cache_dir) / "release.json" if cache_dir else None
    record: dict[str, Any] | None = None
    last: Exception | None = None
    try:
        record = get_json(RELEASE_URL.format(record=CONCEPT), retries=3, timeout=120.0)
    except (ConnectionError, ValueError) as exc:
        last = exc
    if record is None:
        if cache is not None and cache.is_file():
            return {**json.loads(cache.read_text(encoding="utf-8")), "offline": True}
        raise ConnectionError(f"Zenodo's record {CONCEPT} cannot be read and no release is kept: {last}") from last
    files = {m.group(1): FILE_URL.format(record=record["id"], name=f["key"]) for f in record["files"]
             if (m := re.fullmatch(r"(.+)_\d+\.\d+\.\d+\.parquet", f["key"]))}
    versions = {m.group(1) for f in record["files"] if (m := re.fullmatch(r".+_(\d+\.\d+\.\d+)\.parquet", f["key"]))}
    if len(versions) != 1 or not files:
        raise RuntimeError(f"Zenodo record {record['id']} holds files of versions {sorted(versions)}: {[f['key'] for f in record['files']]}")
    release = {"record": record["id"], "version": versions.pop(), "published": record["metadata"]["publication_date"], "files": files}
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(release), encoding="utf-8")
    return release


def monthly(cache_dir: str | Path, release: dict[str, Any], variable: str, log: Any = None) -> Path:
    """Month sums of one variable's daily municipal means, from the release's Parquet, in ``cache_dir`` (kept).

    Columns: ``municipality7``, ``year``, ``month``, ``days`` (days with a value), ``days_missing`` (days with none),
    ``value_sum`` (the sum of the daily means of the days held), ``first_day`` and ``last_day``.
    """
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq

    version = release["version"]
    target = Path(cache_dir) / f"{variable}_{version}_monthly.parquet"
    if target.is_file():
        return target
    url = release["files"][variable]
    wanted = f"{variable}_{version}_mean"
    tail, size = read_range(url, suffix=8)
    if tail[4:] != b"PAR1":
        raise ValueError(f"{url} is not a Parquet file")
    length = int.from_bytes(tail[:4], "little")
    footer_start = size - 8 - length
    spans = [(a, min(a + (1 << 20), size) - 1) for a in range(footer_start, size, 1 << 20)]
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        footer = b"".join(body for body, _ in pool.map(lambda s: read_range(url, s[0], s[1]), spans))
    metadata = pq.read_metadata(_Pieces(size, {footer_start: footer}))
    names = metadata.schema.names
    columns = [names.index(c) for c in ("code_muni", "date", "name", "value")]
    name_at = columns[2]
    groups = []
    for i in range(metadata.num_row_groups):
        stats = metadata.row_group(i).column(name_at).statistics
        if stats is not None and stats.min <= wanted <= stats.max:
            groups.append(i)
    if not groups:
        raise ValueError(f"{url} holds no rows named {wanted}")

    def reduce(i: int) -> Any:
        group = metadata.row_group(i)
        chunks = [group.column(c) for c in columns]
        begin = min(c.dictionary_page_offset if c.has_dictionary_page and c.dictionary_page_offset else c.data_page_offset
                    for c in chunks)
        end = max((c.dictionary_page_offset if c.has_dictionary_page and c.dictionary_page_offset else c.data_page_offset)
                  + c.total_compressed_size for c in chunks)
        body, _ = read_range(url, begin, end - 1)
        part = pq.ParquetFile(_Pieces(size, {begin: body, footer_start: footer}), metadata=metadata).read_row_group(
            i, columns=["code_muni", "date", "name", "value"])
        part = part.filter(pc.equal(part.column("name"), wanted))
        held = pc.fill_null(pc.is_finite(part.column("value")), False)
        part = part.append_column("held", held).append_column("held_value", pc.if_else(held, part.column("value"), 0.0))
        part = part.append_column("year", pc.year(part.column("date"))).append_column("month", pc.month(part.column("date")))
        if log:
            log(f"{variable} row group {i}")
        return part.group_by(["code_muni", "year", "month"]).aggregate([
            ("held", "sum"), ("held", "count"), ("held_value", "sum"), ("date", "min"), ("date", "max")])

    # a stream cut short is retried inside `_read`; a row group still failing after that gets two more passes, so one bad
    # range does not cost the half hour the others took
    done: dict[int, Any] = {}
    pending = groups
    for round_ in range(3):
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            attempts = list(zip(pending, pool.map(lambda i: _try(reduce, i), pending), strict=True))
        done.update({i: r for i, r in attempts if not isinstance(r, Exception)})
        pending = [i for i, r in attempts if isinstance(r, Exception)]
        if not pending:
            break
        time.sleep(30.0 * (round_ + 1))
    if pending:
        raise ConnectionError(f"{url}: {len(pending)} of {len(groups)} row groups could not be read, first {pending[0]}")
    partial = pa.concat_tables([done[i] for i in groups])
    whole = partial.group_by(["code_muni", "year", "month"]).aggregate([
        ("held_sum", "sum"), ("held_count", "sum"), ("held_value_sum", "sum"), ("date_min", "min"), ("date_max", "max")])
    out = pa.table({
        "municipality7": pc.cast(whole.column("code_muni"), pa.string()), "year": pc.cast(whole.column("year"), pa.int32()),
        "month": pc.cast(whole.column("month"), pa.int32()), "days": pc.cast(whole.column("held_sum_sum"), pa.int32()),
        "days_missing": pc.cast(pc.subtract(whole.column("held_count_sum"), whole.column("held_sum_sum")), pa.int32()),
        "value_sum": pc.cast(whole.column("held_value_sum_sum"), pa.float64()),
        "first_day": whole.column("date_min_min"), "last_day": whole.column("date_max_max")})
    out = out.sort_by([("municipality7", "ascending"), ("year", "ascending"), ("month", "ascending")])
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(f"_{target.name}.{os.getpid()}.tmp")
    try:
        pq.write_table(out, tmp, compression="zstd")
        os.replace(tmp, target)
    finally:
        tmp.unlink(missing_ok=True)
    return target


def municipality_months(cache_dir: str | Path, log: Any = None) -> tuple[Any, dict[str, Any]]:
    """Every municipality-month of the latest release that holds a day (a pyarrow table) and the release. A municipality
    with no value on any day (Noronha, Bombinhas: no grid cell) has no row; a sum of nothing is not a zero.

    Columns: ``municipality7``, ``year``, ``month``, ``days`` (days held, the same for the three variables, which the
    release states and this checks), ``tmax_sum`` and ``tmin_sum`` (sums of the daily mean maximum and minimum
    temperature of the municipality, °C), ``precipitation_mm_sum`` (the sum of its daily mean precipitation, mm: the
    month's total when ``days`` is the month's length) and ``product`` (``BR-DWGD v3.2.3 (Zenodo 13906834)``).
    """
    import duckdb

    release = latest_release(cache_dir)
    with ThreadPoolExecutor(max_workers=len(VARIABLES)) as pool:       # the three variables at once: the throttle is per request
        files = dict(zip(VARIABLES, pool.map(lambda bd: monthly(cache_dir, release, bd, log), VARIABLES.values()), strict=True))
    con = duckdb.connect()
    for name, path in files.items():
        con.execute(f"CREATE VIEW {name} AS SELECT * FROM read_parquet('{Path(path).as_posix()}')")
    differing = con.execute("""SELECT count(*) FROM tmax JOIN tmin USING (municipality7, year, month)
        JOIN precipitation_mm USING (municipality7, year, month)
        WHERE tmax.days <> tmin.days OR tmax.days <> precipitation_mm.days""").fetchone()[0]
    rows = [con.execute(f"SELECT count(*) FROM {n}").fetchone()[0] for n in files]
    if differing or len(set(rows)) != 1:
        raise ValueError(f"BR-DWGD {release['version']}: the variables do not hold the same days "
                         f"({differing} municipality-months differ, rows {dict(zip(files, rows, strict=True))})")
    table = con.execute(f"""SELECT municipality7, year, month, tmax.days AS days,
            tmax.value_sum AS tmax_sum, tmin.value_sum AS tmin_sum, precipitation_mm.value_sum AS precipitation_mm_sum,
            'BR-DWGD v{release['version']} (Zenodo {release['record']})' AS product
        FROM tmax JOIN tmin USING (municipality7, year, month) JOIN precipitation_mm USING (municipality7, year, month)
        WHERE tmax.days > 0 ORDER BY municipality7, year, month""").to_arrow_table()
    return table, release


def municipality_years(months: Any) -> Any:
    """One row per municipality and year from the municipality-months (a pyarrow table of `municipality_months`): the
    sums a mean is made of and what they rest on.

    A month's coverage is its days held over its length. Columns: ``temperature_months`` and ``precipitation_months``
    (the sum of the coverages, 12 in a full year); ``air_temperature`` (the sum over months of the monthly mean of the
    mid-range (maximum + minimum) / 2, °C × months), ``air_temperature_monthly_max`` and ``..._min`` (the sums of the
    monthly mean daily maximum and minimum); ``precipitation_mm`` (the sum of the precipitation of the days held) and
    ``product``. Over the months, the means are those of the days held; a month half held counts half.
    """
    import duckdb

    con = duckdb.connect()
    con.register("m", months)
    return con.execute("""
        WITH base AS (
            SELECT *, date_diff('day', make_date(year, month, 1), make_date(year, month, 1) + INTERVAL 1 MONTH) AS length
            FROM m WHERE days > 0)
        SELECT municipality7, substr(municipality7, 1, 6) AS municipality, year,
               sum(days / length) AS temperature_months, sum((tmax_sum + tmin_sum) / 2 / length) AS air_temperature,
               sum(tmax_sum / length) AS air_temperature_monthly_max, sum(tmin_sum / length) AS air_temperature_monthly_min,
               sum(days / length) AS precipitation_months, sum(precipitation_mm_sum) AS precipitation_mm,
               string_agg(DISTINCT product, ' + ' ORDER BY product) AS product
        FROM base GROUP BY municipality7, year ORDER BY municipality7, year""").to_arrow_table()
