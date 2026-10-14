"""The DEMAS open-data API's own description (§11): its OpenAPI document, persisted.

Base ``https://apidadosabertos.saude.gov.br``, OpenAPI document at ``/static/swagger.json``. The document is machine-readable
field metadata, fetched with ``intake.get_json`` (the one polite, retrying client) and persisted at ingestion time to
``api_endpoints``. The API's *tables* are not read here: every one the project uses is a declared source of
``curation/intake.yml``, read by ``intake`` (paging, retry, landing, the check against its other origin). What stays here
is the document: ``declared_endpoints`` sets the endpoints the declarations read against it, so a renamed or removed path is
an open question and not a 404 recorded as an empty table.

Measured 2026-08: the live document is Swagger 2.0, ``version 1.8.32``, exposing 87 paths (113 on 2026-10-10). Where the API
and the FTP cover the same base, :func:`reconciliation_targets` names the pairs worth comparing.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

from ..catalog.store import CatalogStore, utcnow
from ..config import DEMAS_BASE_URL, DEMAS_SWAGGER_PATH

#: FTP systems and API endpoints covering the same base, for the reconciliation
#: report the design rule in §11 calls for.
RECONCILIATION_PAIRS: tuple[tuple[str, str], ...] = (
    ("CNES", "/cnes/estabelecimentos"),
    ("SIM", "/vigilancia-e-meio-ambiente/sistema-de-informacao-sobre-mortalidade"),
    ("SINASC", "/vigilancia-e-meio-ambiente/sistema-de-informacao-sobre-nascidos-vivos"),
    ("SINAN", "/arboviroses/dengue"),
)


@dataclass(slots=True)
class Endpoint:
    path: str
    method: str
    summary: str
    tags: list[str] = field(default_factory=list)
    parameters: list[dict[str, Any]] = field(default_factory=list)
    response_schema: dict[str, Any] | None = None


def swagger() -> dict[str, Any]:
    """The live OpenAPI document, through the intake client."""
    from ..intake import get_json

    return get_json(DEMAS_BASE_URL + DEMAS_SWAGGER_PATH)


def declared_endpoints() -> dict[str, str]:
    """``endpoint path -> source name`` for every DEMAS endpoint ``curation/intake.yml`` reads (the used origin or its
    ``compare`` origin)."""
    from ..intake import _origin, declared_sources

    out: dict[str, str] = {}
    for name, spec in declared_sources().items():
        for which in ("origin", "compare"):
            origin = _origin(spec, which)
            if origin.get("kind") == "api" and origin.get("endpoint") and origin.get("base") == DEMAS_BASE_URL:
                out.setdefault(str(origin["endpoint"]), name)
    return out


def parse_spec(spec: dict[str, Any]) -> list[Endpoint]:
    """Read Swagger 2.0 or OpenAPI 3 into a uniform endpoint list."""
    definitions = spec.get("definitions") or (spec.get("components") or {}).get("schemas") or {}

    def resolve(node: Any, depth: int = 0) -> Any:
        if depth > 6 or not isinstance(node, dict):
            return node
        ref = node.get("$ref")
        if isinstance(ref, str):
            key = ref.rsplit("/", 1)[-1]
            return resolve(definitions.get(key, {}), depth + 1)
        return node

    out: list[Endpoint] = []
    for path, operations in (spec.get("paths") or {}).items():
        if not isinstance(operations, dict):
            continue
        for method, operation in operations.items():
            if method.lower() not in {"get", "post"} or not isinstance(operation, dict):
                continue
            responses = operation.get("responses") or {}
            ok = responses.get("200") or responses.get(200) or {}
            schema = ok.get("schema")
            if schema is None:
                content = (ok.get("content") or {}).get("application/json") or {}
                schema = content.get("schema")
            resolved = resolve(schema) if schema else None
            if isinstance(resolved, dict) and resolved.get("type") == "array":
                resolved = resolve(resolved.get("items"))
            out.append(
                Endpoint(
                    path=path,
                    method=method.upper(),
                    summary=str(operation.get("summary") or operation.get("description") or "").strip(),
                    tags=[str(t) for t in (operation.get("tags") or [])],
                    parameters=[resolve(p) for p in (operation.get("parameters") or [])],
                    response_schema=resolved if isinstance(resolved, dict) else None,
                )
            )
    return out


def persist_spec(catalog: CatalogStore, spec: dict[str, Any], endpoints: Sequence[Endpoint]) -> int:
    version = str((spec.get("info") or {}).get("version") or "unknown")
    catalog.executemany(
        """
        INSERT INTO api_endpoints (path, method, summary, tags, params_json, schema_json, spec_version, fetched_at)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(path) DO UPDATE SET
            method=excluded.method, summary=excluded.summary, tags=excluded.tags,
            params_json=excluded.params_json, schema_json=excluded.schema_json,
            spec_version=excluded.spec_version, fetched_at=excluded.fetched_at
        """,
        [
            (
                e.path, e.method, e.summary, ",".join(e.tags),
                json.dumps(e.parameters, ensure_ascii=False, default=str),
                json.dumps(e.response_schema, ensure_ascii=False, default=str),
                version, utcnow(),
            )
            for e in endpoints
        ],
    )
    return len(endpoints)


def resolve_endpoint(endpoints: Sequence[Endpoint], wanted: str) -> Endpoint | None:
    """Exact match, then a tolerant match on the last path segment.

    The brief's endpoint list was written against an earlier spec version. Rather
    than fail on a renamed path, match what is actually served and let the caller
    record the rename.
    """
    by_path = {e.path: e for e in endpoints}
    if wanted in by_path:
        return by_path[wanted]
    tail = wanted.rstrip("/").rsplit("/", 1)[-1]
    candidates = [e for e in endpoints if e.path.rstrip("/").endswith(tail)]
    if candidates:
        return candidates[0]
    tokens = {t for t in tail.split("-") if len(t) > 3}
    if tokens:
        scored = [
            (len(tokens & {t for t in e.path.replace("/", "-").split("-") if len(t) > 3}), e)
            for e in endpoints
        ]
        scored.sort(key=lambda kv: -kv[0])
        if scored and scored[0][0] >= max(2, len(tokens) // 2):
            return scored[0][1]
    return None


def reconciliation_targets(catalog: CatalogStore) -> list[dict[str, object]]:
    """FTP systems and API endpoints covering the same base (§11 design rule)."""
    out: list[dict[str, object]] = []
    for system, path in RECONCILIATION_PAIRS:
        ftp_present = catalog.count("files", "path LIKE ?", (f"%/{system}/%",)) > 0
        api_present = catalog.count("api_endpoints", "path = ?", (path,)) > 0
        out.append(
            {
                "system": system,
                "endpoint": path,
                "ftp_available": ftp_present,
                "api_available": api_present,
                "comparable": ftp_present and api_present,
            }
        )
    return out
