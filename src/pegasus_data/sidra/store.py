"""The fact store: SIDRA's answers as long rows, with provenance, in the lake.

An observation is (table, variable, period, locality, one category per classification) → value. Each
request becomes one Parquet part under ``<lake>/sidra/facts/table=<id>/``; a table's parts share a
schema, so a table is read as one dataset:

    variable int32 · period str · level str · locality str · c<classification id> int64 ... ·
    value_raw str · value float64 · status str · request str · fetched str

``value_raw`` is what SIDRA sent, never discarded. ``value`` is its number, and ``status`` says why it
is or is not one (`read_value`). The category columns hold category ids: labels, units and the Total of
each classification come from the registry at read time (labels are joined, never frozen). Every part
carries, in its Parquet footer, the URL, the body's SHA-256 and size, the fetch time, the registry's
metadata hash and the library version, so any value can be traced to the bytes it came from
(`provenance`).

Statuses follow IBGE's tabulation convention. ``-`` is an absolute zero (a count of nothing): value 0,
status ``zero``. ``..`` (not applicable), ``...`` (not available) and ``X`` (withheld to protect a
respondent) are no value, never zero. A symbol not in this list is ``unknown_symbol`` with its raw text:
visible, not guessed.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

from ..persist.kept import write_parquet_atomic
from .client import Response

__all__ = ["facts_dir", "load_facts", "parse_values", "part_path", "provenance", "read_value", "write_part", "SYMBOLS"]

#: IBGE's symbols for a cell that is not a number, and what each means.
SYMBOLS = {"-": ("zero", 0.0), "..": ("not_applicable", None), "...": ("not_available", None),
           "X": ("suppressed", None), "": ("empty", None)}
_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")


def read_value(raw: str | None) -> tuple[float | None, str]:
    """One cell as (value, status). A figure is ``value``; an IBGE symbol its reason; anything else
    ``unknown_symbol``, with the raw text kept by the caller."""
    if raw is None:
        return None, "empty"
    text = raw.strip()
    if _NUMBER.match(text):
        return float(text), "value"
    status = SYMBOLS.get(text)
    if status is not None:
        return status[1], status[0]
    return None, "unknown_symbol"


def facts_dir(lake: Path, table: int | None = None) -> Path:
    base = Path(lake) / "sidra" / "facts"
    return base if table is None else base / f"table={table}"


def fact_parts(lake: Path, table: int | None = None) -> list[Path]:
    """The stored fact parts (one per request) of ``table``, or of every table: the store's layout, known here only."""
    base = facts_dir(lake, table)
    pattern = "req-*.parquet" if table is not None else "table=*/req-*.parquet"
    return sorted(base.glob(pattern)) if base.exists() else []


def request_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def part_path(lake: Path, table: int, url: str) -> Path:
    return facts_dir(lake, table) / f"req-{request_id(url)}.parquet"


def parse_values(payload: list[dict[str, Any]], class_ids: list[int]) -> tuple[pa.Table, Counter]:
    """A values response as the fact table of its table (``class_ids``: the table's classifications).

    The response nests variable → result (one category per classification) → locality → period → cell.
    """
    variable: list[int] = []
    period: list[str] = []
    level: list[str] = []
    locality: list[str] = []
    cats: dict[int, list[int]] = {c: [] for c in class_ids}
    raw: list[str | None] = []
    value: list[float | None] = []
    status: list[str] = []
    symbols: Counter = Counter()
    for var in payload:
        vid = int(var["id"])
        for result in var["resultados"]:
            chosen = {int(c["id"]): int(next(iter(c["categoria"]))) for c in result["classificacoes"]}
            if set(chosen) != set(class_ids):
                raise ValueError(f"a result names classifications {sorted(chosen)}, the registry has {class_ids}")
            for series in result["series"]:
                loc = series["localidade"]
                for per, cell in series["serie"].items():
                    number, state = read_value(cell)
                    if state not in ("value", "zero"):
                        symbols[f"{cell!r}:{state}"] += 1
                    variable.append(vid)
                    period.append(per)
                    level.append(loc["nivel"]["id"])
                    locality.append(str(loc["id"]))
                    for c in class_ids:
                        cats[c].append(chosen[c])
                    raw.append(cell)
                    value.append(number)
                    status.append(state)
    columns: dict[str, pa.Array] = {
        "variable": pa.array(variable, pa.int32()), "period": pa.array(period, pa.string()),
        "level": pa.array(level, pa.string()), "locality": pa.array(locality, pa.string())}
    for c in class_ids:
        columns[f"c{c}"] = pa.array(cats[c], pa.int64())
    columns["value_raw"] = pa.array(raw, pa.string())
    columns["value"] = pa.array(value, pa.float64())
    columns["status"] = pa.array(status, pa.string())
    return pa.table(columns), symbols


def write_part(lake: Path, table: int, response: Response, class_ids: list[int], *, metadata_sha: str,
               version: str) -> tuple[Path, int, Counter]:
    """Write one request's facts (atomically); return the part, its rows and its non-numeric symbols."""
    facts, symbols = parse_values(response.payload, class_ids)
    rid = request_id(response.url)
    facts = facts.append_column("request", pa.array([rid] * facts.num_rows, pa.string()))
    facts = facts.append_column("fetched", pa.array([response.fetched_at] * facts.num_rows, pa.string()))
    meta = {"url": response.url, "request": rid, "body_sha256": response.sha256, "body_bytes": str(response.nbytes),
            "fetched_at": response.fetched_at, "registry_metadata_sha256": metadata_sha, "pegasus_data": version,
            "symbols": json.dumps(dict(symbols), ensure_ascii=False)}
    facts = facts.replace_schema_metadata({k.encode(): v.encode() for k, v in meta.items()})
    path = part_path(lake, table, response.url)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_parquet_atomic(facts, path, compression="zstd")
    return path, facts.num_rows, symbols


def load_facts(lake: Path, table: int, *, variables: list[int] | None = None, periods: list[str] | None = None,
               localities: list[str] | None = None, level: str | None = None, light: bool = False) -> pa.Table:
    """A table's stored facts, optionally filtered, one row per observation. ``light`` leaves out ``value_raw``,
    ``request`` and ``fetched`` (long strings, about half the memory of a big table) for analyses that need only values.

    Selections of the same table overlap (a field wants the Total cells, a census series the cells below
    them), so the same observation can sit in two parts; the most recently fetched one is kept. Raises if
    nothing is stored (never an empty table that could pass for an empty result)."""
    import duckdb

    directory = facts_dir(lake, table)
    files = sorted(directory.glob("req-*.parquet")) if directory.exists() else []
    if not files:
        raise FileNotFoundError(f"table {table} has no stored facts; run `pegasus-data sidra fetch {table} …`")
    names = pq.read_schema(files[0]).names
    identity = ["variable", "period", "level", "locality", *[n for n in names if re.fullmatch(r"c\d+", n)]]
    where, args = [], []
    for column, values in (("variable", variables), ("period", periods), ("locality", localities)):
        if values:
            where.append(f"{column} IN ({','.join('?' * len(values))})")
            args += list(values)
    if level:
        where.append("level = ?")
        args.append(level)
    con = duckdb.connect()
    from ..config import load_settings

    spill = load_settings().duckdb_spill()       # this process's own: a shared one broke another process's reads
    con.execute(f"SET memory_limit='2GB'; SET threads=2; SET preserve_insertion_order=false; SET temp_directory='{spill.as_posix()}'")
    drop = "_rn, value_raw, request, fetched" if light else "_rn"
    listing = ",".join("?" * len(files))
    # The window over a big table is held in memory, so a big table is dealt with in buckets of localities (an
    # observation always falls in one bucket), about 1.5 million stored rows each.
    # sized by the rows the filter keeps, not by everything stored: a one-locality read of a national table was cut into
    # buckets that each rescanned every part
    stored = con.execute(f"SELECT count(*) FROM read_parquet([{listing}], union_by_name = true, hive_partitioning = false)"  # type: ignore[index]  # duckdb stub: fetchone is Optional; an aggregate returns one row
                         f"{' WHERE ' + ' AND '.join(where) if where else ''}",
                         [f.as_posix() for f in files] + args).fetchone()[0]
    buckets = max(1, math.ceil(stored / 1_500_000))
    parts = []
    for k in range(buckets):
        cond = [*where, f"hash(locality) % {buckets} = {k}"] if buckets > 1 else where
        sql = (f"SELECT * EXCLUDE ({drop}) FROM (SELECT *, row_number() OVER (PARTITION BY {', '.join(identity)} "
               f"ORDER BY fetched DESC NULLS LAST, request DESC) AS _rn FROM read_parquet([{listing}], "
               f"union_by_name = true, hive_partitioning = false){' WHERE ' + ' AND '.join(cond) if cond else ''}) WHERE _rn = 1")
        parts.append(con.execute(sql, [f.as_posix() for f in files] + args).fetch_arrow_table())
    con.close()
    out = pa.concat_tables(parts) if len(parts) > 1 else parts[0]
    if out.num_rows == 0:
        raise LookupError(f"table {table} has facts, but none match the filter")
    return out


def provenance(lake: Path, table: int) -> list[dict[str, Any]]:
    """Each stored request of a table, from the footers alone."""
    out = []
    for path in sorted(facts_dir(lake, table).glob("req-*.parquet")):
        meta = pq.read_schema(path).metadata or {}
        row = {k.decode(): v.decode() for k, v in meta.items() if k != b"ARROW:schema"}
        row["rows"] = pq.read_metadata(path).num_rows
        row["part"] = path.name
        out.append(row)
    return out
