"""External sources beside DATASUS (IBGE, INMET, S2iD, ANS, INEP, TabNet, ...)."""

from __future__ import annotations

import time
import urllib.request

#: Government servers reset connections from clients that do not look like a
#: browser, and drop long transfers at random (INEP, 2026-10-04).
BROWSER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def fetch_url(url: str, *, timeout: float = 1800.0, attempts: int = 4, agent: str = BROWSER_AGENT) -> bytes:
    """A URL's bytes, retried with backoff when the connection drops.

    One reset mid-transfer is not an outage; four in a row are reported with
    the last error (CLAUDE.md: "unreachable" is a finding, not a guess).
    """
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": agent})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read()
        except (OSError, urllib.error.URLError) as exc:   # ConnectionResetError is an OSError
            last = exc
            time.sleep(min(60.0, 5.0 * 2 ** attempt))
    raise ConnectionError(f"{url}: {attempts} attempts failed; last: {last}") from last
