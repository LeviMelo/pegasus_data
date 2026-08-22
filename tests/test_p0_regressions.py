"""The six P0 defects, each pinned so it cannot come back.

Every one of these produced a *plausible* result rather than an obvious
failure — a stale file decoded as fresh, a longitudinal query that looks like it
naturally starts in 2006, an empty answer that reads as "this state has no
records". That is the failure mode this project exists to prevent, so the guards
belong in tests rather than in comments.
"""

from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from pegasus_data.acquire.fetcher import Fetcher, FetchResult
from pegasus_data.api import _by_vintage, _merge_reports
from pegasus_data.catalog.store import Catalog
from pegasus_data.persist.lake import Lake
from pegasus_data.view import RenderReport


class TestP0_1_AFailedRefreshMustNotServeTheStaleBlob:
    """The cache was most willing to use stale data exactly when it knew better.

    `ensure()` discarded the fetch results and asked `known_for()`, a historical
    lookup that re-checks nothing: stale → refresh fails → yesterday's blob is
    returned and decoded as though acquisition succeeded.
    """

    @staticmethod
    def _fetcher(monkeypatch, *, result: FetchResult, historical: str | None):
        f = Fetcher.__new__(Fetcher)
        f.last_stats = None
        f.last_stale = []

        class _Blobs:
            def known_for(self, _path: str) -> str | None:
                return historical

        f.blobs = _Blobs()

        def fake_fetch_many(paths, *, force=False, on_result=None):
            if on_result:
                on_result(result)
            return object()

        monkeypatch.setattr(f, "fetch_many", fake_fetch_many, raising=False)
        return f

    def test_a_failed_refresh_returns_nothing_for_that_path(self, monkeypatch) -> None:
        f = self._fetcher(
            monkeypatch,
            result=FetchResult(path="/p/x.dbc", sha256=None, byte_size=0, error="boom"),
            historical="yesterdays-digest",
        )
        assert f.ensure(["/p/x.dbc"]) == {}, "the stale blob was served anyway"

    def test_a_successful_fetch_is_returned(self, monkeypatch) -> None:
        f = self._fetcher(
            monkeypatch,
            result=FetchResult(path="/p/x.dbc", sha256="fresh", byte_size=10),
            historical="yesterdays-digest",
        )
        assert f.ensure(["/p/x.dbc"]) == {"/p/x.dbc": "fresh"}

    def test_a_verified_cache_hit_is_returned(self, monkeypatch) -> None:
        """skipped=True means _should_skip() proved it is unchanged."""
        f = self._fetcher(
            monkeypatch,
            result=FetchResult(path="/p/x.dbc", sha256="cached", byte_size=10, skipped=True),
            historical=None,
        )
        assert f.ensure(["/p/x.dbc"]) == {"/p/x.dbc": "cached"}

    def test_stale_is_available_only_on_request_and_is_recorded(self, monkeypatch) -> None:
        f = self._fetcher(
            monkeypatch,
            result=FetchResult(path="/p/x.dbc", sha256=None, byte_size=0, error="boom"),
            historical="yesterdays-digest",
        )
        assert f.ensure(["/p/x.dbc"], allow_stale=True) == {"/p/x.dbc": "yesterdays-digest"}
        assert f.last_stale == ["/p/x.dbc"], "a stale fallback must be reportable"


class TestP0_2_EachVintageRendersAtItsOwn:
    """`min(years)` for the whole result labelled 2024 rows with the 1995 table."""

    @staticmethod
    def _table(years: list[int]) -> pa.Table:
        return pa.table({"year": pa.array(years, pa.int32()),
                         "SEXO": pa.array(["1"] * len(years))})

    def test_a_multi_year_table_is_split_per_year(self) -> None:
        parts = _by_vintage(self._table([1995, 1995, 2024]), [1995, 2024])
        assert sorted(y for _, y in parts) == [1995, 2024]
        assert sum(chunk.num_rows for chunk, _ in parts) == 3

    def test_a_single_year_is_not_split(self) -> None:
        parts = _by_vintage(self._table([2024, 2024]), [2024])
        assert len(parts) == 1 and parts[0][1] == 2024

    def test_the_year_comes_from_the_rows_not_the_request(self) -> None:
        """years=None used to mean "today's codelist" for historical rows."""
        parts = _by_vintage(self._table([1998, 2024]), None)
        assert sorted(y for _, y in parts) == [1998, 2024]

    def test_without_a_year_column_there_is_nothing_to_split_on(self) -> None:
        plain = pa.table({"SEXO": pa.array(["1", "3"])})
        parts = _by_vintage(plain, [2001, 2002])
        assert len(parts) == 1 and parts[0][1] == 2001

    def test_reports_from_every_partition_are_kept(self) -> None:
        a = RenderReport(labelled=["SEXO"], warnings=["one"])
        b = RenderReport(labelled=["SEXO", "RACA"], warnings=["two"])
        b.constant["DEAD"] = "0000"
        merged = _merge_reports(a, b)
        assert set(merged.labelled) == {"SEXO", "RACA"}
        assert merged.warnings == ["one", "two"]
        assert merged.constant == {"DEAD": "0000"}


class TestP0_4_OneAxisPolicyForBothPaths:
    """`fetch()` refused a filter the files are not split on; `load()` did not."""

    def test_the_policy_returns_a_refusal_rather_than_raising(self, settings) -> None:
        from pegasus_data.retrieve import axis_refusal

        store = Catalog(settings.catalog_path)
        try:
            store.upsert_files(
                [{"path": f"/d/DOFET{y}.dbc", "directory": "/d",
                  "filename": f"DOFET{y}.dbc", "extension": ".dbc", "size": 1}
                 for y in (96, 97)]
            )
            for y in (96, 97):
                store.execute(
                    "INSERT OR REPLACE INTO file_facts (path, system, series_prefix,"
                    " geo_code, year, role) VALUES (?,?,?,?,?,?)",
                    (f"/d/DOFET{y}.dbc", "SIM", "DOFET", None, 1900 + y, "data"),
                )
            refusal, notes = axis_refusal(
                store, "SIM", "DOFET", uf=True, years=False, months=False
            )
            assert refusal and "not split by uf" in refusal
            assert notes == []

            allowed, _ = axis_refusal(
                store, "SIM", "DOFET", uf=False, years=True, months=False
            )
            assert allowed is None, "year IS an axis here and must be permitted"
        finally:
            store.close()

    def test_every_public_reader_consults_the_one_policy(
        self, built_lake, monkeypatch
    ) -> None:
        """Two implementations of one rule is how they drifted apart.

        Asserted by observing the CALL, not by grepping load()'s source for it.
        The source check broke the moment resolution moved into a helper that
        load() calls — it was testing where the code lived, which is not the
        guarantee. The guarantee is that no public reader answers an
        axis-filtered question without asking the shared policy first, because
        the alternative is a false empty that reads as "Acre has no records".
        """
        import pegasus_data.retrieve as retrieve
        from pegasus_data.api import load, scan

        settings, _catalog, _ = built_lake
        calls: list[tuple] = []
        real = retrieve.axis_refusal

        def watched(store, system, series, **kw):
            calls.append((system, series, tuple(sorted(kw.items()))))
            return real(store, system, series, **kw)

        monkeypatch.setattr(retrieve, "axis_refusal", watched)

        load("SIHSUS", "RD", uf="AL", root=settings.root, settings=settings, labels=False)
        assert calls, "load() answered a uf-filtered request without asking the policy"

        calls.clear()
        scan("SIHSUS", "RD", uf="AL", root=settings.root, settings=settings).count_rows()
        assert calls, "scan() answered a uf-filtered request without asking the policy"


class TestP0_6_ReplacementDoesNotDestroyBeforeItWrites:
    """The partition was cleared, then written. A failure between the two lost it."""

    @staticmethod
    def _batch(n: int) -> pa.RecordBatch:
        return pa.record_batch({"a": pa.array(list(range(n)), pa.int32())})

    def test_a_failed_replacement_leaves_the_previous_partition(
        self, tmp_path, monkeypatch
    ) -> None:
        lake = Lake(tmp_path, catalog=None)
        first = lake.write_batches(
            [self._batch(3)], system="SIH", family_id="F1",
            schema_signature="s", uf="AC", year=2023,
        )
        assert first is not None
        original = tmp_path / first.relative_path
        assert pq.read_table(original).num_rows == 3

        # Partitions stream through ParquetWriter now (HI-18), so that is where
        # a mid-write failure is injected. The invariant is unchanged.
        boom = pq.ParquetWriter

        def explode(*a, **kw):
            raise OSError("disk full")

        monkeypatch.setattr(pq, "ParquetWriter", explode)
        with pytest.raises(OSError):
            lake.write_batches(
                [self._batch(9)], system="SIH", family_id="F1",
                schema_signature="s", uf="AC", year=2023,
            )
        monkeypatch.setattr(pq, "ParquetWriter", boom)

        assert original.exists(), "the previous partition was destroyed"
        assert pq.read_table(original).num_rows == 3, "and it is still the old data"

    def test_no_staging_debris_is_left_behind(self, tmp_path, monkeypatch) -> None:
        lake = Lake(tmp_path, catalog=None)
        lake.write_batches(
            [self._batch(2)], system="SIH", family_id="F1",
            schema_signature="s", uf="AC", year=2023,
        )
        good = pq.ParquetWriter
        monkeypatch.setattr(
            pq, "ParquetWriter", lambda *a, **k: (_ for _ in ()).throw(OSError("x"))
        )
        with pytest.raises(OSError):
            lake.write_batches(
                [self._batch(2)], system="SIH", family_id="F1",
                schema_signature="s", uf="AC", year=2023,
            )
        monkeypatch.setattr(pq, "ParquetWriter", good)
        leftovers = list(tmp_path.rglob("*.staging"))
        assert leftovers == [], f"staging files survived: {leftovers}"

    def test_a_successful_replacement_still_replaces(self, tmp_path) -> None:
        lake = Lake(tmp_path, catalog=None)
        lake.write_batches(
            [self._batch(3)], system="SIH", family_id="F1",
            schema_signature="s", uf="AC", year=2023,
        )
        second = lake.write_batches(
            [self._batch(7)], system="SIH", family_id="F1",
            schema_signature="s", uf="AC", year=2023,
        )
        assert second is not None
        assert pq.read_table(tmp_path / second.relative_path).num_rows == 7
        parts = list((tmp_path / second.relative_path).parent.glob("*.parquet"))
        assert len(parts) == 1, "replace must not leave the old part beside the new"


class TestHI01_AWarmRequestNeverTouchesTheNetwork:
    """Every worker connected before it took a path off the queue.

    So a request whose bytes were all on the SSD still opened up to eight FTP
    sessions that did no work — and failed outright when DATASUS was
    unreachable. `_should_skip()` reads the catalog, not the network, so it can
    answer before any socket exists.
    """

    @staticmethod
    def _fetcher(catalog, tmp_path, monkeypatch, *, hits: set[str]):
        from pegasus_data.acquire.cache import BlobStore
        from pegasus_data.acquire.fetcher import Fetcher

        f = Fetcher(
            catalog, BlobStore(tmp_path / "blobs"), host="unreachable.invalid",
            concurrency=4, timeout=1, max_retries=1,
            stall_timeout=10, heartbeat_interval=60,
        )
        monkeypatch.setattr(f, "_should_skip", lambda p: "digest" if p in hits else None)

        class _Blobs:
            def path_for(self, _digest):
                target = tmp_path / "blob.bin"
                target.write_bytes(b"x" * 7)
                return target

            def has(self, _digest):
                return True

            def known_for(self, _path):
                return None

        f.blobs = _Blobs()
        return f

    def test_an_all_hit_batch_opens_no_connection(self, catalog, tmp_path, monkeypatch) -> None:
        opened: list[str] = []
        import pegasus_data.acquire.fetcher as mod

        class _Boom:
            def __init__(self, *a, **k) -> None:
                opened.append("connect")

            def connect(self):
                raise AssertionError("a fully warm request opened an FTP connection")

            def close(self):
                pass

        monkeypatch.setattr(mod, "FtpClient", _Boom)
        paths = ["/a/1.dbc", "/a/2.dbc", "/a/3.dbc"]
        f = self._fetcher(catalog, tmp_path, monkeypatch, hits=set(paths))
        stats = f.fetch_many(paths)
        assert stats.skipped == 3
        assert stats.bytes_from_cache == 21, "cache bytes are not download bytes"
        assert stats.bytes_fetched == 0
        assert opened == [], "no FTP client should even be constructed"

    def test_a_partly_warm_batch_only_dials_for_the_misses(
        self, catalog, tmp_path, monkeypatch
    ) -> None:
        f = self._fetcher(catalog, tmp_path, monkeypatch, hits={"/a/1.dbc"})
        stats = f.fetch_many(["/a/1.dbc", "/a/2.dbc"])
        assert stats.skipped == 1, "the hit was served without the network"
        assert stats.requested == 2


class TestHI03_FreshnessComparesThenWithNow:
    """The policy claimed to compare the listing at fetch time with the listing
    now. The table stored neither, so it compared today's listed size against
    the stored blob's byte count and merely checked a modified time existed —
    and a republication with an unchanged byte count was skipped."""

    @staticmethod
    def _catalog_with(catalog, *, then_size, then_mtime, now_size, now_mtime):
        catalog.execute(
            "INSERT INTO files (path, directory, filename, size, modified,"
            " first_seen, last_seen) VALUES (?,?,?,?,?,?,?)",
            ("/p/x.dbc", "/p", "x.dbc", now_size, now_mtime, "t", "t"),
        )
        catalog.execute(
            "INSERT INTO blobs (sha256, byte_size, first_fetched_at, fetch_count)"
            " VALUES ('d', 10, 't', 1)"
        )
        catalog.execute(
            "INSERT INTO fetches (source_path, sha256, byte_size, fetched_at,"
            " remote_size, remote_modified) VALUES (?,?,?,?,?,?)",
            ("/p/x.dbc", "d", 10, "t", then_size, then_mtime),
        )
        return catalog

    @staticmethod
    def _fetcher(catalog, tmp_path):
        from pegasus_data.acquire.cache import BlobStore
        from pegasus_data.acquire.fetcher import Fetcher

        f = Fetcher(catalog, BlobStore(tmp_path / "blobs"), host="h")

        class _Blobs:
            def has(self, _d):
                return True

        f.blobs = _Blobs()
        return f

    def test_a_changed_mtime_at_the_same_size_is_not_skipped(self, catalog, tmp_path) -> None:
        """The exact case the old policy could not see."""
        self._catalog_with(
            catalog, then_size=10, then_mtime="2024-01-01", now_size=10, now_mtime="2025-06-01"
        )
        assert self._fetcher(catalog, tmp_path)._should_skip("/p/x.dbc") is None

    def test_an_unchanged_listing_is_skipped(self, catalog, tmp_path) -> None:
        self._catalog_with(
            catalog, then_size=10, then_mtime="2024-01-01", now_size=10, now_mtime="2024-01-01"
        )
        assert self._fetcher(catalog, tmp_path)._should_skip("/p/x.dbc") == "d"

    def test_a_changed_size_is_not_skipped(self, catalog, tmp_path) -> None:
        self._catalog_with(
            catalog, then_size=10, then_mtime="2024-01-01", now_size=99, now_mtime="2024-01-01"
        )
        assert self._fetcher(catalog, tmp_path)._should_skip("/p/x.dbc") is None

    def test_a_blob_fetched_before_this_was_recorded_still_works(self, catalog, tmp_path) -> None:
        """Old catalogs have no remote_size/remote_modified. Falling back beats
        re-downloading the world."""
        self._catalog_with(
            catalog, then_size=None, then_mtime=None, now_size=10, now_mtime="2024-01-01"
        )
        assert self._fetcher(catalog, tmp_path)._should_skip("/p/x.dbc") == "d"
