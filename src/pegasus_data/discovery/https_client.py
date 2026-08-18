"""HTTPS mirror probe and client ([V]1 in the architecture brief).

The brief hypothesised that an HTTPS mirror of the same tree might exist, which
would restore ``Content-Length``/``Last-Modified`` and give keep-alive instead of
FTP's per-transfer data channel.

**Measured 2026-08:** ``ftp.datasus.gov.br`` accepts nothing on :80 or :443 — the
connections time out. There is no HTTPS mirror on that host. The metadata problem
the mirror was supposed to solve is solved instead by parsing the IIS MS-DOS
``LIST`` dialect (see ``listing.py``), which carries size and mtime directly, and
by ``SIZE``/``MDTM`` per file.

This module keeps the probe as a *runnable check* rather than a settled opinion,
because a mirror may appear later. ``probe_https_mirror`` writes its verdict into
``open_questions`` with the evidence attached, and ``HttpsClient`` is ready to
serve the crawl the moment a mirror answers.
"""

from __future__ import annotations

import hashlib
import socket
from dataclasses import dataclass, field

import httpx

#: Hosts worth trying, in order. The first is the FTP host itself; the others are
#: the public web faces DATASUS runs, which historically have *not* exposed
#: ``/dissemin`` but are cheap to check.
CANDIDATE_HOSTS: tuple[str, ...] = (
    "ftp.datasus.gov.br",
    "datasus.saude.gov.br",
    "arquivosdatasus.saude.gov.br",
)


@dataclass(slots=True)
class MirrorProbe:
    host: str
    reachable: bool
    status: int | None = None
    content_length: int | None = None
    last_modified: str | None = None
    sha256: str | None = None
    matches_ftp: bool | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "host": self.host,
            "reachable": self.reachable,
            "status": self.status,
            "content_length": self.content_length,
            "last_modified": self.last_modified,
            "sha256": self.sha256,
            "matches_ftp": self.matches_ftp,
            "error": self.error,
        }


@dataclass(slots=True)
class MirrorVerdict:
    available: bool
    host: str | None = None
    probes: list[MirrorProbe] = field(default_factory=list)

    def summary(self) -> str:
        if self.available:
            return f"HTTPS mirror available at {self.host}"
        reasons = "; ".join(f"{p.host}: {p.error or p.status}" for p in self.probes)
        return f"no HTTPS mirror reachable ({reasons})"


def _tcp_open(host: str, port: int, timeout: float = 8.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def probe_https_mirror(
    sample_paths: list[str],
    *,
    ftp_hashes: dict[str, str] | None = None,
    hosts: tuple[str, ...] = CANDIDATE_HOSTS,
    timeout: float = 20.0,
) -> MirrorVerdict:
    """Try each candidate host for the same tree.

    ``sample_paths`` are absolute FTP paths (``/dissemin/publicos/...``).
    ``ftp_hashes`` maps those paths to the SHA-256 of the payload fetched over
    FTP; when supplied, the probe compares payloads byte-for-byte, which is the
    verification procedure the brief specifies.
    """
    probes: list[MirrorProbe] = []
    for host in hosts:
        if not _tcp_open(host, 443):
            probes.append(MirrorProbe(host=host, reachable=False, error="tcp 443 unreachable"))
            continue
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                ok_host = False
                for path in sample_paths[:20]:
                    url = f"https://{host}{path}"
                    head = client.head(url)
                    if head.status_code >= 400:
                        probes.append(
                            MirrorProbe(host=host, reachable=True, status=head.status_code, error="not served")
                        )
                        break
                    body = client.get(url)
                    digest = hashlib.sha256(body.content).hexdigest()
                    expected = (ftp_hashes or {}).get(path)
                    probes.append(
                        MirrorProbe(
                            host=host,
                            reachable=True,
                            status=body.status_code,
                            content_length=int(head.headers.get("content-length", 0)) or None,
                            last_modified=head.headers.get("last-modified"),
                            sha256=digest,
                            matches_ftp=None if expected is None else (digest == expected),
                        )
                    )
                    ok_host = True
                if ok_host:
                    return MirrorVerdict(available=True, host=host, probes=probes)
        except Exception as exc:
            probes.append(MirrorProbe(host=host, reachable=True, error=f"{type(exc).__name__}: {exc}"))
    return MirrorVerdict(available=False, probes=probes)


class HttpsClient:
    """Fetch DATASUS paths over HTTPS when a mirror exists.

    Kept deliberately thin and interface-compatible with the parts of
    :class:`~pegasus_data.discovery.ftp_client.FtpClient` the fetcher uses, so
    swapping transports is a one-line change if a mirror appears.
    """

    def __init__(self, host: str, *, timeout: float = 60.0) -> None:
        self.host = host
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=16, max_connections=32),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> HttpsClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def stat(self, path: str) -> tuple[int | None, str | None]:
        r = self._client.head(f"https://{self.host}{path}")
        r.raise_for_status()
        length = r.headers.get("content-length")
        return (int(length) if length else None), r.headers.get("last-modified")

    def retrieve(self, path: str) -> bytes:
        r = self._client.get(f"https://{self.host}{path}")
        r.raise_for_status()
        return r.content
