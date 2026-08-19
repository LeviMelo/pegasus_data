"""Generated documentation (§7).

The pages are the artifact for the working group and eventually the Ministry, so
what these tests protect is the warnings. A person reading about COD_IDADE has to
hit the trap on that page — not in a findings file they will never open.
"""

from __future__ import annotations

from pegasus_data.catalog.store import Catalog
from pegasus_data.docsgen import collect, render_variable, write_database


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


# ---------------------------------------------------------------- helpers


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


def _db(catalog, tmp_path):
    import sqlite3

    path = tmp_path / "dictionary.sqlite"
    write_database(catalog, path)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


class TestTheDictionaryIsADatabase:
    """The documentation is relational, so it is stored relationally.

    It was 3,036 Markdown files, which meant no question anyone would actually
    ask ("which columns anywhere draw on CID-10?") could be answered, the large
    code tables had to be truncated to keep pages readable, and 42 MB of files
    had to be moved to carry it. All three problems belonged to the container,
    not to the content.
    """

    def test_a_system_is_summarised_once(self, catalog: Catalog, tmp_path):
        _family(catalog)
        _profile(catalog, "DIAG_PRINC")
        row = _db(catalog, tmp_path).execute("SELECT * FROM systems").fetchone()
        assert row["system"] == "SIHSUS" and row["variables"] == 1

    def test_every_variable_is_a_row(self, catalog: Catalog, tmp_path):
        _family(catalog)
        _profile(catalog, "DIAG_PRINC")
        row = (
            _db(catalog, tmp_path)
            .execute("SELECT * FROM variables WHERE field_name = 'DIAG_PRINC'")
            .fetchone()
        )
        assert row["system"] == "SIHSUS"

    def test_the_rendered_prose_travels_with_it(self, catalog: Catalog, tmp_path):
        """The page is worth keeping; it just was not worth being a file."""
        _family(catalog)
        _profile(catalog, "DIAG_PRINC")
        row = _db(catalog, tmp_path).execute("SELECT page FROM variables").fetchone()
        assert row["page"].startswith("### DIAG_PRINC")

    def test_every_code_is_stored_with_no_truncation(self, catalog: Catalog, tmp_path):
        """The 500-row cap was a property of the page, not of the knowledge."""
        for n in range(1200):
            _code(catalog, "MUNICBR", str(n), f"Municipio {n}")
        _bind(catalog, "MUNIC_RES", "MUNICBR")
        conn = _db(catalog, tmp_path)
        assert conn.execute("SELECT COUNT(*) FROM codes").fetchone()[0] == 1200

    def test_an_unbound_codelist_is_still_left_out(self, catalog: Catalog, tmp_path):
        _code(catalog, "FXETARIA", "1", "0 a 4 anos")
        _code(catalog, "FXETARIA", "2", "5 a 9 anos")
        conn = _db(catalog, tmp_path)
        assert conn.execute("SELECT COUNT(*) FROM codelists").fetchone()[0] == 0

    def test_a_relabelled_code_keeps_both_readings_and_their_vintages(
        self, catalog: Catalog, tmp_path
    ):
        _code(catalog, "CID10", "C967", "tec linf hematop e relac", valid_from="200801")
        _code(catalog, "CID10", "C967", "tec linf hematop e corr", valid_from="199201")
        _bind(catalog, "DIAG_PRINC", "CID10")
        conn = _db(catalog, tmp_path)
        rows = conn.execute(
            "SELECT label, valid_from FROM code_values WHERE code = 'C967' "
            "ORDER BY valid_from"
        ).fetchall()
        assert [r["valid_from"] for r in rows] == ["199201", "200801"]
        assert conn.execute("SELECT relabelled FROM codelists").fetchone()[0] == 1

    def test_which_columns_a_codelist_decodes_is_recorded(self, catalog: Catalog, tmp_path):
        import json

        _code(catalog, "SEXO", "1", "Masculino")
        _code(catalog, "SEXO", "3", "Feminino")
        _bind(catalog, "SEXO", "SEXO")
        _bind(catalog, "SEXO_PAC", "SEXO")
        row = _db(catalog, tmp_path).execute("SELECT used_by_json FROM codelists").fetchone()
        assert json.loads(row["used_by_json"]) == ["SEXO", "SEXO_PAC"]

    def test_schema_generations_record_what_changed(self, catalog: Catalog, tmp_path):
        import json

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
        row = (
            _db(catalog, tmp_path)
            .execute("SELECT added_json FROM families WHERE family_id = 'f2'")
            .fetchone()
        )
        assert json.loads(row["added_json"]) == ["DIAG_SECUN"]

    def test_an_empty_catalog_produces_an_empty_dictionary_and_no_lies(
        self, catalog: Catalog, tmp_path
    ):
        conn = _db(catalog, tmp_path)
        assert conn.execute("SELECT COUNT(*) FROM systems").fetchone()[0] == 0
        assert conn.execute("SELECT value FROM meta WHERE key='generated_at'").fetchone()

    def test_dataset_prose_is_carried(self, catalog: Catalog, tmp_path):
        catalog.execute(
            "INSERT INTO dataset_docs (dataset_id, what_one_row_is, source) "
            "VALUES ('SIHSUS_RD','one billing episode (AIH)','manual')"
        )
        row = _db(catalog, tmp_path).execute("SELECT * FROM datasets").fetchone()
        assert row["what_one_row_is"] == "one billing episode (AIH)"


class TestItCanBeAsked:
    """The questions a tree of files could not answer at all."""

    def _seeded(self, catalog: Catalog, tmp_path):
        _family(catalog)
        _profile(catalog, "RACACOR")
        catalog.execute(
            "INSERT INTO variable_docs (system, field_name, description, source) "
            "VALUES ('SIHSUS','RACACOR','Raça ou cor da pessoa','manual')"
        )
        _code(catalog, "RACACOR", "3", "Parda")
        _code(catalog, "RACACOR", "1", "Branca")
        _bind(catalog, "RACACOR", "RACACOR")
        return _db(catalog, tmp_path)

    def test_which_columns_draw_on_a_classification(self, catalog: Catalog, tmp_path):
        conn = self._seeded(catalog, tmp_path)
        rows = conn.execute(
            "SELECT field_name FROM variables WHERE codelist = 'RACACOR'"
        ).fetchall()
        assert [r["field_name"] for r in rows] == ["RACACOR"]

    def test_which_code_means_a_given_word(self, catalog: Catalog, tmp_path):
        conn = self._seeded(catalog, tmp_path)
        row = conn.execute(
            "SELECT code, codelist FROM code_values WHERE label = 'Parda'"
        ).fetchone()
        assert row["code"] == "3"

    def test_full_text_search_finds_a_description(self, catalog: Catalog, tmp_path):
        from pegasus_data.docsgen import search_docs

        self._seeded(catalog, tmp_path).close()
        hits = search_docs(tmp_path / "dictionary.sqlite", "cor", kind="variable")
        assert any(h["name"] == "RACACOR" for h in hits)

    def test_search_folds_accents_because_nobody_types_them(
        self, catalog: Catalog, tmp_path
    ):
        from pegasus_data.docsgen import search_docs

        self._seeded(catalog, tmp_path).close()
        assert search_docs(tmp_path / "dictionary.sqlite", "raca")

    def test_a_page_can_still_be_printed_for_a_person(self, catalog: Catalog, tmp_path):
        from pegasus_data.docsgen import read_page

        self._seeded(catalog, tmp_path).close()
        body = read_page(tmp_path / "dictionary.sqlite", "SIHSUS", "RACACOR")
        assert body and "RACACOR" in body

    def test_asking_for_a_variable_that_is_not_there_says_so(
        self, catalog: Catalog, tmp_path
    ):
        from pegasus_data.docsgen import read_page

        self._seeded(catalog, tmp_path).close()
        assert read_page(tmp_path / "dictionary.sqlite", "SIHSUS", "NOPE") is None


    def test_a_label_is_findable_even_though_labels_are_not_in_the_index(
        self, catalog: Catalog, tmp_path
    ):
        """Leaving 7.5M labels out of FTS is an encoding decision. A search that
        answers "nothing matches" because of one is lying about the contents."""
        from pegasus_data.docsgen import search_docs

        self._seeded(catalog, tmp_path).close()
        hits = search_docs(tmp_path / "dictionary.sqlite", "Parda")
        assert any(h["kind"] == "code" and h["context"] == "Parda" for h in hits)

    def test_the_hit_names_the_code_and_the_system_that_uses_it(
        self, catalog: Catalog, tmp_path
    ):
        from pegasus_data.docsgen import search_docs

        self._seeded(catalog, tmp_path).close()
        hit = next(
            h
            for h in search_docs(tmp_path / "dictionary.sqlite", "Parda")
            if h["kind"] == "code"
        )
        assert hit["name"] == "RACACOR = 3" and hit["system"] == "SIHSUS"


class TestTheShapeIsNotWasteful:
    """A container change that made the artifact bigger would be a regression.

    The first schema repeated `system` and `codelist` as text on every one of
    7.5 million code rows and indexed every label into FTS as well: 1.1 GB, for
    content the 3,036 Markdown files held in 42 MB. The knowledge did not grow —
    the encoding did.
    """

    def test_codes_reference_their_codelist_by_id(self, catalog: Catalog, tmp_path):
        _code(catalog, "SEXO", "1", "Masculino")
        _code(catalog, "SEXO", "3", "Feminino")
        _bind(catalog, "SEXO", "SEXO")
        conn = _db(catalog, tmp_path)
        columns = {r[1] for r in conn.execute("PRAGMA table_info(codes)")}
        assert {"codelist_id", "label_id"} <= columns
        assert "system" not in columns and "codelist" not in columns

    def test_a_view_hides_the_join_from_whoever_is_querying(
        self, catalog: Catalog, tmp_path
    ):
        _code(catalog, "SEXO", "3", "Feminino")
        _code(catalog, "SEXO", "1", "Masculino")
        _bind(catalog, "SEXO", "SEXO")
        row = (
            _db(catalog, tmp_path)
            .execute("SELECT system, codelist, code FROM code_values WHERE label='Feminino'")
            .fetchone()
        )
        assert (row["system"], row["codelist"], row["code"]) == ("SIHSUS", "SEXO", "3")

    def test_labels_are_not_duplicated_into_the_search_index(
        self, catalog: Catalog, tmp_path
    ):
        """400 MB of the original 1.1 GB was every label stored a second time."""
        _code(catalog, "SEXO", "3", "Feminino")
        _code(catalog, "SEXO", "1", "Masculino")
        _bind(catalog, "SEXO", "SEXO")
        conn = _db(catalog, tmp_path)
        body = conn.execute(
            "SELECT body FROM search WHERE kind = 'codelist'"
        ).fetchone()[0]
        assert "Feminino" not in body

    def test_an_exact_label_is_still_findable_without_that_index(
        self, catalog: Catalog, tmp_path
    ):
        """Which is what people actually do: they have a label, they want a code."""
        _code(catalog, "RACACOR", "3", "Parda")
        _bind(catalog, "RACACOR", "RACACOR")
        row = (
            _db(catalog, tmp_path)
            .execute("SELECT code FROM code_values WHERE label = 'Parda'")
            .fetchone()
        )
        assert row["code"] == "3"

    def test_a_label_used_by_many_codelists_is_stored_once(
        self, catalog: Catalog, tmp_path
    ):
        """1.47 million distinct labels across 7.47 million codes: "Rio Branco"
        is written once per system, per vintage, per table naming a place."""
        for group in ("MUNICBR", "MUNICMOV", "MUNICRES"):
            _code(catalog, group, "120040", "Rio Branco")
            _code(catalog, group, "120001", "Acrelandia")
            _bind(catalog, f"F_{group}", group)
        conn = _db(catalog, tmp_path)
        assert conn.execute("SELECT COUNT(*) FROM codes").fetchone()[0] == 6
        assert conn.execute("SELECT COUNT(*) FROM labels").fetchone()[0] == 2

    def test_two_systems_that_disagree_keep_both_readings(
        self, catalog: Catalog, tmp_path
    ):
        """235,659 (codelist, code, vintage) triples carry different labels
        depending on the system. Deduplicating across systems would save real
        space and reintroduce the exact bug the system scoping exists to stop."""
        _code(catalog, "SEXO", "1", "Masculino", system="SIHSUS")
        _code(catalog, "SEXO", "1", "Homem", system="SINASC")
        _bind(catalog, "SEXO", "SEXO", system="SIHSUS")
        _bind(catalog, "SEXO", "SEXO", system="SINASC")
        rows = (
            _db(catalog, tmp_path)
            .execute("SELECT system, label FROM code_values WHERE code = '1' ORDER BY system")
            .fetchall()
        )
        assert [(r["system"], r["label"]) for r in rows] == [
            ("SIHSUS", "Masculino"),
            ("SINASC", "Homem"),
        ]
