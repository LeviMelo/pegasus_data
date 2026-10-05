"""Municipalities across vintages: which cells a lattice answers, and roll-ups to comparable areas.

Brazil's municipal lattice changed: 5,507 municipalities in the 2000 census, 5,565 in 2010, 5,570 in 2022.
SIDRA tables follow their own vintage (and the 2000 population table is served on the current list, with
"not available" for the 58 municipalities created since). A series that crosses a creation is broken unless
it is rolled up to IPEA's minimum comparable areas (AMC, Ehrl 2017), the smallest sets of municipalities
whose territory is the same at both ends of a period: 1980-2010, 1991-2010 and 2000-2010 (the geography pack).
Municipalities created after 2010 belong to no published AMC.

`roll_up` is conservative: counts are summed; a sum whose parts include a missing cell is itself missing
(status ``incomplete``), never the sum of what was left; non-additive kinds (means, rates) are refused.
"""

from __future__ import annotations

import pyarrow as pa
import pyarrow.compute as pc

from ..geography import iter_pack, to_code7
from .session import Sidra

__all__ = ["AMC_CLASSIFICATIONS", "comparable_area_map", "roll_up"]

AMC_CLASSIFICATIONS = {1980: "comparable_area_1980_2010", 1991: "comparable_area_1991_2010", 2000: "comparable_area_2000_2010"}


def comparable_area_map(start: int) -> dict[str, str]:
    """Municipality code (7 digits) → minimum comparable area code, for the span ``start``-2010."""
    classification = AMC_CLASSIFICATIONS[start]
    out = {}
    for row in iter_pack():
        if row["classification"] == classification:
            code7 = to_code7(row["municipality"])
            if code7:
                out[code7] = row["member_code"]
    return out


def roll_up(sidra: Sidra, series: pa.Table, start: int, *, keys: list[str] | None = None, nonexistent: bool = False) -> pa.Table:
    """Sum a count series (the output of `series.build_series`) over comparable areas of ``start``-2010.

    ``keys`` are the other columns that identify a cell (period, measure and any axes). Municipalities in no AMC keep
    their own code and are flagged ``unassigned``. A group with a missing part is ``incomplete`` with a null value,
    unless ``nonexistent``: then a ``not_available`` cell is taken as a municipality that did not yet exist (IBGE's
    mark for one created after the census; its territory is in its parent's figure, which is what an AMC guarantees)
    and the area is summed over the members that do have a value, provided one does. Use it only for a vintage that
    predates the creations; any other mark still makes the area incomplete.
    """
    pairs = set(zip(series.column("table").to_pylist(), series.column("variable").to_pylist(), strict=True))
    for table, variable in sorted(pairs):
        kind = next(v["kind"] for v in sidra.registry.variables(table) if v["id"] == variable)
        if kind != "c":
            raise ValueError(f"table {table} variable {variable} is a {kind!r}, not a count: summing it over areas would be wrong")
    amc = comparable_area_map(start)
    keys = keys or [c for c in series.schema.names if c not in {"locality", "level", "value", "status", "unit", "source",
                                                               "table", "variable", "role", "priority", "selected"}]
    series = series.filter(series.column("selected")) if "selected" in series.schema.names else series
    codes = series.column("locality").to_pylist()
    area = pa.array([amc.get(c, c) for c in codes], pa.string())
    assigned = pa.array([c in amc for c in codes], pa.bool_())
    work = series.select([*keys, "value", "status"]).append_column("area", area).append_column("assigned", assigned)
    absent = pc.equal(work.column("status"), "not_available") if nonexistent else pa.array([False] * work.num_rows)
    work = work.append_column("missing", pc.and_(pc.is_null(work.column("value")), pc.invert(absent)))
    work = work.append_column("has_value", pc.is_valid(work.column("value")))
    grouped = work.group_by(["area", *keys]).aggregate(
        [("value", "sum"), ("missing", "any"), ("assigned", "all"), ("has_value", "any"), ("has_value", "sum"),
         ("value", "count", pc.CountOptions(mode="all"))])
    unusable = pc.or_(grouped.column("missing_any"), pc.invert(grouped.column("has_value_any")))
    value = pc.if_else(unusable, pa.scalar(None, pa.float64()), grouped.column("value_sum"))
    status = pc.if_else(unusable, "incomplete", pc.if_else(grouped.column("assigned_all"), "value", "unassigned"))
    return pa.table({"area": grouped.column("area"), **{k: grouped.column(k) for k in keys},
                     "value": value, "status": status, "municipalities": grouped.column("value_count"),
                     "with_value": pc.cast(grouped.column("has_value_sum"), pa.int64())})
