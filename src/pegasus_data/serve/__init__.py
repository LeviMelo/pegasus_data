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

from ._routes import (
    API,
    Context,
    register_capabilities,
    register_cells,
    register_geography,
    register_health,
    register_lifecycle,
    register_links,
    register_population,
    register_records,
)

__all__ = ["create_app", "main"]


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
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import ORJSONResponse

    from .. import __version__
    from ..config import load_settings

    settings = load_settings(root=Path(root) if root else None)
    ctx = Context(settings=settings,
                  meshes=Path(mesh_dir) if mesh_dir else Path(settings.lake_dir) / "geo",
                  allow_records=allow_records)

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

    for register in (register_health, register_capabilities, register_cells, register_population,
                     register_geography, register_links, register_records, register_lifecycle):
        register(app, ctx)
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
