"""``dim.X=a,b`` filters of ``/artifacts``: parsed whole, and checked against what the artifact holds.

Two defects lived here. A repeated parameter replaced the earlier one
(``dim.SEXO=1&dim.SEXO=3`` served SEXO=3 alone: 7.2 M admissions where
``dim.SEXO=1,3`` gave 12.5 M), and a code the artifact does not hold answered an
empty 200, which looks like a legitimate "none". Every value is now checked
against the levels the descriptor lists (or the years, UFs, months, municipalities
and classification members the artifact can have) and the refusal names the valid
ones.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from ..normalize.time import parse_month
from ._errors import Refused

#: How many valid values a refusal lists.
_SHOWN = 200


def parse(query_params: Any) -> dict[str, list[str]]:
    """Every ``dim.X`` parameter, repeats merged and de-duplicated, order kept."""
    where: dict[str, list[str]] = {}
    for key, value in query_params.multi_items():
        if key.startswith("dim.") and value:
            into = where.setdefault(key[4:], [])
            into.extend(v for v in (p.strip() for p in value.split(",")) if v and v not in into)
    return where


@lru_cache(maxsize=64)
def _class_members(classification: str, system: str | None, pack_mtime_ns: int) -> frozenset[str]:
    from ..geography import members

    return frozenset(members(classification, system=system).values())


def _refuse(key: str, values: list[str], valid: Any, artifact: str | None = None) -> Refused:
    shown = sorted(valid)
    return Refused(
        422,
        f"{key}: {values[:10]} {'is' if len(values) == 1 else 'are'} not among the {len(shown)} "
        "values this artifact holds",
        {"filter": key, "invalid": values, "valid": shown[:_SHOWN], "valid_count": len(shown)})


def check(where: dict[str, list[str]], capability: Any, system: str | None) -> dict[str, list[str]]:
    """The filters in the form the roll-up compares them in; :class:`Refused` (422) on a value that matches nothing."""
    from ..config import UF_NUMERIC
    from ..geography import _pack_mtime, _pack_path, classifications, municipalities

    levels = {d.id: {lv.code for lv in d.levels} for d in capability.dimensions}
    years = {str(y) for y in capability.period.get("years") or ()}
    lo = str(capability.period.get("from") or "").replace("-", "")
    hi = str(capability.period.get("to") or "").replace("-", "")
    known = classifications()
    out: dict[str, list[str]] = {}
    for key, values in where.items():
        if key in levels:
            valid: Any = levels[key]
        elif key == "year":
            valid = years
        elif key == "uf":
            valid = set(UF_NUMERIC.values())
        elif key in ("month", "period"):
            # The wire carries months as YYYY-MM; the cells hold YYYYMM.
            parsed = [parse_month(v) for v in values]
            if bad := [v for v, p in zip(values, parsed, strict=True) if p is None]:
                raise Refused(422, f"{key} takes YYYYMM or YYYY-MM, got {bad}", {"filter": key})
            values = [str(p) for p in parsed]
            if outside := [v for v in values if lo and hi and not lo <= v <= hi]:
                raise Refused(422, f"{key} {outside} lies outside this artifact's period {lo}..{hi}",
                              {"filter": key, "from": lo, "to": hi})
            valid = None
        elif key == "municipality":
            # Cells hold the 6-digit DATASUS code; the wire speaks code7 (`_payload`).
            index = municipalities()
            by7 = {row["code7"]: code6 for code6, row in index.items()}
            codes = [by7.get(v) or (v if v in index else None) for v in values]
            if bad := [v for v, code in zip(values, codes, strict=True) if code is None]:
                raise Refused(422, f"unknown municipality code(s) {bad[:10]}", {"filter": key, "invalid": bad})
            values = list(dict.fromkeys(c for c in codes if c))
            valid = None
        elif key in known:
            pack = _pack_path(None)
            valid = _class_members(key, system, _pack_mtime(str(pack)) if pack else 0)
        else:
            raise Refused(
                422, f"cannot filter on {key!r}",
                {"filter": key, "valid": sorted([*levels, "municipality", "uf", "year", "month", *known])})
        if valid is not None and (bad := [v for v in values if v not in valid]):
            raise _refuse(key, bad, valid)
        out[key] = values
    return out
