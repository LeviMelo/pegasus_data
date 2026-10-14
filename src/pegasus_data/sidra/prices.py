"""The consumer price index as a read from the SIDRA fact store: the deflator of nominal reais.

SIH's ``VAL_TOT``, SIA's values and every other amount in reais are nominal (the reais of the month billed), so two years'
costs differ by inflation as much as by care. ``price_index`` returns IBGE's IPCA, the monthly index number (December
1993 = 100), declared as the series ``price_index_ipca`` (``curation/sidra/series.yml``; table 1737, variable 2266): the
planning, the cache, the stored provenance and the symbols are the general SIDRA interface's, not a second mechanism.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc

from . import store
from .session import Sidra

__all__ = ["price_index"]

SERIES = "price_index_ipca"
TABLE = 1737
#: The schema-metadata key under which the table says what it is (JSON): the series, its source and what was read.
METADATA = b"pegasus.price_index"


def price_index(root: str | Path | None = None, *, grain: str = "month", years: list[int] | int | None = None,
                reference: str | int | None = None, fetch: bool = True, refresh: bool = False,
                sidra: Sidra | None = None) -> pa.Table:
    """IBGE's IPCA, the consumer price index, to deflate nominal reais.

    ``grain="month"``: ``period`` (YYYYMM), ``year``, ``month`` and ``index``, the monthly index number (December 1993 =
    100). ``grain="year"``: ``year``, ``months`` (the monthly numbers there are) and ``index``, the mean of the year's
    twelve monthly numbers; a year IBGE has not finished has a null ``index``, never the mean of the months there are.

    ``reference`` (a month ``"2025-12"`` or ``202512``, or for ``grain="year"`` a year) adds ``factor`` =
    index(reference) / index: multiply a nominal amount of that month (year) by it to express it in reais of the
    reference month (year). Deflate by month when an amount has a month (SIH, SIA: the competence month); the annual mean
    is for an amount known by year only. ``years`` cuts the rows, never the reference.

    The index is read from the stored facts of table 1737; ``fetch`` fetches what is not stored (one request) and
    ``refresh`` re-reads IBGE's list of periods first, for the months published since. A month missing between the first
    and the last raises. ``table.schema.metadata[b"pegasus.price_index"]`` (JSON) names the series, the table, the
    variable, the base and the stored requests (fetch time, SHA-256 of the body) the numbers were read from.
    """
    if grain not in ("month", "year"):
        raise ValueError(f"grain is 'month' or 'year', not {grain!r}")
    session = sidra if sidra is not None else Sidra(root)
    if refresh:
        session.client.periods(TABLE, refresh=True)
        session.registry.load_periods(session.client, TABLE)
    series = session.series(SERIES, fetch=fetch, log=lambda _m: None)
    series = series.filter(pc.and_(series.column("selected"), pc.equal(series.column("status"), "value")))
    if series.num_rows == 0:
        raise LookupError(f"series {SERIES!r} has no value")
    order = pc.sort_indices(series.column("period"))
    periods = series.column("period").take(order).to_pylist()
    expected = _months(periods[0], periods[-1])
    if periods != expected:
        raise ValueError(f"the price index has no value for {sorted(set(expected) - set(periods))[:6]}: not a continuous monthly series")
    monthly = pa.table({"period": pa.array(periods, pa.string()),
                        "year": pa.array([int(p[:4]) for p in periods], pa.int32()),
                        "month": pa.array([int(p[4:]) for p in periods], pa.int32()),
                        "index": series.column("value").take(order).cast(pa.float64())})
    if grain == "month":
        table, key, parse = monthly, "period", _month_key
    else:
        grouped = monthly.group_by("year", use_threads=False).aggregate([("index", "mean"), ("index", "count")]).sort_by("year")
        months = grouped.column("index_count")
        mean = pc.if_else(pc.equal(months, 12), grouped.column("index_mean"), pa.scalar(None, pa.float64()))
        table, key, parse = pa.table({"year": grouped.column("year"), "months": pc.cast(months, pa.int32()), "index": mean}), "year", _year_key
    if reference is not None:
        wanted = parse(reference)
        keys = table.column(key).to_pylist()
        if wanted not in keys:
            raise LookupError(f"the reference {reference!r} is not in the series ({keys[0]} to {keys[-1]})")
        base = table.column("index")[keys.index(wanted)].as_py()
        if base is None:
            raise LookupError(f"the reference {reference!r} is a year IBGE has not finished: it has no annual index")
        table = table.append_column("factor", pc.divide(pa.scalar(base, pa.float64()), table.column("index")))
    if years is not None:
        chosen = [years] if isinstance(years, int) else list(years)
        table = table.filter(pc.is_in(table.column("year"), pa.array(chosen, pa.int32())))
        if table.num_rows == 0:
            raise LookupError(f"the price index has no {grain} in {chosen}: it runs {periods[0]} to {periods[-1]}")
    meta = {"series": SERIES, "producer": "IBGE, Índice Nacional de Preços ao Consumidor Amplo (IPCA)", "table": TABLE,
            "variable": 2266, "unit": "Número-índice", "base": "December 1993 = 100", "first": periods[0], "last": periods[-1],
            "grain": grain, "reference": None if reference is None else str(reference),
            "stored": [{"fetched_at": p["fetched_at"], "body_sha256": p["body_sha256"]} for p in store.provenance(session.lake, TABLE)]}
    return table.replace_schema_metadata({METADATA: json.dumps(meta, ensure_ascii=False).encode()})


def _months(first: str, last: str) -> list[str]:
    out, y, m = [], int(first[:4]), int(first[4:])
    while f"{y}{m:02d}" <= last:
        out.append(f"{y}{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _month_key(value: str | int) -> str:
    match = re.fullmatch(r"(\d{4})-?(\d{2})", str(value))
    if not match or not 1 <= int(match.group(2)) <= 12:
        raise ValueError(f"a month is YYYYMM or YYYY-MM, not {value!r}")
    return match.group(1) + match.group(2)


def _year_key(value: str | int) -> int:
    if not re.fullmatch(r"\d{4}", str(value)):
        raise ValueError(f"a year is YYYY, not {value!r}")
    return int(value)
