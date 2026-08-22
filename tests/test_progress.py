"""No stage may hang silently (§A).

These tests exist because of a fifty-minute silence. The exit criterion was
never "make that particular stall impossible" — stalls are not preventable, a
public FTP server will drop a connection whatever we do. It is that a stall can
never be *silent* and can never be *terminal*.

So what is pinned here is the behaviour under stall, not the absence of one: an
item that never returns is abandoned and written down; a batch that stops
completing gives up and says so; a worker that cannot connect does not take the
run with it; and while any of that is happening, something is printing where it
got to.
"""

from __future__ import annotations

import socket
import threading
import time

import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.progress import (
    Heartbeat,
    ItemTimeout,
    StageProgress,
    record_timeout,
    run_with_timeout,
)


class TestItemWatchdog:
    def test_a_hanging_item_raises_instead_of_blocking(self):
        started = time.monotonic()
        with pytest.raises(ItemTimeout, match="RDAC1401"):
            run_with_timeout(lambda: time.sleep(30), seconds=0.2, label="RDAC1401.dbc")
        assert time.monotonic() - started < 5, "gave up promptly rather than waiting it out"

    def test_the_timeout_names_the_item(self):
        """'Something is slow' and 'this file is slow' are different messages."""
        with pytest.raises(ItemTimeout) as excinfo:
            run_with_timeout(lambda: time.sleep(30), seconds=0.1, label="CHBR1901.dbc")
        assert "CHBR1901.dbc" in str(excinfo.value)

    def test_a_normal_item_returns_its_value(self):
        assert run_with_timeout(lambda: 7, seconds=5, label="fast") == 7

    def test_an_error_propagates_unchanged(self):
        """A failing item must not be reported as a timeout."""
        def boom() -> None:
            raise ValueError("bad dbf header")

        with pytest.raises(ValueError, match="bad dbf header"):
            run_with_timeout(boom, seconds=5, label="broken")

    def test_the_abandoned_thread_does_not_block_the_caller(self):
        """Python cannot safely kill a thread, so the item is left, not killed."""
        release = threading.Event()
        with pytest.raises(ItemTimeout):
            run_with_timeout(lambda: release.wait(30), seconds=0.2, label="stuck")
        release.set()  # the abandoned worker finishes on its own; nobody waited


class TestTimeoutsAreRecorded:
    def test_an_abandoned_item_lands_in_coverage_gaps(self, catalog: Catalog):
        record_timeout(
            catalog, stage="profile", item="/a/RDAC1401.dbc", seconds=1200,
            state="stratum SIHSUS|RD|AC|2014",
        )
        row = catalog.query("SELECT * FROM coverage_gaps WHERE path = '/a/RDAC1401.dbc'")[0]
        assert row["kind"] == "timeout"
        assert "abandoned" in row["last_error"]

    def test_the_last_known_state_is_kept(self, catalog: Catalog):
        """What it was doing is the whole value of the record."""
        record_timeout(
            catalog, stage="profile", item="/a/x.dbc", seconds=60, state="stratum S1"
        )
        row = catalog.query("SELECT * FROM coverage_gaps WHERE path = '/a/x.dbc'")[0]
        assert "stratum S1" in row["last_error"]

    def test_it_is_queryable_as_a_gap_like_any_other(self, catalog: Catalog):
        """A timeout is 'we know we do not have this, and why' — same as a gap."""
        record_timeout(catalog, stage="profile", item="/a/y.dbc", seconds=60)
        assert catalog.count("coverage_gaps", "kind = 'timeout' AND resolved = 0") == 1


class TestHeartbeat:
    def test_it_reports_while_the_work_is_stuck(self):
        """A progress bar driven by completions says nothing when nothing completes."""
        lines: list[str] = []
        progress = StageProgress(stage="profile", total=121)
        progress.completed = 8
        progress.current = "CHBR1901.dbc"
        progress.current_started = time.monotonic()
        with Heartbeat(progress, interval=0.05, emit=lines.append):
            time.sleep(0.35)
        assert lines, "a stalled stage still has to say something"
        assert "profile" in lines[0]
        assert "8/121" in lines[0]
        assert "CHBR1901.dbc" in lines[0], "naming the item in flight is the point"

    def test_it_stops_when_the_stage_does(self):
        lines: list[str] = []
        with Heartbeat(StageProgress(stage="s"), interval=0.05, emit=lines.append):
            time.sleep(0.15)
        before = len(lines)
        time.sleep(0.25)
        assert len(lines) == before

    def test_a_broken_emitter_does_not_kill_the_run(self):
        """A closed pipe is not a reason to lose the stage."""
        def broken(_: str) -> None:
            raise BrokenPipeError

        with Heartbeat(StageProgress(stage="s"), interval=0.05, emit=broken):
            time.sleep(0.15)

    def test_counts_and_elapsed_appear(self):
        progress = StageProgress(stage="fetch", total=3)
        progress.completed, progress.failed, progress.timed_out = 1, 1, 1
        line = progress.line()
        assert "1/3" in line and "failed 1" in line and "timed out 1" in line


class TestFetcherCannotDeadlock:
    """A4 — the two hangs found by thread-dumping a wedged run."""

    def _fetcher(self, catalog: Catalog, tmp_path, **kw):
        from pegasus_data.acquire.cache import BlobStore
        from pegasus_data.acquire.fetcher import Fetcher

        return Fetcher(
            catalog, BlobStore(tmp_path / "blobs"), host="unreachable.invalid",
            concurrency=2, timeout=1, max_retries=1, **kw,
        )

    def test_an_unreachable_host_returns_instead_of_hanging(self, catalog: Catalog, tmp_path):
        """Every worker failing to connect used to deadlock the whole stage.

        The first fix had each failed worker DRAIN the shared queue and mark
        every path it saw as failed, because fetch_many then waited on
        work.join(). It no longer does — it polls — so draining only meant one
        transient connection failure could empty the queue and fail a batch that
        healthy workers were about to complete. A worker that cannot connect now
        records itself and leaves, and the scheduler stops when no worker is left
        rather than waiting out the stall timeout.
        """
        fetcher = self._fetcher(catalog, tmp_path, stall_timeout=30, heartbeat_interval=60)
        started = time.monotonic()
        stats = fetcher.fetch_many(["/a/1.dbc", "/a/2.dbc", "/a/3.dbc"])
        assert time.monotonic() - started < 60, "returned instead of hanging"
        assert stats.requested == 3
        assert stats.workers_lost > 0, "the connection failure has to be visible"
        assert stats.fetched == 0

    def test_a_lost_worker_does_not_fail_paths_it_never_touched(
        self, catalog: Catalog, tmp_path
    ):
        """`failed` counts PATHS. A worker that never held one cannot fail it."""
        fetcher = self._fetcher(catalog, tmp_path, stall_timeout=30, heartbeat_interval=60)
        stats = fetcher.fetch_many(["/a/1.dbc", "/a/2.dbc", "/a/3.dbc"])
        assert stats.failed <= stats.requested
        assert any(path == "<connect>" for path, _ in stats.errors)

    def test_an_unreachable_host_is_reported_not_swallowed(self, catalog: Catalog, tmp_path):
        fetcher = self._fetcher(catalog, tmp_path, stall_timeout=30, heartbeat_interval=60)
        stats = fetcher.fetch_many(["/a/1.dbc"])
        assert stats.errors, "the reason has to survive"

    def test_an_empty_batch_is_not_a_stall(self, catalog: Catalog, tmp_path):
        assert self._fetcher(catalog, tmp_path).fetch_many([]).requested == 0


class TestStalledSocketRaises:
    """A stalled data connection must raise rather than block forever.

    ftplib.retrbinary owns its socket and never applies a read timeout to it, so
    a server that accepts the connection and then goes quiet blocks the call
    indefinitely. Driving transfercmd ourselves is what makes the timeout reach
    the read.
    """

    def test_a_silent_data_connection_times_out(self):
        from pegasus_data.discovery.ftp_client import FtpClient

        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        accepted: list[socket.socket] = []

        def _accept() -> None:
            conn, _ = listener.accept()
            accepted.append(conn)  # accepted, then deliberately silent

        threading.Thread(target=_accept, daemon=True).start()

        class _StallingFtp:
            """Hands back a socket that will never deliver a byte."""

            def transfercmd(self, cmd: str) -> socket.socket:
                s = socket.create_connection(listener.getsockname())
                return s

            def voidresp(self) -> None:  # pragma: no cover - never reached
                raise AssertionError("the read should have timed out first")

        client = FtpClient("example.invalid", timeout=1, max_retries=1)
        client._ftp = _StallingFtp()  # type: ignore[assignment]
        started = time.monotonic()
        # _retrying wraps the socket timeout once it has exhausted its attempts;
        # either shape proves the read came back instead of blocking.
        with pytest.raises((TimeoutError, OSError, RuntimeError)) as excinfo:
            client.retrieve("/a/stalled.dbc")
        assert "timed out" in str(excinfo.value)
        assert time.monotonic() - started < 30, "the read timeout fired"
        for s in accepted:
            s.close()
        listener.close()


class TestGuardedLoop:
    def test_a_stalled_stage_gives_up_rather_than_spinning(self, catalog: Catalog):
        from pegasus_data.progress import guarded

        lines: list[str] = []
        seen = []
        for item, _progress in guarded(
            catalog, "demo", [1, 2, 3, 4], label=str,
            stall_timeout=0.05, heartbeat=60, emit=lines.append,
        ):
            seen.append(item)
            time.sleep(0.08)  # work that never reports a completion
        assert seen == [1], "it stops once nothing has completed within the deadline"
        assert any("STALLED" in line for line in lines)

    def test_a_healthy_stage_yields_everything(self, catalog: Catalog):
        from pegasus_data.progress import guarded

        seen = [
            item
            for item, _progress in guarded(
                catalog, "demo", [1, 2, 3], label=str, heartbeat=60, emit=lambda _: None
            )
        ]
        assert seen == [1, 2, 3]
