"""A binding is a claim; the measurement is separate, and consumers use it.

`.DEF` claims a codelist explains a column, generously. It declares tabulation
axes alongside code systems and cannot tell them apart, so a date ends up bound
to a year table and a birth weight in grams to weight ranges.

`measure_bindings` records, per binding, the share of a column's observed values
the codelist actually resolves. `working_bindings` is the consumer that must not
hand back the dead ones. These tests hold the seam between them — a dead binding
that still reaches a caller yields a column reported as decodable and labelled by
nothing, which is worse than being reported as undecodable.

The three-way distinction that matters, and the one an on/off flag would lose:
NULL is *not measured*, 0 is *measured and dead*, and they are not the same. Most
of the tree has never been profiled, so treating unmeasured as dead would strike
out nearly everything.
"""

from __future__ import annotations

import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.config import Settings
from pegasus_data.semantics.bindings import measure_bindings, working_bindings


def _bind(catalog: Catalog, field: str, codelist: str) -> None:
    catalog.execute(
        "INSERT INTO field_codelists (system, family_id, field_name, codelist,"
        " source, source_ref, confidence) VALUES (?,?,?,?,?,?,?)",
        ("SIH", "f1", field, codelist, "def", "t.def", 0.9),
    )


def _seed(catalog: Catalog) -> None:
    """SEXO holds 1 and 3. SEXOBR defines both; ANOMES defines neither."""
    catalog.execute(
        "INSERT OR REPLACE INTO families (family_id, system, series, schema_signature,"
        " field_count, time_min, time_max, file_count) VALUES (?,?,?,?,?,?,?,?)",
        ("f1", "SIH", "RD", "s" * 64, 2, 2022, 2022, 1),
    )
    for value, pct, rank in (("1", 0.6, 1), ("3", 0.4, 2)):
        catalog.execute(
            "INSERT INTO value_frequencies (family_id, field_name, schema_signature,"
            " value, count, percent, rank) VALUES (?,?,?,?,?,?,?)",
            ("f1", "SEXO", "s" * 64, value, 100, pct, rank),
        )
    _bind(catalog, "SEXO", "SEXOBR")
    _bind(catalog, "SEXO", "ANOMES")
    for group, pairs in (
        ("SEXOBR", (("1", "Masculino"), ("3", "Feminino"))),
        ("ANOMES", (("202201", "jan/2022"), ("202202", "fev/2022"))),
    ):
        for value, label in pairs:
            catalog.execute(
                "INSERT INTO dictionary (system, field_name, value_raw, value_label,"
                " value_group, source, source_ref, confidence) VALUES (?,?,?,?,?,?,?,?)",
                ("SIH", "SEXO", value, label, group, "cnv", "t.cnv", 0.9),
            )


@pytest.fixture
def seeded(settings: Settings):
    store = Catalog(settings.catalog_path)
    try:
        _seed(store)
        yield store
    finally:
        store.close()


class TestTheShareIsRecorded:
    def test_a_codelist_that_resolves_the_column_scores_one(self, seeded) -> None:
        measure_bindings(seeded)
        assert seeded.scalar(
            "SELECT decodes_observed FROM field_codelists WHERE codelist='SEXOBR'"
        ) == pytest.approx(1.0)

    def test_a_codelist_bound_to_the_wrong_column_scores_zero(self, seeded) -> None:
        """ANOMES is a year-month table bound to a sex column — the .DEF shape."""
        measure_bindings(seeded)
        assert seeded.scalar(
            "SELECT decodes_observed FROM field_codelists WHERE codelist='ANOMES'"
        ) == pytest.approx(0.0)

    def test_the_report_separates_alive_from_dead(self, seeded) -> None:
        report = measure_bindings(seeded)
        assert (report.measured, report.decoding, report.dead) == (2, 1, 0 + 1)
        assert report.fields_all_dead == 0

    def test_it_stamps_when_it_measured(self, seeded) -> None:
        measure_bindings(seeded)
        assert seeded.scalar(
            "SELECT measured_at FROM field_codelists WHERE codelist='SEXOBR'"
        )


class TestUnmeasuredIsNotDead:
    def test_an_unprofiled_column_is_left_null(self, seeded) -> None:
        """NULL means nobody looked. Most of the tree has never been profiled."""
        _bind(seeded, "CAR_INT", "CARINT")
        report = measure_bindings(seeded)
        assert report.unmeasurable >= 1
        assert seeded.scalar(
            "SELECT decodes_observed FROM field_codelists WHERE codelist='CARINT'"
        ) is None

    def test_an_unmeasured_binding_is_still_offered(self, seeded) -> None:
        """Dropping unmeasured bindings would strike out nearly every column."""
        _bind(seeded, "CAR_INT", "CARINT")
        measure_bindings(seeded)
        assert "CARINT" in working_bindings(seeded, "SIH").get("CAR_INT", [])


class TestTheConsumerHonoursTheMeasurement:
    def test_a_dead_binding_is_not_offered(self, seeded) -> None:
        measure_bindings(seeded)
        assert "ANOMES" not in working_bindings(seeded, "SIH").get("SEXO", [])

    def test_the_working_one_is(self, seeded) -> None:
        measure_bindings(seeded)
        assert working_bindings(seeded, "SIH")["SEXO"] == ["SEXOBR"]

    def test_before_measurement_both_are_offered(self, seeded) -> None:
        """Unmeasured is not dead, so nothing is excluded until it is measured."""
        assert set(working_bindings(seeded, "SIH")["SEXO"]) == {"SEXOBR", "ANOMES"}


class TestItMeasuresRatherThanDeletes:
    def test_a_dead_binding_is_kept_on_record(self, seeded) -> None:
        """`.DEF` really does say what it says; losing that loses the record."""
        measure_bindings(seeded)
        assert seeded.count("field_codelists", "codelist = 'ANOMES'") == 1

    def test_running_twice_gives_the_same_answer(self, seeded) -> None:
        first = measure_bindings(seeded).as_dict()
        assert measure_bindings(seeded).as_dict() == first


class TestAColumnWithNoWorkingBinding:
    def test_it_is_counted(self, settings) -> None:
        """Reported as undecodable, which is honest, rather than mislabelled."""
        store = Catalog(settings.catalog_path)
        try:
            _seed(store)
            store.execute("DELETE FROM field_codelists WHERE codelist='SEXOBR'")
            report = measure_bindings(store)
            assert report.fields_all_dead == 1
            assert working_bindings(store, "SIH").get("SEXO", []) == []
        finally:
            store.close()
