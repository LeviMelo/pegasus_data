"""A timeout has to end the work, not just stop waiting for it.

`run_with_timeout` starts a daemon thread and joins it with a deadline. On
expiry it stops waiting — which is all Python can do, because a thread cannot be
killed and DBC inflation runs inside a native extension that never yields. So a
file recorded as "abandoned after 1200s" went on holding a core, an inflated DBF
and temporary disk while the API moved on, and several of those accumulate.

A process can be killed. These tests assert that it is: that the decoder runs
somewhere else, that its answer matches the in-process one exactly, that the
projection survives the crossing, and that a deadline leaves nothing running.
"""

from __future__ import annotations

import os
import time

import pyarrow as pa
import pytest

from pegasus_data.decode.isolation import DecoderPool, IsolatedDecodeError
from pegasus_data.decode.registry import ReaderRegistry
from pegasus_data.progress import ItemTimeout


@pytest.fixture
def dbf_file(tmp_path, sample_dbf):
    path = tmp_path / "sample.dbf"
    path.write_bytes(sample_dbf)
    return path


@pytest.fixture
def pool():
    with DecoderPool(2) as p:
        yield p


class TestItDecodesSomewhereElse:
    def test_the_work_happens_in_another_process(self, pool, dbf_file):
        pool.decode(dbf_file, logical_path="/x/sample.dbf", timeout=120)
        running = [w for w in pool._workers if w.proc and w.proc.poll() is None]
        assert running, "nothing was spawned; the decode stayed in this interpreter"
        assert all(w.proc.pid != os.getpid() for w in running)

    def test_the_answer_matches_the_in_process_decoder(self, pool, dbf_file):
        local = ReaderRegistry().open_path(dbf_file, logical_path="/x/sample.dbf")
        remote = pool.decode(dbf_file, logical_path="/x/sample.dbf", timeout=120)

        assert [t.member for t in remote.tables] == [t.member for t in local.tables]
        for near, far in zip(local.tables, remote.tables, strict=True):
            assert far.field_names == near.field_names
            assert pa.Table.from_batches(list(far.batches())).to_pydict() == (
                pa.Table.from_batches(list(near.batches())).to_pydict()
            )

    def test_the_logical_path_survives_the_crossing(self, pool, dbf_file):
        remote = pool.decode(dbf_file, logical_path="/x/sample.dbf", timeout=120)
        assert all(t.path == "/x/sample.dbf" for t in remote.tables)

    def test_the_projection_survives_the_crossing(self, pool, dbf_file):
        """The parent's monkeypatches cannot reach the child, so this is what
        the projection assertion has to look like on the isolated path."""
        full = pool.decode(dbf_file, logical_path="/x/sample.dbf", timeout=120)
        first = full.tables[0].field_names[0]
        narrow = pool.decode(
            dbf_file, logical_path="/x/sample.dbf", columns=[first], timeout=120
        )
        batches = list(narrow.tables[0].batches())
        assert batches and batches[0].schema.names == [first], (
            "the child built columns the caller excluded"
        )

    def test_a_worker_is_reused_rather_than_respawned(self, pool, dbf_file):
        pool.decode(dbf_file, logical_path="/x/a.dbf", timeout=120)
        pids = {w.proc.pid for w in pool._workers if w.proc}
        for _ in range(3):
            pool.decode(dbf_file, logical_path="/x/a.dbf", timeout=120)
        assert {w.proc.pid for w in pool._workers if w.proc} == pids, (
            "interpreter startup is the one real cost of this design and it was "
            "being paid per file"
        )

    def test_a_failed_reply_discards_the_worker_before_the_next_job(
        self, dbf_file, tmp_path
    ):
        missing = tmp_path / "does-not-exist.dbf"
        with DecoderPool(1) as pool:
            with pytest.raises(IsolatedDecodeError):
                pool.decode(missing, logical_path="/x/missing.dbf", timeout=120)
            worker = pool._workers[0]
            assert worker.proc is None, "the protocol-failed process was returned to the pool"

            outcome = pool.decode(dbf_file, logical_path="/x/good.dbf", timeout=120)
            assert outcome.tables and list(outcome.tables[0].batches())
            assert worker.proc is not None and worker.proc.poll() is None

    def test_parent_spools_batches_instead_of_retaining_the_whole_table(
        self, pool, dbf_file
    ):
        outcome = pool.decode(dbf_file, logical_path="/x/sample.dbf", timeout=120)
        remote = outcome.tables[0]
        assert remote._spool_path is not None and remote._spool_path.is_file()
        first = pa.Table.from_batches(list(remote.batches())).to_pydict()
        second = pa.Table.from_batches(list(remote.batches())).to_pydict()
        assert first == second, "a shared physical decode must be reusable by archive members"

    def test_archive_member_identity_is_the_same_on_both_decode_paths(self):
        from pegasus_data.decode.base import DecodedTable, logical_source_id
        from pegasus_data.decode.isolation import _RemoteTable

        expected = logical_source_id("/x/apac.exe", "ACAC0202.DBF")
        local = DecodedTable(
            "/x/apac.exe", "dbf", [], lambda: iter(()), member="ACAC0202.DBF"
        )
        remote = _RemoteTable("/x/apac.exe", "ACAC0202.DBF", "dbf", [], None)
        assert local.source_id == remote.source_id == expected

    def test_an_undecodable_source_comes_back_empty_rather_than_hanging(
        self, pool, tmp_path
    ):
        """The reader ladder tries everything and produces no table; that is an
        answer, and it has to cross the pipe like any other."""
        junk = tmp_path / "junk.dbf"
        junk.write_bytes(b"not a dbf at all")
        outcome = pool.decode(junk, logical_path="/x/junk.dbf", timeout=120)
        assert outcome.tables == []
        assert outcome.attempts, "the attempts it made are part of the answer"


class TestATimeoutEndsTheWork:
    @pytest.fixture
    def stuck(self, monkeypatch):
        """A pool whose workers never answer.

        Deterministic on purpose: timing a real decode against a short deadline
        is a race, and this is the one behaviour that must not be raced — a
        decoder that outlives its timeout is the whole defect.
        """
        import subprocess
        import sys

        from pegasus_data.decode.isolation import _Worker

        def _sleep_forever(self):
            if self.proc is None or self.proc.poll() is not None:
                self.proc = subprocess.Popen(
                    [sys.executable, "-c", "import time; time.sleep(600)"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=0,
                )
            return self.proc

        monkeypatch.setattr(_Worker, "start", _sleep_forever)
        with DecoderPool(1) as p:
            yield p

    def test_it_raises_item_timeout(self, stuck, dbf_file):
        with pytest.raises(ItemTimeout, match="killed"):
            stuck.decode(dbf_file, logical_path="/x/slow.dbf", timeout=0.5)

    def test_the_process_is_actually_gone(self, stuck, dbf_file):
        import psutil

        worker = stuck._workers[0]
        worker.start()
        pid = worker.proc.pid
        assert psutil.pid_exists(pid)

        with pytest.raises(ItemTimeout):
            stuck.decode(dbf_file, logical_path="/x/slow.dbf", timeout=0.5)

        deadline = time.monotonic() + 5
        while psutil.pid_exists(pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not psutil.pid_exists(pid), (
            "the decoder outlived its own timeout — 'abandoned' still means "
            "'we stopped watching it'"
        )

    def test_the_pool_recovers_after_a_kill(self, pool, dbf_file, monkeypatch):
        from pegasus_data.decode.isolation import _Worker

        real = _Worker.start
        pool.decode(dbf_file, logical_path="/x/a.dbf", timeout=120)
        pool._workers[0].kill()
        monkeypatch.setattr(_Worker, "start", real)
        out = pool.decode(dbf_file, logical_path="/x/a.dbf", timeout=120)
        assert out.tables, "a killed worker was not replaced"


class TestTheWireFormat:
    def test_frames_round_trip(self):
        import io as _io

        from pegasus_data.decode._worker import read_frame, write_frame

        buffer = _io.BytesIO()
        write_frame(buffer, b"hello")
        write_frame(buffer, b"")
        buffer.seek(0)
        assert read_frame(buffer) == b"hello"
        assert read_frame(buffer) == b"", "a zero length is a terminator, not the end"
        assert read_frame(buffer) is None, "exhausted is None, distinct from a terminator"

    def test_a_large_frame_is_reassembled(self):
        import io as _io

        from pegasus_data.decode._worker import read_frame, write_frame

        payload = bytes(range(256)) * 5000
        buffer = _io.BytesIO()
        write_frame(buffer, payload)
        buffer.seek(0)
        assert read_frame(buffer) == payload


class TestItIsConfigurable:
    def test_isolation_is_on_by_default(self):
        from pegasus_data.config import Settings

        assert Settings().decode_isolation is True

    def test_it_can_be_turned_off(self, settings, seeded):
        """Where spawning a subprocess is not possible."""
        from pegasus_data.retrieve import fetch

        settings.decode_isolation = False
        assert fetch("SIH-RD", settings=settings).num_rows > 0

    def test_both_paths_return_the_same_rows(self, settings, seeded):
        from pegasus_data.retrieve import fetch

        settings.decode_isolation = False
        in_process = fetch("SIH-RD", settings=settings, labels=False).num_rows
        settings.decode_isolation = True
        isolated = fetch("SIH-RD", settings=settings, labels=False).num_rows
        assert in_process == isolated
