"""External sources beside DATASUS (IBGE, INMET, S2iD, ANS, INEP, TabNet, ...)."""

from __future__ import annotations

import time
import urllib.request

#: Government servers reset connections from clients that do not look like a
#: browser, and drop long transfers at random (INEP, 2026-10-04).
BROWSER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def fetch_url(url: str, *, timeout: float = 1800.0, attempts: int = 6, agent: str = BROWSER_AGENT) -> bytes:
    """A URL's bytes, retried with backoff when the connection drops, resuming from the bytes
    already received (HTTP Range) where the server allows it.

    One reset mid-transfer is not an outage; repeated failures are reported with the last error
    (CLAUDE.md: "unreachable" is a finding, not a guess). A truncated body raises
    `http.client.IncompleteRead`, which is not an OSError: it was never retried, and MIDR's
    86 MB S2iD CSV, served at ~320 KB/s, failed on its first reset (2026-10-04).
    """
    import http.client

    buffer = bytearray()
    total: int | None = None
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            headers = {"User-Agent": agent}
            if buffer:
                headers["Range"] = f"bytes={len(buffer)}-"
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=timeout) as response:
                if buffer and response.status != 206:
                    buffer.clear()                     # the server ignored the range: start over
                if total is None or response.status == 200:
                    length = response.headers.get("Content-Length")
                    total = int(length) if length and response.status == 200 else total
                while True:
                    chunk = response.read(1 << 20)
                    if not chunk:
                        break
                    buffer.extend(chunk)
            if total is not None and len(buffer) < total:
                raise http.client.IncompleteRead(bytes(buffer), total - len(buffer))
            return bytes(buffer)
        except (OSError, urllib.error.URLError, http.client.HTTPException) as exc:   # resets and truncations
            last = exc
            time.sleep(min(60.0, 5.0 * 2 ** attempt))
    raise ConnectionError(f"{url}: {attempts} attempts failed ({len(buffer)} bytes received); last: {last}") from last
