"""External sources beside DATASUS (IBGE, INMET, S2iD, ANS, INEP, TabNet, ...)."""

from __future__ import annotations

import http.client
import time
import urllib.error
import urllib.request
from pathlib import Path

#: Government servers reset connections from clients that do not look like a
#: browser, and drop long transfers at random (INEP, 2026-10-04).
BROWSER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"


def download(url: str, destination: str | Path, *, timeout: float = 1800.0, attempts: int = 6, agent: str = BROWSER_AGENT) -> Path:
    """A URL streamed to ``destination`` (a file never held in memory), resumed from the bytes already on disk (HTTP Range)
    when the connection drops, which government servers do at random; an existing ``destination`` is kept.

    One reset mid-transfer is not an outage; repeated failures are reported with the last error (CLAUDE.md: "unreachable" is a
    finding, not a guess). A truncated body (`http.client.IncompleteRead`, not an OSError) is retried too: MIDR's 86 MB S2iD
    CSV, served at ~320 KB/s, failed on its first reset (2026-10-04). The partial file is ``<destination>.part``.
    """
    destination = Path(destination)
    if destination.is_file():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + ".part")
    last: Exception | None = None
    for attempt in range(attempts):
        have = part.stat().st_size if part.is_file() else 0
        headers = {"User-Agent": agent}
        if have:
            headers["Range"] = f"bytes={have}-"
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
                if have and response.status != 206:
                    have = 0                                   # the server ignored the range: start over
                length = response.headers.get("Content-Length")
                expected = int(length) + have if length else None
                with part.open("ab" if have else "wb") as out:
                    while chunk := response.read(1 << 20):
                        out.write(chunk)
            if expected is not None and part.stat().st_size < expected:
                raise http.client.IncompleteRead(b"", expected - part.stat().st_size)
            part.replace(destination)
            return destination
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and have:                       # the range starts at the end: the file was complete
                part.replace(destination)
                return destination
            last = exc
        except (OSError, urllib.error.URLError, http.client.HTTPException) as exc:   # resets and truncations
            last = exc
        time.sleep(min(60.0, 5.0 * 2 ** attempt))
    raise ConnectionError(f"{url}: {attempts} attempts failed ({part.stat().st_size if part.is_file() else 0} bytes received); last: {last}") from last


def fetch_url(url: str, *, timeout: float = 1800.0, attempts: int = 6, agent: str = BROWSER_AGENT) -> bytes:
    """A URL's bytes (`download` through a temporary file, so the same retries and resumption)."""
    import tempfile

    with tempfile.TemporaryDirectory() as folder:
        return download(url, Path(folder) / "body", timeout=timeout, attempts=attempts, agent=agent).read_bytes()
