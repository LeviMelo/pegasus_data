"""Protocol-adaptive FTP client with per-directory method escalation (D4, D6).

Two rules drive this module:

* **Escalate per directory, not once globally.** The prior scan benchmarked
  listing verbs once against the tree root, picked a winner, and used it
  everywhere. One global choice cannot represent a server whose behaviour varies
  by path, and a single global fallback to ``NLST`` destroyed metadata for the
  whole tree.
* **Every network operation is retried.** The server is slow and drops
  connections; transient failure is the normal case. A worker whose connection
  dies reconnects rather than aborting.
"""

from __future__ import annotations

import ftplib
import io
import socket
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime

from .listing import ListingEntry, normalize_path, parse_list_lines, parse_nlst

#: Ordered escalation ladder. MLSD first because where it exists it is the best
#: answer; LIST second because on IIS it is the *only* verb carrying metadata;
#: NLST last, because it carries none and forces content addressing.
LISTING_LADDER: tuple[str, ...] = ("mlsd", "list", "nlst")

_TRANSIENT = (
    ftplib.error_temp,
    ftplib.error_proto,
    ftplib.error_reply,
    socket.timeout,
    ConnectionResetError,
    ConnectionAbortedError,
    BrokenPipeError,
    EOFError,
    OSError,
)


class ListingUnavailable(RuntimeError):
    """Every listing verb failed for a directory."""

    def __init__(self, path: str, attempts: dict[str, str]) -> None:
        self.path = path
        self.attempts = attempts
        super().__init__(f"no listing method succeeded for {path}: {attempts}")


@dataclass(slots=True)
class ServerCapabilities:
    welcome: str = ""
    system: str = ""
    features: tuple[str, ...] = ()

    @property
    def has_mlsd(self) -> bool:
        return any(f.upper().startswith(("MLSD", "MLST")) for f in self.features)

    @property
    def has_size(self) -> bool:
        return any(f.upper().startswith("SIZE") for f in self.features)

    @property
    def has_mdtm(self) -> bool:
        return any(f.upper().startswith("MDTM") for f in self.features)

    @property
    def has_rest(self) -> bool:
        return any(f.upper().startswith("REST") for f in self.features)

    def preferred_ladder(self) -> tuple[str, ...]:
        """Skip verbs the server says it does not have — one round-trip saved per directory."""
        if self.has_mlsd:
            return LISTING_LADDER
        return tuple(m for m in LISTING_LADDER if m != "mlsd")


class FtpClient:
    """One FTP control connection, reconnecting on demand."""

    def __init__(
        self,
        host: str,
        *,
        timeout: int = 60,
        max_retries: int = 4,
        backoff_base: float = 1.5,
        user: str = "anonymous",
        password: str = "pegasus_data@example.org",
    ) -> None:
        self.host = host
        self.timeout = timeout
        self.max_retries = max_retries
        self.backoff_base = backoff_base
        self.user = user
        self.password = password
        self._ftp: ftplib.FTP | None = None
        self.capabilities = ServerCapabilities()
        self.method_hint: str | None = None

    # ------------------------------------------------------------- connection

    def connect(self) -> FtpClient:
        ftp = ftplib.FTP(timeout=self.timeout)
        ftp.connect(self.host)
        ftp.login(self.user, self.password)
        ftp.set_pasv(True)
        try:
            ftp.encoding = "latin-1"  # DATASUS filenames are not all ASCII
        except Exception:  # pragma: no cover - attribute always exists on 3.11
            pass
        self._ftp = ftp
        self._probe_capabilities()
        return self

    def _probe_capabilities(self) -> None:
        ftp = self._ftp
        if ftp is None:
            return
        welcome = ftp.getwelcome() or ""
        features: list[str] = []
        system = ""
        # FEAT and SYST are optional in RFC 959. A server that rejects them is
        # not broken, it is old, and DATASUS is old: absence of an answer IS the
        # answer, recorded as an empty capability set.
        try:
            raw = ftp.sendcmd("FEAT")
            features = [ln.strip() for ln in raw.splitlines()[1:-1] if ln.strip()]
        except Exception:  # noqa: BLE001 - unsupported command, not a failure
            pass
        try:
            system = ftp.sendcmd("SYST")
        except Exception:  # noqa: BLE001 - unsupported command, not a failure
            pass
        self.capabilities = ServerCapabilities(welcome, system, tuple(features))

    def close(self) -> None:
        if self._ftp is None:
            return
        # Closing a connection that is already gone is the normal case after a
        # timeout. QUIT is the polite exit; close() drops the socket regardless.
        # Neither failing tells the caller anything they can act on.
        try:
            self._ftp.quit()
        except Exception:  # noqa: BLE001 - already disconnected
            try:
                self._ftp.close()
            except Exception:  # noqa: BLE001 - socket is gone either way
                pass
        self._ftp = None

    def __enter__(self) -> FtpClient:
        return self.connect()

    def __exit__(self, *exc: object) -> None:
        self.close()

    @property
    def ftp(self) -> ftplib.FTP:
        if self._ftp is None:
            self.connect()
        assert self._ftp is not None
        return self._ftp

    def reconnect(self) -> None:
        self.close()
        self.connect()

    def _retrying(self, op: Callable[[], object], *, what: str) -> object:
        """Run `op`, reconnecting and backing off on transient failure.

        ``error_perm`` (5xx) is *not* transient: a 550 means the path is not
        there, and retrying it wastes the server's patience and ours.
        """
        last: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return op()
            except ftplib.error_perm:
                raise
            except _TRANSIENT as exc:
                last = exc
                if attempt == self.max_retries - 1:
                    break
                time.sleep(min(30.0, self.backoff_base ** (attempt + 1)))
                try:
                    self.reconnect()
                except Exception:  # noqa: BLE001 - the retry below re-reports it
                    pass
        raise RuntimeError(f"{what} failed after {self.max_retries} attempts: {last}") from last

    # ---------------------------------------------------------------- listing

    @contextmanager
    def _cwd(self, directory: str) -> Iterator[None]:
        original = self.ftp.pwd()
        self.ftp.cwd(directory)
        try:
            yield
        finally:
            # Restoring the working directory is a courtesy to the next caller.
            # If the connection died mid-listing there is nothing to restore to,
            # and the real error is already propagating out of the yield.
            try:
                self.ftp.cwd(original)
            except Exception:  # noqa: BLE001 - connection gone; real error is in flight
                pass

    def _mlsd(self, directory: str) -> list[ListingEntry]:
        rows: list[ListingEntry] = []
        for name, facts in self.ftp.mlsd(directory):
            if name in {".", ".."}:
                continue
            kind = facts.get("type")
            if kind in {"cdir", "pdir"}:
                continue
            modified = None
            raw = facts.get("modify")
            if raw and len(raw) >= 14:
                try:
                    modified = datetime.strptime(raw[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC).isoformat()
                except ValueError:
                    modified = None
            size_raw = facts.get("size")
            rows.append(
                ListingEntry(
                    name=name,
                    path=f"{normalize_path(directory)}/{name}",
                    is_dir=(kind == "dir") if kind in {"dir", "file"} else None,
                    size=int(size_raw) if size_raw and str(size_raw).isdigit() else None,
                    modified=modified,
                    method="MLSD",
                )
            )
        return rows

    def _list(self, directory: str) -> list[ListingEntry]:
        lines: list[str] = []
        self.ftp.retrlines(f"LIST {directory}", lines.append)
        if not lines:
            # An empty LIST is ambiguous on IIS: it can mean "empty" or "denied".
            # Re-issue it from inside the directory; if CWD fails we get a clean
            # 550 rather than a false "empty directory".
            with self._cwd(directory):
                lines = []
                self.ftp.retrlines("LIST", lines.append)
        return parse_list_lines(lines, directory)

    def _nlst(self, directory: str) -> list[ListingEntry]:
        return parse_nlst(self.ftp.nlst(directory), directory)

    def list_directory(
        self, directory: str, *, ladder: tuple[str, ...] | None = None
    ) -> tuple[list[ListingEntry], str]:
        """List one directory, escalating through the ladder.

        Returns ``(entries, method)``. The method that worked is returned so the
        caller can persist it per directory and reuse it as a hint next time.
        """
        directory = normalize_path(directory)
        order = list(ladder or self.capabilities.preferred_ladder())
        if self.method_hint and self.method_hint in order:
            order.remove(self.method_hint)
            order.insert(0, self.method_hint)
        impls = {"mlsd": self._mlsd, "list": self._list, "nlst": self._nlst}
        attempts: dict[str, str] = {}
        for method in order:
            impl = impls[method]
            try:
                entries = self._retrying(
                    lambda i=impl: i(directory), what=f"{method} {directory}"
                )
                assert isinstance(entries, list)
                if method == "nlst" and any(e.is_dir is None for e in entries):
                    entries = self._probe_types(entries)
                self.method_hint = method
                return entries, method
            except ftplib.error_perm as exc:
                attempts[method] = f"error_perm: {exc}"
                # A 550 from the first verb usually means the path is gone; but
                # IIS also 550s on LIST for some directories that NLST serves,
                # so we keep walking the ladder rather than giving up here.
            except Exception as exc:
                attempts[method] = f"{type(exc).__name__}: {exc}"
        raise ListingUnavailable(directory, attempts)

    def _probe_types(self, entries: list[ListingEntry]) -> list[ListingEntry]:
        """Resolve NLST's untyped entries with a CWD probe, one round-trip each."""
        original = self.ftp.pwd()
        for entry in entries:
            if entry.is_dir is not None:
                continue
            try:
                self.ftp.cwd(entry.path)
                entry.is_dir = True
            except Exception:
                entry.is_dir = False
            entry.flags.append("entry_type_probed")
        try:
            self.ftp.cwd(original)
        except Exception:  # noqa: BLE001 - courtesy restore; entries are already read
            pass
        return entries

    # ------------------------------------------------------------- per-file IO

    def size(self, path: str) -> int | None:
        if not self.capabilities.has_size:
            return None
        # None means "the server would not tell us", which is a legitimate
        # answer this crawler records rather than an error it hides: SIZE is
        # refused in ASCII mode and on some directories.
        try:
            return self.ftp.size(path)
        except Exception:  # noqa: BLE001 - unknown size is a real state
            return None

    def modified_time(self, path: str) -> str | None:
        if not self.capabilities.has_mdtm:
            return None
        try:
            reply = self.ftp.sendcmd(f"MDTM {path}")
        except Exception:  # noqa: BLE001 - unknown mtime is a real state
            return None
        stamp = reply.split()[-1]
        if len(stamp) < 14:
            return None
        try:
            return datetime.strptime(stamp[:14], "%Y%m%d%H%M%S").replace(tzinfo=UTC).isoformat()
        except ValueError:
            return None

    def stat(self, path: str) -> tuple[int | None, str | None]:
        """``SIZE``/``MDTM`` for one path — the per-file rescue when a listing is unavailable."""
        return self.size(path), self.modified_time(path)

    def retrieve_prefix(self, path: str, max_bytes: int) -> bytes:
        """Download only the first ``max_bytes`` of a file.

        A DBF — and a ``.dbc``, whose DBF header is stored uncompressed ahead of
        the compressed payload — declares its entire schema in a header of a few
        hundred bytes. Reading 1,153 bytes of a 92 KB file yields all 35 field
        names, types and widths; reading the file yields nothing more about its
        *shape*. Across the tree that is the difference between 183 GiB and about
        17 MB, which is the difference between cataloguing every schema and not.

        The transfer is stopped by closing the data socket, then ``ABOR`` and a
        drained response. Skipping that drain is how the control channel ends up
        one reply out of step, so the *next* command reads this transfer's
        completion message and every command after it is answered by the one
        before — a failure that shows up far from its cause.
        """
        def _once() -> bytes:
            conn = self.ftp.transfercmd(f"RETR {path}")
            buf = io.BytesIO()
            try:
                conn.settimeout(self.timeout)
                while buf.tell() < max_bytes:
                    chunk = conn.recv(min(1 << 16, max_bytes - buf.tell()))
                    if not chunk:
                        break
                    buf.write(chunk)
            finally:
                conn.close()
            self._drain_after_partial()
            return buf.getvalue()[:max_bytes]

        data = self._retrying(_once, what=f"RETR(prefix) {path}")
        assert isinstance(data, bytes)
        return data

    def _drain_after_partial(self) -> None:
        """Resynchronise the control channel after an abandoned transfer.

        The server may reply 226 (it finished sending a small file before we
        stopped reading), or 426/226 for a genuine abort. Either way the replies
        are consumed here; anything unexpected reconnects rather than leaving a
        desynchronised session to corrupt later commands.
        """
        try:
            self.ftp.putcmd("ABOR")
            self.ftp.getmultiline()
            self.ftp.getmultiline()
        except Exception:
            try:
                self.reconnect()
            except Exception:  # noqa: BLE001 - the next call will reconnect
                pass

    def retrieve(self, path: str, *, progress: Callable[[int], None] | None = None) -> bytes:
        """Download one file into memory, retrying and resuming where supported.

        Deliberately *not* ``ftplib.retrbinary``. That method owns the data
        socket internally and never applies a read timeout to it, so a server
        that accepts the connection and then stops sending blocks the call
        forever — no exception, no progress, no way to notice. One such stall
        wedged the whole profile stage: seven workers idle, one inside
        ``retrbinary``, and the pipeline waiting on a queue that would never
        drain. A crawl over 200,000 files will meet a stalled transfer sooner or
        later, so the read timeout is not optional.

        Driving ``transfercmd`` directly gives us the socket, and therefore the
        timeout. A stalled read now raises ``socket.timeout``, which
        :meth:`_retrying` treats as transient — it reconnects and retries, and
        after ``max_retries`` records a real error instead of hanging.
        """

        def _once() -> bytes:
            buf = io.BytesIO()
            conn = self.ftp.transfercmd(f"RETR {path}")
            try:
                conn.settimeout(self.timeout)
                while True:
                    chunk = conn.recv(1 << 16)
                    if not chunk:
                        break
                    buf.write(chunk)
                    if progress is not None:
                        progress(len(chunk))
            finally:
                conn.close()
            # The server still owes a completion reply; leaving it unread
            # desynchronises the control channel for every later command.
            self.ftp.voidresp()
            return buf.getvalue()

        data = self._retrying(_once, what=f"RETR {path}")
        assert isinstance(data, bytes)
        return data
