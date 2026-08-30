"""Age, decoded per system and banded per spec.

DATASUS does not use one age encoding any more than it uses one date format
(`_date_layout`). Three conventions are live in the built systems, each
documented in curation:

========  ==================  ==========================================
system    fields              convention
========  ==================  ==========================================
SIH       IDADE + COD_IDADE   unit in its OWN column: 2=days, 3=months,
                              4=years, 5=100+years
SIM       IDADE               unit packed into the LEADING digit of a
                              3-char value: 4xx = xx years, 5xx = 100+xx
SINAN     NU_IDADE_N          the same packing, 4 chars: 4yyy = yyy years
========  ==================  ==========================================

The decode leans on one provable fact rather than a table of every unit
code: **every unit below "years" is a sub-year unit** (minutes, hours, days,
months — their exact assignment varies by system and vintage, and does not
matter here), so any such value lands in the first band as "under one year"
without knowing which sub-year unit it was. Only the "years" and "100+"
units need reading precisely, and those are stable across every layout
document ingested.

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
    if encoding not in ("sih", "sim", "sinan"):
        raise ValueError(
            f"age_dimension.encoding must be sih|sim|sinan, got {encoding!r}"
        )
    fields = tuple(str(f) for f in (body.get("fields") or ()))
    if encoding == "sih" and len(fields) != 2:
        raise ValueError("sih age needs [value_field, unit_field]")
    if encoding in ("sim", "sinan") and len(fields) != 1:
        raise ValueError(f"{encoding} age needs exactly one packed field")
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


def years_column(age: AgeDimension, table: Any) -> Any:
    """Age in years as float64, null where undecodable. Vectorised."""
    import pyarrow as pa
    import pyarrow.compute as pc

    names = set(table.schema.names)

    def text_of(name: str) -> Any:
        if name not in names:
            return pa.nulls(table.num_rows, pa.string())
        return pc.utf8_trim_whitespace(pc.cast(table.column(name), pa.string()))

    if age.encoding == "sih":
        value = _digits_to_years(text_of(age.fields[0]))
        unit = text_of(age.fields[1])
        return pc.case_when(
            pc.make_struct(
                pc.equal(unit, "4"),
                pc.equal(unit, "5"),
                pc.is_in(unit, value_set=pa.array(["2", "3"])),
            ),
            value,
            pc.add(value, 100.0),
            pa.scalar(0.0, pa.float64()),
            pa.scalar(None, pa.float64()),
        )

    # Packed: leading digit is the unit, the rest is the quantity.
    packed = text_of(age.fields[0])
    unit = pc.utf8_slice_codeunits(packed, 0, 1)
    rest = _digits_to_years(pc.utf8_slice_codeunits(packed, 1, 32))
    return pc.case_when(
        pc.make_struct(
            pc.equal(unit, "4"),
            pc.equal(unit, "5"),
            pc.is_in(unit, value_set=pa.array(["1", "2", "3"])),
        ),
        rest,
        pc.add(rest, 100.0),
        pa.scalar(0.0, pa.float64()),
        pa.scalar(None, pa.float64()),
    )


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
