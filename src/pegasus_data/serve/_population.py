"""``/population``: a denominator at the grain a rate needs.

The client divides AFTER aggregating -- sum of events over sum of population --
which is the only order that survives roll-ups, so this serves person-years,
never a pre-divided rate.

What the module guarantees, because each was once silently wrong:

* **One placing rule.** The denominator is the population cube
  (``population:<series>``), which places every code as the events' cubes do: a
  municipality as a 7-digit IBGE code whatever width it was filed at, a state as
  the state its code places. A code no place takes (an extinct one: POPTCU 2001's
  431453) leaves the rows -- never passed through at its own width -- and is named
  in ``unresolved`` with its mass, which stays in ``total``.
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


def _payload(settings: Any, series: str, by: tuple[str, ...], years: tuple[int, ...],
             bands: tuple[int, ...]) -> dict[str, Any]:
    """The denominator as the population cube (`cubes.cube`, ``population:<series>``) at the finest place ``by`` names.

    The cube places every code by the one placing rule, so the municipalities are 7-digit IBGE codes and a state is the
    state its code places; the persons no place takes stay in ``total`` and are named in ``unresolved``."""
    import pyarrow as pa
    import pyarrow.compute as pc

    from ..config import UF_NUMERIC
    from ..cubes import cube, manifest

    place = "municipality" if "municipality" in by else "uf" if "uf" in by else "country"
    facts = cube(f"population:{series}", place=place, by=["age"] if "age_band" in by else [],
                 periods=list(years) or None, settings=settings)
    meta = manifest(facts)
    lost = float(meta.get("unplaced_persons") or 0.0)
    total = float(pc.sum(facts.column("value")).as_py() or 0.0) + lost
    columns: dict[str, Any] = {}
    if place == "municipality":
        columns["municipality"] = pc.cast(facts.column("place"), pa.string())
    if "uf" in by:
        sigla = {int(k): v for k, v in UF_NUMERIC.items()}
        code = facts.column("place") if place == "uf" else pc.divide(facts.column("place"), 100000)
        columns["uf"] = pa.array([sigla[c] for c in code.to_pylist()], pa.string())
    if "year" in by:
        columns["year"] = facts.column("period")
    if "age_band" in by:
        # Banded with the SAME machinery the artifacts use, so the codes match
        # a derived age dimension's cell values exactly when the edges do.
        from .._age import NumericBandDimension

        band = NumericBandDimension(name="age_band", field_name="age", bands=bands, label="age band")
        columns["age_band"] = band.column(facts)
    unresolved = ({"codes": meta.get("unplaced_codes") or [], "years": meta.get("unplaced_years") or [],
                   "population": lost, "note": f"no {place} place (geography.place_municipalities / place_states): "
                                               "left out of the rows, counted in total"} if lost else None)
    body: dict[str, Any]
    if not columns:
        body = {"series": series, "by": [], "rows": 1, "data": {"population": [total]}, "total": total}
    else:
        grouped = (pa.table({**columns, "population": facts.column("value")})
                   .group_by(list(columns)).aggregate([("population", "sum")])
                   .sort_by([(name, "ascending") for name in columns]))
        data = {name: grouped.column(name).to_pylist() for name in columns}
        data["population"] = grouped.column("population_sum").to_pylist()
        body = {"series": series, "by": list(by), "rows": grouped.num_rows, "data": data, "total": total}
    if unresolved:
        body["unresolved"] = unresolved
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
