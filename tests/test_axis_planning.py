"""Measuring one dataset's axes should not cost a sweep of all 131.

``axis_refusal`` asks whether the requested filters correspond to axes the files
are actually split on. It got that answer from ``Ontology.axes``, which groups
every data file on the tree and calls ``bind`` once per group — tens of
thousands of calls resolving the same few hundred distinct pairs, to build a map
of 131 datasets from which the caller took exactly one.

Measured on a warm ``fetch()``: 75% of the whole call, and all of it Python
holding the GIL, so concurrent callers slowed each other down instead of
overlapping — 12 requests on 4 threads took 0.65x as long as running them one
after another. Binding the distinct pairs once and narrowing the scan in SQL
took a warm fetch from 1295ms to 289ms and turned that 0.65x into 1.68x.

The risk in narrowing a query is dropping rows that belonged in the answer, so
the tests that matter here are the equivalence ones: `axes_for` must agree with
the full sweep everywhere, including when one dataset's files sit under more
than one crawled system name.
"""

from __future__ import annotations

import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.config import Settings
from pegasus_data.ontology import Ontology


def _seed(catalog: Catalog, rows) -> None:
    """rows: (path, system, series_prefix, geo_code, year, normalized_date).

    ``normalized_date`` decides the month axis — six characters or more means
    the files are split by competencia — so it is spelled out per row rather
    than derived, which is how the first draft of this fixture accidentally
    gave a state-split monthly series no month.
    """
    catalog.upsert_files(
        [
            {
                "path": row[0],
                "directory": "/d",
                "filename": row[0].rsplit("/", 1)[-1],
                "extension": ".dbc",
                "size": 100,
            }
            for row in rows
        ]
    )
    for path, system, series, geo, year, normalized in rows:
        catalog.execute(
            "INSERT OR REPLACE INTO file_facts (path, system, series_prefix,"
            " geo_code, year, normalized_date, date_format, role)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (
                path,
                system,
                series,
                geo,
                year,
                normalized,
                "YYMM" if len(normalized) >= 6 else "YYYY",
                "data",
            ),
        )


@pytest.fixture
def tree(settings: Settings) -> Settings:
    """A few datasets with genuinely different axes.

    DOFET is national and yearly; RD is split by state and month. Mixing them
    is the point: a narrowed scan that leaked rows between datasets would show
    up as one borrowing the other's axes.
    """
    store = Catalog(settings.catalog_path)
    try:
        _seed(
            store,
            [
                (f"/SIM/DOFET/DOFET{y}.dbc", "SIM", "DOFET", None, y, str(y))
                for y in (1996, 1997, 1998)
            ]
            + [
                (f"/SIH/RD/RD{uf}{y}01.dbc", "SIH", "RD", uf, y, f"{y}01")
                for uf in ("AC", "SP")
                for y in (2020, 2021)
            ],
        )
    finally:
        store.close()
    return settings


def _shape(axes) -> tuple | None:
    if axes is None:
        return None
    return (axes.dataset, axes.files, axes.uf, axes.year, axes.month, dict(axes.date_formats))


class TestItAgreesWithTheFullSweep:
    def test_every_declared_dataset_gets_the_same_answer(self, tree) -> None:
        """The whole safety case for narrowing the query, over all 131 codes."""
        onto = Ontology.load()
        store = Catalog(tree.catalog_path, read_only=True)
        try:
            full = onto.axes(store.conn)
            for code in sorted(set(full) | set(onto.datasets)):
                assert _shape(onto.axes_for(store.conn, code)) == _shape(full.get(code)), code
        finally:
            store.close()

    def test_a_national_dataset_still_has_no_state_axis(self, tree) -> None:
        onto = Ontology.load()
        store = Catalog(tree.catalog_path, read_only=True)
        try:
            axes = onto.axes_for(store.conn, "SIM.DOFET")
        finally:
            store.close()
        assert axes is not None and axes.files == 3
        assert axes.names == ["year"], "the narrowed scan lost the measurement"

    def test_a_state_split_dataset_keeps_all_three(self, tree) -> None:
        onto = Ontology.load()
        store = Catalog(tree.catalog_path, read_only=True)
        try:
            axes = onto.axes_for(store.conn, "SIH.RD")
        finally:
            store.close()
        assert axes is not None and axes.files == 4
        assert axes.names == ["uf", "year", "month"]

    def test_a_dataset_with_no_files_is_none_not_empty(self, tree) -> None:
        """`axes().get()` returned None for these; the narrow path must too, or
        every caller's `if axes is None` branch changes meaning."""
        onto = Ontology.load()
        store = Catalog(tree.catalog_path, read_only=True)
        try:
            assert onto.axes_for(store.conn, "CNES.ST") is None
            assert onto.axes_for(store.conn, "NOT.ADATASET") is None
        finally:
            store.close()


class TestItDoesNotDropRepublishedFiles:
    def test_files_under_a_second_crawled_system_are_counted(self, settings) -> None:
        """A dataset binds through the series-only fallback when the crawled
        directory is not its declared system — the republication trees. Those
        files carry a DIFFERENT `system` value, so a scan narrowed to the
        DECLARED system would silently drop them and report half the files.
        """
        store = Catalog(settings.catalog_path)
        try:
            _seed(
                store,
                [("/SIM/DOFET/DOFET1996.dbc", "SIM", "DOFET", None, 1996, "1996")]
                + [("/OPEN/DOFET1997.dbc", "DADOS_ABERTOS", "DOFET", None, 1997, "1997")],
            )
        finally:
            store.close()

        onto = Ontology.load()
        store = Catalog(settings.catalog_path, read_only=True)
        try:
            assert onto.bind("DADOS_ABERTOS", "DOFET").dataset == "SIM.DOFET", (
                "fixture assumption: the series-only fallback binds this"
            )
            narrow = onto.axes_for(store.conn, "SIM.DOFET")
            assert _shape(narrow) == _shape(onto.axes(store.conn).get("SIM.DOFET"))
        finally:
            store.close()
        assert narrow is not None and narrow.files == 2, (
            "the republished file was dropped by the narrowed scan"
        )


class TestBindIsMemoisedWithoutChangingAnswers:
    def test_the_same_pair_returns_an_equal_binding(self) -> None:
        onto = Ontology.load()
        first = onto.bind("SIM", "DOFET")
        assert onto.bind("SIM", "DOFET") == first

    def test_different_pairs_do_not_share_a_cache_entry(self) -> None:
        onto = Ontology.load()
        assert onto.bind("SIM", "DOFET").dataset != onto.bind("SIH", "RD").dataset

    def test_case_and_blanks_normalise_the_way_they_did(self) -> None:
        onto = Ontology.load()
        assert onto.bind("sim", "dofet") == onto.bind("SIM", "DOFET")
        assert onto.bind("SIM", "").dataset is None
        assert onto.bind("", "").dataset is None

    def test_an_unbound_pair_is_cached_as_unbound(self) -> None:
        """Caching a miss is the common case on a real tree and must not turn
        into a bind on the second ask."""
        onto = Ontology.load()
        assert onto.bind("NOPE", "NOPE").dataset is None
        assert onto.bind("NOPE", "NOPE").dataset is None


class TestItStopsScanningTheWholeTree:
    def test_one_dataset_reads_fewer_rows_than_the_full_sweep(self, tree) -> None:
        """The point of the change, asserted on what SQLite was asked to do
        rather than on a stopwatch, which would be flaky in CI."""
        onto = Ontology.load()
        store = Catalog(tree.catalog_path, read_only=True)
        try:
            counted: list[int] = []

            class Counting:
                """`sqlite3.Connection.execute` is read-only, so the scan is
                observed through a forwarding shim instead of a monkeypatch."""

                def __init__(self, conn):
                    self._conn = conn

                def execute(self, sql, *a):
                    cur = self._conn.execute(sql, *a)
                    if "GROUP BY" in sql:
                        rows = cur.fetchall()
                        counted.append(len(rows))
                        return iter(rows)
                    return cur

            shim = Counting(store.conn)
            onto.axes_for(shim, "SIM.DOFET")
            narrow = sum(counted)
            counted.clear()
            onto.axes(shim)
            full = sum(counted)
        finally:
            store.close()
        assert narrow < full, (
            f"the narrowed scan grouped {narrow} rows and the full sweep {full}; "
            "nothing was pushed into SQL"
        )
