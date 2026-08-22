"""A projected read must still translate each year with its own codebook.

The vintage split reads the lake's `year` partition column to decide which
codebook applies to which rows. A projection built only from the caller's
requested columns dropped `year`, so the split had nothing to split on and fell
back to translating the whole answer at the earliest requested vintage — the
exact defect the split exists to fix, reintroduced through the projection path.

`year` is an internal dependency of rendering, so it is requested as an optional
column and removed again before the result is returned.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from pegasus_data.api import Catalog as PublicCatalog
from pegasus_data.api import load
from pegasus_data.persist.lake import Lake


class TestYearSurvivesProjectionButNotTheResult:
    def test_a_projected_load_does_not_return_year(self, built_lake):
        """It is carried for rendering, not because the caller asked for it."""
        settings, _catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            table = load(
                "SIHSUS", "RD", columns=["SEXO"], catalog=public, labels=False
            )
        finally:
            public.close()
        assert "year" not in table.schema.names, (
            "an internal dependency leaked into the caller's projection"
        )

    def test_asking_for_year_still_returns_it(self, built_lake):
        settings, _catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            table = load(
                "SIHSUS", "RD", columns=["SEXO", "year"], catalog=public, labels=False
            )
        finally:
            public.close()
        assert "year" in table.schema.names

    def test_the_read_actually_requests_year(self, built_lake, monkeypatch):
        """Observed at the call, not grepped from the source.

        A spelling assertion proves nothing about behaviour and breaks the
        moment the line moves to a helper — which is exactly what happened to
        the last one of these.
        """
        from pegasus_data.persist.lake import Lake

        settings, _catalog, _ = built_lake
        asked: list[list[str]] = []
        real = Lake.read

        def watched(self, **kw):
            asked.append(list(kw.get("optional_columns") or []))
            return real(self, **kw)

        monkeypatch.setattr(Lake, "read", watched)
        public = PublicCatalog(settings.root, settings=settings)
        try:
            load("SIHSUS", "RD", columns=["SEXO"], catalog=public, labels=False)
        finally:
            public.close()
        assert asked, "load() never reached the lake"
        assert any("year" in call for call in asked), (
            "a projected read did not ask for `year`, so the vintage split has "
            "nothing to split on and falls back to one codebook for every year"
        )

    def test_an_unprojected_load_is_unaffected(self, built_lake):
        settings, _catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            table = load("SIHSUS", "RD", catalog=public, labels=False)
        finally:
            public.close()
        assert table.num_rows > 0


class TestTheProjectionDistinguishesNoneFromEmpty:
    """`columns=None` means every column. `columns=[]` means none of them.

    Testing truthiness conflated the two, so a generation carrying none of the
    requested fields asked for an empty projection and was handed the whole
    table instead — the opposite of the request, and the shape structural
    null-filling depends on.
    """

    @pytest.fixture
    def lake(self, tmp_path):
        lake = Lake(tmp_path / "lake")
        batch = pa.record_batch({"A": pa.array(["1", "2"]), "B": pa.array(["x", "y"])})
        lake.write_batches(
            iter([batch]), system="SIHSUS", family_id="F1",
            schema_signature="sig", uf="AL", year=2023,
        )
        return lake

    def test_none_reads_every_column(self, lake):
        table = lake.read(system="SIHSUS", family_id="F1", columns=None)
        assert {"A", "B"} <= set(table.schema.names)

    def test_a_named_column_reads_only_that_one(self, lake):
        table = lake.read(system="SIHSUS", family_id="F1", columns=["A"])
        assert "B" not in table.schema.names

    def test_an_empty_projection_does_not_read_everything(self, lake):
        """It must not silently become 'read the whole table'."""
        table = lake.read(system="SIHSUS", family_id="F1", columns=[])
        assert "A" not in table.schema.names and "B" not in table.schema.names

    def test_an_empty_projection_still_yields_the_right_row_count(self, lake):
        """Those rows exist and have to be null-filled, not dropped."""
        full = lake.read(system="SIHSUS", family_id="F1", columns=None)
        empty = lake.read(system="SIHSUS", family_id="F1", columns=[])
        assert empty.num_rows == full.num_rows == 2

    def test_the_scanner_agrees_with_the_reader(self, lake):
        scanner = lake.scanner(system="SIHSUS", family_id="F1", columns=[])
        assert scanner.count_rows() == 2
        named = lake.scanner(system="SIHSUS", family_id="F1", columns=["A"])
        assert "B" not in named.projected_schema.names
