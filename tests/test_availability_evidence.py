"""`absent` is a positive claim, so it has to rest on evidence for that year.

field_available() returned "absent" for a field never seen whenever ANY year of
the dataset had been decoded. A question about 1998, from a catalog that had
only ever decoded 2023, was therefore answered with a positive claim resting on
nothing — inverting the absent/unknown distinction its own docstring promises,
which exists to keep a structural zero from being read as a clinical one.

Year granularity is a second limit. A field introduced mid-year is in some of
that year's publications and not others, and a yearly present/absent has to
round that to one of two wrong answers. field_coverage() reports the evidence.
"""

from __future__ import annotations

from pegasus_data._availability import Availability, FieldWindow, field_coverage


def _seed(catalog, rows):
    """rows: (year, signature, [field names])."""
    # executemany, not execute: only the former commits, and availability()
    # opens its own read-only connection which cannot see an open transaction.
    catalog.executemany(
        "INSERT OR REPLACE INTO strata (stratum_id, system, series, year,"
        " schema_signature, file_count) VALUES (?,?,?,?,?,?)",
        [(f"{sig}-{y}", "SIHSUS", "RD", y, sig, 1) for y, sig, _f in rows],
    )
    catalog.executemany(
        "INSERT OR REPLACE INTO schema_presence (schema_signature, field_name) VALUES (?,?)",
        [(sig, name) for _y, sig, fields in rows for name in fields],
    )


class TestAbsentNeedsEvidenceForThatYear:
    def test_a_year_nothing_was_decoded_for_is_unknown(self, catalog, settings):
        """Even though another year was decoded."""
        from pegasus_data._availability import field_available

        _seed(catalog, [(2023, "sigA", ["ID", "SEXO"])])
        assert field_available("SIH.RD", "SEXO", 1998, settings=settings) == "unknown"

    def test_a_decoded_year_without_the_field_is_absent(self, catalog, settings):
        from pegasus_data._availability import field_available

        _seed(catalog, [(2023, "sigA", ["ID"])])
        assert field_available("SIH.RD", "SEXO", 2023, settings=settings) == "absent"

    def test_a_decoded_year_with_the_field_is_present(self, catalog, settings):
        from pegasus_data._availability import field_available

        _seed(catalog, [(2023, "sigA", ["ID", "SEXO"])])
        assert field_available("SIH.RD", "SEXO", 2023, settings=settings) == "present"

    def test_an_entirely_empty_catalog_says_unknown(self, catalog, settings):
        from pegasus_data._availability import field_available

        assert field_available("SIH.RD", "SEXO", 2023, settings=settings) == "unknown"


class TestWithinYearCoverage:
    def test_a_field_in_every_signature_of_the_year_is_present(self, catalog, settings):
        _seed(catalog, [(2015, "sigA", ["ID", "SEXO"]), (2015, "sigB", ["ID", "SEXO"])])
        got = field_coverage("SIH.RD", "SEXO", 2015, settings=settings)
        assert got["state"] == "present"
        assert got["signatures_carrying"] == got["signatures_decoded"] == 2

    def test_a_field_in_only_some_signatures_is_partial(self, catalog, settings):
        """A column introduced in July: a count over 2015 mixes artifacts that
        have it with artifacts that never had it."""
        _seed(catalog, [(2015, "sigA", ["ID"]), (2015, "sigB", ["ID", "SEXO"])])
        got = field_coverage("SIH.RD", "SEXO", 2015, settings=settings)
        assert got["state"] == "partial"
        assert (got["signatures_carrying"], got["signatures_decoded"]) == (1, 2)

    def test_a_field_in_no_signature_of_the_year_is_absent(self, catalog, settings):
        _seed(catalog, [(2015, "sigA", ["ID"]), (2015, "sigB", ["ID"])])
        assert field_coverage("SIH.RD", "SEXO", 2015, settings=settings)["state"] == "absent"

    def test_an_undecoded_year_is_unknown_with_no_denominator(self, catalog, settings):
        _seed(catalog, [(2015, "sigA", ["SEXO"])])
        got = field_coverage("SIH.RD", "SEXO", 1998, settings=settings)
        assert got["state"] == "unknown" and got["signatures_decoded"] == 0

    def test_the_yearly_answer_rounds_partial_to_present(self, catalog, settings):
        """Documented, not hidden: this is why field_coverage exists."""
        from pegasus_data._availability import field_available

        _seed(catalog, [(2015, "sigA", ["ID"]), (2015, "sigB", ["ID", "SEXO"])])
        assert field_available("SIH.RD", "SEXO", 2015, settings=settings) == "present"
        assert field_coverage("SIH.RD", "SEXO", 2015, settings=settings)["state"] == "partial"


class TestTheStructuresCarryTheEvidence:
    def test_a_window_records_carriers_per_year(self):
        window = FieldWindow(dataset="D", field="F", carriers={2015: 1})
        assert window.carriers[2015] == 1

    def test_availability_records_the_denominator(self):
        found = Availability(dataset="D", signatures={2015: 2})
        assert found.signatures[2015] == 2

    def test_field_coverage_is_public(self):
        import pegasus_data

        assert hasattr(pegasus_data, "field_coverage")
