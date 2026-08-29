"""Shape an aggregate result for the wire.

Three things happen here and nowhere else, because they are presentation
decisions that the algebra must not carry:

1. **The geography column is renamed to ``geo`` whatever the grain.** A client
   that has to know the column is called ``municipality`` at one grain and
   ``health_region`` at another ends up with a branch per grain in every view.
   ``keys.geo`` names the grain instead.

2. **Municipality codes become 7-digit IBGE codes.** DATASUS writes six; every
   IBGE product, including the polygon meshes, keys on seven, and the seventh is
   a check digit that no client can compute. The contract's rule -- the backend
   normalises, the frontend never does -- is right, and this is where it happens.

3. **Codes and labels travel separately.** ``data`` carries codes; ``codelists``
   carries ``code -> label``. Repeating a label on every one of 130,000 rows
   would be most of the payload, and it would also let two rows disagree about
   what one code means.

What does NOT happen here: no rate, no mean, no percentage. The payload carries
accumulator state and the descriptor carries the formula, so the client finalises
after it has finished aggregating. That is not a transport nicety -- finalising
early and re-aggregating the result is exactly how a mean of means happens.
"""

from __future__ import annotations

from typing import Any

import pyarrow as pa

from .._aggregate import _BASE_LEVEL, _NATIONAL_LEVEL, _UF_LEVEL

#: The wire names for the two structural axes. Fixed so a view is written once.
GEO = "geo"
TIME = "time"

_TIME_LEVELS = ("month", "year")


def _is_geography_level(level: str, grains: list[str]) -> bool:
    return level in grains


def shape(
    table: pa.Table,
    *,
    name: str,
    by: list[str],
    grains: list[str],
    dimension_levels: dict[str, dict[str, str]],
    report: Any,
    fingerprint: str,
) -> dict[str, Any]:
    """Turn an ``aggregate()`` table into the JSON body a client consumes."""
    from ..geography import municipalities

    names = list(table.schema.names)
    geo_level = next((lv for lv in by if _is_geography_level(lv, grains)), None)
    time_level = next((lv for lv in by if lv in _TIME_LEVELS), None)
    dimensions = [lv for lv in by if lv != geo_level and lv != time_level]

    columns: dict[str, list[Any]] = {}
    codelists: dict[str, list[dict[str, str]]] = {}
    types: dict[str, dict[str, str]] = {}

    # --- geography -------------------------------------------------------
    if geo_level and geo_level in names:
        raw = [str(v) if v is not None else "" for v in table.column(geo_level).to_pylist()]
        if geo_level == _BASE_LEVEL:
            index = municipalities()
            codes: list[str] = []
            seen: dict[str, str] = {}
            for value in raw:
                row = index.get(value)
                # A code with no identity row keeps its own value rather than
                # being dropped: losing a cell silently would make a total
                # disagree with the sum of its parts, which is the one thing
                # the whole aggregate layer exists to prevent.
                code = row["code7"] if row else value
                codes.append(code)
                if code not in seen:
                    seen[code] = (
                        f"{row['name']}, {row['uf_sigla']}" if row else value
                    )
            columns[GEO] = codes
            codelists[GEO] = [{"code": c, "label": lb} for c, lb in sorted(seen.items())]
            types[GEO] = {"type": "code7", "grain": geo_level}
        else:
            # Classifications and `uf` already carry their label as the value:
            # the membership pack stores `member_label`, and a roll-up groups on
            # it. Code and label coincide, which is stated rather than hidden so
            # a client does not build a join that resolves to nothing.
            columns[GEO] = raw
            unique = sorted(set(raw))
            codelists[GEO] = [{"code": v, "label": v} for v in unique]
            grain_kind = "sigla" if geo_level == _UF_LEVEL else (
                "national" if geo_level == _NATIONAL_LEVEL else "label")
            types[GEO] = {"type": grain_kind, "grain": geo_level}

    # --- time ------------------------------------------------------------
    if time_level and time_level in names:
        raw_time = [str(v) if v is not None else "" for v in table.column(time_level).to_pylist()]
        if time_level == "month":
            raw_time = [f"{v[:4]}-{v[4:6]}" if len(v) == 6 else v for v in raw_time]
        columns[TIME] = raw_time
        types[TIME] = {"type": "period", "grain": time_level}

    # --- dimensions ------------------------------------------------------
    for dimension in dimensions:
        if dimension not in names:
            continue
        values = [str(v) if v is not None else "" for v in table.column(dimension).to_pylist()]
        columns[dimension] = values
        mapping = dimension_levels.get(dimension, {})
        codelists[dimension] = [
            {"code": code, "label": mapping.get(code) or code}
            for code in sorted(set(values))
        ]
        types[dimension] = {"type": "dict", "codelist": dimension}

    # --- measure state ---------------------------------------------------
    structural = {geo_level, time_level, *dimensions}
    for column in names:
        if column in structural:
            continue
        columns[column] = table.column(column).to_pylist()
        types[column] = {"type": "f64"}

    return {
        "artifact_id": f"{name}@{fingerprint[:8]}" if fingerprint else name,
        "recipe_id": name,
        "fingerprint": fingerprint,
        "by": by,
        "keys": {
            "geo": geo_level, "time": time_level, "dimensions": dimensions,
        },
        "rows": table.num_rows,
        "columns": types,
        "codelists": codelists,
        "data": columns,
        "report": {
            "unmapped": getattr(report, "unmapped", {}) or {},
            "partial_periods": list(getattr(report, "partial_periods", ()) or ()),
            "contested": list(getattr(report, "contested", ()) or ()),
            "support": getattr(report, "support", {}) or {},
            "warnings": list(getattr(report, "warnings", []) or []),
        },
    }
