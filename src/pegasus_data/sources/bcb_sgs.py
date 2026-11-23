"""Banco Central do Brasil's SGS time-series API: monthly series stored with their provenance.

The SGS serves FGV's general price indices, which IBGE's SIDRA does not: series 189 is the IGP-M and 190 the IGP-DI, each as
the month's percentage change. One request returns a monthly series whole (the 10-year limit is for daily series). The
request always carries explicit ``dataInicial``/``dataFinal``: the bare URL of the API answered ``304 Not Modified`` with an
empty body to a client that sent no validator (measured 2026-11-23, curl), while the dated URL answers 200.

Layout (the SIDRA fact store's pattern, ``sidra/store.py``): one Parquet part per series under
``<lake>/bcb_sgs/series=<code>/``, ``period`` (YYYYMM) · ``value_raw`` (as sent) · ``value`` (float, percent), its footer holding
the URL, the body's SHA-256 and size and the fetch time. A stored series is read, not fetched; ``refresh`` fetches it again
(the same part is replaced) for the months published since.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from ..catalog.store import utcnow
from ..persist.kept import write_parquet_atomic
from ..transport import request

__all__ = ["load_series", "provenance", "url"]

BASE = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"


def url(code: int) -> str:
    return BASE.format(code=code) + "?formato=json&dataInicial=01/01/1980&dataFinal=31/12/2099"


def _part(lake: Path, code: int) -> Path:
    return Path(lake) / "bcb_sgs" / f"series={code}" / "series.parquet"


def provenance(lake: Path, code: int) -> list[dict[str, Any]]:
    """The stored request of a series, from the footer alone (empty when none is stored)."""
    path = _part(lake, code)
    if not path.is_file():
        return []
    meta = pq.read_schema(path).metadata or {}
    return [{k.decode(): v.decode() for k, v in meta.items() if k != b"ARROW:schema"}]


def load_series(lake: Path, code: int, *, fetch: bool = True, refresh: bool = False) -> pa.Table:
    """The monthly series ``code``: ``period`` (YYYYMM), ``value_raw``, ``value``. Read from the store; fetched when absent
    (``fetch``) or when ``refresh``; a month the source left without a value stays a null ``value``."""
    path = _part(lake, code)
    if not path.is_file() and not fetch:
        raise LookupError(f"BCB SGS series {code} is not stored and fetch=False")
    if refresh or not path.is_file():
        _store(lake, code)
    return pq.read_table(path)


def _store(lake: Path, code: int) -> None:
    address = url(code)
    body = request(address, headers={"Accept": "application/json"}).content
    rows = json.loads(body)
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"BCB SGS series {code} answered no rows: {body[:120]!r}")
    period, raw, value = [], [], []
    for row in rows:
        _day, month, year = str(row["data"]).split("/")
        period.append(f"{year}{month}")
        raw.append(row["valor"])
        try:
            value.append(float(row["valor"]))
        except (TypeError, ValueError):
            value.append(None)
    table = pa.table({"period": pa.array(period, pa.string()), "value_raw": pa.array(raw, pa.string()),
                      "value": pa.array(value, pa.float64())})
    meta = {"url": address, "series": str(code), "body_sha256": hashlib.sha256(body).hexdigest(), "body_bytes": str(len(body)),
            "fetched_at": utcnow()}
    path = _part(lake, code)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_parquet_atomic(table.replace_schema_metadata({k.encode(): v.encode() for k, v in meta.items()}), path, compression="zstd")
