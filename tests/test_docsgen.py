"""Generated documentation (§7).

The pages are the artifact for the working group and eventually the Ministry, so
what these tests protect is the warnings. A person reading about COD_IDADE has to
hit the trap on that page — not in a findings file they will never open.
"""

from __future__ import annotations

from pegasus_data.catalog.store import Catalog
from pegasus_data.docsgen import collect, generate, render_variable


def _family(catalog, family_id="f", system="SIHSUS", time_min=1992, time_max=2026, sig="sig"):
    catalog.execute(
        "INSERT INTO families (family_id, system, series, schema_signature, time_min, time_max) "
        "VALUES (?,?,?,?,?,?)",
        (family_id, system, "RD", sig, time_min, time_max),
    )


def _profile(catalog, name, family_id="f", sig="sig", **kw):
    catalog.execute(
        "INSERT INTO variable_profiles (family_id, field_name, schema_signature, physical_type, "
        "width, distinct_count, non_null) VALUES (?,?,?,?,?,?,?)",
        (
            family_id, name, sig, kw.get("physical_type", "C"), kw.get("width", 4),
            kw.get("distinct_count", 10), kw.get("non_null", 100),
        ),
    )


def _page(catalog, name, system="SIHSUS"):
    return next(p for p in collect(catalog, system) if p.field_name == name)


class TestWarnings:
    def test_a_column_dead_in_the_newest_generation_is_flagged(self, catalog: Catalog):
        """DIAG_SECUN holds real codes until the 113-column era, then only '0000'.

        A global "are all values sentinels" test says no and misses exactly the
        case that matters, which is what a reader gets if they query today.
        """
        _family(catalog, "old", time_min=1998, time_max=2014, sig="s86")
        _family(catalog, "new", time_min=2015, time_max=2026, sig="s113")
        _profile(catalog, "DIAG_SECUN", "old", "s86")
        _profile(catalog, "DIAG_SECUN", "new", "s113")
        for family_id, sig, value in (("old", "s86", "J189"), ("new", "s113", "0000")):
            catalog.execute(
                "INSERT INTO value_frequencies (family_id, field_name, schema_signature, value, "
                "count, percent, rank) VALUES (?,?,?,?,?,?,?)",
                (family_id, "DIAG_SECUN", sig, value, 1000, 1.0, 1),
            )
        page = _page(catalog, "DIAG_SECUN")
        assert page.retired
        assert "RETIRED" in render_variable(page)

    def test_a_healthy_column_carries_no_banner(self, catalog: Catalog):
        _family(catalog)
        _profile(catalog, "DIAG_PRINC")
        catalog.execute(
            "INSERT INTO value_frequencies (family_id, field_name, schema_signature, value, "
            "count, percent, rank) VALUES ('f','DIAG_PRINC','sig','J189',10,1.0,1)"
        )
        page = _page(catalog, "DIAG_PRINC")
        assert not page.retired
        assert render_variable(page).splitlines()[0].strip() == "### DIAG_PRINC"

    def test_a_modifier_warns_on_the_page_it_modifies_from(self, catalog: Catalog):
        _family(catalog)
        _profile(catalog, "COD_IDADE")
        catalog.execute(
            "INSERT INTO variable_docs (system, field_name, code_system, modifies, source) "
            "VALUES ('SIHSUS','COD_IDADE','internal','IDADE','layout_doc')"
        )
        text = render_variable(_page(catalog, "COD_IDADE"))
        assert "MODIFIES IDADE" in text
        assert "changes what `IDADE` means" in text

    def test_a_dependent_column_says_it_is_not_usable_alone(self, catalog: Catalog):
        _family(catalog)
        _profile(catalog, "IDADE")
        catalog.execute(
            'INSERT INTO variable_docs (system, field_name, code_system, depends_on, source) '
            "VALUES ('SIHSUS','IDADE','none','[\"COD_IDADE\"]','layout_doc')"
        )
        assert "NOT INTERPRETABLE ALONE" in render_variable(_page(catalog, "IDADE"))

    def test_an_inferred_meaning_is_marked_and_shows_its_reasoning(self, catalog: Catalog):
        _family(catalog)
        _profile(catalog, "LINHAA")
        catalog.execute(
            "INSERT INTO variable_docs (system, field_name, code_system, source, reasoning, "
            "asserted_by) VALUES ('SIHSUS','LINHAA','external','inferred',"
            "'measured over 7823 values','t')"
        )
        text = render_variable(_page(catalog, "LINHAA"))
        assert "INFERRED, NOT DOCUMENTED" in text
        assert "measured over 7823 values" in text


class TestItDoesNotMislead:
    def test_a_binding_that_decodes_nothing_is_not_offered_as_a_join(self, catalog: Catalog):
        """COD_IDADE is bound by .DEF to age-band axes that decode none of it."""
        _family(catalog)
        _profile(catalog, "COD_IDADE")
        catalog.execute(
            "INSERT INTO field_codelists (system, family_id, field_name, codelist, source, "
            "source_ref, confidence) VALUES ('SIHSUS','','COD_IDADE','IDADE18','def','d',0.9)"
        )
        catalog.execute(
            "INSERT INTO ledger (system, family_id, field_name, schema_signature_scope, "
            "dictionary_coverage) VALUES ('SIHSUS','f','COD_IDADE','sig',0.0)"
        )
        text = render_variable(_page(catalog, "COD_IDADE"))
        assert "NO WORKING CODELIST" in text
        assert "join `lake/reference/IDADE18/`" not in text

    def test_a_working_binding_is_offered(self, catalog: Catalog):
        _family(catalog)
        _profile(catalog, "DIAG_PRINC")
        catalog.execute(
            "INSERT INTO field_codelists (system, family_id, field_name, codelist, source, "
            "source_ref, confidence) VALUES ('SIHSUS','','DIAG_PRINC','CID10','cnv','c',0.95)"
        )
        catalog.execute(
            "INSERT INTO ledger (system, family_id, field_name, schema_signature_scope, "
            "dictionary_coverage) VALUES ('SIHSUS','f','DIAG_PRINC','sig',1.0)"
        )
        assert "join `lake/reference/CID10/` on `code`" in render_variable(
            _page(catalog, "DIAG_PRINC")
        )

    def test_rollups_of_the_same_classification_come_first(self, catalog: Catalog):
        """A diagnosis column does not roll up into notifiable diseases."""
        _family(catalog)
        _profile(catalog, "DIAG_PRINC")
        from pegasus_data.semantics.dictionary import DictionaryEntry, persist_entries

        entries = []
        for group, labels in (
            ("CID10", ("Septicemia", "Diabetes")),
            ("CID10CAP", ("Capítulo I", "Capítulo II")),
            ("AGRAVONOT", ("Dengue", "Malária")),
        ):
            entries += [
                DictionaryEntry(system="SIHSUS", value_raw=f"{group}{i}", value_label=label,
                                source="cnv", source_ref="x", confidence=0.95, value_group=group)
                for i, label in enumerate(labels)
            ]
        persist_entries(catalog, entries)
        for group, confidence in (("CID10", 0.95), ("CID10CAP", 0.9), ("AGRAVONOT", 0.9)):
            catalog.execute(
                "INSERT INTO field_codelists (system, family_id, field_name, codelist, source, "
                "source_ref, confidence) VALUES ('SIHSUS','','DIAG_PRINC',?,'cnv','x',?)",
                (group, confidence),
            )
        names = [name for name, _ in _page(catalog, "DIAG_PRINC").rollups]
        assert names.index("CID10CAP") < names.index("AGRAVONOT")

    def test_a_rollup_is_counted_in_categories_not_codes(self, catalog: Catalog):
        """CID10CAP maps 14,000 codes onto 22 chapters; 22 is the useful number."""
        _family(catalog)
        _profile(catalog, "DIAG_PRINC")
        from pegasus_data.semantics.dictionary import DictionaryEntry, persist_entries

        persist_entries(
            catalog,
            [
                DictionaryEntry(system="SIHSUS", value_raw=f"A{i:03d}", value_label="Capítulo I",
                                source="cnv", source_ref="x", confidence=0.95, value_group="CID10CAP")
                for i in range(50)
            ]
            + [
                DictionaryEntry(system="SIHSUS", value_raw="B001", value_label="Capítulo II",
                                source="cnv", source_ref="x", confidence=0.95, value_group="CID10CAP")
            ],
        )
        catalog.execute(
            "INSERT INTO field_codelists (system, family_id, field_name, codelist, source, "
            "source_ref, confidence) VALUES ('SIHSUS','','DIAG_PRINC','CID10CAP','cnv','x',0.9)"
        )
        assert _page(catalog, "DIAG_PRINC").rollups == [("CID10CAP", 2)]


class TestGeneration:
    def test_it_writes_an_index_and_a_page_per_system(self, catalog: Catalog, tmp_path):
        _family(catalog)
        _profile(catalog, "DIAG_PRINC")
        result = generate(catalog, tmp_path / "dict")
        assert (tmp_path / "dict" / "README.md").exists()
        assert (tmp_path / "dict" / "sihsus.md").exists()
        assert result["systems"][0]["system"] == "SIHSUS"

    def test_dataset_prose_becomes_its_own_page(self, catalog: Catalog, tmp_path):
        catalog.execute(
            "INSERT INTO dataset_docs (dataset_id, what_one_row_is, gotchas, source) "
            "VALUES ('SIHSUS_RD','one billing episode (AIH)','[\"not one patient\"]','manual')"
        )
        generate(catalog, tmp_path / "dict")
        text = (tmp_path / "dict" / "datasets" / "sihsus_rd.md").read_text(encoding="utf-8")
        assert "one billing episode (AIH)" in text
        assert "not one patient" in text

    def test_an_empty_catalog_produces_an_index_and_no_lies(self, catalog: Catalog, tmp_path):
        result = generate(catalog, tmp_path / "dict")
        assert result["systems"] == []
        assert (tmp_path / "dict" / "README.md").exists()


class TestCensusColumns:
    """A column nobody profiled is still a column (header census)."""

    def _census_column(self, catalog: Catalog, name="PA_CODUNI", system="SIASUS"):
        catalog.execute(
            "INSERT INTO strata (stratum_id, system, series, year, file_count, "
            "schema_signature, sample_status) VALUES ('S1',?,'PA',2024,1,'sig','header')",
            (system,),
        )
        catalog.execute(
            "INSERT INTO schema_header_facts (schema_signature, path, field_name, field_order, "
            "type_code, width, decimals, record_length, widths_consistent) "
            "VALUES ('sig','/a/x.dbc',?,0,'C',7,0,100,1)",
            (name,),
        )

    def test_a_census_column_appears_in_the_dictionary(self, catalog: Catalog):
        """Otherwise the dictionary reports on the sample, not the archive."""
        self._census_column(catalog)
        page = next(p for p in collect(catalog, "SIASUS") if p.field_name == "PA_CODUNI")
        assert page.schema_only
        assert page.declared_type == "C(7)"

    def test_it_says_plainly_that_no_values_are_known(self, catalog: Catalog):
        self._census_column(catalog)
        text = render_variable(next(p for p in collect(catalog, "SIASUS")))
        assert "SCHEMA ONLY" in text
        assert "nothing here describes its *values*" in text

    def test_a_profiled_column_is_not_downgraded_by_the_census(self, catalog: Catalog):
        """Profiles know more; the census must not overwrite them."""
        _family(catalog, system="SIASUS")
        _profile(catalog, "PA_CODUNI")
        self._census_column(catalog)
        page = next(p for p in collect(catalog, "SIASUS") if p.field_name == "PA_CODUNI")
        assert not page.schema_only

    def test_the_index_counts_census_only_columns_apart(self, catalog: Catalog, tmp_path):
        self._census_column(catalog)
        _family(catalog, system="SIASUS")  # a system page needs a family to be listed
        generate(catalog, tmp_path / "d")
        text = (tmp_path / "d" / "siasus.md").read_text(encoding="utf-8")
        assert "known from the header census only" in text
