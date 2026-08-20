"""Decoding data somebody already has.

A lot of DATASUS microdata is already on people's disks — exported from TabNet,
pulled with R's microdatasus, mailed by a colleague. It is all coded, and the
codelists live in `.CNV` files nobody parses. This module has 19.9 million rows
of them. Making people re-download data they already hold in order to reach that
is an artificial toll, so the dictionary is a service on its own.

The thing these tests defend is the refusal. Labelling without knowing which
system produced a row is guessing: `SEXO=3` is Feminino in SIHSUS and undefined
in SINASC. A function that guesses helpfully here would produce wrong labels on
real records with no error anywhere, which is the exact failure this project
exists to prevent.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.persist.reference import register_reference_tables, write_reference_tables
from pegasus_data.semantics.dictionary import DictionaryEntry, persist_entries
from pegasus_data.translate import TranslationImpossible, translate


@pytest.fixture
def dictionary(settings):
    """A catalog that knows SEXO, and nothing else about the world."""
    catalog = Catalog(settings.catalog_path)
    persist_entries(
        catalog,
        [
            DictionaryEntry(system="SIHSUS", value_raw="1", value_label="Masculino",
                            source="cnv", source_ref="a:1", confidence=0.95, value_group="SEXO"),
            DictionaryEntry(system="SIHSUS", value_raw="3", value_label="Feminino",
                            source="cnv", source_ref="a:3", confidence=0.95, value_group="SEXO"),
        ],
    )
    catalog.execute(
        "INSERT INTO field_codelists (system, family_id, field_name, codelist, source, "
        "source_ref, confidence) VALUES ('SIHSUS','','SEXO','SEXO','def','x',0.9)"
    )
    catalog.execute(
        "INSERT INTO variable_docs (system, field_name, code_system, codelist, source) "
        "VALUES ('SIHSUS','SEXO','internal','SEXO','manual')"
    )
    register_reference_tables(catalog, write_reference_tables(catalog, settings.lake_dir))
    catalog.close()
    return settings


SAMPLE = pa.table({"N_AIH": ["A1", "A2"], "SEXO": ["1", "3"]})


class TestItLabels:
    def test_an_arrow_table_comes_back_labelled(self, dictionary):
        out = translate(SAMPLE, system="SIHSUS", settings=dictionary)
        assert out.column("SEXO").to_pylist() == ["Masculino", "Feminino"]

    def test_columns_it_knows_nothing_about_pass_through_untouched(self, dictionary):
        out = translate(SAMPLE, system="SIHSUS", settings=dictionary)
        assert out.column("N_AIH").to_pylist() == ["A1", "A2"]

    def test_a_csv_on_disk_can_be_translated(self, dictionary, tmp_path):
        csv = tmp_path / "extract.csv"
        csv.write_text("N_AIH;SEXO\nA1;1\nA2;3\n", encoding="latin-1")
        out = translate(csv, system="SIHSUS", settings=dictionary)
        assert out.column("SEXO").to_pylist() == ["Masculino", "Feminino"]

    def test_a_comma_separated_export_works_too(self, dictionary, tmp_path):
        """DATASUS exports use ';' about as often as ','."""
        csv = tmp_path / "extract.csv"
        csv.write_text("N_AIH,SEXO\nA1,1\nA2,3\n", encoding="latin-1")
        out = translate(csv, system="SIHSUS", settings=dictionary)
        assert out.column("SEXO").to_pylist() == ["Masculino", "Feminino"]

    def test_a_parquet_file_can_be_translated(self, dictionary, tmp_path):
        import pyarrow.parquet as pq

        target = tmp_path / "extract.parquet"
        pq.write_table(SAMPLE, target)
        out = translate(target, system="SIHSUS", settings=dictionary)
        assert out.column("SEXO").to_pylist() == ["Masculino", "Feminino"]

    def test_the_codes_can_be_kept_instead(self, dictionary):
        out = translate(SAMPLE, system="SIHSUS", profile="codes", settings=dictionary)
        assert out.column("SEXO").to_pylist() == ["1", "3"]

    def test_it_reports_what_it_could_not_label(self, dictionary):
        _, report = translate(SAMPLE, system="SIHSUS", settings=dictionary, report=True)
        assert report is not None


class TestItRefusesToGuess:
    def test_no_system_is_refused_rather_than_guessed(self, dictionary):
        """SEXO=3 is Feminino in SIHSUS and undefined in SINASC."""
        with pytest.raises(TranslationImpossible, match="system is required"):
            translate(SAMPLE, system="", settings=dictionary)

    def test_an_empty_table_is_refused(self, dictionary):
        empty = pa.table({"SEXO": pa.array([], type=pa.string())})
        with pytest.raises(TranslationImpossible, match="no rows"):
            translate(empty, system="SIHSUS", settings=dictionary)

    def test_with_no_catalog_it_says_how_to_get_one(self, settings):
        with pytest.raises(TranslationImpossible, match="unpack"):
            translate(SAMPLE, system="SIHSUS", settings=settings)

    def test_with_a_catalog_but_no_codelists_it_says_that_instead(self, settings):
        Catalog(settings.catalog_path).close()
        with pytest.raises(TranslationImpossible, match="no codelists"):
            translate(SAMPLE, system="SIHSUS", settings=settings)

    def test_something_that_is_not_a_table_is_refused_clearly(self, dictionary):
        with pytest.raises(TranslationImpossible, match="cannot turn"):
            translate(object(), system="SIHSUS", settings=dictionary)

    def test_an_unreadable_file_format_is_named(self, dictionary, tmp_path):
        stray = tmp_path / "notes.docx"
        stray.write_bytes(b"nope")
        with pytest.raises(TranslationImpossible, match="unknown format"):
            translate(stray, system="SIHSUS", settings=dictionary)


class TestCodesAreNotNumbers:
    def test_a_leading_zero_survives_reading_a_csv(self, dictionary, tmp_path):
        """Reading MUNIC_RES as int64 turns 012345 into 12345 and the join
        against a 6-character reference table silently stops matching."""
        csv = tmp_path / "extract.csv"
        csv.write_text("MUNIC_RES;SEXO\n012345;1\n", encoding="latin-1")
        out = translate(csv, system="SIHSUS", profile="codes", settings=dictionary)
        assert out.column("MUNIC_RES").to_pylist() == ["012345"]


class TestItSharesTheRenderPath:
    def test_a_per_column_override_behaves_as_it_does_in_load(self, dictionary):
        """One rendering implementation, or two sets of labels to keep true.

        'both' keeps the code and adds the label beside it, which is what an
        external identifier needs — the code is a join key in its own right."""
        out = translate(
            SAMPLE, system="SIHSUS", render={"SEXO": "both"}, settings=dictionary
        )
        assert out.column("SEXO").to_pylist() == ["1", "3"]
        assert out.column("SEXO_label").to_pylist() == ["Masculino", "Feminino"]

    def test_combined_folds_them_into_one_readable_column(self, dictionary):
        out = translate(
            SAMPLE, system="SIHSUS", render={"SEXO": "combined"}, settings=dictionary
        )
        assert "Masculino" in out.column("SEXO").to_pylist()[0]
