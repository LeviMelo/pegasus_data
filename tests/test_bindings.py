"""Does a bound codelist actually decode the column it is bound to?

`.DEF` declares tabulation axes alongside code systems and does not distinguish
them. ``LAno/mês de internação,DT_INTER,,ANOMES.CNV`` says TabNet can group
admissions by year-month *derived from* DT_INTER; it does not say DT_INTER is
coded in ANOMES. The binder cannot tell them apart from the grammar, so dates end
up bound to year tables, ages to age bands, and birth weight in grams to a table
of weight ranges.

Measured on the shipped catalog: **35.2% of checkable bindings decode none of
their column's observed values**, and 35 columns were reported as decodable with
every binding dead. That number reached users.

What these tests hold is the distinction between the three states, because
collapsing any two of them produces a lie: *decodes*, *measured and decodes
nothing*, and *never measured* — which is not zero, and treating it as zero would
strike out every column the profiler has not reached, which is most of the tree.
"""

from __future__ import annotations

from pegasus_data.catalog.store import Catalog
from pegasus_data.semantics.bindings import measure_bindings, working_bindings


def bind(catalog: Catalog, field: str, codelist: str, *, system: str = "SIHSUS") -> None:
    catalog.execute(
        "INSERT OR REPLACE INTO field_codelists (system, family_id, field_name, codelist, "
        "source, source_ref, confidence) VALUES (?,'',?,?,'def','RD.DEF',0.9)",
        (system, field, codelist),
    )


def codes(catalog: Catalog, codelist: str, values: dict[str, str], *, system: str = "SIHSUS") -> None:
    for code, label in values.items():
        catalog.execute(
            "INSERT INTO dictionary (system, value_group, field_name, value_raw, value_label, "
            "source, source_ref, confidence) VALUES (?,?,'',?,?,'cnv','x',0.9)",
            (system, codelist, code, label),
        )


def observed(catalog: Catalog, field: str, values: dict[str, int], *, system: str = "SIHSUS") -> None:
    catalog.execute(
        "INSERT OR IGNORE INTO families (family_id, system, series, schema_signature) "
        "VALUES ('F1',?,'RD','sig')",
        (system,),
    )
    for value, count in values.items():
        catalog.execute(
            "INSERT INTO value_frequencies (family_id, field_name, schema_signature, value, count) "
            "VALUES ('F1',?,'sig',?,?)",
            (field, value, count),
        )


class TestMeasuringWhatABindingDecodes:
    def test_a_codelist_that_decodes_is_recorded_as_such(self, catalog: Catalog):
        bind(catalog, "SEXO", "SEXO")
        codes(catalog, "SEXO", {"1": "Masculino", "3": "Feminino"})
        observed(catalog, "SEXO", {"1": 500, "3": 400})
        report = measure_bindings(catalog)
        assert (report.measured, report.decoding, report.dead) == (1, 1, 0)

    def test_a_tabulation_axis_bound_to_a_date_decodes_nothing(self, catalog: Catalog):
        """The defect this exists for: DT_INTER holds 8-digit dates and ANOMES
        holds 6-digit year-months, so the axis matches none of them."""
        bind(catalog, "DT_INTER", "ANOMES")
        codes(catalog, "ANOMES", {"202301": "jan/2023", "202302": "fev/2023"})
        observed(catalog, "DT_INTER", {"20230115": 90, "20230220": 60})
        report = measure_bindings(catalog)
        assert (report.measured, report.dead) == (1, 1)
        assert report.fields_all_dead == 1

    def test_the_share_decoded_is_stored_beside_the_claim(self, catalog: Catalog):
        bind(catalog, "SEXO", "SEXO")
        codes(catalog, "SEXO", {"1": "Masculino"})
        observed(catalog, "SEXO", {"1": 500, "3": 400})
        measure_bindings(catalog)
        row = catalog.query("SELECT decodes_observed FROM field_codelists")[0]
        assert row["decodes_observed"] == 0.5

    def test_the_claim_itself_is_never_deleted(self, catalog: Catalog):
        """.DEF really did say it. Throwing that away loses the only record of
        what DATASUS published."""
        bind(catalog, "DT_INTER", "ANOMES")
        codes(catalog, "ANOMES", {"202301": "jan/2023"})
        observed(catalog, "DT_INTER", {"20230115": 90})
        measure_bindings(catalog)
        row = catalog.query("SELECT codelist, source, source_ref FROM field_codelists")[0]
        assert (row["codelist"], row["source"], row["source_ref"]) == (
            "ANOMES", "def", "RD.DEF",
        )

    def test_it_is_recorded_in_the_event_log(self, catalog: Catalog):
        bind(catalog, "SEXO", "SEXO")
        codes(catalog, "SEXO", {"1": "Masculino"})
        observed(catalog, "SEXO", {"1": 5})
        measure_bindings(catalog)
        assert catalog.count("events", "stage = 'bindings'") == 1


class TestUnmeasuredIsNotZero:
    def test_a_column_nobody_profiled_is_not_measured(self, catalog: Catalog):
        """Most of the tree is census-only. Treating unmeasured as dead would
        strike out nearly every column."""
        bind(catalog, "PA_CODUNI", "CNES")
        codes(catalog, "CNES", {"0000001": "Hospital"})
        report = measure_bindings(catalog)
        assert (report.measured, report.unmeasurable) == (0, 1)

    def test_it_stays_null_rather_than_zero(self, catalog: Catalog):
        bind(catalog, "PA_CODUNI", "CNES")
        codes(catalog, "CNES", {"0000001": "Hospital"})
        measure_bindings(catalog)
        assert catalog.query("SELECT decodes_observed FROM field_codelists")[0][0] is None

    def test_an_unmeasured_binding_is_still_offered(self, catalog: Catalog):
        bind(catalog, "PA_CODUNI", "CNES")
        codes(catalog, "CNES", {"0000001": "Hospital"})
        measure_bindings(catalog)
        assert working_bindings(catalog, "SIHSUS") == {"PA_CODUNI": ["CNES"]}


class TestWhatConsumersSee:
    def test_a_dead_binding_is_withheld(self, catalog: Catalog):
        bind(catalog, "DT_INTER", "ANOMES")
        codes(catalog, "ANOMES", {"202301": "jan/2023"})
        observed(catalog, "DT_INTER", {"20230115": 90})
        measure_bindings(catalog)
        assert working_bindings(catalog, "SIHSUS") == {}

    def test_a_working_one_survives_beside_a_dead_one(self, catalog: Catalog):
        bind(catalog, "SEXO", "SEXO")
        bind(catalog, "SEXO", "ANOMES")
        codes(catalog, "SEXO", {"1": "Masculino"})
        codes(catalog, "ANOMES", {"202301": "jan/2023"})
        observed(catalog, "SEXO", {"1": 90})
        measure_bindings(catalog)
        assert working_bindings(catalog, "SIHSUS") == {"SEXO": ["SEXO"]}

    def test_the_best_decoder_is_offered_first(self, catalog: Catalog):
        bind(catalog, "SEXO", "PARTIAL")
        bind(catalog, "SEXO", "FULL")
        codes(catalog, "PARTIAL", {"1": "Masculino"})
        codes(catalog, "FULL", {"1": "Masculino", "3": "Feminino"})
        observed(catalog, "SEXO", {"1": 90, "3": 10})
        measure_bindings(catalog)
        assert working_bindings(catalog, "SIHSUS")["SEXO"][0] == "FULL"


class TestItIsRepeatable:
    def test_measuring_twice_gives_the_same_answer(self, catalog: Catalog):
        bind(catalog, "SEXO", "SEXO")
        codes(catalog, "SEXO", {"1": "Masculino"})
        observed(catalog, "SEXO", {"1": 5, "9": 1})
        first = measure_bindings(catalog).as_dict()
        assert measure_bindings(catalog).as_dict() == first
