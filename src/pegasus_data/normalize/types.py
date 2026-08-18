"""Type canonicalisation from the container's own declarations.

DBF declares a type letter, a width and a decimal count for every column, and
that declaration is real signal — it is what tells a ``N`` column with 2 decimals
apart from a ``N`` column with none, and therefore money apart from a count.

Nothing here applies a sentinel rule. Sentinel nulling is per field and driven by
the ledger (§13); this module only turns text into the type the container says it
is, and leaves a value it cannot parse as null with the raw column retained
alongside.
"""

from __future__ import annotations

import pyarrow as pa
import pyarrow.compute as pc

#: dBase type letters → the Arrow type they canonically become.
DBF_TYPE_MAP: dict[str, str] = {
    "C": "string",
    "N": "numeric",   # width/decimals decide integer vs decimal
    "F": "numeric",
    "D": "date",
    "L": "boolean",
    "M": "string",    # memo
    "I": "int32",
    "B": "double",
    "Y": "decimal",
    "T": "timestamp",
    "@": "timestamp",
    "+": "int32",
}


def arrow_type_for(physical_type: str | None, width: int | None, decimals: int | None) -> pa.DataType:
    """The Arrow type a declared DBF field should become."""
    kind = DBF_TYPE_MAP.get((physical_type or "").upper(), "string")
    if kind == "numeric":
        if decimals and decimals > 0:
            precision = min(38, max((width or 18), decimals + 1))
            return pa.decimal128(precision, min(decimals, precision - 1))
        if width and width <= 9:
            return pa.int32()
        if width and width <= 18:
            return pa.int64()
        return pa.float64()
    return {
        "string": pa.string(),
        "date": pa.date32(),
        "boolean": pa.bool_(),
        "int32": pa.int32(),
        "double": pa.float64(),
        "decimal": pa.decimal128(19, 4),
        "timestamp": pa.timestamp("s"),
    }[kind]


def cast_numeric(array: pa.Array, target: pa.DataType, *, decimals: int | None = None) -> pa.Array:
    """Parse a numeric text column, tolerating DATASUS's implied decimal point.

    Old SIH files store money as an integer string with the decimal point implied
    by the DBF's declared decimal count, e.g. ``123456`` with 2 decimals meaning
    1234.56. The declared count is therefore applied rather than assumed away.
    """
    if array.type != pa.string():
        array = array.cast(pa.string())
    text = pc.utf8_trim_whitespace(array)
    text = pc.replace_substring_regex(text, r"^([+-]?\d+),(\d+)$", r"\1.\2")
    numeric_like = pc.fill_null(pc.match_substring_regex(text, r"^[+-]?\d+(\.\d+)?$"), False)
    text = pc.if_else(numeric_like, text, pa.scalar(None, pa.string()))
    has_point = pc.fill_null(pc.match_substring_regex(text, r"\."), False)
    try:
        values = pc.cast(text, pa.float64())
    except pa.ArrowInvalid:
        return pa.nulls(len(array), type=target)
    if decimals and decimals > 0:
        scaled = pc.divide(values, float(10**decimals))
        values = pc.if_else(has_point, values, scaled)
    if pa.types.is_decimal(target):
        return pc.cast(values, target, safe=False)
    if pa.types.is_integer(target):
        return pc.cast(pc.round(values), target, safe=False)
    return pc.cast(values, target, safe=False)


def cast_boolean(array: pa.Array) -> pa.Array:
    """dBase logical: ``T``/``Y``/``1`` true, ``F``/``N``/``0`` false, else null."""
    if array.type != pa.string():
        array = array.cast(pa.string())
    upper = pc.utf8_upper(pc.utf8_trim_whitespace(array))
    true_set = pa.array(["T", "Y", "1", "TRUE", "S"], type=pa.string())
    false_set = pa.array(["F", "N", "0", "FALSE"], type=pa.string())
    is_true = pc.fill_null(pc.is_in(upper, value_set=true_set), False)
    is_false = pc.fill_null(pc.is_in(upper, value_set=false_set), False)
    return pc.if_else(is_true, True, pc.if_else(is_false, False, pa.scalar(None, pa.bool_())))
