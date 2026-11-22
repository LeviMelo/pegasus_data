"""The value as filed, kept where it says more than the typed value: a render learned per column and per landing.

An intake column that is typed (a date, a number, a code read as an integer) keeps its text as filed beside it,
``<NAME>__RAW``: the rule that a raw value is never discarded, and what lets a unit be landed again under a changed
declaration from its own records, nothing downloaded (`intake._reland`). Stored whole, that text was 12% of the lake
(4.0 GB; ANS TISS items 28%, SNGPC 18%; 2026-11-22), and almost all of it is the typed value written back: 99.5% of the
TISS item values are their number with a decimal comma and no ".0".

So a landing keeps the text only where a render of the typed value does not give it back, character for character, and
records the render it used in the file's metadata (``pegasus.raw_render``, a JSON ``{column: render}``). A reader gets
``coalesce(<NAME>__RAW, render(<NAME>))``: the same text on every row, so nothing is lost. The render is chosen among a
fixed set by the share of a unit's rows it gives back (`choose`), since sources write numbers and dates in their own
ways ("3,53", "30.", "2014/08/14 08:37:42"); one under half is not used, and the text is kept whole.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

#: the file metadata key a landing writes its renders under
META_KEY = b"pegasus.raw_render"

#: renders of a typed value back to text, by the typed column's DuckDB type; ``{x}`` is the typed column
_NUMBER = {
    "text": "CAST({x} AS VARCHAR)",
    "int": "regexp_replace(CAST({x} AS VARCHAR), '\\.0$', '')",
    "dot": "regexp_replace(CAST({x} AS VARCHAR), '\\.0$', '.')",
    "comma": "replace(CAST({x} AS VARCHAR), '.', ',')",
    "int_comma": "replace(regexp_replace(CAST({x} AS VARCHAR), '\\.0$', ''), '.', ',')",
}
RENDERS: dict[str, dict[str, str]] = {
    "DOUBLE": _NUMBER,
    "BIGINT": {"text": "CAST({x} AS VARCHAR)"},
    "VARCHAR": {"text": "{x}", "dot0": "{x} || '.0'", "dot": "{x} || '.'"},
    "DATE": {"iso": "strftime({x}, '%Y-%m-%d')", "br": "strftime({x}, '%d/%m/%Y')", "slash": "strftime({x}, '%Y/%m/%d')",
             "compact": "strftime({x}, '%Y%m%d')", "br_compact": "strftime({x}, '%d%m%Y')"},
}
#: the least share of a unit's filed values a render must give back to be used
MIN_SHARE = 0.5
#: rows a landing looks at to choose its renders (the choice changes how much is stored, never what is read)
SAMPLE_ROWS = 200_000


def quote(name: str) -> str:
    """A column name as a DuckDB identifier."""
    return '"' + name.replace('"', '""') + '"'


def render_sql(name: str, column: str, duck_type: str) -> str:
    """The SQL of render ``name`` of the typed ``column`` (quoted by the caller), for a column of ``duck_type``. A name
    ``fmt:<strftime format>`` is a date written in that format: a date column's own declared format, the way its source
    writes it ("2023-02" for a month filed as %Y-%m)."""
    if name.startswith("fmt:"):
        fmt = name[4:].replace("'", "''")
        return f"strftime({column}, '{fmt}')"
    return RENDERS[_family(duck_type)][name].format(x=column)


def _family(duck_type: str) -> str:
    t = duck_type.upper()
    if t in ("DOUBLE", "FLOAT", "REAL") or t.startswith("DECIMAL"):
        return "DOUBLE"
    if t in ("BIGINT", "INTEGER", "SMALLINT", "TINYINT", "HUGEINT"):
        return "BIGINT"
    if t == "DATE":
        return "DATE"
    return "VARCHAR"


def choose(con: Any, relation: str, columns: Mapping[str, str], quote: Any,
           formats: Mapping[str, Sequence[str]] | None = None) -> dict[str, str]:
    """For each typed column (``{name: DuckDB type}``) whose ``<name>__RAW`` the relation holds, the render that gives back
    the most of a sample's filed values, when it gives back at least `MIN_SHARE` of them. ``formats`` adds a date column's
    declared formats to its candidates (``fmt:<format>``)."""
    chosen: dict[str, str] = {}
    sample = f"(SELECT * FROM {relation} LIMIT {SAMPLE_ROWS})"
    for name, duck_type in columns.items():
        raw = quote(f"{name}__RAW")
        options = dict(RENDERS[_family(duck_type)])
        if _family(duck_type) == "DATE":
            options.update({f"fmt:{f}": "" for f in (formats or {}).get(name, ())})
        counts = ", ".join(f"count(*) FILTER (WHERE {render_sql(r, quote(name), duck_type)} = {raw})" for r in options)
        row = con.execute(f"SELECT count({raw}), {counts} FROM {sample}").fetchone()
        filed, hits = int(row[0] or 0), [int(v or 0) for v in row[1:]]
        if filed and max(hits) >= MIN_SHARE * filed:
            chosen[name] = list(options)[hits.index(max(hits))]
    return chosen


def compacted_sql(name: str, render: str, duck_type: str, quote: Any) -> str:
    """``<name>__RAW`` stored as the text only where the render does not give it back."""
    raw = quote(f"{name}__RAW")
    return f"CASE WHEN {render_sql(render, quote(name), duck_type)} IS NOT DISTINCT FROM {raw} THEN NULL ELSE {raw} END"


def renders_of(metadata: Mapping[bytes, bytes] | None) -> dict[str, dict[str, str]]:
    """A file's renders, ``{column: {"render": name, "type": duck type}}``, from its metadata; {} when it has none."""
    text = (metadata or {}).get(META_KEY)
    return json.loads(text) if text else {}


def restored(table: Any, renders: Mapping[str, Mapping[str, str]], quote: Any) -> Any:
    """``table`` with each ``<name>__RAW`` of ``renders`` given back whole: ``coalesce(<name>__RAW, render(<name>))``.
    A raw column whose typed column the table does not hold is left as stored (the caller reads the typed one too)."""
    import duckdb

    present = [n for n in renders if f"{n}__RAW" in table.column_names and n in table.column_names]
    if not present:
        return table
    import pyarrow as pa

    con = duckdb.connect()
    try:
        con.execute("SET preserve_insertion_order = true")
        con.register("t", table.select([c for n in present for c in (n, f"{n}__RAW")]))
        exprs = ", ".join(f"coalesce({quote(n + '__RAW')}, {render_sql(renders[n]['render'], quote(n), renders[n]['type'])}) "
                          f"AS {quote(n + '__RAW')}" for n in present)
        whole = con.execute(f"SELECT {exprs} FROM t").to_arrow_table()
    finally:
        con.close()
    for n in present:
        at = table.column_names.index(f"{n}__RAW")
        column = whole.column(f"{n}__RAW").cast(pa.string())
        table = table.set_column(at, table.schema.field(at).with_type(pa.string()), column)
    return table


__all__ = ["META_KEY", "RENDERS", "choose", "compacted_sql", "quote", "render_sql", "renders_of", "restored"]
