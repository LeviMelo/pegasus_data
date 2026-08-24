"""Immutable source-publication provenance and source-period selection."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from .model import Period


def _with_competence(table: pa.Table, source_report: Any) -> pa.Table:
    if "_source_path" not in table.column_names:
        return table
    facts = getattr(source_report, "source_facts", {}) or {}
    resolutions = getattr(source_report, "source_resolutions", {}) or {}
    paths = table["_source_path"].to_pylist()
    if "_competencia" not in table.column_names:
        values = [
            (facts.get(str(path), (None, None, None))[2] if path is not None else None)
            for path in paths
        ]
        table = table.append_column("_competencia", pa.array(values, pa.int32()))
    if "year" not in table.column_names:
        years = [
            (facts.get(str(path), (None, None, None))[1] if path is not None else None)
            for path in paths
        ]
        table = table.append_column("year", pa.array(years, pa.int32()))
    if "_source_resolution" not in table.column_names:
        values = [
            resolutions.get(str(path), "unknown") if path is not None else "unknown"
            for path in paths
        ]
        table = table.append_column(
            "_source_resolution", pa.array(values, pa.string())
        )
    return table


def _with_source_resolution(
    table: pa.Table, year_resolutions: Sequence[tuple[int, str]]
) -> pa.Table:
    """Backfill explicit precision for safe legacy annual lake partitions.

    New builds carry this per source. An old annual-only year can be upgraded
    from reviewed publication metadata without inventing a month; mixed and
    monthly years remain unknown when their competence is missing.
    """
    by_year = dict(year_resolutions)
    years = (
        table["year"].to_pylist()
        if "year" in table.column_names
        else [None] * table.num_rows
    )
    competences = (
        table["_competencia"].to_pylist()
        if "_competencia" in table.column_names
        else [None] * table.num_rows
    )
    current = (
        table["_source_resolution"].to_pylist()
        if "_source_resolution" in table.column_names
        else [None] * table.num_rows
    )
    values: list[str] = []
    for resolution, year, competence in zip(current, years, competences, strict=True):
        if resolution in {"year", "month"}:
            values.append(str(resolution))
        elif competence and 1 <= int(competence) % 100 <= 12:
            values.append("month")
        elif year and by_year.get(int(year)) == "year":
            values.append("year")
        else:
            values.append("unknown")
    array = pa.array(values, pa.string())
    if "_source_resolution" in table.column_names:
        return table.set_column(
            table.column_names.index("_source_resolution"),
            "_source_resolution",
            array,
        )
    return table.append_column("_source_resolution", array)


def _filter_source_period(
    table: pa.Table,
    period: Period | None,
    *,
    retain_annual_enclosures: bool = False,
) -> pa.Table:
    """Limit lake rows by immutable publication competence, never a fact field."""
    if (
        period is None
        or period.precision != "month"
        or "_competencia" not in table.column_names
    ):
        return table
    values = table["_competencia"]
    mask = pc.and_(pc.greater_equal(values, period.start), pc.less_equal(values, period.end))
    if retain_annual_enclosures:
        if "_source_resolution" not in table.column_names:
            raise ValueError(
                "annual enclosure retention requires explicit source-resolution provenance"
            )
        annual = pc.equal(table["_source_resolution"], "year")
        unresolved = pc.and_(pc.is_null(values), pc.invert(pc.fill_null(annual, False)))
        if pc.any(unresolved).as_py():
            raise ValueError(
                "monthly source selection found null competence that is not an "
                "explicit annual enclosure"
            )
        return table.filter(pc.or_(pc.fill_null(mask, False), pc.fill_null(annual, False)))
    if values.null_count:
        raise ValueError(
            "monthly source selection requires publication competence provenance; "
            "the selected lake rows contain unresolved source competence"
        )
    return table.filter(mask)
