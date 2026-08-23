"""Immutable source-publication provenance and source-period selection."""

from __future__ import annotations

from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

from .model import Period


def _with_competence(table: pa.Table, source_report: Any) -> pa.Table:
    if "_competencia" in table.column_names or "_source_path" not in table.column_names:
        return table
    facts = getattr(source_report, "source_facts", {}) or {}
    values = [
        (facts.get(str(path), (None, None, None))[2] if path is not None else None)
        for path in table["_source_path"].to_pylist()
    ]
    return table.append_column("_competencia", pa.array(values, pa.int32()))


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
        return table.filter(pc.fill_null(mask, True))
    if values.null_count:
        raise ValueError(
            "monthly source selection requires publication competence provenance; "
            "the selected lake rows contain unresolved source competence"
        )
    return table.filter(mask)
