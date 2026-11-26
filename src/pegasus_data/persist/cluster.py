"""The row order of a closed partition, found by measurement (ADR-0239).

A dataset that republishes a whole register every month (CNES) files each record once a month: a year's partition
holds twelve copies of most rows, in twelve separate places. Sorted so that a record's copies sit together (its key,
then the publication), every column becomes runs that the dictionary and zstd collapse: CNES-PF AL 2023, 913,623
rows, 24.93 MB as written, 4.80 MB sorted by establishment, record key and publication (scratch measurement
2026-11-26, docs/plans/storage.md). The rows stay the rows: a reader sees the same records, `_row` keeps each one's
place in its source file, and nothing outside the file changes.

Nothing is declared. On a probe file of the family: the share of exact repeats across publications decides whether an
order is worth seeking, columns constant within a publication left out (event datasets have none and keep their file
order); the record key is found by greedy
distinct counting within each publication; candidate orders are the key with each of its columns first, then the
publication, and the smallest probe written in the closed encoding wins, if it beats the file order by `MIN_GAIN`.
The choice is kept per family in ``<family>/_order.json`` and stamped in each file it orders (``pegasus.order``).
"""

from __future__ import annotations

import io
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq

ORDER_FILE = "_order.json"
ORDER_META = b"pegasus.order"
PUBLICATION = "_source_path"
#: an order is kept only where it shrinks the probe by this much against the file order
MIN_GAIN = 0.10
#: below this share of exact repeats across publications no order is sought (event records repeat nothing)
MIN_REPEAT = 0.20
MAX_KEY = 6
PROBE_ROWS = 2_000_000


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _closed_size(table: pa.Table) -> int:
    from .kept import CLOSED_ROW_GROUP_ROWS, CLOSED_ZSTD_LEVEL
    from .lake import probe_dictionary

    sink = io.BytesIO()
    pq.write_table(table, sink, compression="zstd", compression_level=CLOSED_ZSTD_LEVEL, row_group_size=CLOSED_ROW_GROUP_ROWS)
    dictionary = probe_dictionary(pq.ParquetFile(pa.BufferReader(sink.getvalue())), table.column_names)
    sink = io.BytesIO()
    pq.write_table(table, sink, compression="zstd", compression_level=CLOSED_ZSTD_LEVEL, row_group_size=CLOSED_ROW_GROUP_ROWS,
                   use_dictionary=[c for c in dictionary if c != "_row"],
                   column_encoding={"_row": "DELTA_BINARY_PACKED"} if "_row" in table.column_names else None)
    return sink.tell()


def choose_order(path: Path, con: Any) -> dict[str, Any]:
    """The order for the files of ``path``'s family, measured on ``path``: ``{"order": [...] | None, "why", ...}``."""
    rel = f"read_parquet('{Path(path).as_posix()}', hive_partitioning=false)"
    names = [str(r[0]) for r in con.execute(f"DESCRIBE SELECT * FROM {rel}").fetchall()]
    data = [n for n in names if not n.startswith("_")]
    rows = int(con.execute(f"SELECT count(*) FROM {rel}").fetchone()[0])
    out: dict[str, Any] = {"probe": Path(path).as_posix(), "rows": rows}
    if PUBLICATION not in names or not data:
        return {**out, "order": None, "why": f"no {PUBLICATION} or no data column"}
    if rows < 10_000:
        return {**out, "order": None, "why": "probe under 10,000 rows"}
    if rows > PROBE_ROWS:
        return {**out, "order": None, "why": f"probe over {PROBE_ROWS:,} rows"}
    publications = int(con.execute(f"SELECT count(DISTINCT {PUBLICATION}) FROM {rel}").fetchone()[0])
    # a column constant within each publication (CNES's COMPETEN: the month) says which copy a row is, not what record:
    # it is left out of the repeat count and of the key, found by counting, not named
    per_publication = [c for c in data if int(con.execute(
        f"SELECT count(*) FROM (SELECT DISTINCT {PUBLICATION}, {_q(c)} FROM {rel})").fetchone()[0]) == publications]
    data = [c for c in data if c not in per_publication]
    out["per_publication"] = per_publication
    if not data:
        return {**out, "order": None, "why": "every data column is constant within a publication"}
    cols = ", ".join(_q(c) for c in data)
    distinct = int(con.execute(f"SELECT count(*) FROM (SELECT DISTINCT {cols} FROM {rel})").fetchone()[0])
    repeat = 1 - distinct / rows
    out.update(publications=publications, repeat_share=round(repeat, 4))
    if publications < 2 or repeat < MIN_REPEAT:
        return {**out, "order": None, "why": f"repeats {repeat:.1%} across {publications} publications"}
    con.execute(f"CREATE OR REPLACE TEMP TABLE _probe AS SELECT * FROM {rel}")
    key: list[str] = []
    best = 0
    while len(key) < MAX_KEY and best < rows:
        scored = []
        for c in data:
            if c in key:
                continue
            k = ", ".join(_q(x) for x in [PUBLICATION, *key, c])
            scored.append((int(con.execute(f"SELECT count(*) FROM (SELECT DISTINCT {k} FROM _probe)").fetchone()[0]), c))
        top = max(scored)
        if top[0] <= best:
            break
        key.append(top[1])
        best = top[0]
    out.update(key=key, key_unique=best == rows)
    candidates: list[list[str] | None] = [None]
    for first in key:
        candidates.append([first, *[c for c in key if c != first], PUBLICATION])
    sizes: dict[str, int] = {}
    for order in candidates:
        sql = "SELECT * FROM _probe" + ("" if order is None else " ORDER BY " + ", ".join(_q(c) for c in order) + ", _row")
        if order is None:
            sql += " ORDER BY " + PUBLICATION + ", _row" if "_row" in names else ""
        sizes[json.dumps(order)] = _closed_size(con.execute(sql).to_arrow_table())
    con.execute("DROP TABLE _probe")
    file_size = sizes[json.dumps(None)]
    chosen, size = min(sizes.items(), key=lambda kv: kv[1])
    out["sizes"] = sizes
    if chosen == json.dumps(None) or size > file_size * (1 - MIN_GAIN):
        return {**out, "order": None, "why": f"no order beat the file order by {MIN_GAIN:.0%}"}
    return {**out, "order": json.loads(chosen), "why": f"{size / file_size:.2f} of the file order's size"}


def family_dir(path: Path) -> Path:
    """The family directory of a partition file (``<family>/schema_signature=.../uf=.../year=.../part.parquet``)."""
    return Path(path).parents[3]


def kept_order(family: Path) -> dict[str, Any] | None:
    target = family / ORDER_FILE
    return json.loads(target.read_text(encoding="utf-8")) if target.is_file() else None


def keep_order(family: Path, choice: dict[str, Any]) -> None:
    from .kept import write_json_atomic

    write_json_atomic(choice, family / ORDER_FILE)


def ordered_batches(con: Any, path: Path, columns: Sequence[str], order: Sequence[str], batch_size: int = 65_536):
    """The file's rows in ``order`` (then `_row`), streamed by DuckDB, which sorts beyond its memory limit on disk."""
    cols = ", ".join(_q(c) for c in columns)
    by = ", ".join(_q(c) for c in [*order, *(["_row"] if "_row" in columns else [])])
    reader = con.execute(f"SELECT {cols} FROM read_parquet('{Path(path).as_posix()}', hive_partitioning=false) "
                         f"ORDER BY {by}").fetch_record_batch(batch_size)
    yield from reader
