"""Partition axes: how the FILES are split, versus what the ROWS contain.

The API had been assuming every dataset is split by state, year and month. That
assumption is false, and false in the worst possible way: filtering on an axis a
dataset does not have matches zero files and returns an empty table, which is
indistinguishable from a truthful "no records".

``SIM.DOFET`` is the proof. Fetal deaths are published as 48 NATIONAL files —
``DOFET79.DBC`` — and the state lives in ``CODMUNRES``, a column *inside* them.
``explore("SIM-DOFET", uf="AC")`` returned 0 of 48 files and said nothing, which
reads as "Acre records no fetal deaths".

Every test here guards the distinction between a structural zero and a factual
one.
"""

from __future__ import annotations

import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.config import Settings
from pegasus_data.ontology import DatasetAxes


class TestMeasuringTheAxes:
    def test_a_national_series_has_no_state_axis(self) -> None:
        rows = [{"uf": None, "year": 1979 + i, "yyyymm": None} for i in range(48)]
        axes = DatasetAxes.measure("SIM.DOFET", rows)
        assert axes.names == ["year"]
        assert "uf" not in axes.names
        assert axes.missing(uf=True) == ["uf"]

    def test_a_state_split_series_has_all_three(self) -> None:
        rows = [{"uf": "AC", "year": 2022, "yyyymm": "202201"}] * 10
        axes = DatasetAxes.measure("SIH.RD", rows)
        assert axes.names == ["uf", "year", "month"]
        assert axes.missing(uf=True, year=True, month=True) == []

    def test_a_stray_state_file_does_not_make_a_series_filterable(self) -> None:
        """One file in a hundred carrying a UF is noise, not an axis."""
        rows = [{"uf": None, "year": 2020, "yyyymm": None}] * 99
        rows.append({"uf": "AC", "year": 2020, "yyyymm": None})
        assert "uf" not in DatasetAxes.measure("X.Y", rows).names

    def test_a_mostly_present_axis_is_flagged_as_a_silent_drop(self) -> None:
        """SIA.PA carries a state on 93% of files; the other 7% vanish silently."""
        rows = [{"uf": "AC", "year": 2020, "yyyymm": "202001"}] * 93
        rows += [{"uf": None, "year": 2020, "yyyymm": "202001"}] * 7
        axes = DatasetAxes.measure("SIA.PA", rows)
        assert "uf" in axes.names
        assert [name for name, _ in axes.partial()] == ["uf"]

    def test_a_complete_axis_is_not_reported_as_partial(self) -> None:
        """Without the rounding guard this warns "only 100% of files carry a year"."""
        rows = [{"uf": "AC", "year": 2020, "yyyymm": "202001"}] * 2000
        assert DatasetAxes.measure("SIH.RD", rows).partial() == []

    def test_an_empty_dataset_claims_no_axes(self) -> None:
        axes = DatasetAxes.measure("X.Y", [])
        assert axes.names == []
        assert axes.fractions() == {"uf": 0.0, "year": 0.0, "month": 0.0}

    def test_explain_names_what_is_there_instead(self) -> None:
        rows = [{"uf": None, "year": 1979, "yyyymm": None}] * 48
        message = DatasetAxes.measure("SIM.DOFET", rows).explain("uf")
        assert "not split by uf" in message
        assert "48 files" in message
        assert "year" in message


def _seed_national(catalog: Catalog) -> None:
    """SIM.DOFET as it really is: national files, a year, no state, no month."""
    catalog.upsert_files(
        [
            {"path": f"/dissemin/publicos/SIM/CID10/DOFET/DOFET{yy}.dbc",
             "directory": "/d", "filename": f"DOFET{yy}.dbc",
             "extension": ".dbc", "size": 100}
            for yy in range(96, 99)
        ]
    )
    for yy in range(96, 99):
        catalog.execute(
            "INSERT OR REPLACE INTO file_facts (path, system, series_prefix, geo_code,"
            " year, normalized_date, date_format, role) VALUES (?,?,?,?,?,?,?,?)",
            (f"/dissemin/publicos/SIM/CID10/DOFET/DOFET{yy}.dbc", "SIM", "DOFET",
             None, 1900 + yy, str(1900 + yy), "YY", "data"),
        )


@pytest.fixture
def national(settings: Settings) -> Settings:
    store = Catalog(settings.catalog_path)
    try:
        _seed_national(store)
    finally:
        store.close()
    return settings


class TestTheOntologyMeasuresTheCatalog:
    def test_it_reads_the_axes_off_file_facts(self, national) -> None:
        from pegasus_data.ontology import Ontology

        store = Catalog(national.catalog_path, read_only=True)
        try:
            axes = Ontology.load().axes(store.conn)
        finally:
            store.close()
        got = axes.get("SIM.DOFET")
        assert got is not None and got.files == 3
        assert got.names == ["year"]


class TestExploreSaysWhyItIsEmpty:
    def test_it_warns_instead_of_returning_a_bare_zero(self, national) -> None:
        from pegasus_data import explore

        found = explore("SIM-DOFET", uf="AC", settings=national)
        assert found.total_files == 0
        assert found.warnings and "not split by uf" in found.warnings[0]
        assert "not split by uf" in repr(found)

    def test_a_real_axis_produces_no_warning(self, national) -> None:
        from pegasus_data import explore

        assert explore("SIM-DOFET", year=1997, settings=national).warnings == []

    def test_an_unfiltered_look_is_never_warned_about(self, national) -> None:
        from pegasus_data import explore

        found = explore("SIM-DOFET", settings=national)
        assert found.warnings == []
        assert found.total_files == 3


class TestFetchRefusesRatherThanReturningEmpty:
    def test_it_raises_on_an_absent_axis(self, national) -> None:
        from pegasus_data import FilterHasNoAxis, fetch

        with pytest.raises(FilterHasNoAxis) as caught:
            fetch("SIM-DOFET", uf="AC", settings=national)
        message = str(caught.value)
        assert "not split by uf" in message
        assert "CODMUNRES" in message  # tells them where the state actually lives


class TestTheCompendiumCarriesIt:
    def test_a_dataset_row_records_how_it_is_split(self, national, tmp_path) -> None:
        import json
        import sqlite3

        from pegasus_data._compendium import compendium

        out = tmp_path / "c.sqlite"
        compendium(out, settings=national)
        conn = sqlite3.connect(f"file:{out}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT split_by, split_by_uf, split_by_year FROM datasets WHERE code='SIM.DOFET'"
        ).fetchone()
        assert json.loads(row["split_by"]) == ["year"]
        assert row["split_by_uf"] == 0.0
        assert row["split_by_year"] == 1.0
