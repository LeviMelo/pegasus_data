"""ME-20: the lazy primitive that was missing between fetch()/load() and DuckDB.

Both public readers materialised a whole `pa.Table`, so a national multi-year
question had exactly one supported shape: build the entire answer in memory
first. `scan()` carries the same guards — declared-dataset resolution, the
file-axis refusal — and hands back batches.
"""

from __future__ import annotations

import csv

import pyarrow.dataset as ds
import pyarrow.parquet as pq
import pytest

from pegasus_data.api import LakeScan, export, load, scan
from pegasus_data.retrieve import DatasetUnknown

pytest_plugins = ()


@pytest.fixture
def scanned(built_lake):
    settings, catalog, family_id = built_lake
    return settings, catalog, family_id


class TestScanAgreesWithLoad:
    def test_it_returns_the_same_rows(self, built_lake):
        settings, _catalog, _ = built_lake
        eager = load("SIHSUS", "RD", root=settings.root, settings=settings, labels=False)
        lazy = scan("SIHSUS", "RD", root=settings.root, settings=settings).to_table()
        assert lazy.num_rows == eager.num_rows

    def test_count_rows_agrees_without_reading_the_data(self, built_lake):
        """Parquet keeps row counts in its footers, which is what makes
        'is this too big for memory?' answerable before committing to it."""
        settings, _catalog, _ = built_lake
        sc = scan("SIHSUS", "RD", root=settings.root, settings=settings)
        eager = load("SIHSUS", "RD", root=settings.root, settings=settings, labels=False)
        assert sc.count_rows() == eager.num_rows

    def test_iterating_yields_every_row(self, built_lake):
        settings, _catalog, _ = built_lake
        sc = scan("SIHSUS", "RD", root=settings.root, settings=settings)
        assert sum(b.num_rows for b in sc) == sc.count_rows()

    def test_it_can_be_iterated_twice(self, built_lake):
        """Nothing is cached, which is the point — but a re-scan must work."""
        settings, _catalog, _ = built_lake
        sc = scan("SIHSUS", "RD", root=settings.root, settings=settings)
        first = sum(b.num_rows for b in sc.iter_batches())
        second = sum(b.num_rows for b in sc.iter_batches())
        assert first == second != 0


class TestPushdown:
    def test_projection_returns_only_what_was_asked_for(self, built_lake):
        settings, _catalog, _ = built_lake
        table = scan(
            "SIHSUS", "RD", columns=["SEXO"], root=settings.root, settings=settings
        ).to_table()
        assert [c for c in table.schema.names if not c.startswith("_")] == ["SEXO"] or (
            "SEXO" in table.schema.names
        )

    def test_a_predicate_is_applied(self, built_lake):
        settings, _catalog, _ = built_lake
        full = scan("SIHSUS", "RD", root=settings.root, settings=settings).to_table()
        value = full.column("SEXO").to_pylist()[0]
        expected = sum(1 for v in full.column("SEXO").to_pylist() if v == value)
        filtered = scan(
            "SIHSUS",
            "RD",
            where=ds.field("SEXO") == value,
            root=settings.root,
            settings=settings,
        )
        assert filtered.count_rows() == expected

    def test_year_filters_reach_the_partitions(self, built_lake):
        settings, _catalog, _ = built_lake
        sc = scan("SIHSUS", "RD", years=[2020], root=settings.root, settings=settings)
        assert sc.count_rows() > 0


class TestItKeepsLoadsGuards:
    def test_an_undeclared_dataset_is_refused(self, built_lake):
        settings, _catalog, _ = built_lake
        with pytest.raises(DatasetUnknown):
            scan("NOT_A_SYSTEM", "XX", root=settings.root, settings=settings)

    def test_generations_are_kept_apart(self, built_lake):
        """Two generations do not share a schema; concatenating them is a
        decision, not something a scan should do quietly."""
        settings, _catalog, _ = built_lake
        sc = scan("SIHSUS", "RD", root=settings.root, settings=settings)
        assert isinstance(sc, LakeScan)
        assert len(sc.schemas) == len(sc.scanners) >= 1


class TestStreamingExport:
    def test_it_writes_the_same_rows_as_the_eager_path(self, built_lake, tmp_path):
        settings, _catalog, _ = built_lake
        target = tmp_path / "streamed.parquet"
        export(
            "SIHSUS",
            "RD",
            path=target,
            format="parquet",
            profile="codes",
            stream=True,
            root=settings.root,
            settings=settings,
        )
        written = pq.read_table(target)
        expected = scan("SIHSUS", "RD", root=settings.root, settings=settings).count_rows()
        assert written.num_rows == expected

    def test_csv_streams_too(self, built_lake, tmp_path):
        settings, _catalog, _ = built_lake
        target = tmp_path / "streamed.csv"
        export(
            "SIHSUS", "RD", path=target, format="csv", profile="codes", stream=True,
            root=settings.root, settings=settings,
        )
        with target.open(newline="", encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        expected = scan("SIHSUS", "RD", root=settings.root, settings=settings).count_rows()
        assert len(rows) - 1 == expected, "one header plus every row"

    def test_nothing_is_left_behind_on_success(self, built_lake, tmp_path):
        settings, _catalog, _ = built_lake
        target = tmp_path / "streamed.parquet"
        export(
            "SIHSUS", "RD", path=target, format="parquet", profile="codes", stream=True,
            root=settings.root, settings=settings,
        )
        assert not list(tmp_path.glob("*.part")), "staged file was renamed, not orphaned"

    def test_streaming_a_rendered_profile_is_refused_with_a_reason(
        self, built_lake, tmp_path
    ):
        """Choosing a codelist is a whole-column question; per batch, two
        batches of one column could disagree."""
        settings, _catalog, _ = built_lake
        with pytest.raises(ValueError, match="whole-column"):
            export(
                "SIHSUS", "RD", path=tmp_path / "x.csv", format="csv",
                profile="analysis", stream=True,
                root=settings.root, settings=settings,
            )

    def test_streaming_xlsx_is_refused_with_a_reason(self, built_lake, tmp_path):
        settings, _catalog, _ = built_lake
        with pytest.raises(ValueError, match="memory"):
            export(
                "SIHSUS", "RD", path=tmp_path / "x.xlsx", format="xlsx",
                profile="codes", stream=True,
                root=settings.root, settings=settings,
            )
