"""External sources beside DATASUS (IBGE, INMET, S2iD, ANS, INEP, TabNet, ...)."""

from __future__ import annotations

import http.client
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

#: Government servers reset connections from clients that do not look like a
#: browser, and drop long transfers at random (INEP, 2026-10-04).
BROWSER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
#: Statuses that mean "try again": the request timed out, the server is busy, the server failed. Every other 4xx says the
#: URL has no such thing, and asking again does not change that.
RETRYABLE = frozenset({408, 425, 429})
#: A ``.part`` with no validator (ETag, Last-Modified) older than this is not resumed: nothing says it is the file now served.
RESUME_WINDOW = 600.0


class SourceAbsent(ConnectionError):
    """The server answered, and what was asked for is not there (a 4xx other than a timeout or a throttle): a gap to record,
    not an outage to retry."""

    def __init__(self, url: str, status: int, note: str = "") -> None:
        super().__init__(f"{url}: HTTP {status}" + (f" ({note})" if note else ""))
        self.url, self.status = url, status


def retryable(status: int) -> bool:
    return status in RETRYABLE or status >= 500


class _Restart(Exception):
    """The bytes held belong to another version of the file: discard them and read from the start."""


def _validator(headers: http.client.HTTPMessage) -> str | None:
    """What identifies this version of the file for ``If-Range``: a strong ETag, else Last-Modified."""
    etag = headers.get("ETag")
    return etag if etag and not etag.startswith("W/") else headers.get("Last-Modified")


def download(url: str, destination: str | Path, *, timeout: float = 1800.0, attempts: int = 6, agent: str = BROWSER_AGENT) -> Path:
    """A URL streamed to ``destination`` (a file never held in memory), resumed from the bytes already on disk (HTTP Range,
    guarded by ``If-Range`` with the validator saved beside the partial file) when the connection drops, which government
    servers do at random; an existing ``destination`` is kept.

    One reset mid-transfer is not an outage; repeated failures are reported with the last error (CLAUDE.md: "unreachable" is a
    finding, not a guess). A truncated body (`http.client.IncompleteRead`, not an OSError) is retried too: MIDR's 86 MB S2iD
    CSV, served at ~320 KB/s, failed on its first reset (2026-10-04). Only resets, timeouts, 408/425/429 and 5xx are retried:
    any other 4xx raises `SourceAbsent` at once (a month not yet published waited 195 s and stopped the source). A 416 is
    "already complete" only when the server's ``Content-Range: bytes */N`` says N is what is held; otherwise the partial file
    is discarded. A partial file with no validator that is older than `RESUME_WINDOW` is discarded, never spliced onto what
    the server serves now. The partial file is ``<destination>.part`` (its validator ``.part.json``).
    """
    destination = Path(destination)
    if destination.is_file():
        return destination
    destination.parent.mkdir(parents=True, exist_ok=True)
    part = destination.with_name(destination.name + ".part")
    meta = destination.with_name(destination.name + ".part.json")

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
        headers = {"User-Agent": agent}
        if have:
            headers["Range"] = f"bytes={have}-"
            if held:
                headers["If-Range"] = held
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as response:
                validator = _validator(response.headers)
                if have and response.status == 206:
                    start = re.match(r"bytes (\d+)-", response.headers.get("Content-Range") or "")
                    if (start and int(start.group(1)) != have) or (held and validator and validator != held):
                        raise _Restart          # a server that ignores If-Range served another version's tail
                elif have:
                    have = 0                    # the range was ignored or the validator changed: the whole body follows
                if not have:
                    meta.unlink(missing_ok=True)
                    if validator:
                        meta.write_text(json.dumps({"validator": validator}), encoding="utf8")
                length = response.headers.get("Content-Length")
                expected = int(length) + have if length else None
                with part.open("ab" if have else "wb") as out:
                    while chunk := response.read(1 << 20):
                        out.write(chunk)
            if expected is not None and part.stat().st_size < expected:
                raise http.client.IncompleteRead(b"", expected - part.stat().st_size)
            return finish()
        except _Restart:
            discard()
            last = ConnectionError(f"{url}: the partial file belongs to another version; restarted")
            continue
        except urllib.error.HTTPError as exc:
            if exc.code == 416 and have:
                total = re.fullmatch(r"bytes \*/(\d+)", exc.headers.get("Content-Range") or "") if exc.headers else None
                if total and int(total.group(1)) == have:
                    return finish()             # the range starts at the end and the length matches: the file was complete
                discard()                       # a replacement of another length (or no length stated): start again
                last = exc
                continue
            if not retryable(exc.code):
                raise SourceAbsent(url, exc.code) from exc
            last = exc
        except (OSError, urllib.error.URLError, http.client.HTTPException) as exc:   # resets and truncations
            last = exc
        if attempt < attempts - 1:
            time.sleep(min(60.0, 5.0 * 2 ** attempt))
    raise ConnectionError(f"{url}: {attempts} attempts failed ({part.stat().st_size if part.is_file() else 0} bytes received); last: {last}") from last
