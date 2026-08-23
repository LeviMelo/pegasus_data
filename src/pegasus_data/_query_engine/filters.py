"""Declared temporal and geographic row filtering."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal

import pyarrow as pa
import pyarrow.compute as pc

from ..config import UF_TO_NUMERIC
from .model import Geography, Period, QueryReport


def _with_competence(table: pa.Table, source_report: Any) -> pa.Table:
    if "_competencia" in table.column_names or "_source_path" not in table.column_names:
        return table
    facts = getattr(source_report, "source_facts", {}) or {}
    values = [
        (facts.get(str(path), (None, None, None))[2] if path is not None else None)
        for path in table["_source_path"].to_pylist()
    ]
    return table.append_column("_competencia", pa.array(values, pa.int32()))


def _competence_value(value: object) -> int | None:
    """Return YYYYMM from common DATASUS competence/date encodings."""
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.year * 100 + value.month
    text = str(value).strip()
    if not text:
        return None
    if len(text) >= 7 and text[:4].isdigit() and text[4] in {"-", "/"}:
        month = text[5:7]
        if month.isdigit() and 1 <= int(month) <= 12:
            return int(text[:4]) * 100 + int(month)
    digits = "".join(character for character in text if character.isdigit())
    if len(digits) == 6 and 190001 <= int(digits) <= 219912:
        month = int(digits[4:])
        return int(digits) if 1 <= month <= 12 else None
    if len(digits) == 8:
        if 1900 <= int(digits[:4]) <= 2199 and 1 <= int(digits[4:6]) <= 12:
            return int(digits[:6])
        if 1900 <= int(digits[-4:]) <= 2199 and 1 <= int(digits[2:4]) <= 12:
            return int(digits[-4:]) * 100 + int(digits[2:4])
    return None


def _with_row_competence(table: pa.Table, row_time_field: str | None) -> pa.Table:
    if not row_time_field:
        return table
    if "+" in row_time_field:
        year_field, month_field = row_time_field.split("+", 1)
        if year_field not in table.column_names or month_field not in table.column_names:
            return table
        values = []
        for year, month in zip(
            table[year_field].to_pylist(), table[month_field].to_pylist(), strict=True
        ):
            try:
                year_number, month_number = int(year), int(month)
            except (TypeError, ValueError):
                values.append(None)
                continue
            values.append(
                year_number * 100 + month_number
                if 1900 <= year_number <= 2199 and 1 <= month_number <= 12
                else None
            )
    else:
        if row_time_field not in table.column_names:
            return table
        values = [_competence_value(value) for value in table[row_time_field].to_pylist()]
    row_values = pa.array(values, pa.int32())
    if "_competencia" not in table.column_names:
        return table.append_column("_competencia", row_values)
    # A declared row-time field is analytically more precise than the file
    # competence. This matters for annual containers, whose file fact is an
    # enclosure (YYYY00), not the month of every contained record.
    return table.set_column(table.column_names.index("_competencia"), "_competencia", row_values)


def _filter_period(
    table: pa.Table,
    period: Period | None,
    adapted: bool,
    *,
    unresolved_time: Literal["exclude", "retain", "error"] = "exclude",
    report: QueryReport | None = None,
) -> pa.Table:
    if period is None or adapted or "_competencia" not in table.column_names:
        return table
    values = table["_competencia"]
    unresolved = values.null_count
    if report is not None:
        report.rows_time_unresolved += unresolved
    if unresolved and unresolved_time == "error":
        raise ValueError(
            f"{unresolved} row(s) have no parseable value for the declared time axis"
        )
    mask = pc.and_(pc.greater_equal(values, period.start), pc.less_equal(values, period.end))
    if unresolved_time == "retain":
        return table.filter(pc.fill_null(mask, True))
    if report is not None:
        report.rows_time_excluded += unresolved
    return table.filter(pc.fill_null(mask, False))


def _filter_geography(
    table: pa.Table,
    geography: Geography | None,
    physical: bool,
    row_field: str | None = None,
) -> pa.Table:
    if geography is None or (physical and not geography.municipality):
        return table
    if geography.municipality:
        if row_field and row_field in table.column_names:
            return table.filter(
                pc.equal(pc.cast(table[row_field], pa.string()), geography.municipality)
            )
        raise ValueError("requested municipality cannot be represented by this dataset's rows")
    if geography.uf:
        prefix = UF_TO_NUMERIC.get(geography.uf)
        if row_field and row_field in table.column_names and prefix:
            return table.filter(
                pc.starts_with(pc.cast(table[row_field], pa.string()), prefix)
            )
        raise ValueError("requested UF cannot be represented physically or by a reliable row field")
    return table
