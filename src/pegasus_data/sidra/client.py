"""The one door to IBGE's aggregates API (v3): polite, cached, and honest about what came back.

Everything that talks to SIDRA goes through ``SidraClient.get``. It is sequential and paced (the
server is shared), sends a browser User-Agent, and keeps every response it receives on disk with its
provenance, so a run that stops resumes without a request and a figure can be traced to the bytes
it came from.

What the server does, as measured (DATA_SOURCES, "SIDRA's limits"), is handled here and nowhere else:

- a body that starts with ``<`` is the firewall's "Request Rejected" page answered with HTTP 200: it
  is an error (`SidraRejected`), never data and never cached as data;
- gzip arrives without ``Content-Encoding`` and is read by its magic bytes;
- HTTP 500 means a request the server will not serve (too many values, or ID lists too long): it is
  raised as `SidraRefused` for the planner to split, not retried unchanged;
- a reset, a timeout or a body cut short (seen on table 1436 at 2.3 of 5.9 MB) is transient and is retried with backoff
  by `pegasus_data.transport`, the one client of every non-FTP byte.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..persist.kept import write_atomic, write_json_atomic
from ..transport import SourceAbsent, request

BASE = "https://servicodados.ibge.gov.br/api/v3/agregados"
LOCALIDADES = "https://servicodados.ibge.gov.br/api/v1/localidades"
#: The statuses worth asking again. HTTP 500 is not one: it means a request the server will not serve.
TRANSIENT = frozenset({429, 502, 503, 504})

__all__ = ["BASE", "SidraClient", "SidraError", "SidraRefused", "SidraRejected", "Response"]


class SidraError(RuntimeError):
    """A request SIDRA did not answer with data."""


class SidraRejected(SidraError):
    """The firewall's HTML page, answered with status 200 (URL of about 8 KB or more)."""


class SidraRefused(SidraError):
    """HTTP 4xx/5xx for a well-formed URL: the request is beyond what the server serves."""

    def __init__(self, status: int, url: str, body: str = "") -> None:
        super().__init__(f"HTTP {status} for {url[:200]}{'…' if len(url) > 200 else ''} {body[:120]}")
        self.status = status


@dataclass(frozen=True, slots=True)
class Response:
    """A parsed answer and where it came from."""

    payload: Any
    url: str
    from_cache: bool
    nbytes: int          # size of the body as received
    sha256: str
    fetched_at: str      # ISO-8601 UTC, of the original fetch
    seconds: float       # of the original fetch


class SidraClient:
    """Sequential, paced, cached access to the aggregates API.

    ``cache_dir`` holds ``<kind>/<sha256(url)[:2]>/<sha256(url)>.json.gz`` plus a ``.meta.json``
    sidecar (URL, status, bytes, body sha256, fetched_at, seconds). ``delay`` is the minimum gap
    between two requests that reach the network.
    """

    #: seconds to wait for an answer, by kind: metadata is a few KB (a hung request is a fault), values are megabytes
    TIMEOUTS = {"catalog": 120.0, "metadata": 60.0, "periods": 60.0, "localities": 90.0, "values": 300.0}

    def __init__(self, cache_dir: Path, *, delay: float = 0.3, attempts: int = 5) -> None:
        self.cache_dir = Path(cache_dir)
        self.delay = delay
        self.attempts = attempts
        self.network_requests = 0
        self.cache_hits = 0

    # -- cache -----------------------------------------------------------------------------------

    def _paths(self, kind: str, url: str) -> tuple[Path, Path]:
        key = hashlib.sha256(url.encode()).hexdigest()
        base = self.cache_dir / kind / key[:2]
        return base / f"{key}.json.gz", base / f"{key}.meta.json"

    def cached(self, kind: str, url: str) -> bool:
        return self._paths(kind, url)[0].exists()

    def _read_cache(self, kind: str, url: str) -> Response | None:
        body_path, meta_path = self._paths(kind, url)
        if not body_path.exists() or not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text("utf-8"))
        raw = gzip.decompress(body_path.read_bytes())
        self.cache_hits += 1
        return Response(json.loads(raw.decode("utf-8")), url, True, meta["bytes"], meta["sha256"],
                        meta["fetched_at"], meta["seconds"])

    def _write_cache(self, kind: str, url: str, raw: bytes, seconds: float) -> Response:
        body_path, meta_path = self._paths(kind, url)
        body_path.parent.mkdir(parents=True, exist_ok=True)
        sha = hashlib.sha256(raw).hexdigest()
        fetched_at = datetime.now(UTC).isoformat(timespec="seconds")
        write_atomic(body_path, lambda tmp: tmp.write_bytes(gzip.compress(raw, 6)))
        write_json_atomic({"url": url, "status": 200, "bytes": len(raw), "sha256": sha,
                           "fetched_at": fetched_at, "seconds": round(seconds, 3)}, meta_path)
        return Response(json.loads(raw.decode("utf-8")), url, False, len(raw), sha, fetched_at, seconds)

    # -- network ---------------------------------------------------------------------------------

    def _fetch(self, url: str, timeout: float) -> tuple[bytes, float]:
        started = time.monotonic()
        try:
            response = request(url, timeout=timeout, retries=self.attempts - 1, interval=self.delay, retry_on=TRANSIENT.__contains__)
        except SourceAbsent as exc:         # HTTP 500 and the other statuses SIDRA answers for a request it will not serve
            self.network_requests += 1
            raise SidraRefused(exc.status, url, exc.body) from exc
        except ConnectionError as exc:      # resets, timeouts, truncated bodies and throttles that outlasted the attempts
            raise SidraError(f"{url[:200]}: {self.attempts} attempts failed; last: {exc}") from exc
        self.network_requests += 1
        body = response.content
        if body[:2] == bytes((0x1F, 0x8B)):                  # gzip without Content-Encoding
            body = gzip.decompress(body)
        if body.lstrip()[:1] == b"<":
            raise SidraRejected(f"IBGE answered an HTML page with status 200 (the firewall): {url[:160]}…")
        return body, time.monotonic() - started

    def get(self, kind: str, url: str, *, refresh: bool = False) -> Response:
        """``url``'s JSON; from the cache unless ``refresh``. ``kind`` names the cache folder
        (``catalog``, ``metadata``, ``periods``, ``localities``, ``values``)."""
        if not refresh and (hit := self._read_cache(kind, url)) is not None:
            return hit
        raw, seconds = self._fetch(url, self.TIMEOUTS.get(kind, 300.0))
        try:
            return self._write_cache(kind, url, raw, seconds)
        except json.JSONDecodeError as exc:
            raise SidraError(f"{url[:200]}: the body is not JSON ({raw[:80]!r})") from exc

    # -- the endpoints ---------------------------------------------------------------------------

    def catalog(self, **filters: str) -> Response:
        """``/agregados`` grouped by research; filters: nivel, assunto, periodicidade, periodo, classificacao."""
        query = "&".join(f"{k}={v}" for k, v in filters.items())
        return self.get("catalog", f"{BASE}?{query}" if query else BASE)

    def metadata(self, table: int | str, *, refresh: bool = False) -> Response:
        return self.get("metadata", f"{BASE}/{table}/metadados", refresh=refresh)

    def periods(self, table: int | str, *, refresh: bool = False) -> Response:
        return self.get("periods", f"{BASE}/{table}/periodos", refresh=refresh)

    def localities(self, table: int | str, level: str, *, refresh: bool = False) -> Response:
        return self.get("localities", f"{BASE}/{table}/localidades/{level}", refresh=refresh)

    def values_url(self, table: int | str, periods: str, variables: str, localities: str,
                   classification: str = "") -> str:
        url = f"{BASE}/{table}/periodos/{periods}/variaveis/{variables}?localidades={localities}"
        return url + (f"&classificacao={classification}" if classification else "")

    def values(self, url: str) -> Response:
        return self.get("values", url)
