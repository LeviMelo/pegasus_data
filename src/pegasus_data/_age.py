"""Age, decoded into one number: years, fractional (ADR-0070).

DATASUS states an age as ONE quantity in ONE unit ("18 months", "5 hours", "78 years"). Each is decoded into
``IDADE_anos``: exact years, fractional. 18 months is 1.5, 12 days is 12 / 365.25. Completed years, if wanted, is
``floor(IDADE_anos)``; age bands use this same number.

How a system writes its age is declared once, on the derived variable that decodes it (``IDADE_anos`` in
``curation/variables/<system>``, an ``age:`` block), as one of five FORMS with its unit table as data. No system is
named here: the conventions are the declarations' (the 2026-11-08 principles audit, defect 4).

===============  ============================  ================================================================
form             fields                        what the declaration gives
===============  ============================  ================================================================
``unit_column``  the value, the unit           ``units``: unit code -> unit (SIH's COD_IDADE, SIVEP's TP_IDADE)
``packed``       one column                    ``units`` of the leading character, the rest the quantity;
                                               ``unknown`` codes; ``plain_below``: a shorter value has no unit
                                               digit and is plain years (SINAN's 1-3 character ages)
``years``        one column                    the value already is years (SINASC IDADEMAE)
``dates``        birth date, reference date    the years between them
``band``         one code column               ``lookup``: the lower edge, in years, of the band a code names
===============  ============================  ================================================================

A unit is ``minute``, ``hour``, ``day``, ``month`` or ``year``; ``hundred_plus`` is 100 + the value in years (SIH,
SIM and SINAN's unit 5); ``decade`` is 10 x the value, the first year of the decade (CIH and CIHA's unit 5: IDADE 10
is 100.0-109.9 years measured against NASC and the admission; a lower bound, never a guess inside the decade). The
unit tables were MEASURED against the records' own dates, not copied from layout documents (evaluation 2026-09-28:
SIM's structure document says 1 = minutes and 2 = hours, the data say 0 = minutes, 1 = hours, 2 = days). A negative
value is no age. An unparseable or absent age is a LEVEL, not a dropped row: unknown age is data, and the sentinel
code sorts after every band.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any

#: The code an undecodable age lands in. "Z" so it sorts after "000".."120".
UNKNOWN_CODE = "ZIG"
UNKNOWN_LABEL = "Idade ignorada"

#: Decade-ish bands with the epidemiologically load-bearing splits kept:
#: under-1 (infant), 1-4 (early childhood), then five-year steps to 80+.
DEFAULT_BANDS = (0, 1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80)

#: Years per unit. A month is 1/12 year exactly (an age in months is a count of calendar months); a day is 1/365.25.
_YEAR, _MONTH, _DAY, _HOUR, _MINUTE = 1.0, 1 / 12, 1 / 365.25, 1 / 8766.0, 1 / 525960.0
UNIT_YEARS = {"minute": _MINUTE, "hour": _HOUR, "day": _DAY, "month": _MONTH, "year": _YEAR}
#: units that are not a scale: 100 + the value, and 10 x the value
OFFSET_UNITS = ("hundred_plus", "decade")
FORMS = ("unit_column", "packed", "years", "dates", "band")
_FIELDS = {"unit_column": 2, "dates": 2, "packed": 1, "years": 1, "band": 1}


@dataclass(frozen=True, slots=True)
class AgeDimension:
    """An age: its form, its source columns and its unit table, and (as a dimension) its bands.

    ``of`` names the derived variable whose declaration gives the form (an aggregate's ``age_dimension: {of:
    IDADE_anos}``); `resolve_age` replaces it with that declaration before anything is decoded."""

    name: str
    form: str
    fields: tuple[str, ...]
    units: tuple[tuple[str, str], ...] = ()
    unknown: tuple[str, ...] = ()
    plain_below: int = 0
    bands: tuple[int, ...] = DEFAULT_BANDS
    label: str = "Faixa etária"
    #: ``band`` form: (code, lower edge in years) of each band the source file's own table names
    lookup: tuple[tuple[str, float], ...] = ()
    of: str = ""

    def band_levels(self) -> dict[str, str]:
        """``code -> label`` for every band plus the unknown level."""
        out: dict[str, str] = {}
        edges = list(self.bands)
        for i, lo in enumerate(edges):
            code = f"{lo:03d}"
            if i + 1 < len(edges):
                hi = edges[i + 1] - 1
                out[code] = "menos de 1 ano" if (lo == 0 and hi == 0) else f"{lo}–{hi}"
            else:
                out[code] = f"{lo}+"
        out[UNKNOWN_CODE] = UNKNOWN_LABEL
        return out


def parse_age(body: Any, fields: Any = None, *, name: str = "FAIXA_ETARIA") -> AgeDimension | None:
    """An ``age:`` declaration (a derived variable's, its ``from`` columns as ``fields``) or an aggregate's
    ``age_dimension:`` block, validated. An aggregate names the derived variable (``of``) or gives the form itself."""
    if not body:
        return None
    bands = tuple(int(b) for b in (body.get("bands") or DEFAULT_BANDS))
    if list(bands) != sorted(set(bands)) or (bands and bands[0] != 0):
        raise ValueError("bands must be strictly increasing and start at 0")
    label = str(body.get("label") or "Faixa etária")
    name = str(body.get("name") or name)
    if body.get("of"):
        return AgeDimension(name=name, form="", fields=(), bands=bands, label=label, of=str(body["of"]))
    form = str(body.get("form") or "")
    if form not in FORMS:
        raise ValueError(f"an age's form must be {'|'.join(FORMS)}, got {form!r}")
    columns = tuple(str(f) for f in (fields if fields is not None else body.get("fields") or ()))
    if len(columns) != _FIELDS[form]:
        raise ValueError(f"a {form} age reads {_FIELDS[form]} column(s), got {list(columns)}")
    units = tuple((str(k), str(v)) for k, v in (body.get("units") or {}).items())
    bad = [v for _, v in units if v not in UNIT_YEARS and v not in OFFSET_UNITS]
    if bad:
        raise ValueError(f"age units are {sorted(UNIT_YEARS)} or {list(OFFSET_UNITS)}, got {bad}")
    if form in ("unit_column", "packed") and not units:
        raise ValueError(f"a {form} age needs its units: unit code -> unit")
    lookup = tuple((str(k), float(v)) for k, v in (body.get("lookup") or {}).items())
    if form == "band" and not lookup:
        raise ValueError("a band age needs its lookup: code -> the band's lower edge in years")
    return AgeDimension(name=name, form=form, fields=columns, units=units,
                        unknown=tuple(str(c) for c in (body.get("unknown") or ())),
                        plain_below=int(body.get("plain_below") or 0), bands=bands, label=label, lookup=lookup)


def resolve_age(age: AgeDimension, docs: Any) -> AgeDimension:
    """An aggregate's age that names a derived variable (``of``), as that variable declares it: its form, columns and
    units, the aggregate's bands and label kept. One declaration per system, read by every aggregate of it."""
    if not age.of:
        return age
    found = []
    for doc in docs.values():
        for recipe in getattr(doc, "derived", None) or []:
            if str(recipe.get("name") or "").upper() == age.of.upper() and recipe.get("age"):
                found.append(parse_age(recipe["age"], recipe.get("from") or ()))
    forms = {(a.form, a.fields, a.units, a.unknown, a.plain_below, a.lookup) for a in found if a is not None}
    if len(forms) != 1:
        raise ValueError(f"{age.of}: {len(forms)} age declarations among the dataset's variables (one is needed)")
    return replace(found[0], name=age.name, bands=age.bands, label=age.label)


def _digits_to_years(text: Any) -> Any:
    """A string column of digit runs -> float64 years, null where not digits."""
    import pyarrow as pa
    import pyarrow.compute as pc

    ok = pc.match_substring_regex(text, r"^\d+$")
    safe = pc.if_else(pc.fill_null(ok, False), text, None)
    return pc.cast(safe, pa.float64())


def _scaled(value: Any, unit: Any, units: tuple[tuple[str, str], ...]) -> Any:
    """value in the unit its code names, in years; null for a code the table does not hold."""
    import pyarrow as pa
    import pyarrow.compute as pc

    conditions, choices = [], []
    for code, name in units:
        conditions.append(pc.equal(unit, code))
        if name == "hundred_plus":
            choices.append(pc.add(value, 100.0))
        elif name == "decade":
            choices.append(pc.multiply(value, 10.0))
        else:
            choices.append(pc.multiply(value, UNIT_YEARS[name]))
    return pc.case_when(pc.make_struct(*conditions), *choices, pa.scalar(None, pa.float64()))


def _date_of(text: Any) -> Any:
    """A string column of dates in the forms DATASUS writes (ISO, YYYYMMDD, DDMMYYYY, DD/MM/YYYY) -> timestamp[s],
    null where none gives a date in 1880-2035. No eight-digit string is a date both ways inside that window (one
    reading puts the year outside it or the month above 12)."""
    import pyarrow as pa
    import pyarrow.compute as pc

    head = pc.utf8_slice_codeunits(text, 0, 10)
    out = pa.nulls(len(text), pa.timestamp("s"))
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%d%m%Y", "%d/%m/%Y"):
        d = pc.strptime(head, format=fmt, unit="s", error_is_null=True)
        year = pc.year(d)
        inside = pc.and_(pc.greater_equal(year, 1880), pc.less_equal(year, 2035))
        out = pc.coalesce(out, pc.if_else(pc.fill_null(inside, False), d, pa.scalar(None, pa.timestamp("s"))))
    return out


def years_column(age: AgeDimension, table: Any) -> Any:
    """Age in fractional years as float64, null where undecodable. Vectorised."""
    import pyarrow as pa
    import pyarrow.compute as pc

    if age.of:
        raise ValueError(f"{age.name}: resolve the age of {age.of!r} (`resolve_age`) before decoding it")
    names = set(table.schema.names)

    def text_of(name: str) -> Any:
        if name not in names:
            return pa.nulls(table.num_rows, pa.string())
        return pc.utf8_trim_whitespace(pc.cast(table.column(name), pa.string()))

    def number_of(name: str) -> Any:
        # a number typed as one (SRAG's NU_IDADE_N is a double) or its digits as text; a negative one is no age
        column = table.column(name) if name in names else None
        if column is not None and (pa.types.is_floating(column.type) or pa.types.is_integer(column.type)
                                   or pa.types.is_decimal(column.type)):
            value = pc.cast(column, pa.float64())
        else:
            value = _digits_to_years(text_of(name))
        return pc.if_else(pc.fill_null(pc.less(value, 0.0), False), pa.scalar(None, pa.float64()), value)

    if age.form == "years":
        return number_of(age.fields[0])
    if age.form == "band":
        # the lower edge of the band a code names; the exact code (a width is never padded or cut), null for any other
        edges = pa.array([v for _, v in age.lookup], pa.float64())
        return pc.take(edges, pc.index_in(text_of(age.fields[0]),
                                          value_set=pa.array([k for k, _ in age.lookup], pa.string())))
    if age.form == "dates":
        born, then = _date_of(text_of(age.fields[0])), _date_of(text_of(age.fields[1]))
        days = pc.divide(pc.cast(pc.cast(pc.subtract(then, born), pa.int64()), pa.float64()), 86400.0)
        years = pc.divide(days, 365.25)
        return pc.if_else(pc.fill_null(pc.less(years, 0.0), True), pa.scalar(None, pa.float64()), years)
    if age.form == "unit_column":
        return _scaled(number_of(age.fields[0]), text_of(age.fields[1]), age.units)
    packed = text_of(age.fields[0])
    scaled = _scaled(_digits_to_years(pc.utf8_slice_codeunits(packed, 1, 32)), pc.utf8_slice_codeunits(packed, 0, 1),
                     age.units)
    if age.unknown:
        # an unfilled field, not an age (SIM's "000": measured unit-0 quantities run 1-52; fetal deaths leave it empty)
        unknown = pc.is_in(packed, value_set=pa.array(list(age.unknown), pa.string()))
        scaled = pc.if_else(pc.fill_null(unknown, False), pa.scalar(None, pa.float64()), scaled)
    if age.plain_below:
        short = pc.less(pc.utf8_length(packed), age.plain_below)
        scaled = pc.if_else(pc.fill_null(short, False), _digits_to_years(packed), scaled)
    return scaled


def band_column(age: AgeDimension, years: Any) -> Any:
    """Years -> band code, ``ZIG`` where years is null. Vectorised."""
    import pyarrow as pa
    import pyarrow.compute as pc

    out = pa.nulls(len(years), pa.string())
    # Painted from the lowest band up: each band overwrites where years >= lo,
    # so the last band that applies wins — exactly the half-open interval.
    for lo in age.bands:
        out = pc.if_else(
            pc.fill_null(pc.greater_equal(years, float(lo)), False),
            f"{lo:03d}",
            out,
        )
    return pc.fill_null(out, UNKNOWN_CODE)


@dataclass(frozen=True, slots=True)
class NumericBandDimension:
    """A banded numeric dimension, declared in the spec.

    The same shape as the age dimension minus the unit decoding: the field is
    already a plain number (grams, weeks, counts) and only needs parsing and
    banding. Declared per artifact because the bands are an analytical claim
    -- birth weight's 1500/2500/4000 splits are WHO's, not the data's.
    """

    name: str
    field_name: str
    bands: tuple[int, ...]
    label: str
    unit: str = ""

    def _width(self) -> int:
        return max(3, len(str(self.bands[-1])))

    def band_levels(self) -> dict[str, str]:
        def fmt(value: int) -> str:
            return f"{value:,}".replace(",", ".")

        out: dict[str, str] = {}
        edges = list(self.bands)
        suffix = f" {self.unit}" if self.unit else ""
        for i, lo in enumerate(edges):
            code = f"{lo:0{self._width()}d}"
            if i + 1 < len(edges):
                hi = edges[i + 1] - 1
                out[code] = (
                    f"menos de {fmt(edges[i + 1])}{suffix}" if lo == 0
                    else f"{fmt(lo)}–{fmt(hi)}{suffix}"
                )
            else:
                out[code] = f"{fmt(lo)}+{suffix}"
        out[UNKNOWN_CODE] = "Ignorado"
        return out

    def column(self, table: Any) -> Any:
        """The band code column for this table. Vectorised, unknowns kept."""
        import pyarrow as pa
        import pyarrow.compute as pc

        if self.field_name not in set(table.schema.names):
            numeric = pa.nulls(table.num_rows, pa.float64())
        else:
            text = pc.utf8_trim_whitespace(
                pc.cast(table.column(self.field_name), pa.string()))
            numeric = _digits_to_years(text)
        out = pa.nulls(len(numeric), pa.string())
        for lo in self.bands:
            out = pc.if_else(
                pc.fill_null(pc.greater_equal(numeric, float(lo)), False),
                f"{lo:0{self._width()}d}",
                out,
            )
        return pc.fill_null(out, UNKNOWN_CODE)


def parse_band_dimensions(body: Any) -> tuple[NumericBandDimension, ...]:
    """The spec's ``band_dimensions:`` block, validated."""
    out: list[NumericBandDimension] = []
    for name, spec in (body or {}).items():
        spec = spec or {}
        bands = tuple(int(b) for b in (spec.get("bands") or ()))
        if not bands or list(bands) != sorted(set(bands)) or bands[0] != 0:
            raise ValueError(
                f"band_dimensions.{name}: bands must be strictly increasing "
                "and start at 0"
            )
        out.append(NumericBandDimension(
            name=str(name),
            field_name=str(spec.get("field") or name),
            bands=bands,
            label=str(spec.get("label") or name),
            unit=str(spec.get("unit") or ""),
        ))
    return tuple(out)
