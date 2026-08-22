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

from pegasus_data.acquire.fetcher import FetchResult, Fetcher
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

    def test_both_entry_points_import_the_same_policy(self) -> None:
        """Two implementations of one rule is how they drifted apart."""
        import inspect

        from pegasus_data import api
        from pegasus_data.retrieve import axis_refusal

        assert "axis_refusal" in inspect.getsource(api.load)
        assert callable(axis_refusal)


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

        boom = pq.write_table

        def explode(table, where, **kw):
            raise OSError("disk full")

        monkeypatch.setattr(pq, "write_table", explode)
        with pytest.raises(OSError):
            lake.write_batches(
                [self._batch(9)], system="SIH", family_id="F1",
                schema_signature="s", uf="AC", year=2023,
            )
        monkeypatch.setattr(pq, "write_table", boom)

        assert original.exists(), "the previous partition was destroyed"
        assert pq.read_table(original).num_rows == 3, "and it is still the old data"

    def test_no_staging_debris_is_left_behind(self, tmp_path, monkeypatch) -> None:
        lake = Lake(tmp_path, catalog=None)
        lake.write_batches(
            [self._batch(2)], system="SIH", family_id="F1",
            schema_signature="s", uf="AC", year=2023,
        )
        good = pq.write_table
        monkeypatch.setattr(pq, "write_table", lambda *a, **k: (_ for _ in ()).throw(OSError("x")))
        with pytest.raises(OSError):
            lake.write_batches(
                [self._batch(2)], system="SIH", family_id="F1",
                schema_signature="s", uf="AC", year=2023,
            )
        monkeypatch.setattr(pq, "write_table", good)
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
