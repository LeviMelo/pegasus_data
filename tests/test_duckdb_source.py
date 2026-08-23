"""DATASUS publishes loose DuckDB databases; decoding them was broken.

Two defects in one path. The registry read the whole file into a Python
`bytes` and wrote it back out to a temporary file — the tree carries a 12 GB
`SIHSUS/base_aih1.duck`, so that is not a viable way to open a database. And it
deleted that temporary directory in a `finally`, on a comment claiming
`read_duckdb` returns tables already in memory. It does not: the batches are
lazy generators that connect when first iterated. Decoding therefore reported
success and iterating raised "Cannot open file".
"""

from __future__ import annotations

import gc

import pytest

from pegasus_data.decode.registry import ReaderRegistry


@pytest.fixture
def database(tmp_path):
    duckdb = pytest.importorskip("duckdb")
    path = tmp_path / "sample.duck"
    conn = duckdb.connect(str(path))
    conn.execute("CREATE TABLE aih AS SELECT i AS id, 'x' || i AS name FROM range(500) t(i)")
    conn.execute("CREATE TABLE sp AS SELECT i AS n FROM range(7) t(i)")
    conn.close()
    return path


class TestLooseDatabasesDecodeFromTheirPath:
    def test_every_table_is_found(self, database):
        outcome = ReaderRegistry().open_path(database, logical_path="/x/sample.duck")
        assert sorted(t.member for t in outcome.tables) == ["aih", "sp"]

    def test_the_rows_can_actually_be_read(self, database):
        """The defect: decoding succeeded and iterating raised."""
        outcome = ReaderRegistry().open_path(database, logical_path="/x/sample.duck")
        counts = {t.member: sum(b.num_rows for b in t.batches()) for t in outcome.tables}
        assert counts == {"aih": 500, "sp": 7}

    def test_the_logical_path_is_kept(self, database):
        outcome = ReaderRegistry().open_path(database, logical_path="/x/sample.duck")
        assert all(t.path == "/x/sample.duck" for t in outcome.tables)

    def test_it_is_re_iterable(self, database):
        outcome = ReaderRegistry().open_path(database, logical_path="/x/sample.duck")
        table = next(t for t in outcome.tables if t.member == "aih")
        assert sum(b.num_rows for b in table.batches()) == 500
        assert sum(b.num_rows for b in table.batches()) == 500

    def test_no_whole_file_copy_is_made(self, database, monkeypatch):
        """A 12 GB database must not go through a Python bytes object."""
        from pathlib import Path

        real = Path.read_bytes
        seen: list[str] = []

        def watched(self, *a, **k):
            seen.append(str(self))
            return real(self, *a, **k)

        monkeypatch.setattr(Path, "read_bytes", watched)
        ReaderRegistry().open_path(database, logical_path="/x/sample.duck")
        assert not any(str(database) == s for s in seen), (
            "the database was slurped into memory rather than opened in place"
        )

    def test_member_and_column_selection_reach_duckdb(self, database):
        outcome = ReaderRegistry().open_path(
            database,
            logical_path="/x/sample.duck",
            members=frozenset({"aih"}),
            columns=frozenset({"ID"}),
        )
        assert [table.member for table in outcome.tables] == ["aih"]
        batches = list(outcome.tables[0].batches())
        assert batches and batches[0].schema.names == ["ID"]


class TestStagedDatabasesKeepTheirFile:
    """A .duck inside an archive has no blob path of its own, so it is staged —
    and the staging has to outlive the decode."""

    def test_rows_survive_after_the_handler_returned(self, database):
        outcome = ReaderRegistry().open_bytes(database.read_bytes(), path="/x/sample.duck")
        gc.collect()  # the handler's frame is long gone
        counts = {t.member: sum(b.num_rows for b in t.batches()) for t in outcome.tables}
        assert counts == {"aih": 500, "sp": 7}

    def test_the_staging_is_owned_by_the_table(self, database):
        outcome = ReaderRegistry().open_bytes(database.read_bytes(), path="/x/sample.duck")
        assert all(t.retains is not None for t in outcome.tables), (
            "nothing owned the temporary directory, so it was deleted before use"
        )
