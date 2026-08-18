"""Readers for the text-ish containers: CSV/TXT, JSON, XML, XLSX, Parquet.

All of them are minority formats on the DATASUS tree, but they matter for a
specific reason (D3): SIH republishes the *same* AIH records as ``.dbc``,
``.dbf``, ``.xml`` and ``.csv``. Reading them is what proves those four are one
family with four representations rather than four datasets, and what stops a
downstream aggregation from silently counting the same admission four times.
"""

from __future__ import annotations

import csv
import io
import json
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from pathlib import Path

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from ..textenc import best_effort_decode
from .base import (
    DecodedTable,
    DecodeError,
    FieldMeta,
    UnsupportedContainer,
    batches_from_table,
    fields_from_schema,
)

_TEXT_ENCODINGS = ("utf-8", "cp1252", "latin-1", "cp850")


def _decode_text(data: bytes) -> tuple[str, str]:
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:].decode("utf-8", errors="replace"), "utf-8-sig"
    return best_effort_decode(data, candidates=_TEXT_ENCODINGS)


def _sniff_delimiter(sample: str) -> str:
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        # DATASUS CSVs are semicolon-delimited more often than not; fall back to
        # whichever candidate appears most in the header line.
        header = sample.splitlines()[0] if sample.splitlines() else ""
        counts = {d: header.count(d) for d in ";,\t|"}
        best = max(counts, key=lambda d: counts[d])
        return best if counts[best] else ","


def read_csv_bytes(data: bytes, *, path: str, member: str = "", row_limit: int | None = None) -> DecodedTable:
    text, encoding = _decode_text(data)
    if not text.strip():
        raise DecodeError(f"empty text payload: {path}")
    delimiter = _sniff_delimiter(text[:16384])
    read_options = pacsv.ReadOptions(encoding="utf8", block_size=1 << 22)
    parse_options = pacsv.ParseOptions(delimiter=delimiter, newlines_in_values=True)
    # Everything stays a string: the profiler needs the raw token, and CSV
    # declares no types worth trusting.
    convert_options = pacsv.ConvertOptions(strings_can_be_null=True, null_values=[""])
    try:
        table = pacsv.read_csv(
            io.BytesIO(text.encode("utf-8")),
            read_options=read_options,
            parse_options=parse_options,
            convert_options=convert_options,
        )
    except Exception as exc:
        raise DecodeError(f"csv parse failed for {path}: {exc}") from exc
    table = table.cast(pa.schema([pa.field(n, pa.string()) for n in table.schema.names]))
    if row_limit is not None and table.num_rows > row_limit:
        table = table.slice(0, row_limit)
    fields = [
        FieldMeta(name=n.strip().upper() or f"COL_{i + 1}", physical_type="csv", order=i)
        for i, n in enumerate(table.schema.names)
    ]
    table = table.rename_columns([f.name for f in fields])
    return DecodedTable(
        path=path,
        member=member,
        reader="csv",
        fields=fields,
        batches=batches_from_table(table),
        row_count=table.num_rows,
        warnings=[f"encoding:{encoding}", f"delimiter:{delimiter!r}"],
    )


def _json_rows(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        arrays = [v for v in payload.values() if isinstance(v, list) and any(isinstance(x, dict) for x in v)]
        if arrays:
            best = max(arrays, key=len)
            return [r for r in best if isinstance(r, dict)]
        return [payload]
    return []


def read_json_bytes(data: bytes, *, path: str, member: str = "", row_limit: int | None = None) -> DecodedTable:
    text, _ = _decode_text(data)
    stripped = text.lstrip()
    rows: list[dict[str, object]]
    if stripped.startswith("{") and "\n" in stripped and not stripped.rstrip().endswith("}\n}"):
        # Try newline-delimited JSON first; fall back to a single document.
        try:
            rows = [json.loads(line) for line in text.splitlines() if line.strip()]
            rows = [r for r in rows if isinstance(r, dict)]
        except json.JSONDecodeError:
            rows = _json_rows(json.loads(text))
    else:
        try:
            rows = _json_rows(json.loads(text))
        except json.JSONDecodeError as exc:
            raise DecodeError(f"json parse failed for {path}: {exc}") from exc
    if not rows:
        raise DecodeError(f"no object rows found in json payload: {path}")
    if row_limit is not None:
        rows = rows[:row_limit]
    names: list[str] = []
    for row in rows[:1000]:
        for key in row:
            upper = str(key).upper()
            if upper not in names:
                names.append(upper)
    columns = {
        name: pa.array([_stringify(r.get(name) if name in r else r.get(name.lower())) for r in rows], type=pa.string())
        for name in names
    }
    table = pa.table(columns)
    return DecodedTable(
        path=path,
        member=member,
        reader="json",
        fields=[FieldMeta(name=n, physical_type="json", order=i) for i, n in enumerate(names)],
        batches=batches_from_table(table),
        row_count=table.num_rows,
    )


def _stringify(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def read_xml_bytes(data: bytes, *, path: str, member: str = "", row_limit: int | None = None) -> DecodedTable:
    text, _ = _decode_text(data)
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise DecodeError(f"xml parse failed for {path}: {exc}") from exc
    grouped: dict[str, list[ET.Element]] = {}
    for child in root:
        grouped.setdefault(child.tag, []).append(child)
    rows: list[dict[str, str]] = []
    if grouped:
        _, nodes = max(grouped.items(), key=lambda kv: len(kv[1]))
        for node in nodes:
            row = {str(k).upper(): str(v) for k, v in node.attrib.items()}
            for sub in node:
                row[sub.tag.upper()] = (sub.text or "").strip()
            if row:
                rows.append(row)
    if not rows:
        rows = [{c.tag.upper(): (c.text or "").strip() for c in root}]
        rows = [r for r in rows if r]
    if not rows:
        raise DecodeError(f"no repeating element found in xml payload: {path}")
    if row_limit is not None:
        rows = rows[:row_limit]
    names: list[str] = []
    for row in rows[:1000]:
        for key in row:
            if key not in names:
                names.append(key)
    table = pa.table({n: pa.array([r.get(n) for r in rows], type=pa.string()) for n in names})
    return DecodedTable(
        path=path,
        member=member,
        reader="xml",
        fields=[FieldMeta(name=n, physical_type="xml", order=i) for i, n in enumerate(names)],
        batches=batches_from_table(table),
        row_count=table.num_rows,
    )


def read_parquet(path: str | Path, *, member: str = "", row_limit: int | None = None) -> DecodedTable:
    try:
        pf = pq.ParquetFile(str(path))
    except Exception as exc:
        raise DecodeError(f"parquet open failed for {path}: {exc}") from exc
    schema = pf.schema_arrow
    fields = fields_from_schema(schema, physical_prefix="parquet:")

    def _iter() -> Iterator[pa.RecordBatch]:
        produced = 0
        for batch in pf.iter_batches(batch_size=65_536):
            if row_limit is not None and produced + batch.num_rows > row_limit:
                batch = batch.slice(0, row_limit - produced)
            produced += batch.num_rows
            yield batch
            if row_limit is not None and produced >= row_limit:
                return

    return DecodedTable(
        path=str(path),
        member=member,
        reader="parquet",
        fields=fields,
        batches=_iter,
        row_count=pf.metadata.num_rows if pf.metadata else None,
    )


def read_xlsx(path: str | Path, *, member: str = "", row_limit: int | None = None) -> DecodedTable:
    try:
        import openpyxl
    except ImportError as exc:
        raise UnsupportedContainer("openpyxl is required to read .xls/.xlsx files") from exc
    try:
        wb = openpyxl.load_workbook(str(path), read_only=True, data_only=True)
    except Exception as exc:
        raise DecodeError(f"xlsx open failed for {path}: {exc}") from exc
    try:
        ws = wb.active
        if ws is None:
            raise DecodeError(f"workbook has no active sheet: {path}")
        rows_iter = ws.iter_rows(values_only=True)
        try:
            header = next(rows_iter)
        except StopIteration as exc:
            raise DecodeError(f"empty worksheet: {path}") from exc
        names = [
            (str(v).strip().upper() if v is not None and str(v).strip() else f"COL_{i + 1}")
            for i, v in enumerate(header)
        ]
        data_rows: list[tuple[object, ...]] = []
        for i, values in enumerate(rows_iter):
            if row_limit is not None and i >= row_limit:
                break
            data_rows.append(values)
    finally:
        wb.close()
    columns = {
        name: pa.array(
            [_stringify(row[i]) if i < len(row) else None for row in data_rows], type=pa.string()
        )
        for i, name in enumerate(names)
    }
    table = pa.table(columns)
    return DecodedTable(
        path=str(path),
        member=member,
        reader="xlsx",
        fields=[FieldMeta(name=n, physical_type="xlsx", order=i) for i, n in enumerate(names)],
        batches=batches_from_table(table),
        row_count=table.num_rows,
    )
