"""Time canonicalisation: competência, epidemiological week, epidemiological year.

This is the one place a period is read or computed. A **competência** is ``AAAAMM`` (an ``int`` or its text); a
month label is ``AAAA-MM`` (the wire and cube spelling); a year-only file is ``AAAA00`` in the catalog. The scalar
helpers (:func:`compose`, :func:`year_of`, :func:`month_of`, :func:`add_months`, :func:`months_between`,
:func:`month_range`, :func:`month_label`, :func:`parse_month`) and the column readers (:func:`date_layout`,
:func:`date_column`, :func:`competencia_column`, :func:`competencia_from_parts`) all judge a month the same way: a
month outside 1..12 is **null**, never wrapped into the next year and never kept as a period of its own. The
one twin is ``intake._records_sql``, which states the same rules in DuckDB SQL at landing (it cannot share code with
Python, and changing it would change landed units' fingerprints).

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

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pyarrow as pa
import pyarrow.compute as pc

__all__ = [
    "epi_week",
    "epi_year_weeks",
    "competencia_to_year_month",
    "COMPETENCIA_RE",
    "compose",
    "year_of",
    "month_of",
    "years_of",
    "add_months",
    "months_between",
    "month_range",
    "year_bounds",
    "month_label",
    "parse_month",
    "date_layout",
    "date_column",
    "competencia_column",
    "year_column",
    "competencia_from_parts",
    "parse_date_array",
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


#: AAAAMM: a year 1900-2200 and a month 01-12 (:func:`competencia_to_year_month`'s own bounds), as a regex for columns.
COMPETENCIA_RE = r"^(19\d\d|20\d\d|21\d\d|2200)(0[1-9]|1[0-2])$"


def compose(year: int | str | None, month: int | str | None) -> int | None:
    """``AAAAMM`` as an int from a year and a month; None when either is missing or the month is not 1..12."""
    try:
        y, m = int(year), int(month)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return y * 100 + m if 1 <= m <= 12 else None


def year_of(value: int | str | None) -> int | None:
    """The year of a period: the first four digits of a competência, month label, date or year (``202203``,
    ``2022-03``, ``2022``, ``202200``). None when it does not start with four digits."""
    text = str(value).strip() if value is not None else ""
    return int(text[:4]) if len(text) >= 4 and text[:4].isdigit() else None


def month_of(value: int | str | None) -> int | None:
    """The month (1..12) of an ``AAAAMM`` int or text or an ``AAAA-MM`` label; None for a year-only value (month 00)
    and for any month outside 1..12 (it is not January, and it is not a month of its own)."""
    text = str(value).strip() if value is not None else ""
    if len(text) == 7 and text[4] == "-":
        text = text[:4] + text[5:]
    if len(text) < 6 or not text[:6].isdigit():
        return None
    month = int(text[4:6])
    return month if 1 <= month <= 12 else None


def years_of(periods: Iterable[int | str]) -> list[int]:
    """The year of each of ``periods`` in order; a period that does not start with a year raises ``ValueError``."""
    out = []
    for period in periods:
        year = year_of(period)
        if year is None:
            raise ValueError(f"period {period!r} does not start with a year")
        out.append(year)
    return out


def _index(competencia: int | str) -> int:
    year, month = year_of(competencia), month_of(competencia)
    if year is None or month is None:
        raise ValueError(f"{competencia!r} is not a month (AAAAMM)")
    return year * 12 + month - 1


def add_months(competencia: int | str, months: int) -> int:
    """The competência ``months`` after (negative: before) ``competencia``: ``add_months(202401, -1) == 202312``."""
    year, month = divmod(_index(competencia) + int(months), 12)
    return year * 100 + month + 1


def months_between(first: int | str, last: int | str) -> int:
    """Whole months from ``first`` to ``last`` (negative when ``last`` is earlier)."""
    return _index(last) - _index(first)


def month_range(first: int | str, last: int | str) -> list[int]:
    """Every competência from ``first`` to ``last`` inclusive; empty when ``last`` is before ``first``."""
    return [add_months(first, i) for i in range(months_between(first, last) + 1)]


def year_bounds(year: int | str) -> tuple[int, int]:
    """``(AAAA01, AAAA12)``: the competências a year spans."""
    return int(year) * 100 + 1, int(year) * 100 + 12


def month_label(competencia: int | str) -> str:
    """``202203`` -> ``2022-03``; a text that is not six digits is returned as it is (``2022`` stays ``2022``)."""
    text = str(competencia)
    return f"{text[:4]}-{text[4:6]}" if len(text) == 6 and text.isdigit() else text


def parse_month(text: int | str) -> int | None:
    """``AAAAMM`` int from ``AAAAMM`` or ``AAAA-MM`` text; None for anything else, a month outside 1..12 included."""
    value = str(text).strip()
    if len(value) == 7 and value[4] == "-":
        value = value[:4] + value[5:]
    if len(value) != 6 or not value.isdigit():
        return None
    return compose(value[:4], value[4:])


#: How many values to look at when deciding a date column's layout. The two
#: hypotheses separate on the first handful of real rows; this is generous.
_LAYOUT_SAMPLE = 4_000
#: The winner must explain at least this share of the values it was shown.
_LAYOUT_CONFIDENCE = 0.9


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


def date_layout(values: Sequence[Any]) -> str | None:
    """``"ymd"``, ``"dmy"``, ``"ym"`` (a year-first month with no day) or None, decided by measurement.

    DATASUS does not use one date format. Measured on live 2022 files:

    ==========  ==========  ==========  ==================
    dataset     column      example     layout
    ==========  ==========  ==========  ==================
    SIH-RD      DT_INTER    20211227    AAAAMMDD (ymd)
    SIM-DO      DTOBITO     07052022    DDMMAAAA (dmy)
    SINASC-DN   DTNASC      16041976    DDMMAAAA (dmy)
    ==========  ==========  ==========  ==================

    Nineteen (system, field) pairs declare a `date` encoding, so a table of
    declared formats is nineteen things to maintain and to get wrong. The two
    layouts are separable by inspection instead: `20211227` cannot be day-first
    because `12` is a plausible month but `1227` is not a year, and `07052022`
    cannot be year-first because `0705` is not a year.

    The two readings are in fact DISJOINT for any real date: if `text[4:8]` is a
    plausible year (19xx/20xx) then `text[4:6]` is 19 or 20, which is not a
    month, so year-first cannot also hold. There is no genuinely ambiguous
    eight-digit date after 1900 -- which is why a sample of a few rows settles
    it and why the confidence threshold is a guard against junk rather than a
    tie-break.

    Returns None when neither hypothesis dominates. That is deliberate -- a
    column this cannot read is refused upstream rather than bucketed under a
    period that means nothing, which is how `0101` through `3112` became months.
    """
    ymd = dmy = ym = seen = 0
    for value in values:
        text = str(value or "").strip()
        if len(text) == 6 and text.isdigit():
            # a month written year-first with no day (ANS's ID_CMPT_MOVEL, 2024-12 once its dash is read away)
            seen += 1
            ym += 1900 <= int(text[0:4]) <= 2100 and 1 <= int(text[4:6]) <= 12
            continue
        if len(text) != 8 or not text.isdigit():
            continue
        seen += 1
        # year-first: YYYYMMDD
        if 1900 <= int(text[0:4]) <= 2100 and 1 <= int(text[4:6]) <= 12:
            ymd += 1
        # day-first: DDMMYYYY
        if 1900 <= int(text[4:8]) <= 2100 and 1 <= int(text[2:4]) <= 12:
            dmy += 1
    if not seen:
        return None
    if ym >= _LAYOUT_CONFIDENCE * seen:
        return "ym"
    if ymd >= _LAYOUT_CONFIDENCE * seen and ymd > dmy:
        return "ymd"
    if dmy >= _LAYOUT_CONFIDENCE * seen and dmy > ymd:
        return "dmy"
    return None


def _digits_year_first(array: Any) -> tuple[Any, str | None]:
    """A column as trimmed text with an ISO dash read away (2024-12-31 is its digits year-first), and its measured layout."""
    joined = pc.utf8_trim_whitespace(pc.cast(array, pa.string()))
    joined = pc.replace_substring(joined, "-", "")
    return joined, date_layout(joined.slice(0, min(_LAYOUT_SAMPLE, len(joined))).to_pylist())


def date_column(array: Any) -> Any | None:
    """A column of record dates in any measured layout (``AAAAMMDD``, ``DDMMAAAA``, ISO ``AAAA-MM-DD``) as ``date32``;
    an already typed date passes through. None when the layout is not a day layout (unreadable, or a month with no day).
    An impossible calendar date is null (:func:`parse_date_array`)."""
    if pa.types.is_date(array.type) or pa.types.is_timestamp(array.type):
        return array.cast(pa.date32())
    text, layout = _digits_year_first(array)
    if layout not in ("ymd", "dmy"):
        return None
    return parse_date_array(text, order="DDMMYYYY" if layout == "dmy" else "YYYYMMDD")


def _valid_competencia(text: Any) -> Any:
    """The first six characters of ``text`` where they are a month of a plausible year, else null: the length alone
    let `00000000` and `20229999` become periods 000000 and 202299 (month 99), each a cell of its own."""
    sliced = pc.utf8_slice_codeunits(text, 0, 6)
    valid = pc.fill_null(pc.match_substring_regex(sliced, COMPETENCIA_RE), False)
    return pc.if_else(valid, sliced, pa.nulls(len(sliced), pa.string()))


def competencia_from_parts(year: Any, month: Any) -> Any:
    """``AAAAMM`` text from a year column and a month column held apart (``ANO_CMPT``, ``MES_CMPT``); a month outside
    1..12 or a year outside 1900..2200 is null."""
    y = pc.utf8_trim_whitespace(pc.cast(year, pa.string()))
    m = pc.utf8_lpad(pc.utf8_trim_whitespace(pc.cast(month, pa.string())), 2, padding="0")
    return _valid_competencia(pc.binary_join_element_wise(y, m, ""))


def year_column(table: Any, time_fields: Sequence[str], encoding: str = "", century: str = "") -> Any | None:
    """The year (``AAAA`` text) each record's period holds even where its month does not: a year held apart, a year
    binding, or a date whose day and month are unknown or absent (``00001994``, ``2000``, ``022000``, the two-digit
    ``95``); null where no year 1900-2199 is readable. The year of a full date is :func:`competencia_column`'s; this is
    for the records it cannot place in a month."""
    present = [f for f in time_fields if f in table.schema.names]
    if not present:
        return None
    column = table.column(present[0])
    if pa.types.is_date(column.type) or pa.types.is_timestamp(column.type):
        return pc.strftime(column, format="%Y")
    text = pc.replace_substring(pc.utf8_trim_whitespace(pc.cast(column, pa.string())), "-", "")
    if century:
        year = pc.binary_join_element_wise(pa.scalar(century), pc.utf8_slice_codeunits(text, 0, 2), "")
    elif len(present) >= 2 or encoding in ("year", "year_month"):
        year = pc.utf8_slice_codeunits(text, 0, 4)
    else:
        layout = date_layout(text.slice(0, min(_LAYOUT_SAMPLE, len(text))).to_pylist())
        length = pc.utf8_length(text)
        # day-first: the year is the last four digits of DDMMAAAA, MMAAAA or AAAA; year-first, the first four
        year = (pc.utf8_slice_codeunits(text, -4, None) if layout == "dmy" else pc.utf8_slice_codeunits(text, 0, 4))
        year = pc.if_else(pc.fill_null(pc.equal(length, 4), False), text, year)
    valid = pc.fill_null(pc.match_substring_regex(year, r"^(19|20|21)\d\d$"), False)
    return pc.if_else(valid, year, pa.nulls(len(year), pa.string()))


def competencia_column(table: Any, time_fields: Sequence[str], encoding: str = "", century: str = "") -> Any | None:
    """AAAAMM text from the declared time fields, as a column; None when no field is present or a date column's layout
    cannot be measured.

    Two fields means year and month held apart (`ANO_CMPT`, `MES_CMPT`). One
    field is either a competence already packed year-first -- of which the first
    six characters ARE the period -- or a record date, whose layout is measured
    rather than assumed (:func:`date_layout`).
    """
    present = [f for f in time_fields if f in table.schema.names]
    if not present:
        return None
    if len(present) >= 2:
        return competencia_from_parts(table.column(present[0]), table.column(present[1]))
    column = table.column(present[0])
    if encoding == "date" and (pa.types.is_date(column.type) or pa.types.is_timestamp(column.type)):
        # a column already typed as a date (SINAN's, from its DBF header) has no layout to guess
        return pc.strftime(column, format="%Y%m")
    if encoding != "date":
        return _valid_competencia(pc.utf8_trim_whitespace(pc.cast(column, pa.string())))
    if century:
        # a date of a two-digit year (AAMMDD; SIM's ICD-9-era layout writes 950914), its century declared by the binding
        text = pc.utf8_trim_whitespace(pc.cast(column, pa.string()))
        return _valid_competencia(pc.binary_join_element_wise(pa.scalar(century), pc.utf8_slice_codeunits(text, 0, 4), ""))
    joined, layout = _digits_year_first(column)
    if layout is None:
        return None
    if layout == "dmy":
        # DDMMAAAA -> AAAAMM. Built by concatenation rather than by a regex so it stays inside Arrow at national volume.
        # A date filed without its day is MMAAAA in the same order (SIM-DO 2000: one death, 022000) -> AAAAMM too.
        no_day = pc.equal(pc.utf8_length(joined), 6)
        joined = pc.if_else(
            pc.fill_null(no_day, False),
            pc.binary_join_element_wise(pc.utf8_slice_codeunits(joined, 2, 6), pc.utf8_slice_codeunits(joined, 0, 2), ""),
            pc.binary_join_element_wise(pc.utf8_slice_codeunits(joined, 4, 8), pc.utf8_slice_codeunits(joined, 2, 4), ""))
    return _valid_competencia(joined)
