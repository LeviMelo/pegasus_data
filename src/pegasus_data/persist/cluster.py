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
#: event records (no repeats) are tried in one more order, on the probe's first rows: its columns of few values, fewest
#: first. Measured on 400,000 rows (2026-11-26): SIA-PA AL 2015 0.84 of the file order, CIHA RS 2018 0.83; SIH-RD, SIM-DO
#: and SINASC-DN larger (1.05, 1.15, 1.39), where the file order stays
EVENT_BLOCK = 400_000
LOW_CARDINALITY = 0.05
#: the rule's version: a family's kept choice made by another is measured again
ORDER_RULE = 2


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
    out: dict[str, Any] = {"probe": Path(path).as_posix(), "rows": rows, "rule": ORDER_RULE}
    if PUBLICATION not in names or not data:
        return {**out, "order": None, "why": f"no {PUBLICATION} or no data column"}
    if rows < 10_000:
        return {**out, "order": None, "why": "probe under 10,000 rows"}
    if rows > PROBE_ROWS:
        return _event_order(con, rel, names, data, out, f"probe over {PROBE_ROWS:,} rows")
    publications = int(con.execute(f"SELECT count(DISTINCT {PUBLICATION}) FROM {rel}").fetchone()[0])
    # a column constant within each publication (CNES's COMPETEN: the month) says which copy a row is, not what record:
    # it is left out of the repeat count and of the key, found by counting, not named
    # one scan for every column: constant within each publication where its least and greatest values agree and it is
    # filled on all or none of the publication's rows (a DISTINCT per column had cost 120 scans of SIH-RD's probe)
    grouped = ", ".join(f"min({_q(c)}) IS NOT DISTINCT FROM max({_q(c)}) AND count({_q(c)}) IN (0, count(*)) AS f{i}"
                        for i, c in enumerate(data))
    flags = con.execute(f"SELECT {', '.join(f'bool_and(f{i})' for i in range(len(data)))} FROM "
                        f"(SELECT {grouped} FROM {rel} GROUP BY {PUBLICATION})").fetchone()
    per_publication = [c for c, constant in zip(data, flags) if constant]
    data = [c for c in data if c not in per_publication]
    out["per_publication"] = per_publication
    if not data:
        return {**out, "order": None, "why": "every data column is constant within a publication"}
    cols = ", ".join(_q(c) for c in data)
    # rows counted by a 64-bit hash of their columns: a DISTINCT over every column of a wide file had asked DuckDB for
    # one 7.2 GiB block (2026-11-26); a collision among 2 M rows is about 1e-7 likely and only nudges a share
    distinct = int(con.execute(f"SELECT count(DISTINCT hash({cols})) FROM {rel}").fetchone()[0])
    repeat = 1 - distinct / rows
    out.update(publications=publications, repeat_share=round(repeat, 4))
    if publications < 2 or repeat < MIN_REPEAT:
        return _event_order(con, rel, names, data, out, f"repeats {repeat:.1%} across {publications} publications")
    con.execute(f"CREATE OR REPLACE TEMP TABLE _probe AS SELECT * FROM {rel}")
    key: list[str] = []
    best = 0
    while len(key) < MAX_KEY and best < rows:
        scored = []
        for c in data:
            if c in key:
                continue
            k = ", ".join(_q(x) for x in [PUBLICATION, *key, c])
            scored.append((int(con.execute(f"SELECT count(DISTINCT hash({k})) FROM _probe").fetchone()[0]), c))
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


def _event_order(con: Any, rel: str, names: Sequence[str], data: Sequence[str], out: dict[str, Any],
                 why: str) -> dict[str, Any]:
    """Records that do not repeat: their columns of few values (under `LOW_CARDINALITY` of the rows, by DuckDB's
    approximate count), fewest first, against the file order, on the probe's first `EVENT_BLOCK` rows."""
    by = ", _row" if "_row" in names else ""
    con.execute(f"CREATE OR REPLACE TEMP TABLE _block AS SELECT * FROM {rel} ORDER BY {PUBLICATION}{by} "
                f"LIMIT {EVENT_BLOCK}")
    try:
        block = int(con.execute("SELECT count(*) FROM _block").fetchone()[0])
        cards = con.execute("SELECT " + ", ".join(f"approx_count_distinct({_q(c)})" for c in data) + " FROM _block").fetchone()
        order = [c for n, c in sorted((int(n or 0), c) for n, c in zip(cards, data)) if 1 < n < LOW_CARDINALITY * block]
        if not order:
            return {**out, "order": None, "why": f"{why}; no column of few values"}
        file_size = _closed_size(con.execute(f"SELECT * FROM _block ORDER BY {PUBLICATION}{by}").to_arrow_table())
        size = _closed_size(con.execute("SELECT * FROM _block ORDER BY " + ", ".join(_q(c) for c in order) + by).to_arrow_table())
    finally:
        con.execute("DROP TABLE IF EXISTS _block")
    out["event_sizes"] = {"file_order": file_size, "by_cardinality": size}
    ratio = size / file_size
    if ratio > 1 - MIN_GAIN:
        return {**out, "order": None, "why": f"{why}; by cardinality {ratio:.2f} of the file order's size"}
    return {**out, "order": order, "why": f"{why}; by cardinality {ratio:.2f} of the file order's size"}


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
