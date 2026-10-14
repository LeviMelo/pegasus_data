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

import logging

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


#: ``(field, decimals)`` already reported by :func:`cast_numeric`: one warning per column and process, not per batch.
_POINTLESS_REPORTED: set[tuple[str, int]] = set()


def cast_numeric(
    array: pa.Array, target: pa.DataType, *, decimals: int | None = None, field: str = ""
) -> pa.Array:
    """Parse a numeric text column at face value; a value that does not parse is null (``_raw`` keeps the text).

    The value is what the text says. A dBase numeric declared with ``decimals > 0`` writes its decimal point in every
    value: 278,906 values in 40 such columns of SIH, SIASUS, SINAN and PNI files (14 blobs, measured 2026-10-14) carry
    it, none lacks it. Dividing a point-less value by ``10**decimals`` (the previous rule, "implied decimals") decided
    per cell and so mixed a column that held both spellings by 100; a point-less value in such a column is not known to
    be scaled, and a scale a source needs belongs in the ledger for that field. It is kept as written, and counted:
    ``decimals`` and ``field`` serve only to report it once per column.
    """
    if array.type != pa.string():
        array = array.cast(pa.string())
    text = pc.utf8_trim_whitespace(array)
    text = pc.replace_substring_regex(text, r"^([+-]?\d+),(\d+)$", r"\1.\2")
    numeric_like = pc.fill_null(pc.match_substring_regex(text, r"^[+-]?\d+(\.\d+)?$"), False)
    text = pc.if_else(numeric_like, text, pa.scalar(None, pa.string()))
    try:
        values = pc.cast(text, pa.float64())
    except pa.ArrowInvalid:
        return pa.nulls(len(array), type=target)
    if decimals and decimals > 0 and (field, decimals) not in _POINTLESS_REPORTED:
        has_point = pc.fill_null(pc.match_substring(text, "."), False)
        pointless = pc.sum(pc.and_(numeric_like, pc.invert(has_point)).cast(pa.int64())).as_py() or 0
        if pointless:
            _POINTLESS_REPORTED.add((field, decimals))
            logging.getLogger(__name__).warning(
                "%s is declared with %d decimals but %d value(s) in a batch have no decimal point; they are read at "
                "face value, not rescaled", field or "a numeric column", decimals, pointless,
            )
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
