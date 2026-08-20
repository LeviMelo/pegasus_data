"""Asking what DATASUS has, without downloading it.

DATASUS publishes no index. Finding out what exists has meant clicking through an
FTP tree, which is why most people use one system for the years someone told them
about. This module crawled the whole thing and the map compresses to about a
megabyte, so it ships — and that changes what a fresh install *is*: not "crawl
for a few hours and then ask", but an answer immediately, offline.

What these tests protect is that the answer never overstates itself. A shipped
snapshot is a photograph of a server that keeps moving, so every result has to
name where it came from and when. A result that silently presents a two-year-old
snapshot as the state of the server is worse than no answer, because nobody
thinks to doubt it.
"""

from __future__ import annotations

import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.explore import explore, tree_snapshot


def add_file(
    catalog: Catalog,
    path: str,
    *,
    system: str = "SIHSUS",
    series: str = "RD",
    uf: str = "AL",
    year: int = 2023,
    yyyymm: int = 202301,
    size: int = 1000,
    role: str = "data",
) -> None:
    catalog.execute(
        "INSERT INTO files (path, directory, filename, size, first_seen, last_seen) "
        "VALUES (?,?,?,?,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')",
        (path, path.rsplit("/", 1)[0], path.rsplit("/", 1)[-1], size),
    )
    catalog.execute(
        "INSERT INTO file_facts (path, system, series_prefix, geo_code, year, "
        "normalized_date, role, container_format) VALUES (?,?,?,?,?,?,?, '.dbc')",
        (path, system, series, uf, year, yyyymm, role),
    )


@pytest.fixture
def crawled(settings):
    catalog = Catalog(settings.catalog_path)
    add_file(catalog, "/p/RDAL2301.dbc", size=2 * 2**20)
    add_file(catalog, "/p/RDAL2302.dbc", yyyymm=202302, size=2 * 2**20)
    add_file(catalog, "/p/RDSP2401.dbc", uf="SP", year=2024, yyyymm=202401, size=8 * 2**20)
    add_file(catalog, "/p/SPAL2301.dbc", series="SP", size=2**20)
    add_file(catalog, "/p/DOAL2023.dbc", system="SIM", series="DO", year=2023, size=2**20)
    add_file(
        catalog, "/p/IT_SIHSUS.pdf", role="documentation", size=2**19,
    )
    catalog.execute(
        "INSERT INTO crawl_runs (run_id, host, base_path, started_at, finished_at, "
        "directories, files, gaps, connections) "
        "VALUES ('r1','h','/p','2026-01-01T00:00:00Z','2026-01-02T00:00:00Z',1,6,0,1)"
    )
    catalog.close()
    return settings


class TestTheFourQuestions:
    def test_with_no_target_it_lists_the_systems(self, crawled):
        result = explore(settings=crawled)
        assert result.level == "systems"
        assert {r["system"] for r in result.rows} == {"SIHSUS", "SIM"}

    def test_a_system_lists_its_series(self, crawled):
        result = explore("SIHSUS", settings=crawled)
        assert result.level == "series"
        assert {r["series"] for r in result.rows} == {"RD", "SP"}

    def test_a_dataset_gives_its_coverage_by_year(self, crawled):
        result = explore("SIH-RD", settings=crawled)
        assert result.level == "coverage"
        assert [r["year"] for r in result.rows] == [2023, 2024]

    def test_naming_a_year_gives_the_files_themselves(self, crawled):
        result = explore("SIH-RD", year=2023, settings=crawled)
        assert result.level == "files"
        assert {r["path"] for r in result.rows} == {"/p/RDAL2301.dbc", "/p/RDAL2302.dbc"}

    def test_the_files_carry_their_size_so_a_download_can_be_judged(self, crawled):
        result = explore("SIH-RD", year=2023, settings=crawled)
        assert all(r["megabytes"] == 2.0 for r in result.rows)


class TestCoverageIsChronological:
    def test_years_read_in_order_not_by_volume(self, settings):
        """A missing year is the thing people look for, and it only shows up
        when the years are in order."""
        catalog = Catalog(settings.catalog_path)
        add_file(catalog, "/p/a.dbc", year=2020, size=9 * 2**20)
        add_file(catalog, "/p/b.dbc", year=2018, size=2**20)
        add_file(catalog, "/p/c.dbc", year=2019, size=2**20)
        catalog.close()
        assert [r["year"] for r in explore("SIH-RD", settings=settings).rows] == [
            2018, 2019, 2020
        ]


class TestItSaysWhereTheAnswerCameFrom:
    def test_a_local_crawl_is_named_as_the_source(self, crawled):
        result = explore(settings=crawled)
        assert result.source == "local crawl"

    def test_the_date_of_the_crawl_travels_with_the_answer(self, crawled):
        """A snapshot presented without its date is the failure mode."""
        assert explore(settings=crawled).as_of == "2026-01-02T00:00:00Z"

    def test_a_local_crawl_beats_the_shipped_snapshot(self, crawled):
        """The snapshot is a photograph; the crawl is the server."""
        assert explore(settings=crawled).source == "local crawl"

    def test_with_no_crawl_it_falls_back_to_what_shipped(self, settings):
        rows, _ = tree_snapshot()
        if not rows:
            pytest.skip("this build ships no snapshot")
        assert explore(settings=settings).source == "packaged snapshot"

    def test_the_snapshot_can_be_asked_for_explicitly(self, crawled):
        rows, _ = tree_snapshot()
        if not rows:
            pytest.skip("this build ships no snapshot")
        assert explore(source="packaged", settings=crawled).source == "packaged snapshot"


class TestFiltering:
    def test_documentation_is_excluded_by_default(self, crawled):
        """Asking what data exists should not count the PDFs beside it."""
        assert explore("SIHSUS", settings=crawled).total_files == 4

    def test_but_can_be_asked_for(self, crawled):
        assert explore("SIHSUS", role=None, settings=crawled).total_files == 5

    def test_a_state_filter_narrows_it(self, crawled):
        assert explore("SIH-RD", uf="SP", settings=crawled).total_files == 1


class TestItDoesNotPretendToKnow:
    def test_an_unknown_system_returns_nothing_and_suggests_what_exists(self, crawled):
        result = explore("SIHSUSX", settings=crawled)
        assert result.rows == []
        assert result.unknown, "names what it does know rather than an empty answer"

    def test_with_no_map_at_all_it_says_so_rather_than_returning_empty(
        self, settings, monkeypatch
    ):
        import pegasus_data.explore as module

        monkeypatch.setattr(module, "tree_snapshot", lambda: ([], None))
        with pytest.raises(FileNotFoundError, match="no map of DATASUS"):
            explore(settings=settings)


class TestTheResultIsUsable:
    def test_it_converts_to_arrow_for_analysis(self, crawled):
        table = explore("SIHSUS", settings=crawled).table
        assert table.num_rows == 2 and "series" in table.column_names

    def test_it_is_iterable_and_sized(self, crawled):
        result = explore("SIHSUS", settings=crawled)
        assert len(result) == 2 and len(list(result)) == 2

    def test_the_repr_leads_with_volume_because_that_decides_the_download(self, crawled):
        text = repr(explore("SIHSUS", settings=crawled))
        assert "files" in text and "GiB" in text and "local crawl" in text

    def test_it_serialises_to_plain_data(self, crawled):
        import json

        payload = json.loads(json.dumps(explore("SIHSUS", settings=crawled).as_dict()))
        assert payload["level"] == "series" and payload["source"] == "local crawl"


class TestTheShippedMap:
    def test_the_snapshot_covers_the_whole_tree_if_it_ships_at_all(self):
        rows, as_of = tree_snapshot()
        if not rows:
            pytest.skip("this build ships no snapshot")
        assert len(rows) > 100_000, "a partial map would be worse than none"
        assert as_of, "a snapshot without a date cannot be judged for staleness"
