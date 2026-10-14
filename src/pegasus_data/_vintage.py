"""Source-vintage intervals without invented temporal precision."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pyarrow as pa


@dataclass(frozen=True, slots=True)
class SourceVintage:
    start: int
    end: int
    precision: Literal["month", "year"]

    @property
    def exact(self) -> bool:
        return self.start == self.end


def vintage_groups(table: pa.Table) -> tuple[list[SourceVintage | None], pa.Array]:
    """Each row's source vintage as ``(distinct vintages, index of each row's)``: read exact months, coarse years, or
    genuinely unknown source vintage, computed in Arrow and resolved once per DISTINCT vintage (a table has a handful of
    months; a Python object per row was 11.8 s per million rows). A caller that resolves something per (value, vintage)
    groups on the index and takes the answers back by it.

    ``_source_resolution`` is optional for direct enrichment primitives. When it
    is present, a year is trusted only for an explicitly annual source; a null
    competence on a monthly/unknown source remains unknown rather than being
    upgraded from a convenient partition column.
    """
    import pyarrow.compute as pc

    n = table.num_rows

    def whole(name: str) -> pa.Array:
        if name not in table.column_names:
            return pa.repeat(pa.scalar(0, pa.int64()), n)
        return pc.fill_null(pc.cast(table[name], pa.int64()), 0).combine_chunks() if n else pa.array([], pa.int64())

    competence, year = whole("_competencia"), whole("year")
    in_year = pc.subtract(competence, pc.multiply(pc.divide(competence, 100), 100))     # the MM of YYYYMM
    month = pc.and_(pc.greater(competence, 0), pc.and_(pc.greater_equal(in_year, 1), pc.less_equal(in_year, 12)))
    annual_source = (pc.fill_null(pc.equal(pc.cast(table["_source_resolution"], pa.string()), "year"), True)
                     if "_source_resolution" in table.column_names else pa.repeat(pa.scalar(True), n))
    if isinstance(annual_source, pa.ChunkedArray):
        annual_source = annual_source.combine_chunks()
    coarse = pc.and_(pc.invert(month), pc.and_(pc.greater(year, 0), annual_source))
    start = pc.if_else(month, competence, pc.if_else(coarse, pc.add(pc.multiply(year, 100), 1), 0))
    end = pc.if_else(month, competence, pc.if_else(coarse, pc.add(pc.multiply(year, 100), 12), 0))
    # one integer per vintage: both ends are YYYYMM, below 10^6
    encoded = pc.dictionary_encode(pc.add(pc.multiply(start, 1_000_000), end))
    if isinstance(encoded, pa.ChunkedArray):
        encoded = encoded.combine_chunks()
    distinct: list[SourceVintage | None] = []
    for key in encoded.dictionary.to_pylist():
        lo, hi = divmod(int(key), 1_000_000)
        distinct.append(None if not lo else SourceVintage(lo, hi, "month" if lo == hi else "year"))
    return distinct, encoded.indices


def source_vintages(table: pa.Table) -> list[SourceVintage | None]:
    """The source vintage of each row (`vintage_groups`), one object per row."""
    distinct, index = vintage_groups(table)
    return [distinct[i] for i in index.to_pylist()]


def months_in(vintage: SourceVintage) -> tuple[int, ...]:
    values: list[int] = []
    cursor = vintage.start
    while cursor <= vintage.end:
        values.append(cursor)
        year, month = divmod(cursor, 100)
        cursor = (year + 1) * 100 + 1 if month == 12 else year * 100 + month + 1
    return tuple(values)


def window_covers(lo: str, hi: str, vintage: SourceVintage | None) -> bool:
    if vintage is None:
        return not lo and not hi
    lower = int(lo) if lo else 0
    upper = int(hi) if hi else 999912
    return lower <= vintage.start and vintage.end <= upper


def window_overlaps(lo: str, hi: str, vintage: SourceVintage | None) -> bool:
    if vintage is None:
        return not lo and not hi
    lower = int(lo) if lo else 0
    upper = int(hi) if hi else 999912
    return lower <= vintage.end and vintage.start <= upper
