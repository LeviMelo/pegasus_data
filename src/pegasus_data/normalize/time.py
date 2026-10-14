"""Time canonicalisation: competência, epidemiological week, epidemiological year.

The epidemiological week is the trap. It runs **Sunday to Saturday**, and week 1
is the one containing 4 January — so an epi year has **52 or 53** weeks. Computing
``year(date), week(date)`` instead produces a spurious gap or spike every few
years, right where a surveillance series would be read as a signal.

And the harder rule: **where the source already carries the official epi week,
use the source's value; do not recompute.** SINAN publishes ``SEM_PRI`` and
``SEM_NOT``; recomputing them diverges from the Ministry's own calculation at the
year boundary and silently desynchronises every comparison against a published
figure (§7.1, §13).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

import pyarrow as pa
import pyarrow.compute as pc

__all__ = [
    "epi_week",
    "epi_year_weeks",
    "competencia_to_year_month",
    "build_calendar",
    "epi_week_array",
    "SOURCE_EPI_WEEK_FIELDS",
]

#: Fields that already carry the official epidemiological week. Never recomputed.
SOURCE_EPI_WEEK_FIELDS: frozenset[str] = frozenset(
    {"SEM_PRI", "SEM_NOT", "SEM_DIAG", "SEMANA", "SEM_SIN_PRI", "NU_SEMANA"}
)


def _week_start(d: date) -> date:
    """The Sunday that opens the epidemiological week containing `d`."""
    # Python's weekday(): Monday=0 … Sunday=6. Epi weeks open on Sunday.
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _epi_year_first_week_start(year: int) -> date:
    """Start of week 1: the Sunday-to-Saturday week containing 4 January."""
    return _week_start(date(year, 1, 4))


@dataclass(frozen=True, slots=True)
class EpiWeek:
    year: int
    week: int

    def __str__(self) -> str:
        return f"{self.year}W{self.week:02d}"


def epi_week(d: date) -> EpiWeek:
    """Epidemiological year and week for a calendar date.

    The last days of December frequently belong to week 1 of the following epi
    year, and the first days of January frequently belong to week 52 or 53 of the
    previous one. Both directions are handled explicitly rather than clamped.
    """
    start = _week_start(d)
    candidate_year = d.year
    first = _epi_year_first_week_start(candidate_year)
    if start < first:
        candidate_year -= 1
        first = _epi_year_first_week_start(candidate_year)
    else:
        next_first = _epi_year_first_week_start(candidate_year + 1)
        if start >= next_first:
            candidate_year += 1
            first = next_first
    week = (start - first).days // 7 + 1
    return EpiWeek(candidate_year, week)


def epi_year_weeks(year: int) -> int:
    """52 or 53 — the reason a naive week number drifts."""
    first = _epi_year_first_week_start(year)
    nxt = _epi_year_first_week_start(year + 1)
    return (nxt - first).days // 7


def competencia_to_year_month(value: str | int | None) -> tuple[int, int] | None:
    """Parse ``AAAAMM``. Returns None rather than guessing on anything else."""
    if value is None:
        return None
    text = str(value).strip()
    if len(text) != 6 or not text.isdigit():
        return None
    year, month = int(text[:4]), int(text[4:])
    if not (1900 <= year <= 2200) or not (1 <= month <= 12):
        return None
    return year, month


def build_calendar(start_year: int, end_year: int) -> pa.Table:
    """A date dimension computed once, rather than per query (§7.1).

    Columns: ``date``, ``year``, ``month``, ``competencia``, ``epi_year``,
    ``epi_week``, ``epi_year_week``, ``epi_year_total_weeks``.
    """
    days: list[date] = []
    cursor = date(start_year, 1, 1)
    last = date(end_year, 12, 31)
    while cursor <= last:
        days.append(cursor)
        cursor += timedelta(days=1)
    weeks = [epi_week(d) for d in days]
    totals = {y: epi_year_weeks(y) for y in range(start_year - 1, end_year + 2)}
    return pa.table(
        {
            "date": pa.array(days, type=pa.date32()),
            "year": pa.array([d.year for d in days], type=pa.int16()),
            "month": pa.array([d.month for d in days], type=pa.int8()),
            "competencia": pa.array([d.year * 100 + d.month for d in days], type=pa.int32()),
            "epi_year": pa.array([w.year for w in weeks], type=pa.int16()),
            "epi_week": pa.array([w.week for w in weeks], type=pa.int8()),
            "epi_year_week": pa.array([str(w) for w in weeks], type=pa.string()),
            "epi_year_total_weeks": pa.array([totals[w.year] for w in weeks], type=pa.int8()),
        }
    )


def parse_date_array(array: pa.Array, *, order: str = "YYYYMMDD", sentinels: tuple[str, ...] = ()) -> pa.Array:
    """Vectorised parse of a fixed-width date column into ``date32``.

    Sentinels are nulled *only* when the caller names them — which the engine
    takes from the ledger, per field. There is no global sentinel rule here (§13).
    """
    if pa.types.is_date(array.type) or pa.types.is_timestamp(array.type):
        return array.cast(pa.date32())      # already a date: a typed source needs no parsing
    if array.type != pa.string():
        array = array.cast(pa.string())
    cleaned = pc.utf8_trim_whitespace(array)
    if sentinels:
        mask = pc.is_in(cleaned, value_set=pa.array(list(sentinels), type=pa.string()))
        cleaned = pc.if_else(pc.fill_null(mask, False), pa.scalar(None, pa.string()), cleaned)
    # The open-data CSVs write the same dates as ISO text (2014-03-02, optionally with a time):
    # one date, two spellings across representations of one publication.
    cleaned = pc.replace_substring_regex(
        cleaned, r"^(\d{4})-(\d{2})-(\d{2})(?:[ T].*)?$", r"\1\2\3")
    valid = pc.fill_null(pc.match_substring_regex(cleaned, r"^\d{8}$"), False)
    cleaned = pc.if_else(valid, cleaned, pa.scalar(None, pa.string()))
    if order == "DDMMYYYY":
        iso = pc.binary_join_element_wise(
            pc.utf8_slice_codeunits(cleaned, 4, 8),
            pc.utf8_slice_codeunits(cleaned, 2, 4),
            pc.utf8_slice_codeunits(cleaned, 0, 2),
            "-",
        )
    else:
        iso = pc.binary_join_element_wise(
            pc.utf8_slice_codeunits(cleaned, 0, 4),
            pc.utf8_slice_codeunits(cleaned, 4, 6),
            pc.utf8_slice_codeunits(cleaned, 6, 8),
            "-",
        )
    try:
        return pc.cast(iso, pa.date32())
    except pa.ArrowInvalid:
        # Impossible calendar dates (e.g. 20150230) exist in the raw data. Parse
        # element-wise so one bad row does not null a whole column.
        out: list[date | None] = []
        for value in iso.to_pylist():
            if not value:
                out.append(None)
                continue
            try:
                y, m, d = value.split("-")
                out.append(date(int(y), int(m), int(d)))
            except (ValueError, TypeError):
                out.append(None)
        return pa.array(out, type=pa.date32())


_EPOCH = date(1970, 1, 1)
#: The days an epidemiological week is computed for: 1900-01-01 .. 2100-12-31 as day numbers. A date outside is a
#: parsed value no health record carries (the open-ended sentinel 99991231, 00010101), not a week of any calendar year
#: a surveillance system counts: its week is null and the raw text stays in `_raw`. Before, such a value raised
#: (`year 10000 is out of range`) and one value killed the whole fetch or partition build.
_EPI_MIN_DAY = (date(1900, 1, 1) - _EPOCH).days
_EPI_MAX_DAY = (date(2100, 12, 31) - _EPOCH).days

#: day number -> (epi_year, epi_week), filled on demand; at most the 73,000 days of 1900..2100, so it stays small.
_EPI_DAYS: dict[int, tuple[int, int]] = {}


def epi_week_array(dates: pa.Array) -> tuple[pa.Array, pa.Array]:
    """``(epi_year, epi_week)`` for a date32 column; null for a null or out-of-range (1900..2100) date.

    Only use this where the source publishes no official week. Where it does —
    ``SEM_PRI``, ``SEM_NOT`` — carry the source's value through untouched.

    A lookup, not a loop. The epi week of a date depends only on the date, and
    DATASUS spans a few tens of thousands of distinct days against tens of
    millions of rows — so the rule is evaluated once per DISTINCT day (and cached
    for the process) and the column is an Arrow take. The rule is
    :func:`epi_week` itself, so this vectorised path and the scalar one cannot drift.
    """
    n = len(dates)
    days = pc.cast(dates.cast(pa.date32()), pa.int32())
    in_range = pc.fill_null(
        pc.and_(pc.greater_equal(days, _EPI_MIN_DAY), pc.less_equal(days, _EPI_MAX_DAY)), False
    )
    distinct = pc.unique(pc.filter(days, in_range))
    if len(distinct) == 0:
        return pa.nulls(n, type=pa.int16()), pa.nulls(n, type=pa.int8())
    values = distinct.to_pylist()
    for day in values:
        if day not in _EPI_DAYS:
            week = epi_week(_EPOCH + timedelta(days=day))
            _EPI_DAYS[day] = (week.year, week.week)
    years = pa.array([_EPI_DAYS[d][0] for d in values], type=pa.int16())
    weeks = pa.array([_EPI_DAYS[d][1] for d in values], type=pa.int8())
    # a null or out-of-range day is not in `distinct`: its index is null, so its year and week are
    index = pc.index_in(days, value_set=distinct)
    return pc.take(years, index), pc.take(weeks, index)
