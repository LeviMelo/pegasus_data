"""HI-15: a timed-out operation must not leave its client in shared use.

`run_with_timeout` abandons its worker rather than killing it. For a decode
that is fine — it owns its inputs. For an `ftplib.FTP` it is not: one control
connection carries one reply stream, so an abandoned thread still reading it
makes every later command read the previous command's reply.
"""

from __future__ import annotations

import threading
import time

import pytest

from pegasus_data.progress import ItemTimeout, run_with_timeout


class TestAbandon:
    def test_it_drops_the_sockets_without_sending_quit(self):
        """QUIT writes to a connection the abandoned thread may be mid-read on."""
        from pegasus_data.discovery.ftp_client import FtpClient

        closed: list[str] = []
        quit_called = False

        class _Sock:
            def __init__(self, tag: str) -> None:
                self.tag = tag

            def close(self) -> None:
                closed.append(self.tag)

        class _Ftp:
            sock = _Sock("sock")
            file = _Sock("file")

            def quit(self) -> None:
                nonlocal quit_called
                quit_called = True

        client = FtpClient("example.invalid")
        client._ftp = _Ftp()  # type: ignore[assignment]
        client.abandon()

        assert not quit_called, "abandon() must not talk protocol on a doubtful connection"
        assert sorted(closed) == ["file", "sock"]
        assert client._ftp is None, "the retired client is not reusable by accident"

    def test_abandoning_twice_is_harmless(self):
        from pegasus_data.discovery.ftp_client import FtpClient

        client = FtpClient("example.invalid")
        client.abandon()
        client.abandon()

    def test_closing_the_socket_unblocks_the_abandoned_reader(self):
        """The point of closing rather than leaking: it stops the work."""
        import socket

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        accepted: list[socket.socket] = []
        threading.Thread(
            target=lambda: accepted.append(listener.accept()[0]), daemon=True
        ).start()

        client_sock = socket.create_connection(listener.getsockname())
        unblocked = threading.Event()

        def _read_forever() -> None:
            try:
                client_sock.recv(1)
            except OSError:
                pass
            finally:
                unblocked.set()

        threading.Thread(target=_read_forever, daemon=True).start()
        time.sleep(0.2)
        assert not unblocked.is_set(), "the reader is parked, as an abandoned thread would be"

        client_sock.close()
        assert unblocked.wait(5), "closing the socket released the parked reader"

        for s in accepted:
            s.close()
        listener.close()


class TestTheCensusReplacesATimedOutClient:
    def test_a_timeout_retires_the_client_instead_of_reusing_it(self):
        """The shape of pipeline.schemas()' _fetch, isolated from the network."""
        retired: list[object] = []
        connected: list[object] = []

        class _Client:
            def __init__(self, n: int) -> None:
                self.n = n

            def abandon(self) -> None:
                retired.append(self)

        def _connect() -> _Client:
            c = _Client(len(connected))
            connected.append(c)
            return c

        cell = [_connect()]
        abandoned: list[object] = []

        def _fetch(hang: bool) -> str:
            client = cell[0]
            try:
                return run_with_timeout(
                    lambda: (time.sleep(5) if hang else f"ok from {client.n}"),
                    seconds=0.2,
                    label="x",
                )
            except ItemTimeout:
                client.abandon()
                abandoned.append(client)
                cell[0] = _connect()
                raise

        assert _fetch(False) == "ok from 0"
        with pytest.raises(ItemTimeout):
            _fetch(True)

        assert len(retired) == 1, "the client the abandoned thread is inside was retired"
        assert cell[0] is not retired[0], "the next request uses a fresh connection"
        assert _fetch(False) == "ok from 1", "and it works"
