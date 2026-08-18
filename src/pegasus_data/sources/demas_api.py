"""DEMAS open-data API adapter (§11).

Base ``https://apidadosabertos.saude.gov.br``, OpenAPI document at
``/static/swagger.json``. The spec is **fetched and persisted at ingestion time**:
it is machine-readable field metadata and feeds the ledger at higher confidence
than PDF harvesting.

Measured 2026-08: the live document is Swagger 2.0, ``version 1.8.32``, exposing
**87 paths**. Several endpoint names in the architecture brief no longer resolve
— the Previne Brasil ones in particular — so :func:`resolve_endpoint` matches by
fuzzy path and records what it could not find as an open question instead of
failing silently or, worse, hitting a 404 and recording an empty result as data.

The adapter is a *source*, not a special case: it lands in the same lake, with
the same ledger and dictionary treatment. Where the API and the FTP cover the
same base, both are ingested and :func:`reconciliation_targets` names the pairs
worth comparing — divergence between them is itself a finding worth publishing.
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from typing import Any

import httpx
import pyarrow as pa

from ..catalog.store import Catalog, utcnow
from ..config import DEMAS_BASE_URL, DEMAS_SWAGGER_PATH

#: Endpoints the companion research plan actually needs, with why. Kept here so a
#: missing one is a visible gap rather than an unnoticed absence.
PRIORITY_ENDPOINTS: dict[str, str] = {
    "/daf/estoque-medicamentos-bnafar-horus": (
        "medication stock (BNAFAR/Hórus) — the only face that can see a chronic "
        "patient before decompensation; nothing equivalent exists on the FTP"
    ),
    "/macrorregiao-e-regiao-de-saude/municipio": (
        "official município → região de saúde crosswalk; there is no clean copy "
        "of this on the FTP, and it is the level at which small counts stop being noise"
    ),
    "/assistencia-a-saude/hospitais-e-leitos": "beds and facilities; corroborates CNES",
    "/sisvan/estado-nutricional": "nutritional status by município — obesity proxy",
    "/arboviroses/dengue": "aggregated dengue by year and município; a cross-validation target",
    "/arboviroses/chikungunya": "aggregated chikungunya; cross-validation",
    "/arboviroses/zikavirus": "aggregated zika; cross-validation",
    "/cnes/estabelecimentos": "establishment register; corroborates CNES on the FTP",
}

#: Endpoints the brief names that may have been superseded. Checked, not assumed.
BRIEF_ENDPOINTS_TO_VERIFY: tuple[str, ...] = (
    "/atencao-primaria/cadastro-vinculado-programa-previne-brasil",
    "/atencao-primaria/indicador-desempenho-programa-previne-brasil",
    "/vigilancia-e-meio-ambiente/sistema-de-informacao-sobre-mortalidade",
    "/vigilancia-e-meio-ambiente/sistema-de-informacao-sobre-nascidos-vivos",
)

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

    @property
    def paginated(self) -> bool:
        names = {str(p.get("name", "")).lower() for p in self.parameters}
        return bool(names & {"limit", "offset", "page", "pagina"})

    def field_names(self) -> list[str]:
        schema = self.response_schema or {}
        props = schema.get("properties") or {}
        if not props and schema.get("items"):
            props = (schema["items"] or {}).get("properties") or {}
        return sorted(props)


class DemasClient:
    """Thin, polite client. The API is public and unauthenticated."""

    def __init__(
        self,
        base_url: str = DEMAS_BASE_URL,
        *,
        timeout: float = 60.0,
        min_interval: float = 0.25,
        user_agent: str = "pegasus-data/0.1 (+public health research)",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.min_interval = min_interval
        self._last_call = 0.0
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> DemasClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_call = time.time()

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self._throttle()
        response = self._client.get(f"{self.base_url}{path}", params=params or {})
        response.raise_for_status()
        return response.json()

    def swagger(self) -> dict[str, Any]:
        self._throttle()
        response = self._client.get(f"{self.base_url}{DEMAS_SWAGGER_PATH}")
        response.raise_for_status()
        return response.json()


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


def persist_spec(catalog: Catalog, spec: dict[str, Any], endpoints: Sequence[Endpoint]) -> int:
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


def fetch_all(
    client: DemasClient,
    endpoint: Endpoint,
    *,
    params: dict[str, Any] | None = None,
    page_size: int = 100,
    max_pages: int = 200,
) -> Iterator[list[dict[str, Any]]]:
    """Yield pages of rows, following the API's limit/offset convention."""
    base = dict(params or {})
    if not endpoint.paginated:
        payload = client.get(endpoint.path, base)
        yield _rows_from(payload)
        return
    offset = 0
    for _ in range(max_pages):
        page_params = {**base, "limit": page_size, "offset": offset}
        payload = client.get(endpoint.path, page_params)
        rows = _rows_from(payload)
        if not rows:
            return
        yield rows
        if len(rows) < page_size:
            return
        offset += page_size


def _rows_from(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if isinstance(payload, dict):
        for key in ("dados", "data", "items", "results", "registros", "content"):
            value = payload.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
        arrays = [v for v in payload.values() if isinstance(v, list) and any(isinstance(x, dict) for x in v)]
        if arrays:
            return [r for r in max(arrays, key=len) if isinstance(r, dict)]
        return [payload]
    return []


def rows_to_table(rows: Sequence[dict[str, Any]]) -> pa.Table:
    """Everything to string, matching the FTP readers: the profiler wants raw tokens."""
    names: list[str] = []
    for row in rows[:2000]:
        for key in row:
            upper = str(key).upper()
            if upper not in names:
                names.append(upper)
    lower_for = {n: n.lower() for n in names}
    columns = {}
    for name in names:
        low = lower_for[name]
        values: list[str | None] = []
        for row in rows:
            value = row.get(name, row.get(low))
            if value is None:
                values.append(None)
            elif isinstance(value, str):
                values.append(value)
            elif isinstance(value, (int, float, bool)):
                values.append(str(value))
            else:
                values.append(json.dumps(value, ensure_ascii=False, default=str))
        columns[name] = pa.array(values, type=pa.string())
    return pa.table(columns)


def reconciliation_targets(catalog: Catalog) -> list[dict[str, object]]:
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
