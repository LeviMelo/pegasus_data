"""Age, decoded per system into one number: years, fractional (ADR-0070).

DATASUS states an age as ONE quantity in ONE unit ("18 months", "5 hours",
"78 years"), encoded three different ways. Each is decoded into
``IDADE_anos``: exact years, fractional. 18 months is 1.5, 12 days is
12 / 365.25. Completed years, if wanted, is ``floor(IDADE_anos)``; age bands
use this same number.

The unit tables are MEASURED, not copied from layout documents. On
2026-09-28, each unit digit was checked against the record's own dates:
birth to death in SIM, birth to admission in SIH, and birth year to symptom
onset in SINAN (evaluation 2026-09-28, "age units measured against dates").
SIM's own structure document (``sources/sim2025.txt``) says 1 = minutes and
2 = hours. The data says 0 = minutes, 1 = hours and 2 = days: unit-2
quantities of 0–28 run at exactly 1.0 day per unit.

========  ==================  ============================================
encoding  fields              units
========  ==================  ============================================
sih       IDADE + COD_IDADE   COD_IDADE 2 days, 3 months, 4 years,
                              5 = 100 + years; 0 ignored
sim       IDADE (3 chars)     leading digit 0 minutes, 1 hours, 2 days,
                              3 months, 4 years, 5 = 100 + years; 999 and
                              000 ignored
sinan     NU_IDADE_N          4 chars: leading digit 1 hours, 2 days,
                              3 months, 4 years. 1–3 chars: plain years
                              (0.8% of SINAN-DENG 2022, confirmed by the
                              birth year)
years     any                 the value already is years (SINASC IDADEMAE)
========  ==================  ============================================

An unparseable or absent age is a LEVEL, not a dropped row: unknown age is
data, and a pyramid that silently sheds its unknowns claims a completeness
the source does not have. The sentinel code sorts after every band.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#: The code an undecodable age lands in. "Z" so it sorts after "000".."120".
UNKNOWN_CODE = "ZIG"
UNKNOWN_LABEL = "Idade ignorada"

#: Decade-ish bands with the epidemiologically load-bearing splits kept:
#: under-1 (infant), 1-4 (early childhood), then five-year steps to 80+.
DEFAULT_BANDS = (0, 1, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80)


@dataclass(frozen=True, slots=True)
class AgeDimension:
    """A derived age-band dimension, declared in the spec.

    ``encoding`` names the decode convention; ``fields`` the source columns
    (two for SIH's separate unit column, one for the packed encodings).
    """

    name: str
    encoding: str  # "sih" | "sim" | "sinan"
    fields: tuple[str, ...]
    bands: tuple[int, ...] = DEFAULT_BANDS
    label: str = "Faixa etária"

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


def parse_age_dimension(body: Any) -> AgeDimension | None:
    """The spec's ``age_dimension:`` block, validated."""
    if not body:
        return None
    encoding = str(body.get("encoding") or "")
    if encoding not in ("sih", "sim", "sinan", "years"):
        raise ValueError(
            f"age_dimension.encoding must be sih|sim|sinan|years, got {encoding!r}"
        )
    fields = tuple(str(f) for f in (body.get("fields") or ()))
    if encoding == "sih" and len(fields) != 2:
        raise ValueError("sih age needs [value_field, unit_field]")
    if encoding in ("sim", "sinan", "years") and len(fields) != 1:
        raise ValueError(f"{encoding} age needs exactly one field")
    bands = tuple(int(b) for b in (body.get("bands") or DEFAULT_BANDS))
    if list(bands) != sorted(set(bands)) or (bands and bands[0] != 0):
        raise ValueError("bands must be strictly increasing and start at 0")
    return AgeDimension(
        name=str(body.get("name") or "FAIXA_ETARIA"),
        encoding=encoding,
        fields=fields,
        bands=bands,
        label=str(body.get("label") or "Faixa etária"),
    )


def _digits_to_years(text: Any) -> Any:
    """A string column of digit runs -> float64 years, null where not digits."""
    import pyarrow as pa
    import pyarrow.compute as pc

    ok = pc.match_substring_regex(text, r"^\d+$")
    safe = pc.if_else(pc.fill_null(ok, False), text, None)
    return pc.cast(safe, pa.float64())


#: Years per unit. A month is 1/12 year exactly (an age in months is a count
#: of calendar months); a day is 1/365.25.
_YEAR, _MONTH, _DAY, _HOUR, _MINUTE = 1.0, 1 / 12, 1 / 365.25, 1 / 8766.0, 1 / 525960.0

#: ``encoding -> {unit code -> years per unit}``. "100+" is handled apart.
UNITS: dict[str, dict[str, float]] = {
    "sih": {"2": _DAY, "3": _MONTH, "4": _YEAR},
    "sim": {"0": _MINUTE, "1": _HOUR, "2": _DAY, "3": _MONTH, "4": _YEAR},
    "sinan": {"1": _HOUR, "2": _DAY, "3": _MONTH, "4": _YEAR},
}


def _scaled(value: Any, unit: Any, table: dict[str, float]) -> Any:
    """value x years-per-unit, 100 + value for unit 5, null for anything else."""
    import pyarrow as pa
    import pyarrow.compute as pc

    conditions, choices = [], []
    for code, per in table.items():
        conditions.append(pc.equal(unit, code))
        choices.append(pc.multiply(value, per))
    conditions.append(pc.equal(unit, "5"))
    choices.append(pc.add(value, 100.0))
    return pc.case_when(pc.make_struct(*conditions), *choices, pa.scalar(None, pa.float64()))


def years_column(age: AgeDimension, table: Any) -> Any:
    """Age in fractional years as float64, null where undecodable. Vectorised."""
    import pyarrow as pa
    import pyarrow.compute as pc

    names = set(table.schema.names)

    def text_of(name: str) -> Any:
        if name not in names:
            return pa.nulls(table.num_rows, pa.string())
        return pc.utf8_trim_whitespace(pc.cast(table.column(name), pa.string()))

    if age.encoding == "years":
        return _digits_to_years(text_of(age.fields[0]))
    if age.encoding == "sih":
        return _scaled(_digits_to_years(text_of(age.fields[0])), text_of(age.fields[1]), UNITS["sih"])

    packed = text_of(age.fields[0])
    unit = pc.utf8_slice_codeunits(packed, 0, 1)
    rest = _digits_to_years(pc.utf8_slice_codeunits(packed, 1, 32))
    scaled = _scaled(rest, unit, UNITS[age.encoding])
    if age.encoding == "sim":
        # "000" is an unfilled field, not zero minutes: measured unit-0
        # quantities run 1-52, and fetal deaths leave IDADE empty.
        return pc.if_else(pc.fill_null(pc.equal(packed, "000"), False), pa.scalar(None, pa.float64()), scaled)
    if age.encoding == "sinan":
        # Fewer than four characters carries no unit digit: plain years.
        short = pc.less(pc.utf8_length(packed), 4)
        return pc.if_else(pc.fill_null(short, False), _digits_to_years(packed), scaled)
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
