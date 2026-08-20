"""Documenting columns from the names `.DEF` files already carried.

A TabNet `.DEF` declares every column it can tabulate, *with a name*:
``IAdenocarc.invasor,ADENCARCIN`` says what that column counts. Those lines have
been parsed since the beginning — 42,045 of them sit in ``def_variables`` — and
almost none reached the documentation, because the ledger only picked up a name
where a codelist binding happened to carry one. 169 columns had a name; 1,101
undescribed columns had one waiting in a file already read.

So the evidence is not new. What these tests protect is the honesty of moving
it: the name is DATASUS's own words and is recorded verbatim, the description
claims only what the `.DEF` establishes, and a hand-written description is never
overwritten by one of these.
"""

from __future__ import annotations

from pegasus_data.catalog.store import Catalog
from pegasus_data.semantics.defnames import document_from_def


def declare(
    catalog: Catalog,
    field: str,
    name: str,
    *,
    system: str = "SISCAN",
    usage: str = "I",
    path: str = "kit.zip!CColo4.def",
    line: int = 10,
) -> None:
    catalog.execute(
        "INSERT INTO def_variables (def_path, system, usage, display_name, field_name, line_no) "
        "VALUES (?,?,?,?,?,?)",
        (path, system, usage, name, field, line),
    )


def documented(catalog: Catalog, field: str) -> dict[str, str]:
    """Read back what the extraction wrote. Runs it first, so a test that only
    cares about the result does not have to say so twice."""
    document_from_def(catalog)
    row = catalog.query(
        "SELECT official_name, description, source, source_ref, confidence "
        "FROM field_documentation WHERE field_name = ?",
        (field,),
    )
    return dict(row[0]) if row else {}


class TestItMovesWhatWasAlreadyThere:
    def test_a_declared_column_gets_its_name(self, catalog: Catalog):
        declare(catalog, "ADENCARCIN", "Adenocarc.invasor")
        assert document_from_def(catalog).columns == 1
        assert documented(catalog, "ADENCARCIN")["official_name"] == "Adenocarc.invasor"

    def test_the_name_is_recorded_verbatim(self, catalog: Catalog):
        """"Alt.Ben.Atrofia" abbreviated by the Ministry is a fact. My guess at
        what it stands for is not."""
        declare(catalog, "CBEMATROF", "Alt.Ben.Atrofia")
        assert documented(catalog, "CBEMATROF")["official_name"] == "Alt.Ben.Atrofia"

    def test_provenance_points_at_the_def_and_its_line(self, catalog: Catalog):
        declare(catalog, "CARCINO", "Carc.Epid.invasor", path="kit.zip!CColo4.def", line=226)
        row = documented(catalog, "CARCINO")
        assert row["source"] == "def"
        assert row["source_ref"] == "kit.zip!CColo4.def:226"

    def test_a_measure_is_described_as_something_to_sum(self, catalog: Catalog):
        """`I` is Incremento: TabNet adds it up. That is a fact about the column
        worth having, and it is all the .DEF establishes."""
        declare(catalog, "QUANTEXAME", "Quantidade de exames", usage="I")
        assert "sums it" in documented(catalog, "QUANTEXAME")["description"]

    def test_an_axis_is_described_as_something_to_group_by(self, catalog: Catalog):
        declare(catalog, "CO_PAC_SEX", "Sexo", usage="L")
        text = documented(catalog, "CO_PAC_SEX")["description"]
        assert "group or filter by" in text and "sum" not in text.split("rather than")[0]

    def test_measures_and_axes_are_counted_apart(self, catalog: Catalog):
        declare(catalog, "A", "Quantidade", usage="I")
        declare(catalog, "B", "Sexo", usage="L")
        report = document_from_def(catalog)
        assert (report.measures, report.axes) == (1, 1)


class TestWhereTheDefsDisagree:
    def test_both_names_survive_in_the_description(self, catalog: Catalog):
        """ADENCARCIN is "Adenocarc.In Situ" in the cytology .DEF and
        "Adenocarc.invasor" in the histopathology one. Picking one would invent
        an agreement DATASUS did not express."""
        declare(catalog, "ADENCARCIN", "Adenocarc.In Situ", path="kit.zip!CColo4.def")
        declare(catalog, "ADENCARCIN", "Adenocarc.invasor", path="kit.zip!HColo4.def")
        document_from_def(catalog)
        text = documented(catalog, "ADENCARCIN")["description"]
        assert "Adenocarc.In Situ" in text or "Adenocarc.invasor" in text
        assert "depends on which file" in text

    def test_a_disagreement_lowers_the_confidence(self, catalog: Catalog):
        declare(catalog, "X", "One name", path="a.def")
        declare(catalog, "X", "Another name", path="b.def")
        document_from_def(catalog)
        assert float(documented(catalog, "X")["confidence"]) < 0.65

    def test_a_disagreement_is_reported(self, catalog: Catalog):
        declare(catalog, "X", "One name", path="a.def")
        declare(catalog, "X", "Another name", path="b.def")
        assert document_from_def(catalog).disputed == 1

    def test_agreement_across_files_is_not_a_dispute(self, catalog: Catalog):
        declare(catalog, "X", "Same name", path="a.def")
        declare(catalog, "X", "Same name", path="b.def")
        report = document_from_def(catalog)
        assert report.disputed == 0
        assert "depends on which file" not in documented(catalog, "X")["description"]


class TestItNeverOverwritesSomethingBetter:
    def test_a_hand_written_description_wins(self, catalog: Catalog):
        """`manual` is authority 0 and this is one of the weakest rungs."""
        catalog.execute(
            "INSERT INTO variable_docs (system, field_name, description, source, asserted_by) "
            "VALUES ('SISCAN','CARCINO','Number of exams reporting invasive squamous "
            "carcinoma.','manual','a-person')"
        )
        declare(catalog, "CARCINO", "Carc.Epid.invasor")
        assert document_from_def(catalog).columns == 0
        assert catalog.count("field_documentation") == 0

    def test_an_existing_extracted_description_also_wins(self, catalog: Catalog):
        catalog.execute(
            "INSERT INTO field_documentation (system, field_name, description, source, "
            "source_ref, confidence) VALUES ('SISCAN','CARCINO','From the layout table.',"
            "'layout_doc','IT.pdf',0.9)"
        )
        declare(catalog, "CARCINO", "Carc.Epid.invasor")
        assert document_from_def(catalog).columns == 0

    def test_overwrite_is_available_but_not_the_default(self, catalog: Catalog):
        catalog.execute(
            "INSERT INTO field_documentation (system, field_name, description, source, "
            "source_ref, confidence) VALUES ('SISCAN','CARCINO','stale','layout_doc','x',0.9)"
        )
        declare(catalog, "CARCINO", "Carc.Epid.invasor")
        assert document_from_def(catalog, overwrite=True).columns == 1


class TestItRefusesRubbish:
    def test_a_one_character_name_is_not_a_name(self, catalog: Catalog):
        declare(catalog, "X", "I")
        assert document_from_def(catalog).columns == 0

    def test_a_blank_name_is_skipped(self, catalog: Catalog):
        declare(catalog, "X", "   ")
        assert document_from_def(catalog).columns == 0

    def test_running_twice_changes_nothing(self, catalog: Catalog):
        declare(catalog, "CARCINO", "Carc.Epid.invasor")
        document_from_def(catalog)
        before = catalog.count("field_documentation")
        document_from_def(catalog)
        assert catalog.count("field_documentation") == before


class TestScoping:
    def test_one_system_can_be_done_alone(self, catalog: Catalog):
        declare(catalog, "A", "Um", system="SISCAN")
        declare(catalog, "B", "Dois", system="SINAN")
        report = document_from_def(catalog, systems=["SISCAN"])
        assert report.columns == 1 and set(report.systems) == {"SISCAN"}

    def test_it_is_recorded_in_the_event_log(self, catalog: Catalog):
        declare(catalog, "A", "Um")
        document_from_def(catalog)
        assert catalog.count("events", "stage = 'defnames'") == 1
