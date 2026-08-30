"""HTTP transport over the existing library. No analysis lives here.

Every handler is a call into a function that already exists, plus JSON shaping.
If a request needs a decision -- what a level means, whether a measure may be
summed, which municipality a code names -- that decision is made in the module
that owns it and this layer carries the answer.

Run it::

    python -m pegasus_data.serve --port 8000
    pegasus serve --port 8000

Microdata is OFF by default. ``--allow-records`` turns on ``/api/v1/records``,
which pages raw rows out of :func:`pegasus_data.query`. That switch exists
because *exposing* identifiable rows over a network is a different decision from
*retaining* them in a local lake, and only the operator can make it. Personal
identifiers are never modified: no masking, no hashing, no dropping. The
detector and its open question stay on, because that flag is the evidence.
"""

# NOTE: deliberately NO `from __future__ import annotations` here.
#
# FastAPI resolves a handler's annotations with `typing.get_type_hints`, which
# looks them up in the MODULE globals. `fastapi` is imported inside
# `create_app` so that importing `pegasus_data` never pays for a web framework
# -- which means `Request` is a local name. Under PEP 563 every annotation
# becomes a string, `get_type_hints` cannot find `Request`, and FastAPI decides
# it must be a query parameter. The symptom is a 422 demanding a `request`
# query argument on every route that takes one.
#
# Evaluating annotations eagerly costs nothing here and keeps the lazy import.

from functools import lru_cache
from pathlib import Path
from typing import Any

__all__ = ["create_app", "main"]

API = "/api/v1"


@lru_cache(maxsize=64)
def _population_payload(
    lake_dir: str,
    series: str,
    by: tuple[str, ...],
    years: tuple[int, ...],
    dir_mtime_ns: int,
    bands: tuple[int, ...] = (),
) -> dict[str, Any]:
    """One grouped denominator, cached per (request shape, series version).

    ``dir_mtime_ns`` is the series directory's mtime: a re-ingested population
    is a new key, the same discipline every artifact cache here follows.
    """
    import pyarrow as pa
    import pyarrow.compute as pc

    from ..api import load_population
    from ..normalize.geo import uf_from_code

    table = load_population(series=series, years=list(years) or None)
    columns: dict[str, Any] = {}
    if "municipality" in by or "uf" in by:
        code = pc.cast(table.column("municipality"), pa.string())
        if "municipality" in by:
            columns["municipality"] = code
        if "uf" in by:
            distinct = pc.unique(code).to_pylist()
            mapping = {c: str(uf_from_code(str(c)) or "") for c in distinct}
            keys = pa.array(list(mapping.keys()), pa.string())
            values = pa.array(list(mapping.values()), pa.string())
            columns["uf"] = pc.take(values, pc.index_in(code, value_set=keys))
    if "year" in by:
        columns["year"] = pc.cast(table.column("year"), pa.string())
    if "age_band" in by:
        # Banded with the SAME machinery the artifacts use, so the codes match
        # a derived age dimension's cell values exactly when the edges do.
        from .._age import NumericBandDimension

        band = NumericBandDimension(
            name="age_band", field_name="age", bands=bands, label="age band")
        columns["age_band"] = band.column(table)
    pop = pc.cast(table.column("population"), pa.float64())
    total = float(pc.sum(pop).as_py() or 0.0)
    if not columns:
        return {"series": series, "by": [], "rows": 1,
                "data": {"population": [total]}, "total": total}
    grouped = (
        pa.table({**columns, "population": pop})
        .group_by(list(columns))
        .aggregate([("population", "sum")])
        .sort_by([(name, "ascending") for name in columns])
    )
    data = {name: grouped.column(name).to_pylist() for name in columns}
    data["population"] = grouped.column("population_sum").to_pylist()
    return {"series": series, "by": list(by), "rows": grouped.num_rows,
            "data": data, "total": total}


#: Shaped responses as SERIALISED BYTES, keyed by (artifact identity, the
#: whole request). Bytes, not the dict: FastAPI's encoder walk over a 66k-row
#: payload costs ~0.4 s per response, which is most of the route's warm time
#: -- serialising once with orjson and replaying the bytes skips it entirely.
#: The identity is the pair of file mtimes every other cache here keys on, so
#: a rebuild is a different key and nothing needs invalidating.
_RESPONSE_CACHE: dict[tuple, bytes] = {}
_RESPONSE_CACHE_LIMIT = 256


def _artifact_identity(settings: Any, artifact: str) -> tuple[int, int]:
    from .._aggregate import artifact_dir

    target = artifact_dir(artifact, settings)
    try:
        return (
            (target / "cells.parquet").stat().st_mtime_ns,
            (target / "manifest.json").stat().st_mtime_ns,
        )
    except OSError:
        return (0, 0)


@lru_cache(maxsize=6)
def _records_table(
    lake_dir: str, dataset: str, period: str, geography: str, select: tuple[str, ...]
):
    """One scope's microdata, assembled once and paged from memory.

    The assembly decodes a territory's source files -- tens of seconds cold --
    and the pager was doing it PER PAGE. Bounded small: each entry is one
    territory-period of rows, and six covers a browsing session.
    """
    from .. import query as _query

    return _query(
        dataset, period=period, geography=geography, select=list(select) or None,
    )


def _error(status: int, message: str, **extra: Any):
    from fastapi.responses import JSONResponse

    return JSONResponse({"error": message, **extra}, status_code=status)


def create_app(
    *,
    root: str | Path | None = None,
    allow_records: bool = False,
    origins: tuple[str, ...] = ("http://localhost:5173", "http://127.0.0.1:5173"),
    mesh_dir: str | Path | None = None,
) -> Any:
    """Build the ASGI application.

    `origins` defaults to the Vite dev server. A deployment behind one origin
    passes its own; a wildcard is deliberately not the default, because this
    server can be configured to serve microdata.
    """
    from fastapi import FastAPI, Query, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import FileResponse, JSONResponse, ORJSONResponse

    from .. import __version__
    from .._aggregate import AggregationRefused, ArtifactMissing, aggregate, spec_named
    from ..capabilities import capabilities, catalogue
    from ..config import load_settings
    from ..geography import classifications, memberships, municipalities
    from ._payload import shape

    settings = load_settings(root=Path(root) if root else None)
    meshes = Path(mesh_dir) if mesh_dir else Path(settings.lake_dir) / "geo"

    app = FastAPI(
        title="pegasus_data",
        version=__version__,
        description="Aggregated DATASUS artifacts and the capabilities that "
                    "say what may legitimately be done with them.",
        docs_url=f"{API}/docs",
        openapi_url=f"{API}/openapi.json",
        # The municipality-month payload is megabytes of JSON; stdlib
        # json.dumps was a visible share of serving it.
        default_response_class=ORJSONResponse,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(origins),
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=["*"],
    )

    # ------------------------------------------------------------ health

    @app.get(f"{API}/health")
    def health() -> dict[str, Any]:
        entries = catalogue(settings=settings)
        return {
            "version": __version__,
            "lake": str(settings.lake_dir),
            "artifacts": len(entries),
            "built": sum(1 for e in entries if e["built"]),
            "records_enabled": allow_records,
            "meshes": sorted(p.name for p in meshes.glob("*.json")) if meshes.exists() else [],
        }

    # -------------------------------------------------------- capabilities

    @app.get(f"{API}/datasets")
    def datasets() -> list[dict[str, Any]]:
        return catalogue(settings=settings)

    @app.get(f"{API}/datasets/{{artifact}}/capabilities")
    def dataset_capabilities(artifact: str):
        try:
            return capabilities(artifact, settings=settings).as_dict()
        except ArtifactMissing as exc:
            return _error(404, str(exc), artifact=artifact)
        except (AggregationRefused, KeyError) as exc:
            return _error(400, str(exc), artifact=artifact)

    # ------------------------------------------------------------ cells

    @app.get(f"{API}/artifacts/{{artifact}}")
    def artifact_cells(
        request: Request,
        artifact: str,
        by: str = Query("", description="comma-separated levels, e.g. municipality,year,SEXO"),
        measures: str = Query("", description="comma-separated measure ids; empty means all"),
        system: str | None = Query(None, description="which publishing system's geography to use"),
    ):
        """Roll the base cuboid up to the requested levels and serve the state.

        Any query parameter named ``dim.X`` filters dimension ``X`` to the
        listed codes: ``?dim.SEXO=1,3``. Filtering and marginalising are
        different operations and stay different here -- a level named in ``by``
        is kept as an axis, a level filtered by ``dim.`` restricts the
        population.
        """
        levels = [p.strip() for p in by.split(",") if p.strip()]
        wanted = [p.strip() for p in measures.split(",") if p.strip()]
        where: dict[str, Any] = {}
        for key, value in request.query_params.multi_items():
            if key.startswith("dim.") and value:
                where[key[4:]] = [v.strip() for v in value.split(",") if v.strip()]
        cache_key = (
            artifact, tuple(levels), tuple(wanted), system,
            tuple(sorted((k, tuple(v)) for k, v in where.items())),
            _artifact_identity(settings, artifact),
        )
        cached = _RESPONSE_CACHE.get(cache_key)
        if cached is not None:
            from fastapi import Response

            return Response(content=cached, media_type="application/json")
        # Resolved before the try, so "there is no such recipe" cannot be
        # reported as "that roll-up does not mean anything".
        try:
            spec = spec_named(artifact)
        except Exception:
            return _error(404, f"no artifact named {artifact!r}")
        try:
            table, report = aggregate(
                artifact, by=levels or None, measures=wanted or None,
                where=where or None, system=system, settings=settings,
                return_report=True,
                # State, not finished values. The client still has aggregating
                # to do -- a Total row, a facet, a national line drawn from
                # municipal cells -- and finalising here would hand it a mean it
                # can only average again. The descriptor carries the formula.
                finalize=False,
            )
        except ArtifactMissing as exc:
            return _error(404, str(exc), artifact=artifact)
        except AggregationRefused as exc:
            # A refusal is the point of the algebra, not a failure of it: the
            # message names what was asked and why it does not mean anything.
            return _error(422, str(exc), artifact=artifact, by=levels)
        except KeyError as exc:
            return _error(404, f"no artifact named {artifact!r}", detail=str(exc))

        capability = capabilities(artifact, settings=settings)
        levels_by_dimension = {
            d.id: {lv.code: lv.label for lv in d.levels} for d in capability.dimensions
        }
        body = shape(
            table, name=artifact, by=levels or [],
            grains=list(capability.spatial["grains"]),
            dimension_levels=levels_by_dimension,
            report=report, fingerprint=report.fingerprint,
        )
        body["dataset"] = spec.dataset
        import orjson
        from fastapi import Response

        blob = orjson.dumps(body)
        if len(_RESPONSE_CACHE) >= _RESPONSE_CACHE_LIMIT:
            _RESPONSE_CACHE.clear()
        _RESPONSE_CACHE[cache_key] = blob
        return Response(content=blob, media_type="application/json")

    # --------------------------------------------------------- geography

    # ------------------------------------------------------------ population

    @app.get(f"{API}/population")
    def population(
        series: str = Query("POPSVS"),
        by: str = Query("municipality,year", description="comma-separated: municipality, uf, year, age_band"),
        years: str = Query("", description="comma-separated years; empty means all"),
        bands: str = Query("", description="age band edges for by=age_band, e.g. 0,1,5,10"),
    ):
        """A denominator, served at the grain a rate needs.

        The client divides AFTER aggregating -- sum of events over sum of
        population -- which is the only order that survives roll-ups. Serving
        pre-divided rates would hand back exactly the mean-of-means the whole
        cube layer exists to prevent.
        """
        from ..sources.ibge import KNOWN_SERIES

        spec_ = KNOWN_SERIES.get(series)
        if spec_ is None:
            return _error(422, f"unknown population series {series!r}", known=sorted(KNOWN_SERIES))
        wanted = tuple(dict.fromkeys(p.strip() for p in by.split(",") if p.strip()))
        allowed = {"municipality", "uf", "year", "age_band"}
        if bad := [w for w in wanted if w not in allowed]:
            return _error(422, f"cannot serve population by {bad}", allowed=sorted(allowed))
        try:
            band_edges = tuple(int(b) for b in bands.split(",") if b.strip())
        except ValueError:
            return _error(422, f"bands must be integers, got {bands!r}")
        if "age_band" in wanted and not band_edges:
            return _error(
                422,
                "by=age_band needs the band edges (bands=0,1,5,...) — the bands "
                "are the caller's analytical claim, and serving a default would "
                "let two artifacts silently disagree about what 'menos de 1' means",
            )
        supported, missing = spec_.supports(
            ["age" if w == "age_band" else w for w in wanted if w != "uf"])
        if not supported:
            return _error(
                422,
                f"{series} does not carry {missing}; a rate built on it would "
                "divide by a population that does not stratify that way",
                stratifications=spec_.stratifications,
            )
        try:
            year_tuple = tuple(int(y) for y in years.split(",") if y.strip())
        except ValueError:
            return _error(422, f"years must be integers, got {years!r}")
        directory = settings.population_dir / series
        if not directory.exists():
            return _error(
                404,
                f"population series {series!r} is not materialised; "
                "run `pegasus-data population`",
            )
        try:
            payload = _population_payload(
                str(settings.lake_dir), series, wanted, year_tuple,
                directory.stat().st_mtime_ns, band_edges,
            )
        except Exception as exc:  # noqa: BLE001 - refusal with reason, not a bare 500
            return _error(422, f"{type(exc).__name__}: {exc}", series=series)
        return payload

    @app.get(f"{API}/geo/hierarchies")
    def hierarchies() -> dict[str, Any]:
        declared = classifications()
        return {
            "classifications": {
                key: {
                    "authority": str(body.get("authority") or "datasus"),
                    "what": str(body.get("what") or "").strip(),
                    "partial_coverage": bool(body.get("partial_coverage")),
                    "attribute": bool(body.get("attribute")),
                }
                for key, body in declared.items()
            },
        }

    @app.get(f"{API}/geo/membership")
    def membership(
        system: str | None = Query(None),
        uf: str | None = Query(None, description="restrict to one UF sigla"),
    ) -> dict[str, Any]:
        """`code7 -> {name, uf, <classification>: <member>}` for every municipality.

        This is the identity service the client joins against. It is one request
        and it is cacheable forever, so a client never asks the server what a
        code means twice.
        """
        index = municipalities()
        out: dict[str, dict[str, str]] = {}
        for code6, row in index.items():
            if uf and row["uf_sigla"].upper() != uf.upper():
                continue
            # Identity and containment are kept in separate objects because
            # they COLLIDE: identity's `uf` is the sigla `AC`, while the `uf`
            # classification's member label is `AC Acre`. Merging them let the
            # classification silently overwrite the sigla, and the sigla is what
            # the UF mesh joins on.
            out[row["code7"]] = {
                "code6": code6,
                "name": row["name"],
                "uf": row["uf_sigla"],
                "uf_name": row["uf_name"],
                "uf_code": row["uf_code"],
                "macroregion": row["macroregion"],
                "memberships": memberships(code6, system=system).as_dict(),
            }
        return {"count": len(out), "system": system, "membership": out}

    @app.get(f"{API}/geo/mesh/{{grain}}")
    def mesh(grain: str):
        """TopoJSON for one grain, immutable once built."""
        path = meshes / f"{grain}.topo.json"
        if not path.exists():
            return _error(
                404,
                f"no mesh for {grain!r}; build it with "
                f"`python -m pegasus_data.serve.geometry --grain {grain}`",
                available=sorted(p.stem.replace(".topo", "") for p in meshes.glob("*.topo.json")),
            )
        return FileResponse(
            path, media_type="application/json",
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

    # ----------------------------------------------------------- records

    @app.get(f"{API}/records")
    def records(
        dataset: str = Query(..., description="e.g. SIH-RD"),
        period: str = Query(...),
        geography: str | None = Query(None),
        select: str = Query("", description="comma-separated columns"),
        limit: int = Query(500, ge=1, le=5000),
        offset: int = Query(0, ge=0),
    ):
        """A page of microdata. Off unless the operator turned it on.

        Personal identifiers pass through unmodified -- this endpoint does not
        mask, hash or drop anything. What it does is refuse to exist unless
        someone decided it should.
        """
        if not allow_records:
            return _error(
                403,
                "microdata is disabled on this server; start it with "
                "--allow-records to enable /api/v1/records",
            )
        columns = [c.strip() for c in select.split(",") if c.strip()]
        if not geography:
            # A national page decodes every state's files for two hundred
            # rows. The client scopes; an unscoped ask is refused with the
            # reason rather than answered minutes later.
            return _error(
                422,
                "records need a geography (a UF sigla or municipality code); "
                "a national page would decode every state's files for one "
                "screen of rows",
            )
        try:
            table = _records_table(
                str(settings.lake_dir), dataset, period, geography,
                tuple(columns),
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller as 400
            return _error(400, f"{type(exc).__name__}: {exc}")
        page = table.slice(offset, limit)
        return {
            "dataset": dataset, "period": period, "geography": geography,
            "total": table.num_rows, "offset": offset, "limit": limit,
            "columns": list(page.schema.names),
            "rows": page.to_pylist(),
        }

    @app.on_event("startup")
    def _prewarm() -> None:  # pragma: no cover - timing-dependent warmup
        """Warm each built artifact's canonical shape before anyone asks.

        The first municipality-month question against a national artifact
        costs ~1.5 s of reads and grouping; every later identical question is
        the response cache. Paying the first one at startup, in a thread,
        means no user ever does.
        """
        import threading

        def work() -> None:
            from .._aggregate import aggregate as _aggregate

            for entry in catalogue(settings=settings):
                if not entry.get("built"):
                    continue
                try:
                    _aggregate(
                        entry["id"], by=["municipality", "month"],
                        settings=settings, finalize=False,
                    )
                except Exception:  # noqa: BLE001 - warmup must never block serving
                    continue

        threading.Thread(target=work, name="prewarm", daemon=True).start()

    # Registered on Exception, not on 500: Starlette dispatches int-keyed
    # handlers only for HTTPExceptions RAISED with that status, and nothing
    # here raises one -- so the int-keyed version was dead code and a genuine
    # crash surfaced as Starlette's bare-text default instead of a JSON body
    # the frontend can read.
    @app.exception_handler(Exception)
    def _unhandled(request: Request, exc: Exception):  # pragma: no cover
        return JSONResponse({"error": f"{type(exc).__name__}: {exc}"}, status_code=500)

    return app


def main(argv: list[str] | None = None) -> int:
    """``python -m pegasus_data.serve``."""
    import argparse

    import uvicorn

    parser = argparse.ArgumentParser(prog="pegasus-serve", description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--root", default=None, help="settings root")
    parser.add_argument("--mesh-dir", default=None)
    parser.add_argument(
        "--allow-records", action="store_true",
        help="expose /api/v1/records, which serves unmodified microdata",
    )
    parser.add_argument(
        "--origin", action="append", default=[],
        help="allowed CORS origin; repeatable. Defaults to the Vite dev server.",
    )
    args = parser.parse_args(argv)

    origins = tuple(args.origin) or ("http://localhost:5173", "http://127.0.0.1:5173")
    app = create_app(
        root=args.root, allow_records=args.allow_records,
        origins=origins, mesh_dir=args.mesh_dir,
    )
    if args.allow_records:
        print("WARNING: /api/v1/records is enabled -- this server will return "
              "unmodified personal identifiers to any allowed origin.")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    return 0
