"""The one transport for every byte that is not on the DATASUS FTP tree (ADR-0188).

A reader of an API, a file, a table or a cloud record never opens a connection of its own: it calls `get_json`, `get_text`,
`request` (any answer held in memory), `read_range` (a byte range of a remote file) or `download` (a file streamed to disk
and resumed). They share, so a server is treated the same whoever asks:

* **One client.** HTTP/1.1 over IPv4, the operating system's trust store, redirects followed, a browser User-Agent. The trust
  store is the system's, as `urllib`'s was: IBGE and INEP serve a certificate chain the bundled `certifi` roots reject
  (`servicodados.ibge.gov.br`: "unable to get local issuer certificate"; INEP: a reset), so `fetch_municipalities` failed
  after 77 s of retries. IPv4 only: from this network `zenodo.org` answers 403 over IPv6 and serves over IPv4, which failed
  every BR-DWGD read (``PEGASUS_IPV6=1`` lets the system choose).
* **One politeness.** At most one request per `INTERVAL` to a host (reserved under a lock, so threads share the schedule;
  ``interval=0`` for a caller that is throttled by the server itself, as BR-DWGD's ranged reads are by Zenodo's 429).
* **One classification.** A reset, a timeout, a truncated body, 408/425/429 and 5xx are transient and retried with
  backoff (the server's ``Retry-After`` honoured); any other 4xx raises `SourceAbsent` at once (the thing asked for is not
  there: a month not yet published waited 195 s and stopped the source); a certificate that does not verify is not
  transient either. A caller whose server answers some 5xx for a request it will never serve (SIDRA's 500) passes ``retry_on``.
* **One resume rule.** A partial file is continued with ``Range`` guarded by ``If-Range`` (the ETag or Last-Modified saved
  beside it); a 416 is "already complete" only when the server's length equals what is held; a partial file without a
  validator that is older than `RESUME_WINDOW` is discarded, never spliced onto what is served now.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx

__all__ = ["BROWSER_AGENT", "INTERVAL", "RESUME_WINDOW", "SourceAbsent", "download", "get_json", "get_text", "read_range", "request", "retryable"]

#: Government servers reset connections from clients that do not look like a browser (INEP, INMET), and drop long transfers at random.
BROWSER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0 Safari/537.36"
#: Seconds between two requests to one host.
INTERVAL = 1.1
#: Statuses that mean "try again": the request timed out, the server is busy, the server failed. Every other 4xx says the
#: URL has no such thing, and asking again does not change that.
RETRYABLE = frozenset({408, 425, 429})
#: A ``.part`` with no validator (ETag, Last-Modified) older than this is not resumed: nothing says it is the file now served.
RESUME_WINDOW = 600.0
#: The longest a ``Retry-After`` is obeyed.
RETRY_AFTER_CAP = 120.0

_client_lock = threading.Lock()
_clients: list[httpx.Client] = []
_slots: dict[str, float] = {}
_slots_lock = threading.Lock()


class SourceAbsent(ConnectionError):
    """The server answered, and what was asked for is not there (a 4xx other than a timeout or a throttle): a gap to record,
    not an outage to retry. ``body`` holds the first bytes of the answer, for a caller that reports the server's words."""

    def __init__(self, url: str, status: int, note: str = "", body: str = "") -> None:
        super().__init__(f"{url}: HTTP {status}" + (f" ({note})" if note else ""))
        self.url, self.status, self.body = url, status, body


def retryable(status: int) -> bool:
    return status in RETRYABLE or status >= 500


class _Restart(Exception):
    """The bytes held belong to another version of the file: discard them and read from the start."""


class _Short(Exception):
    """A body shorter than the server announced."""


def _client() -> httpx.Client:
    with _client_lock:
        if not _clients:
            transport = httpx.HTTPTransport(verify=ssl.create_default_context(),
                                            local_address=None if os.environ.get("PEGASUS_IPV6") else "0.0.0.0")
            _clients.append(httpx.Client(transport=transport, headers={"User-Agent": BROWSER_AGENT}, follow_redirects=True, timeout=120))
        return _clients[0]


def _wait(url: str, interval: float) -> None:
    """Sleep until this host's next free slot (one request per ``interval``), reserving the slot under a lock."""
    if interval <= 0:
        return
    host = urlsplit(url).netloc
    with _slots_lock:
        now = time.monotonic()
        slot = max(now, _slots.get(host, 0.0))
        _slots[host] = slot + interval
    if slot > now:
        time.sleep(slot - now)


def _backoff(attempt: int, response: httpx.Response | None = None) -> float:
    """Seconds before the next attempt: 5, 10, 20, 40, 60... or what the server asked (``Retry-After``, capped)."""
    asked = 0.0
    if response is not None:
        try:
            asked = min(RETRY_AFTER_CAP, float(response.headers.get("Retry-After") or 0))
        except ValueError:
            asked = 0.0
    return max(asked, min(60.0, 5.0 * 2 ** attempt))


def _certificate_failure(exc: Exception) -> bool:
    """A certificate that does not verify says nothing about the server's load: retrying only waits."""
    return isinstance(exc.__cause__, ssl.SSLCertVerificationError) or "CERTIFICATE_VERIFY_FAILED" in str(exc)


def request(url: str, *, method: str = "GET", params: dict[str, Any] | None = None, content: bytes | None = None,
            headers: dict[str, str] | None = None, retries: int = 4, timeout: float = 120.0, interval: float = INTERVAL,
            retry_on: Callable[[int], bool] = retryable) -> httpx.Response:
    """An answer held in memory (``retries`` more tries on a transient failure, ``retry_on`` saying which statuses are one).
    Any other status of 400 or more raises `SourceAbsent`; a failure that outlasts the tries raises `ConnectionError`."""
    client = _client()
    last: Exception | None = None
    for attempt in range(retries + 1):
        _wait(url, interval)
        response = None
        try:
            response = client.request(method, url, params=params, content=content, headers=headers, timeout=timeout)
        except httpx.TransportError as exc:
            if _certificate_failure(exc):
                raise ConnectionError(f"{url}: the server's certificate does not verify: {exc}") from exc
            last = exc
        else:
            if response.status_code < 400:
                return response
            if not retry_on(response.status_code):
                raise SourceAbsent(str(response.url), response.status_code, body=response.text[:200])
            last = ConnectionError(f"HTTP {response.status_code}")
        if attempt < retries:
            time.sleep(_backoff(attempt, response))
    raise ConnectionError(f"{url}: {retries + 1} attempts failed; last: {last}") from last


def get_json(url: str, params: dict[str, Any] | None = None, retries: int = 4, **options: Any) -> Any:
    """GET json."""
    return request(url, params=params, headers={"Accept": "application/json"}, retries=retries, **options).json()


def get_text(url: str, params: dict[str, Any] | None = None, retries: int = 4, **options: Any) -> str:
    """GET a text body (a source file read whole)."""
    return request(url, params=params, retries=retries, **options).text


def read_range(url: str, start: int | None = None, end: int | None = None, *, suffix: int | None = None, attempts: int = 10,
               timeout: float = 180.0, interval: float = 0.0) -> tuple[bytes, int]:
    """Bytes ``start``..``end`` (inclusive) of ``url``, or the last ``suffix`` bytes, and the size of the whole file. A body
    shorter than the range is an error, never a short answer. ``interval`` defaults to none: the ranges of one file are read
    several at once, and the server (Zenodo) throttles by itself with a 429 and a ``Retry-After``."""
    span = f"bytes=-{suffix}" if suffix else f"bytes={start}-{end}"
    response = request(url, headers={"Range": span, "Accept-Encoding": "identity"}, retries=attempts - 1, timeout=timeout, interval=interval)
    body = response.content
    if suffix is None and len(body) != end - start + 1:  # type: ignore[operator]
        raise ConnectionError(f"{url} {span}: {len(body)} bytes came back")
    return body, int(response.headers.get("Content-Range", "bytes 0-0/0").rsplit("/", 1)[-1])


def _validator(headers: httpx.Headers) -> str | None:
    """What identifies this version of the file for ``If-Range``: a strong ETag, else Last-Modified."""
    etag = headers.get("ETag")
    return etag if etag and not etag.startswith("W/") else headers.get("Last-Modified")


def download(url: str, destination: str | Path, *, timeout: float = 1800.0, attempts: int = 6, interval: float = INTERVAL) -> Path:
    """A URL streamed to ``destination`` (a file never held in memory), resumed from the bytes already on disk (HTTP Range,
    guarded by ``If-Range`` with the validator saved beside the partial file) when the connection drops, which government
    servers do at random; an existing ``destination`` is kept.

    One reset mid-transfer is not an outage; repeated failures are reported with the last error (CLAUDE.md: "unreachable" is a
    finding, not a guess). A truncated body is retried too: MIDR's 86 MB S2iD CSV, served at ~320 KB/s, failed on its first
    reset (2026-10-04). Only resets, timeouts, 408/425/429 and 5xx are retried: any other 4xx raises `SourceAbsent` at once.
    A 416 is "already complete" only when the server's ``Content-Range: bytes */N`` says N is what is held; otherwise the
    partial file is discarded. A partial file with no validator that is older than `RESUME_WINDOW` is discarded, never
    spliced onto what the server serves now. The partial file is ``<destination>.part`` (its validator ``.part.json``).
    """
    destination = Path(destination)
    if destination.is_file():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + ".part")
    meta = destination.with_name(destination.name + ".part.json")
    client = _client()

    def discard() -> None:
        part.unlink(missing_ok=True)
        meta.unlink(missing_ok=True)

    def finish() -> Path:
        part.replace(destination)
        meta.unlink(missing_ok=True)
        return destination

    last: Exception | None = None
    for attempt in range(attempts):
        have = part.stat().st_size if part.is_file() else 0
        held: str | None = None
        if have:
            try:
                held = json.loads(meta.read_text(encoding="utf8")).get("validator") if meta.is_file() else None
            except (OSError, ValueError):
                held = None
            if held is None and time.time() - part.stat().st_mtime > RESUME_WINDOW:
                discard()
                have = 0
        headers = {"Accept-Encoding": "identity"}
        if have:
            headers["Range"] = f"bytes={have}-"
            if held:
                headers["If-Range"] = held
        answer: httpx.Response | None = None
        _wait(url, interval)
        try:
            with client.stream("GET", url, headers=headers, timeout=timeout) as response:
                answer = response
                status = response.status_code
                if status == 416 and have:
                    total = re.fullmatch(r"bytes \*/(\d+)", response.headers.get("Content-Range") or "")
                    if total and int(total.group(1)) == have:
                        return finish()         # the range starts at the end and the length matches: the file was complete
                    discard()                   # a replacement of another length (or no length stated): start again
                    last = ConnectionError(f"HTTP 416 for {have} bytes held")
                    continue
                if status >= 400:
                    response.read()
                    if not retryable(status):
                        raise SourceAbsent(url, status, body=response.text[:200])
                    last = ConnectionError(f"HTTP {status}")
                else:
                    validator = _validator(response.headers)
                    if have and status == 206:
                        start = re.match(r"bytes (\d+)-", response.headers.get("Content-Range") or "")
                        if (start and int(start.group(1)) != have) or (held and validator and validator != held):
                            raise _Restart      # a server that ignores If-Range served another version's tail
                    elif have:
                        have = 0                # the range was ignored or the validator changed: the whole body follows
                    if not have:
                        meta.unlink(missing_ok=True)
                        if validator:
                            meta.write_text(json.dumps({"validator": validator}), encoding="utf8")
                    length = response.headers.get("Content-Length")
                    expected = int(length) + have if length else None
                    with part.open("ab" if have else "wb") as out:
                        for chunk in response.iter_raw():
                            out.write(chunk)
                    if expected is not None and part.stat().st_size < expected:
                        raise _Short(f"{part.stat().st_size} of {expected} bytes")
                    return finish()
        except _Restart:
            discard()
            last = ConnectionError(f"{url}: the partial file belongs to another version; restarted")
            continue
        except (httpx.TransportError, _Short) as exc:    # resets and truncations
            if isinstance(exc, httpx.TransportError) and _certificate_failure(exc):
                raise ConnectionError(f"{url}: the server's certificate does not verify: {exc}") from exc
            last = exc
        if attempt < attempts - 1:
            time.sleep(_backoff(attempt, answer))
    raise ConnectionError(f"{url}: {attempts} attempts failed ({part.stat().st_size if part.is_file() else 0} bytes received); last: {last}") from last
