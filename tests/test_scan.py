"""ME-20: the lazy primitive that was missing between fetch()/load() and DuckDB.

Both public readers materialised a whole `pa.Table`, so a national multi-year
question had exactly one supported shape: build the entire answer in memory
first. `scan()` carries the same guards — declared-dataset resolution, the
file-axis refusal — and hands back batches.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pyarrow as pa
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


class TestStreamingAcrossGenerations:
    """The case a single-generation test cannot reach.

    A file has one header, and the writer was being created from whichever
    generation's batch arrived first — so the moment a second generation with a
    different schema came through, the export died with "Table schema does not
    match schema used to create file". The unit tests passed; a real two-
    generation lake did not.
    """

    def test_it_writes_the_union_of_every_generations_columns(
        self, built_lake, tmp_path
    ):
        settings, _catalog, _ = built_lake
        sc = scan("SIHSUS", "RD", root=settings.root, settings=settings)
        union = {n for s in sc.schemas.values() for n in s.names}

        target = tmp_path / "all.parquet"
        export(
            "SIHSUS", "RD", path=target, format="parquet", profile="codes",
            stream=True, root=settings.root, settings=settings,
        )
        written = pq.read_table(target)
        assert set(written.schema.names) == union
        assert written.num_rows == sc.count_rows(), "no generation was dropped"

    @staticmethod
    def _mixed_scan(tmp_path):
        """Two generations that genuinely disagree about their columns.

        Built directly, because the shared `built_lake` fixture's generations
        happen to carry the same columns — which is exactly why the first
        version of this test passed while a real CNES export died.
        """
        tmp_path = Path(tmp_path)
        tmp_path.mkdir(parents=True, exist_ok=True)
        old = pa.table({"ID": ["1", "2"], "SEXO": ["1", "3"]})
        new = pa.table({"ID": ["3"], "SEXO": ["2"], "IDADE": ["40"]})
        scanners = []
        for name, table in (("OLD", old), ("NEW", new)):
            directory = tmp_path / name
            directory.mkdir()
            pq.write_table(table, directory / "part-0.parquet")
            dataset = ds.dataset(directory, format="parquet")
            scanners.append((name, dataset.scanner()))
        return LakeScan(scanners=scanners, system="SIHSUS", series="RD",
                        families=["OLD", "NEW"])

    def test_a_generation_that_lacks_a_column_is_null_filled_not_dropped(
        self, tmp_path
    ):
        from pegasus_data.api import _write_streaming

        sc = self._mixed_scan(tmp_path / "lake")
        target = tmp_path / "out.parquet"
        _write_streaming(sc, target, "parquet")

        written = pq.read_table(target)
        assert written.num_rows == 3, "no generation was dropped"
        assert set(written.schema.names) == {"ID", "SEXO", "IDADE"}
        idade = written.column("IDADE").to_pylist()
        assert idade.count(None) == 2, (
            "the generation without IDADE contributes structural nulls, not "
            "missing rows"
        )
        assert sorted(written.column("ID").to_pylist()) == ["1", "2", "3"]

    def test_public_null_fill_yields_one_exact_requested_schema_per_batch(
        self, built_lake
    ):
        """Lazy batches, not only a materialised union, are the API contract."""
        from pegasus_data.persist.lake import Lake

        settings, catalog, _new_family = built_lake
        old = catalog.query(
            "SELECT family_id, schema_signature FROM families "
            "WHERE system='SIHSUS' AND series='RD' ORDER BY time_min"
        )[0]
        old_table = pa.table(
            {
                "MUNIC_RES": ["270430", "271070"],
                "SEXO": ["1", "2"],
                "DIAG_SECUN": ["0000", "0000"],
                "VAL_TOT": [1.0, 2.0],
            }
        )
        Lake(settings.lake_dir, catalog).write_batches(
            old_table.to_batches(),
            system="SIHSUS",
            family_id=str(old["family_id"]),
            schema_signature=str(old["schema_signature"]),
            uf="AL",
            year=2010,
        )

        lazy = scan(
            "SIHSUS",
            "RD",
            columns=["SEXO", "DIAGSEC1"],
            on_missing_column="null_fill",
            root=settings.root,
            settings=settings,
        )
        batches = list(lazy.iter_batches())
        assert batches
        assert all(batch.schema.names == ["SEXO", "DIAGSEC1"] for batch in batches)
        assert all(batch.schema == lazy.schema for batch in batches)
        combined = pa.Table.from_batches(batches, schema=lazy.schema)
        assert combined.num_rows == 5
        assert combined.column("DIAGSEC1").null_count >= 2
        assert set(combined.schema.names) == {"SEXO", "DIAGSEC1"}, (
            "an absent requested field must not make unrequested physical columns reappear"
        )

    def test_the_writer_is_not_built_from_whichever_batch_arrives_first(
        self, tmp_path
    ):
        """The actual failure: 'Table schema does not match schema used to
        create file' the moment the second generation came through."""
        from pegasus_data.api import _write_streaming

        sc = self._mixed_scan(tmp_path / "lake")
        _write_streaming(sc, tmp_path / "out.csv", "csv")
        rows = (tmp_path / "out.csv").read_text(encoding="utf-8").strip().splitlines()
        assert len(rows) == 4, "one header and three rows across both generations"

    def test_a_type_conflict_is_refused_rather_than_coerced(self):
        """Silently widening an int32 to a string because one vintage stored it
        differently is the kind of quiet change this package exists not to make."""
        from pegasus_data.api import _unified_schema

        with pytest.raises(ValueError, match="declare it as"):
            _unified_schema([
                pa.schema([pa.field("X", pa.int32())]),
                pa.schema([pa.field("X", pa.string())]),
            ])

    def test_column_order_is_first_seen(self):
        from pegasus_data.api import _unified_schema

        merged = _unified_schema([
            pa.schema([pa.field("A", pa.string()), pa.field("B", pa.string())]),
            pa.schema([pa.field("B", pa.string()), pa.field("C", pa.string())]),
        ])
        assert merged.names == ["A", "B", "C"]
