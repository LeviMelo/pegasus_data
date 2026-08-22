"""A codelist bound to a column it cannot decode, measured rather than assumed.

`field_codelists` is built mostly from `.DEF` files, which declare that a
codelist labels a column without anyone checking against data. The schema
anticipated the problem — `decodes_observed` has always existed — and nothing
ever filled it in, so a binding resolving nothing ranked exactly as high as one
resolving everything.
"""

from __future__ import annotations

import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.config import Settings
from pegasus_data.semantics.bindings import measure_bindings


def _seed(catalog: Catalog) -> None:
    catalog.execute(
        "INSERT OR REPLACE INTO families (family_id, system, series, schema_signature,"
        " field_count, time_min, time_max, file_count) VALUES (?,?,?,?,?,?,?,?)",
        ("f1", "SIH", "RD", "s" * 64, 2, 2022, 2022, 1),
    )
    # SEXO holds 1 and 3, which SEXOBR defines and IDADEBR does not.
    for value, pct, rank in (("1", 0.6, 1), ("3", 0.4, 2)):
        catalog.execute(
            "INSERT INTO value_frequencies (family_id, field_name, schema_signature,"
            " value, count, percent, rank) VALUES (?,?,?,?,?,?,?)",
            ("f1", "SEXO", "s" * 64, value, 100, pct, rank),
        )
    for codelist in ("SEXOBR", "IDADEBR"):
        catalog.execute(
            "INSERT INTO field_codelists (system, family_id, field_name, codelist,"
            " source, source_ref, confidence) VALUES (?,?,?,?,?,?,?)",
            ("SIH", "", "SEXO", codelist, "def", "t.def", 0.9),
        )
    for value, label in (("1", "Masculino"), ("3", "Feminino")):
        catalog.execute(
            "INSERT INTO dictionary (system, field_name, value_raw, value_label,"
            " value_group, source, source_ref, confidence) VALUES (?,?,?,?,?,?,?,?)",
            ("SIH", "SEXO", value, label, "SEXOBR", "cnv", "t.cnv", 0.9),
        )
    for value, label in (("000", "menor de 1"), ("001", "1 ano")):
        catalog.execute(
            "INSERT INTO dictionary (system, field_name, value_raw, value_label,"
            " value_group, source, source_ref, confidence) VALUES (?,?,?,?,?,?,?,?)",
            ("SIH", "IDADE", value, label, "IDADEBR", "cnv", "t.cnv", 0.9),
        )


@pytest.fixture
def seeded(settings: Settings) -> Catalog:
    store = Catalog(settings.catalog_path)
    _seed(store)
    yield store
    store.close()


class TestTheRateIsMeasured:
    def test_a_working_binding_scores_one(self, seeded) -> None:
        measure_bindings(seeded)
        rate = seeded.scalar(
            "SELECT decodes_observed FROM field_codelists WHERE codelist='SEXOBR'"
        )
        assert rate == pytest.approx(1.0)

    def test_a_binding_that_decodes_nothing_scores_zero(self, seeded) -> None:
        """IDADEBR is bound to SEXO and defines no value SEXO ever holds."""
        measure_bindings(seeded)
        rate = seeded.scalar(
            "SELECT decodes_observed FROM field_codelists WHERE codelist='IDADEBR'"
        )
        assert rate == pytest.approx(0.0)

    def test_the_report_separates_the_two(self, seeded) -> None:
        report = measure_bindings(seeded)
        assert report.decodes_all == 1
        assert report.decodes_nothing == 1
        assert {w["codelist"] for w in report.worst} == {"IDADEBR"}

    def test_it_stamps_when_it_measured(self, seeded) -> None:
        measure_bindings(seeded)
        assert seeded.scalar(
            "SELECT measured_at FROM field_codelists WHERE codelist='SEXOBR'"
        )


class TestItMeasuresRatherThanDeletes:
    def test_a_zero_rate_binding_is_kept(self, seeded) -> None:
        """A rate of zero is evidence. Deciding what to do is curation."""
        measure_bindings(seeded)
        assert seeded.count("field_codelists", "codelist = 'IDADEBR'") == 1

    def test_running_twice_is_idempotent(self, seeded) -> None:
        first = measure_bindings(seeded).counts
        assert measure_bindings(seeded).counts == first


class TestItDegradesHonestly:
    def test_no_profile_means_no_claim(self, settings) -> None:
        store = Catalog(settings.catalog_path)
        try:
            store.execute(
                "INSERT INTO field_codelists (system, family_id, field_name, codelist,"
                " source, source_ref, confidence) VALUES (?,?,?,?,?,?,?)",
                ("SIH", "", "SEXO", "SEXOBR", "def", "t.def", 0.9),
            )
            report = measure_bindings(store)
            assert report.measured == 0
            assert store.scalar(
                "SELECT decodes_observed FROM field_codelists WHERE codelist='SEXOBR'"
            ) is None
        finally:
            store.close()
