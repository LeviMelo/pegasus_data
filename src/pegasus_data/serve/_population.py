"""``/population``: a denominator at the grain a rate needs.

The client divides AFTER aggregating -- sum of events over sum of population --
which is the only order that survives roll-ups, so this serves person-years,
never a pre-divided rate.

What the module guarantees, because each was once silently wrong:

* **One municipality code width.** Events travel as 7-digit IBGE codes; a
  series may be filed at six (POP, POPTCU before 2017) or seven (POPSVS, POPTCU
  from 2017). Every code is mapped through ``geography.to_code7`` before
  grouping, so a client joining events to this denominator loses no year. A code
  the pack cannot resolve (an extinct one: 53 in POP, 1 in POPTCU 2001) leaves the
  municipal rows -- widths are matched exactly, so it is never passed through at
  its own width -- and is named in ``unresolved`` with its mass, which stays in
  ``total``.
* **A year the series does not hold is a refusal**, with the years it does hold,
  not a ``0.0`` that a client divides by.
* **What a series can stratify by is what its files carry** (``materialised``),
  not what its name suggests.
"""

from __future__ import annotations

from typing import Any

from ._cache import ByteCache
from ._errors import Refused

#: Serialised payloads, bounded by bytes (a municipality-by-year payload is ~1 MB).
_CACHE = ByteCache(64 * 1024 * 1024)

ALLOWED_AXES = ("municipality", "uf", "year", "age_band")


def _to_code7(code: Any) -> tuple[Any, list[str]]:
    """Map a municipality column (any width) to 7-digit codes; return the codes no pack row resolves."""
    import pyarrow as pa
    import pyarrow.compute as pc

    from ..geography import to_code7

    text = pc.cast(code, pa.string())
    mapping = {c: to_code7(c) for c in pc.unique(text).drop_null().to_pylist()}
    keys = pa.array(list(mapping), pa.string())
    values = pa.array(list(mapping.values()), pa.string())
    unresolved = sorted(c for c, v in mapping.items() if v is None)
    return pc.take(values, pc.index_in(text, value_set=keys)), unresolved


def _uf_column(code: Any) -> Any:
    """UF siglas from the first two digits of a municipality (or UF) code, whatever its width."""
    import pyarrow as pa
    import pyarrow.compute as pc

    from ..normalize.geo import uf_array

    return pc.fill_null(uf_array(pc.cast(code, pa.string())), "")


def _payload(settings: Any, series: str, by: tuple[str, ...], years: tuple[int, ...],
             bands: tuple[int, ...]) -> dict[str, Any]:
    import pyarrow as pa
    import pyarrow.compute as pc

    from ..api import load_population

    table = load_population(series=series, years=list(years) or None, by=(), settings=settings)
    names = set(table.schema.names)
    columns: dict[str, Any] = {}
    unresolved_report: dict[str, Any] | None = None
    if "municipality" in by:
        code7, unresolved = _to_code7(table.column("municipality"))
        if unresolved:
            # An extinct or never-IBGE code (POP before 1996: 53; POPTCU 2001: 1) can match no event, whose
            # codes come from the same pack. Its rows leave the municipal axis -- one width throughout, never
            # a 6-digit code beside the 7-digit ones -- and are NAMED here with their mass, which stays in `total`.
            bad = pc.is_in(pc.cast(table.column("municipality"), pa.string()),
                           value_set=pa.array(unresolved, pa.string()))
            seen = sorted({int(y) for y in pc.unique(pc.filter(table.column("year"), bad)).to_pylist()})
            unresolved_report = {
                "codes": unresolved, "years": seen,
                "population": float(pc.sum(pc.filter(pc.cast(table.column("population"), pa.float64()), bad)).as_py() or 0.0),
                "note": "no IBGE code7 in the membership pack: left out of the rows, counted in total",
            }
            table = table.filter(pc.invert(bad))
            code7 = pc.filter(code7, pc.invert(bad))
        columns["municipality"] = code7
    if "uf" in by:
        if "municipality" in names:
            columns["uf"] = _uf_column(table.column("municipality"))
        elif "ufcod" in names:
            columns["uf"] = _uf_column(table.column("ufcod"))
        else:
            columns["uf"] = pc.cast(table.column("uf"), pa.string())
    if "year" in by:
        columns["year"] = pc.cast(table.column("year"), pa.string())
    if "age_band" in by:
        # Banded with the SAME machinery the artifacts use, so the codes match
        # a derived age dimension's cell values exactly when the edges do.
        from .._age import NumericBandDimension

        band = NumericBandDimension(name="age_band", field_name="age", bands=bands, label="age band")
        columns["age_band"] = band.column(table)
    pop = pc.cast(table.column("population"), pa.float64())
    total = float(pc.sum(pop).as_py() or 0.0) + (unresolved_report["population"] if unresolved_report else 0.0)
    if not columns:
        return {"series": series, "by": [], "rows": 1, "data": {"population": [total]}, "total": total}
    grouped = (
        pa.table({**columns, "population": pop})
        .group_by(list(columns))
        .aggregate([("population", "sum")])
        .sort_by([(name, "ascending") for name in columns])
    )
    data = {name: grouped.column(name).to_pylist() for name in columns}
    data["population"] = grouped.column("population_sum").to_pylist()
    body = {"series": series, "by": list(by), "rows": grouped.num_rows, "data": data, "total": total}
    if unresolved_report:
        body["unresolved"] = unresolved_report
    return body


def population_body(settings: Any, series: str, by: str, years: str, bands: str) -> bytes:
    """The serialised response for one request, or :class:`Refused`.

    Cached per (lake, series, request, series files' mtimes): a re-ingested
    population is a new key, the discipline every artifact cache here follows.
    """
    import orjson

    from ..sources.ibge import KNOWN_SERIES, materialised, tree_mtime_ns

    spec = KNOWN_SERIES.get(series)
    if spec is None:
        raise Refused(422, f"unknown population series {series!r}", {"known": sorted(KNOWN_SERIES)})
    if spec.kind != "denominator":
        raise Refused(422, f"{series} is a census covariate table, not a denominator: it carries no population count",
                      {"known": sorted(n for n, s in KNOWN_SERIES.items() if s.kind == "denominator")})
    wanted = tuple(dict.fromkeys(p.strip() for p in by.split(",") if p.strip()))
    if bad := [w for w in wanted if w not in ALLOWED_AXES]:
        raise Refused(422, f"cannot serve population by {bad}", {"allowed": sorted(ALLOWED_AXES)})
    try:
        band_edges = tuple(int(b) for b in bands.split(",") if b.strip())
    except ValueError:
        raise Refused(422, f"bands must be integers, got {bands!r}") from None
    if "age_band" in wanted and not band_edges:
        raise Refused(
            422,
            "by=age_band needs the band edges (bands=0,1,5,...) — the bands "
            "are the caller's analytical claim, and serving a default would "
            "let two artifacts silently disagree about what 'menos de 1' means",
        )
    try:
        year_tuple = tuple(dict.fromkeys(int(y) for y in years.split(",") if y.strip()))
    except ValueError:
        raise Refused(422, f"years must be integers, got {years!r}") from None
    directory = settings.population_dir / series
    held = materialised(directory) if directory.exists() else None
    if held is None or "population" not in held.columns:
        raise Refused(404, f"population series {series!r} is not materialised; run `pegasus-data population`")
    # `uf` is derived from a municipality code when the files carry one; `age_band` bands a single-year `age`.
    needs = {"uf": ("uf", "municipality"), "age_band": ("age",)}
    if missing := [w for w in wanted if not any(held.has(n) for n in needs.get(w, (w,)))]:
        raise Refused(
            422,
            f"{series} does not carry {missing}; a rate built on it would "
            "divide by a population that does not stratify that way",
            {"stratifications": held.stratifications(spec.stratifications)})
    if year_tuple and (absent := [y for y in year_tuple if y not in held.years]):
        raise Refused(422, f"{series} holds no population for {absent}",
                      {"series": series, "years": list(held.years), "requested": list(year_tuple)})
    key = (str(settings.lake_dir), series, wanted, year_tuple, band_edges, tree_mtime_ns(directory))

    def build() -> tuple[bytes, int]:
        try:
            body = orjson.dumps(_payload(settings, series, wanted, year_tuple, band_edges))
        except Refused:
            raise
        except Exception as exc:  # noqa: BLE001 - refusal with the reason, not a bare 500
            raise Refused(422, f"{type(exc).__name__}: {exc}", {"series": series}) from exc
        return body, len(body)

    return _CACHE.once(key, build)
