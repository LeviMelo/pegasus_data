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


from pathlib import Path
from typing import Any

from ._cache import ByteCache
from ._errors import Refused

__all__ = ["create_app", "main"]

API = "/api/v1"

#: Shaped responses as SERIALISED BYTES, keyed by (the whole request, the
#: artifact's identity). Bytes, not the dict: FastAPI's encoder walk over a 66k-row
#: payload costs ~0.4 s per response, which is most of the route's warm time --
#: serialising once with orjson and replaying the bytes skips it entirely. Bounded
#: by BYTES (a municipality-month body is megabytes), evicting one entry at a time.
#: The identity is `capabilities.artifact_identity`, the SAME function the
#: descriptor cache keys on, so a body and its descriptor never disagree about what
#: is fresh.
_RESPONSES = ByteCache(256 * 1024 * 1024)


def _error(status: int, message: str, **extra: Any):
    from fastapi.responses import JSONResponse

    return JSONResponse({"error": message, **extra}, status_code=status)


def _refusal(refused: Refused):
    return _error(refused.status, refused.message, **refused.extra)


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
    from fastapi import FastAPI, Query, Request, Response
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, ORJSONResponse

    from .. import __version__
    from .._aggregate import AggregationRefused, ArtifactMissing, aggregate, spec_named
    from ..capabilities import artifact_identity, capabilities, catalogue
    from ..config import load_settings
    from ..geography import classifications
    from . import _filters
    from ._membership import canonical_system, membership_body, systems
    from ._payload import shape
    from ._population import population_body
    from ._records import records_page

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
        listed codes: ``?dim.SEXO=1,3`` (repeating the parameter adds codes, it
        does not replace them). Filtering and marginalising are different
        operations and stay different here -- a level named in ``by`` is kept as
        an axis, a level filtered by ``dim.`` restricts the population. A code
        the artifact does not hold is refused (422) with the codes it does.
        """
        levels = [p.strip() for p in by.split(",") if p.strip()]
        wanted = [p.strip() for p in measures.split(",") if p.strip()]
        where = _filters.parse(request.query_params)
        cache_key = (
            artifact, str(settings.lake_dir), tuple(levels), tuple(wanted), system,
            tuple(sorted((k, tuple(v)) for k, v in where.items())),
            artifact_identity(artifact, settings),
        )
        cached = _RESPONSES.get(cache_key)
        if cached is not None:
            return Response(content=cached, media_type="application/json")
        # Resolved before the try, so "there is no such recipe" cannot be
        # reported as "that roll-up does not mean anything".
        try:
            spec = spec_named(artifact)
        except Exception:  # noqa: BLE001
            return _error(404, f"no artifact named {artifact!r}")
        try:
            canonical_system(system)
        except ValueError as exc:
            return _error(422, str(exc), artifact=artifact, systems=list(systems()))
        try:
            capability = capabilities(artifact, settings=settings)
            where = _filters.check(where, capability, system)
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
        except Refused as refused:
            return _error(refused.status, refused.message, artifact=artifact, **refused.extra)
        except AggregationRefused as exc:
            # A refusal is the point of the algebra, not a failure of it: the
            # message names what was asked and why it does not mean anything.
            return _error(422, str(exc), artifact=artifact, by=levels)
        except KeyError as exc:
            return _error(404, f"no artifact named {artifact!r}", detail=str(exc))

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

        blob = orjson.dumps(body)
        _RESPONSES.put(cache_key, blob, len(blob))
        return Response(content=blob, media_type="application/json")

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
        cube layer exists to prevent. Municipalities are 7-digit IBGE codes in
        every year of every series; a year the series does not hold is a 422.
        """
        try:
            return Response(content=population_body(settings, series, by, years, bands),
                            media_type="application/json")
        except Refused as refused:
            return _refusal(refused)

    # --------------------------------------------------------- geography

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
        request: Request,
        system: str | None = Query(None),
        uf: str | None = Query(None, description="restrict to one UF sigla"),
    ):
        """`code7 -> {name, uf, memberships: {<classification>: <member>}, conflicts: [...]}`.

        This is the identity service the client joins against. The body is built
        once per (pack, system) and sent with an ETag and a day's max-age, so a
        client never asks the server what a code means twice. A classification
        the publishing systems disagree about is listed in that municipality's
        `conflicts` (its value in `memberships` is then one of several
        defensible answers); an unknown `system` is a 422.
        """
        try:
            body, etag = membership_body(system, uf)
        except ValueError as exc:
            return _error(422, str(exc), systems=list(systems()))
        headers = {"ETag": etag, "Cache-Control": "public, max-age=86400"}
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers=headers)
        return Response(content=body, media_type="application/json", headers=headers)

    # ----------------------------------------------------------- linkage

    @app.get(f"{API}/links")
    def links() -> dict[str, Any]:
        """Declared link specs and every stored run's report (ADR-0112).

        Reports are aggregate facts about a linkage (pairs, chance, validations,
        verdict) and are always served; the pairs themselves are microdata.
        """
        from ..linkage import store
        from ..linkage.engine import load_links

        specs = [
            {"name": name, "description": s.description, "left": s.left.dataset, "right": s.right.dataset,
             "passes": [p.name for p in s.passes]}
            for name, s in load_links().items()
        ]
        return {"specs": specs, "runs": store.runs(settings)}

    def _timeline_refusal():
        """The timeline readers take no settings: another home's request would be answered from the default one."""
        default = load_settings().lake_dir
        if default != settings.lake_dir:
            return _error(
                409,
                f"timelines read the default data home ({default}), not this server's "
                f"({settings.lake_dir}); start the server without --root",
            )
        return None

    @app.get(f"{API}/links/timeline")
    def timeline_notable(
        period: str = Query(...),
        geography: str = Query(...),
        method: str = Query("probabilistic"),
        limit: int = Query(30, ge=1, le=200),
    ):
        """Births with the most linked events, to open a timeline from. Microdata."""
        if not allow_records:
            return _error(403, "timelines are microdata; start the server with --allow-records")
        if (refusal := _timeline_refusal()) is not None:
            return refusal
        from ..linkage.timeline import notable_births

        try:
            return {"period": period, "geography": geography, "method": method,
                    "births": notable_births(period=period, geography=geography, method=method, limit=limit)}
        except LookupError as exc:
            # A timeline is read from STORED link runs; computing one here took hours.
            return _error(409, str(exc))
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller as 400
            return _error(400, f"{type(exc).__name__}: {exc}")

    @app.get(f"{API}/links/timeline/{{birth}}")
    def timeline_one(
        birth: str,
        period: str = Query(...),
        geography: str = Query(...),
        method: str = Query("probabilistic"),
    ):
        """One pregnancy: a birth and the events linked to it. Microdata."""
        if not allow_records:
            return _error(403, "timelines are microdata; start the server with --allow-records")
        if (refusal := _timeline_refusal()) is not None:
            return refusal
        from ..linkage.timeline import timeline

        try:
            return timeline(birth, period=period, geography=geography, method=method)
        except KeyError as exc:
            return _error(404, str(exc))
        except LookupError as exc:
            return _error(409, str(exc))
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller as 400
            return _error(400, f"{type(exc).__name__}: {exc}")

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
        """A page of microdata from the lake. Off unless the operator turned it on.

        Personal identifiers pass through unmodified -- this endpoint does not
        mask, hash or drop anything. What it does is refuse to exist unless
        someone decided it should, and refuse to download or decode a territory
        the lake does not already hold (409), or a span wider than three years.
        Values are the codes as filed; `effective_period`, `warnings`,
        `structural_absence`, `complete` and `geography_basis` say what the
        engine actually did.
        """
        if not allow_records:
            return _error(
                403,
                "microdata is disabled on this server; start it with "
                "--allow-records to enable /api/v1/records",
            )
        columns = tuple(c.strip() for c in select.split(",") if c.strip())
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
            return records_page(settings, dataset, period, geography, columns, offset, limit)
        except Refused as refused:
            return _refusal(refused)
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller as 400
            return _error(400, f"{type(exc).__name__}: {exc}")

    @app.on_event("startup")
    def _prewarm() -> None:  # pragma: no cover - timing-dependent warmup
        """Build the one body every session asks for first: the system-neutral membership.

        Artifact roll-ups are not warmed: they were read and thrown away by an LRU smaller
        than the number of artifacts, and competed with the first real requests.
        """
        import threading

        def work() -> None:
            try:
                membership_body(None, None)
            except Exception:  # noqa: BLE001 - warmup must never block serving
                return

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
