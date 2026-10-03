"""Immutable source-publication provenance and source-period selection."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from .model import Period


def _per_path(paths: pa.ChunkedArray | pa.Array, values: dict[str, Any], default: Any,
              kind: pa.DataType) -> pa.Array:
    """One value per row from a per-source-file mapping, computed once per file.

    A state-year holds millions of rows from a few dozen files; looking each
    row up in Python cost seconds per query (2026-10-02, SIH SP: 9.6 of 19.7 s).
    A null path takes ``default`` like an unknown one.
    """
    chunks = paths.chunks if isinstance(paths, pa.ChunkedArray) else [paths]
    out = []
    for chunk in chunks:
        if pa.types.is_dictionary(chunk.type):
            # Already one entry per distinct file, with per-row indices.
            unique, index = chunk.dictionary, chunk.indices
        else:
            chunk = pc.cast(chunk, pa.string())
            unique = pc.unique(chunk).drop_null()
            index = pc.index_in(chunk, value_set=unique)
        per_file = pa.array([values.get(str(path), default) for path in unique.to_pylist()], kind)
        out.append(pc.take(per_file, index))
    taken = pa.concat_arrays(out) if out else pa.array([], kind)
    if default is None:
        return taken
    return pc.fill_null(taken, pa.scalar(default, kind))


def _with_competence(table: pa.Table, source_report: Any) -> pa.Table:
    if "_source_path" not in table.column_names:
        return table
    facts = getattr(source_report, "source_facts", {}) or {}
    resolutions = getattr(source_report, "source_resolutions", {}) or {}
    paths = table["_source_path"]
    if "_competencia" not in table.column_names:
        competence = {path: fact[2] for path, fact in facts.items()}
        table = table.append_column("_competencia", _per_path(paths, competence, None, pa.int32()))
    if "year" not in table.column_names:
        year = {path: fact[1] for path, fact in facts.items()}
        table = table.append_column("year", _per_path(paths, year, None, pa.int32()))
    if "_source_resolution" not in table.column_names:
        table = table.append_column(
            "_source_resolution", _per_path(paths, resolutions, "unknown", pa.string())
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
    n = table.num_rows
    annual_years = pa.array([int(y) for y, r in year_resolutions if r == "year"], pa.int64())
    current = (
        table["_source_resolution"] if "_source_resolution" in table.column_names
        else pa.nulls(n, pa.string())
    )
    competence = (
        pc.cast(table["_competencia"], pa.int64()) if "_competencia" in table.column_names
        else pa.nulls(n, pa.int64())
    )
    year = pc.cast(table["year"], pa.int64()) if "year" in table.column_names else pa.nulls(n, pa.int64())
    keep = pc.fill_null(pc.is_in(current, value_set=pa.array(["year", "month"])), False)
    month_of = pc.cast(pc.subtract(competence, pc.multiply(pc.divide(competence, 100), 100)), pa.int64())
    monthly = pc.fill_null(
        pc.and_(pc.not_equal(competence, 0),
                pc.and_(pc.greater_equal(month_of, 1), pc.less_equal(month_of, 12))),
        False,
    )
    annual = pc.fill_null(pc.and_(pc.not_equal(year, 0), pc.is_in(year, value_set=annual_years)), False)
    values = pc.if_else(
        keep, pc.cast(current, pa.string()),
        pc.if_else(monthly, "month", pc.if_else(annual, "year", "unknown")),
    )
    array = values.combine_chunks() if isinstance(values, pa.ChunkedArray) else values
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
