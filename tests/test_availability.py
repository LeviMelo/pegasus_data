"""Structural absence is not missingness, and neither is silence.

A research group reading a compendium asked for a field-by-time validity layer,
because ``SIH.RD``'s nine secondary-diagnosis columns first appear in 2014 and a
query for ``DIAGSEC4`` in 2007 returns nothing for a reason that has nothing to
do with clinical reporting.

They proposed ``valid_from | valid_to``. That is one state short. In the real
catalog ``DIAGSEC4`` is carried by decoded files for 2014–2016 and 2018 onward,
and an interval reading 2014–2026 quietly asserts something about 2017 — a year
nothing has been decoded for at all. These tests hold all three states apart.
"""

from __future__ import annotations

import pytest

from pegasus_data._availability import FieldWindow, availability, field_available
from pegasus_data.catalog.store import Catalog
from pegasus_data.config import Settings


def _seed(catalog: Catalog) -> None:
    """SIH.RD in miniature: a column arrives, one year is never decoded.

    2005 and 2006 carry two columns; 2008 carries a third. 2007 has a published
    file but nothing decoded from it, which is the case an interval cannot
    express.
    """
    old, new = "a" * 64, "b" * 64
    years = {2005: old, 2006: old, 2008: new, 2009: new}
    paths = []
    for year in list(years) + [2007]:
        path = f"/dissemin/publicos/SIHSUS/RDAC{str(year)[2:]}01.dbc"
        paths.append((path, year))
    catalog.upsert_files(
        [{"path": p, "directory": "/d", "filename": p.rsplit("/", 1)[1],
          "extension": ".dbc", "size": 10} for p, _ in paths]
    )
    for path, year in paths:
        catalog.execute(
            "INSERT OR REPLACE INTO file_facts (path, system, series_prefix, geo_code,"
            " year, role) VALUES (?,?,?,?,?,?)",
            (path, "SIHSUS", "RD", "AC", year, "data"),
        )
    for year, sig in years.items():
        catalog.execute(
            "INSERT OR REPLACE INTO strata (stratum_id, system, series, year,"
            " schema_signature, file_count) VALUES (?,?,?,?,?,?)",
            (f"s{year}", "SIHSUS", "RD", year, sig, 1),
        )
    for sig, fields in ((old, ["N_AIH", "SEXO"]), (new, ["N_AIH", "SEXO", "DIAGSEC4"])):
        for order, name in enumerate(fields):
            catalog.execute(
                "INSERT INTO schema_presence (schema_signature, field_name, field_order)"
                " VALUES (?,?,?)",
                (sig, name, order),
            )


@pytest.fixture
def seeded(settings: Settings) -> Settings:
    store = Catalog(settings.catalog_path)
    try:
        _seed(store)
    finally:
        store.close()
    return settings


class TestTheThreeStates:
    def test_a_year_before_the_column_existed_is_a_positive_absent(self, seeded) -> None:
        """The load-bearing answer: the schema for 2005 exists and lacks it."""
        assert field_available("SIH-RD", "DIAGSEC4", 2005, settings=seeded) == "absent"

    def test_a_year_the_column_exists_in_is_present(self, seeded) -> None:
        assert field_available("SIH-RD", "DIAGSEC4", 2008, settings=seeded) == "present"

    def test_a_year_nothing_was_decoded_for_is_unknown(self, seeded) -> None:
        """2007 has a published file and no decoded schema. Neither claim holds."""
        assert field_available("SIH-RD", "DIAGSEC4", 2007, settings=seeded) == "unknown"

    def test_unknown_wins_over_a_bridged_interval(self, seeded) -> None:
        """A column spanning the gap still cannot be claimed for the gap year."""
        found = availability("SIH-RD", settings=seeded)
        sexo = found["SEXO"]
        assert sexo.intervals == [(2005, 2009)]      # bridged, so it reads as one run
        assert sexo.state(2007) == "unknown"          # but the year itself is not claimed
        assert sexo.bridged_years() == [2007]


class TestSpansReadHonestly:
    def test_a_gap_year_does_not_split_a_column_into_two_lives(self, seeded) -> None:
        """Splitting would imply the column was removed and reinstated."""
        found = availability("SIH-RD", settings=seeded)
        assert found["SEXO"].intervals == [(2005, 2009)]

    def test_the_span_names_what_was_never_decoded(self, seeded) -> None:
        assert "nothing decoded for 2007" in availability(
            "SIH-RD", settings=seeded
        )["SEXO"].span()

    def test_a_late_arriving_column_starts_where_it_arrived(self, seeded) -> None:
        found = availability("SIH-RD", settings=seeded)
        assert found["DIAGSEC4"].first_seen == 2008
        assert found["DIAGSEC4"].current is True

    def test_the_undecoded_years_are_reported(self, seeded) -> None:
        found = availability("SIH-RD", settings=seeded)
        assert found.undecoded_years == [2007]
        assert found.decoded_years == [2005, 2006, 2008, 2009]


class TestTheBoundaryList:
    def test_it_names_the_year_a_column_arrived(self, seeded) -> None:
        """Every entry is a year where a naive pooled query changes meaning."""
        changes = availability("SIH-RD", settings=seeded).changed_at()
        assert 2008 in changes
        assert "DIAGSEC4" in changes[2008]["added"]

    def test_the_first_year_is_not_reported_as_a_change(self, seeded) -> None:
        """Everything "arrives" in the first year; saying so is noise."""
        assert 2005 not in availability("SIH-RD", settings=seeded).changed_at()


class TestItRefusesToGuess:
    def test_an_unknown_dataset_suggests_rather_than_empties(self, seeded) -> None:
        with pytest.raises(ValueError, match="Did you mean"):
            availability("SIH-XX", settings=seeded)

    def test_both_spellings_of_a_dataset_resolve(self, seeded) -> None:
        """The rest of the API says SIH-RD; the ontology is keyed SIH.RD."""
        assert availability("SIH.RD", settings=seeded).dataset == "SIH.RD"
        assert availability("SIH-RD", settings=seeded).dataset == "SIH.RD"


class TestTheWindowStandsAlone:
    def test_a_window_with_no_observations_says_so(self) -> None:
        window = FieldWindow(dataset="X.Y", field="F")
        assert window.span() == "never observed"
        assert window.state(2020) == "unknown"
        assert window.first_seen is None
