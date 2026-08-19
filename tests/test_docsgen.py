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


def _code(catalog, group, code, label, system="SIHSUS", valid_from="", source="cnv"):
    catalog.execute(
        "INSERT INTO dictionary (system, value_group, field_name, value_raw, value_label, "
        "source, source_ref, confidence, valid_from) VALUES (?,?,?,?,?,?,?,0.9,?)",
        (system, group, "", code, label, source, f"{group}.CNV", valid_from),
    )


def _bind(catalog, field, codelist, system="SIHSUS"):
    catalog.execute(
        "INSERT OR IGNORE INTO field_codelists (system, family_id, field_name, codelist, "
        "source, source_ref, confidence) VALUES (?,'',?,?,'def','x',0.9)",
        (system, field, codelist),
    )


class TestTheValuesAreDocumented:
    """Naming a codelist documents that an answer exists; it is not the answer.

    A person reading these pages usually has a code in their hand — `SEXO=3`,
    `RACACOR=4` — and the page has to say what it means, not where the table
    that says so is kept.
    """

    def test_a_bound_codelist_gets_a_page_with_its_codes(self, catalog: Catalog, tmp_path):
        _code(catalog, "SEXO", "1", "Masculino")
        _code(catalog, "SEXO", "3", "Feminino")
        _bind(catalog, "SEXO", "SEXO")
        generate(catalog, tmp_path / "d")
        page = (tmp_path / "d" / "sihsus" / "codelists" / "SEXO.md").read_text(encoding="utf-8")
        assert "Feminino" in page and "`3`" in page

    def test_the_page_says_which_columns_it_decodes(self, catalog: Catalog, tmp_path):
        _code(catalog, "SEXO", "1", "Masculino")
        _code(catalog, "SEXO", "3", "Feminino")
        _bind(catalog, "SEXO", "SEXO")
        _bind(catalog, "SEXO_PAC", "SEXO")
        generate(catalog, tmp_path / "d")
        page = (tmp_path / "d" / "sihsus" / "codelists" / "SEXO.md").read_text(encoding="utf-8")
        assert "`SEXO`" in page and "`SEXO_PAC`" in page

    def test_an_unbound_codelist_gets_no_page(self, catalog: Catalog, tmp_path):
        """Four in five codelists are tabulation axes nothing decodes against."""
        _code(catalog, "FXETARIA", "1", "0 a 4 anos")
        _code(catalog, "FXETARIA", "2", "5 a 9 anos")
        generate(catalog, tmp_path / "d")
        assert not (tmp_path / "d" / "sihsus" / "codelists" / "FXETARIA.md").exists()

    def test_a_relabelled_code_shows_both_readings_and_their_vintages(
        self, catalog: Catalog, tmp_path
    ):
        _code(catalog, "CID10", "C967", "…tec linf hematop e relac", valid_from="200801")
        _code(catalog, "CID10", "C967", "…tec linf hematop e corr", valid_from="199201")
        _code(catalog, "CID10", "A419", "Septicemia", valid_from="199201")
        _bind(catalog, "DIAG_PRINC", "CID10")
        generate(catalog, tmp_path / "d")
        page = (tmp_path / "d" / "sihsus" / "codelists" / "CID10.md").read_text(encoding="utf-8")
        assert "relabelled" in page
        assert "e relac" in page and "e corr" in page, "both readings, not the newest only"
        assert "199201" in page and "200801" in page

    def test_an_enormous_codelist_is_truncated_and_says_so(self, catalog: Catalog, tmp_path):
        from pegasus_data.docsgen import MAX_CODES_ON_A_PAGE, render_codelist

        entries = [(str(n), f"Município {n}", "", "cnv") for n in range(MAX_CODES_ON_A_PAGE + 40)]
        page = render_codelist("SIHSUS", "MUNICBR", entries)
        assert "40 further entries are not listed" in page
        assert "load_reference" in page, "and says how to get the rest"

    def test_a_label_containing_a_pipe_does_not_break_the_table(self):
        from pegasus_data.docsgen import render_codelist

        page = render_codelist("SIHSUS", "X", [("1", "a | b", "", "cnv")])
        assert r"a \| b" in page

    def test_the_variable_entry_links_to_the_values(self, catalog: Catalog, tmp_path):
        _family(catalog)
        _profile(catalog, "SEXO")
        _code(catalog, "SEXO", "1", "Masculino")
        _bind(catalog, "SEXO", "SEXO")
        catalog.execute(
            "INSERT INTO value_frequencies (family_id, field_name, schema_signature, value, "
            "count) VALUES ('f','SEXO','sig','1',10)"
        )
        generate(catalog, tmp_path / "d")
        page = (tmp_path / "d" / "sihsus.md").read_text(encoding="utf-8")
        assert "sihsus/codelists/SEXO.md" in page


class TestTheSchemaGenerationsArePublished:
    def test_each_family_appears_with_its_span_and_column_count(
        self, catalog: Catalog, tmp_path
    ):
        _family(catalog, family_id="f1", sig="s1", time_min=199201, time_max=200712)
        _profile(catalog, "UF_ZI", family_id="f1", sig="s1")
        generate(catalog, tmp_path / "d")
        page = (tmp_path / "d" / "sihsus" / "schemas.md").read_text(encoding="utf-8")
        assert "f1" in page and "199201" in page

    def test_what_a_generation_added_is_stated_not_left_to_be_diffed(
        self, catalog: Catalog, tmp_path
    ):
        """The DIAG_SECUN question, answerable at a glance instead of by hand."""
        _family(catalog, family_id="f1", sig="s1", time_min=199201, time_max=200712)
        _family(catalog, family_id="f2", sig="s2", time_min=200801, time_max=202612)
        for order, name in enumerate(["UF_ZI", "N_AIH"]):
            catalog.execute(
                "INSERT INTO schema_presence (schema_signature, field_name, field_order) "
                "VALUES ('s1',?,?)",
                (name, order),
            )
        for order, name in enumerate(["UF_ZI", "N_AIH", "DIAG_SECUN"]):
            catalog.execute(
                "INSERT INTO schema_presence (schema_signature, field_name, field_order) "
                "VALUES ('s2',?,?)",
                (name, order),
            )
        generate(catalog, tmp_path / "d")
        page = (tmp_path / "d" / "sihsus" / "schemas.md").read_text(encoding="utf-8")
        assert "**Added**" in page and "`DIAG_SECUN`" in page


class TestTheColumnIndex:
    def test_every_column_is_listed_with_the_systems_that_carry_it(
        self, catalog: Catalog, tmp_path
    ):
        for system, sig in (("SIHSUS", "s1"), ("SINASC", "s2")):
            catalog.execute(
                "INSERT INTO strata (stratum_id, system, series, file_count, schema_signature) "
                "VALUES (?,?,'X',1,?)",
                (f"st_{system}", system, sig),
            )
            catalog.execute(
                "INSERT INTO schema_presence (schema_signature, field_name, field_order) "
                "VALUES (?,'SEXO',0)",
                (sig,),
            )
        generate(catalog, tmp_path / "d")
        page = (tmp_path / "d" / "columns.md").read_text(encoding="utf-8")
        assert "`SEXO`" in page
        assert "sihsus.md" in page and "sinasc.md" in page

    def test_it_warns_that_a_shared_name_is_not_a_shared_meaning(
        self, catalog: Catalog, tmp_path
    ):
        generate(catalog, tmp_path / "d")
        page = (tmp_path / "d" / "columns.md").read_text(encoding="utf-8")
        assert "not** a shared meaning" in page

    def test_the_readme_points_at_it(self, catalog: Catalog, tmp_path):
        generate(catalog, tmp_path / "d")
        readme = (tmp_path / "d" / "README.md").read_text(encoding="utf-8")
        assert "columns.md" in readme


class TestPagesStayReadable:
    """A page GitHub refuses to render is a page nobody reads.

    SINAN has 2,250 columns and came to 1,043 KB — over the limit at which
    GitHub shows "we can't show files that are this big" instead of the content.
    The most exhaustive page in the set was the one that did not work.
    """

    def test_a_page_within_the_limit_stays_one_file(self):
        from pegasus_data.docsgen import paginate

        assert len(paginate(["# X"], ["a", "b", "c"])) == 1

    def test_an_oversized_page_is_split(self):
        from pegasus_data.docsgen import MAX_PAGE_BYTES, paginate

        entry = "x" * 100_000
        bodies = paginate(["# X"], [entry] * 10)
        assert len(bodies) > 1
        assert all(len(b.encode("utf-8")) <= MAX_PAGE_BYTES for b in bodies)

    def test_every_part_repeats_the_header(self):
        """Someone arriving at part 3 from a search needs to know what it is."""
        from pegasus_data.docsgen import paginate

        bodies = paginate(["# SINAN", "", "2,250 columns"], ["y" * 200_000] * 6)
        assert len(bodies) > 1
        assert all(b.startswith("# SINAN") for b in bodies)

    def test_an_entry_larger_than_the_budget_still_gets_written(self):
        """Truncating a variable to fit a page would lose the documentation."""
        from pegasus_data.docsgen import MAX_PAGE_BYTES, paginate

        giant = "z" * (MAX_PAGE_BYTES * 2)
        bodies = paginate(["# X"], [giant])
        assert len(bodies) == 1 and giant in bodies[0]

    def test_generated_pages_link_to_their_other_parts(self, catalog: Catalog, tmp_path):
        _family(catalog)
        for n in range(400):
            _profile(catalog, f"FIELD_{n:04d}")
            catalog.execute(
                "INSERT INTO variable_docs (system, field_name, description, source) "
                "VALUES ('SIHSUS', ?, ?, 'manual')",
                (f"FIELD_{n:04d}", "long description " * 200),
            )
        generate(catalog, tmp_path / "d")
        first = (tmp_path / "d" / "sihsus.md").read_text(encoding="utf-8")
        assert (tmp_path / "d" / "sihsus-2.md").exists()
        assert "sihsus-2.md" in first


class TestTheGeneratedSiteHangsTogether:
    """A wiki with dead links is a wiki people stop trusting.

    Both of these were real: systems whose dictionary was parsed but whose files
    were never decoded got an index entry pointing at a page that was never
    written, and a variable's link to its codelist page pointed into a directory
    that only exists when that codelist is bound.
    """

    def _links(self, text: str) -> list[str]:
        import re

        return [
            target
            for target in re.findall(r"\]\(([^)]+)\)", text)
            if not target.startswith(("http://", "https://", "#"))
        ]

    def test_no_link_on_the_index_points_at_a_missing_page(
        self, catalog: Catalog, tmp_path
    ):
        _family(catalog)
        _profile(catalog, "SEXO")
        _code(catalog, "SEXO", "1", "Masculino")
        _bind(catalog, "SEXO", "SEXO")
        # A system with codelists and nothing else — the case that broke it.
        _code(catalog, "PROC", "01", "Consulta", system="CMD")
        _bind(catalog, "PROC_REA", "PROC", system="CMD")
        root = tmp_path / "d"
        generate(catalog, root)

        readme = (root / "README.md").read_text(encoding="utf-8")
        missing = [t for t in self._links(readme) if not (root / t).exists()]
        assert missing == []

    def test_a_system_with_no_variable_page_is_not_linked_as_though_it_had_one(
        self, catalog: Catalog, tmp_path
    ):
        _code(catalog, "PROC", "01", "Consulta", system="CMD")
        _bind(catalog, "PROC_REA", "PROC", system="CMD")
        generate(catalog, tmp_path / "d")
        readme = (tmp_path / "d" / "README.md").read_text(encoding="utf-8")
        assert "(cmd.md)" not in readme
        assert "no columns catalogued yet" in readme

    def test_every_link_out_of_a_system_page_resolves(self, catalog: Catalog, tmp_path):
        _family(catalog)
        _profile(catalog, "SEXO")
        _code(catalog, "SEXO", "1", "Masculino")
        _bind(catalog, "SEXO", "SEXO")
        catalog.execute(
            "INSERT INTO value_frequencies (family_id, field_name, schema_signature, value, "
            "count) VALUES ('f','SEXO','sig','1',10)"
        )
        root = tmp_path / "d"
        generate(catalog, root)
        page = (root / "sihsus.md").read_text(encoding="utf-8")
        missing = [t for t in self._links(page) if not (root / t).exists()]
        assert missing == []
