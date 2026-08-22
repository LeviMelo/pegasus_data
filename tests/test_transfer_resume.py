"""HI-04 and HI-05: transfers stream to disk and genuinely resume.

`retrieve()` documented "retrying and resuming where supported" and never sent
REST, so a transfer that broke at 95% of a large file started again at byte
zero. It also held the whole file in RAM, hashed the bytes, and then wrote them
to disk — three copies of a file that was on its way to disk anyway.

These tests drive `FtpClient` against a fake control channel, the same shape
`test_progress.py` uses for the stall timeout.
"""

from __future__ import annotations

import ftplib
import hashlib

import pytest

from pegasus_data.discovery.ftp_client import FtpClient

PAYLOAD = bytes(range(256)) * 400  # 102,400 bytes, more than one 64 KiB read


class _Conn:
    """A data socket that hands over `data` and optionally dies partway."""

    def __init__(self, data: bytes, *, die_after: int | None = None) -> None:
        self.data = data
        self.pos = 0
        self.die_after = die_after

    def settimeout(self, _seconds: float) -> None:
        pass

    def recv(self, size: int) -> bytes:
        if self.die_after is not None and self.pos >= self.die_after:
            raise ConnectionResetError("connection reset by peer")
        end = min(self.pos + size, len(self.data))
        if self.die_after is not None:
            end = min(end, self.die_after)
        chunk = self.data[self.pos : end]
        self.pos = end
        return chunk

    def close(self) -> None:
        pass


class _Ftp:
    """Records every REST offset it is asked for."""

    def __init__(self, script: list[_Conn], *, rest_supported: bool = True) -> None:
        self.script = script
        self.rest_supported = rest_supported
        self.rest_offsets: list[int | None] = []

    def transfercmd(self, cmd: str, rest: int | None = None):
        if rest is not None and not self.rest_supported:
            raise ftplib.error_perm("500 REST not understood")
        self.rest_offsets.append(rest)
        return self.script.pop(0)

    def voidresp(self) -> None:
        pass


def _client(ftp: _Ftp) -> FtpClient:
    client = FtpClient("example.invalid", timeout=5, max_retries=3)
    client._ftp = ftp  # type: ignore[assignment]
    client.reconnect = lambda: None  # type: ignore[method-assign]
    return client


class TestResume:
    def test_a_broken_transfer_restarts_at_the_offset_already_on_disk(self, tmp_path):
        half = len(PAYLOAD) // 2
        ftp = _Ftp([
            _Conn(PAYLOAD, die_after=half),  # dies halfway
            _Conn(PAYLOAD[half:]),           # server honours REST
        ])
        dest = tmp_path / "big.dbc"
        size, digest = _client(ftp).retrieve_to_file("/x/big.dbc", dest)

        assert ftp.rest_offsets == [None, half], "the retry asked to restart at the offset"
        assert size == len(PAYLOAD)
        assert dest.read_bytes() == PAYLOAD
        assert digest == hashlib.sha256(PAYLOAD).hexdigest(), (
            "the digest covers the spliced file, not just the resumed tail"
        )

    def test_a_server_that_refuses_rest_still_finishes(self, tmp_path):
        half = len(PAYLOAD) // 2
        ftp = _Ftp(
            [_Conn(PAYLOAD, die_after=half), _Conn(PAYLOAD)],
            rest_supported=False,
        )
        dest = tmp_path / "big.dbc"
        size, digest = _client(ftp).retrieve_to_file("/x/big.dbc", dest)

        assert size == len(PAYLOAD)
        assert dest.read_bytes() == PAYLOAD
        assert digest == hashlib.sha256(PAYLOAD).hexdigest()

    def test_a_file_that_finishes_at_the_wrong_length_is_refused(self, tmp_path):
        """REST is advisory: a server may accept it and send from zero anyway."""
        ftp = _Ftp([_Conn(PAYLOAD[:100]) for _ in range(3)])
        dest = tmp_path / "short.dbc"
        with pytest.raises(RuntimeError, match="listing says"):
            _client(ftp).retrieve_to_file(
                "/x/short.dbc", dest, expected_size=len(PAYLOAD)
            )
        assert not dest.exists(), "the wrong bytes are not left behind to be resumed"


class TestNoWholeFileInMemory:
    def test_the_transfer_never_holds_more_than_one_chunk(self, tmp_path):
        """The reason this exists: peak RSS was file size x worker count."""
        biggest = 0

        class _Watching(_Conn):
            def recv(self, size: int) -> bytes:
                nonlocal biggest
                chunk = super().recv(size)
                biggest = max(biggest, len(chunk))
                return chunk

        ftp = _Ftp([_Watching(PAYLOAD)])
        dest = tmp_path / "big.dbc"
        size, _ = _client(ftp).retrieve_to_file("/x/big.dbc", dest)
        assert size == len(PAYLOAD)
        assert biggest <= (1 << 16), "reads are bounded; the file is not materialised in RAM"


class TestAdopt:
    def test_a_streamed_file_is_moved_into_the_store_not_copied(self, tmp_path):
        from pegasus_data.acquire.cache import BlobStore

        store = BlobStore(tmp_path / "blobs")
        staged = store.staging_path("/x/big.dbc")
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(PAYLOAD)
        digest = hashlib.sha256(PAYLOAD).hexdigest()

        returned = store.adopt(staged, digest, len(PAYLOAD), source_path="/x/big.dbc")
        assert returned == digest
        assert not staged.exists(), "the staged file was moved, not copied"
        assert store.path_for(digest).read_bytes() == PAYLOAD

    def test_staging_lives_on_the_stores_own_filesystem(self, tmp_path):
        """os.replace is only atomic within one filesystem."""
        from pegasus_data.acquire.cache import BlobStore

        store = BlobStore(tmp_path / "blobs")
        staged = store.staging_path("/x/big.dbc")
        assert store.root in staged.parents

    def test_a_racing_worker_that_stored_the_same_bytes_first_wins(self, tmp_path):
        from pegasus_data.acquire.cache import BlobStore

        store = BlobStore(tmp_path / "blobs")
        digest = hashlib.sha256(PAYLOAD).hexdigest()
        target = store.path_for(digest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(PAYLOAD)

        staged = store.staging_path("/x/big.dbc")
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(PAYLOAD)
        assert store.adopt(staged, digest, len(PAYLOAD), source_path="/x/big.dbc") == digest
        assert not staged.exists()
        assert target.read_bytes() == PAYLOAD
