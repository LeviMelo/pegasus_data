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


def source_vintages(table: pa.Table) -> list[SourceVintage | None]:
    """Read exact months, coarse years, or genuinely unknown source vintage.

    ``_source_resolution`` is optional for direct enrichment primitives. When it
    is present, a year is trusted only for an explicitly annual source; a null
    competence on a monthly/unknown source remains unknown rather than being
    upgraded from a convenient partition column.
    """
    competences = (
        table["_competencia"].to_pylist()
        if "_competencia" in table.column_names
        else [None] * table.num_rows
    )
    years = (
        table["year"].to_pylist()
        if "year" in table.column_names
        else [None] * table.num_rows
    )
    resolutions = (
        table["_source_resolution"].to_pylist()
        if "_source_resolution" in table.column_names
        else [None] * table.num_rows
    )
    out: list[SourceVintage | None] = []
    for competence, year, resolution in zip(
        competences, years, resolutions, strict=True
    ):
        number = int(competence or 0)
        if number and 1 <= number % 100 <= 12:
            out.append(SourceVintage(number, number, "month"))
            continue
        if year and (resolution is None or str(resolution) == "year"):
            annual = int(year)
            out.append(SourceVintage(annual * 100 + 1, annual * 100 + 12, "year"))
            continue
        out.append(None)
    return out


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
