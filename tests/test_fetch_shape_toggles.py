"""`fetch()`'s three shape switches: names, provenance, dictionary.

None of them change which ROWS come back. They change what the answer looks
like, and each exists because the default was wrong for somebody:

  ``provenance`` — ``_source_path``, ``_blob_sha256``, ``_ingested_at`` and
  ``_schema_signature`` were on every row of every result. They are constant per
  source file, so they cost width in every row to repeat something the report
  already says once. Now off by default; a caller who wants byte-level
  traceability asks for it.

  ``names`` — ``CODMUNRES`` is unreadable unless you already know the layout,
  and the English name was in curation the whole time with no way to get it onto
  the table.

  ``dictionary`` — the answer to "what is this column and how was it decoded"
  existed only through `describe()`, one field at a time, against a catalog. It
  now travels with the table it describes.

These use a stub catalog rather than the network: the switches are about the
shape of the return, and a fetch would test the FTP tree instead.
"""

from __future__ import annotations

import pytest

from pegasus_data._dictionary import (
    build_dictionary,
)
from pegasus_data.normalize.engine import PROVENANCE_COLUMNS
from pegasus_data.semantics.curation import VariableDoc
from pegasus_data.view import RenderReport


class _Catalog:
    """Just enough catalog for `load_variable_docs` to be stubbed past."""


@pytest.fixture
def docs(monkeypatch):
    """Two curated columns, one with a label companion and one without."""
    entries = {
        "CODMUNRES": VariableDoc(
            system="SINASC",
            field_name="CODMUNRES",
            official_name="Município de residência",
            translated_name="Municipality of residence",
            description="IBGE code of the mother's municipality of residence.",
            code_system="external",
            codelist="BR_MUNICIPALFA",
            source="layout_doc",
            source_ref="[DIC-DN]",
        ),
        "PESO": VariableDoc(
            system="SINASC",
            field_name="PESO",
            official_name="Peso ao nascer",
            translated_name="Birth weight",
            description="Birth weight in grams.",
            code_system="none",
            source="layout_doc",
        ),
    }
    monkeypatch.setattr(
        "pegasus_data.semantics.curation.load_variable_docs",
        lambda catalog, system=None: entries,
    )
    return entries


def _book(columns, report=None, **kw):
    return build_dictionary(_Catalog(), "SINASC", columns, render_report=report, **kw)


def test_dictionary_has_one_row_per_column_in_table_order(docs) -> None:
    columns = ["CODMUNRES", "CODMUNRES_label", "PESO"]
    book = _book(columns)
    assert [r["column"] for r in book.rows] == columns
    assert len(book) == 3


def test_dictionary_carries_the_english_name_and_the_official_one(docs) -> None:
    book = _book(["CODMUNRES", "PESO"])
    row = book.rows[0]
    assert row["translated_name"] == "Municipality of residence"
    assert row["official_name"] == "Município de residência"
    assert row["description"].startswith("IBGE code")
    assert row["source"] == "layout_doc"


def test_dictionary_names_the_table_that_actually_decoded_the_column(docs) -> None:
    """The point of the whole thing.

    `labelled` says THAT a column was decoded. Only the table name says whether
    it was decoded correctly — CODMUNRES was `labelled` throughout the months it
    was being named with health regions.

    The rendered report wins over curation where they differ, because a column
    with no curated table can still be labelled from a measured binding, and
    reporting the curated `None` beside a full label column is a lie of omission.
    """
    report = RenderReport()
    report.labelled.append("CODMUNRES")
    report.codelist_used["CODMUNRES"] = "CIRAC"
    book = _book(["CODMUNRES", "CODMUNRES_label"], report=report)
    assert book.rows[0]["codelist"] == "CIRAC"
    assert book.rows[0]["labelled"] is True
    assert book.rows[0]["label_column"] == "CODMUNRES_label"


def test_a_column_with_no_curation_still_gets_a_row(docs) -> None:
    """A missing row reads as a column nobody has looked at."""
    book = _book(["CODMUNRES", "UNKNOWN_COL"])
    row = next(r for r in book.rows if r["column"] == "UNKNOWN_COL")
    assert row["kind"] == "data"
    assert row["translated_name"] is None


def test_provenance_columns_are_described_not_ignored(docs) -> None:
    book = _book(["PESO", *PROVENANCE_COLUMNS])
    for name in PROVENANCE_COLUMNS:
        row = next(r for r in book.rows if r["column"] == name)
        assert row["kind"] == "provenance"
        assert row["description"], f"{name} has no description"


def test_derived_companions_are_described(docs) -> None:
    """`CODANOMAL_codes` and `_unmatched` are ours, so curation has no entry."""
    book = _book(["CODMUNRES", "CODMUNRES_codes", "CODMUNRES_unmatched"])
    kinds = {r["column"]: r["kind"] for r in book.rows}
    assert kinds["CODMUNRES_codes"] == "derived"
    assert kinds["CODMUNRES_unmatched"] == "derived"
    assert all(r["description"] for r in book.rows)


def test_dictionary_exports_as_a_table_and_as_markdown(docs, tmp_path) -> None:
    book = _book(["CODMUNRES", "CODMUNRES_label", "PESO"])
    table = book.table
    assert table.num_rows == 3
    assert "translated_name" in table.schema.names

    md = tmp_path / "dict.md"
    book.write(md)
    text = md.read_text(encoding="utf-8")
    assert "CODMUNRES" in text and "Municipality of residence" in text

    js = tmp_path / "dict.json"
    book.write(js)
    assert "CODMUNRES" in js.read_text(encoding="utf-8")


class TestACombinedValueDoesNotRepeatTheCode:
    """`120001 – 120001 Acrelândia, AC` was in the report profile's real output.

    Many DATASUS `.CNV` tables write the code into the label itself, so joining
    `code – label` printed the code twice. Found by reading a produced CSV, not
    by a test — which is the point: nothing asserted on the rendered STRING.
    """

    @staticmethod
    def _combine(codes, labels):
        import pyarrow as pa

        from pegasus_data.view import _combine

        return _combine(pa.array(codes), pa.array(labels)).to_pylist()

    def test_a_label_that_opens_with_the_code_is_used_as_is(self) -> None:
        got = self._combine(["120001"], ["120001 Acrelândia, AC"])
        assert got == ["120001 Acrelândia, AC"]

    def test_a_label_that_does_not_repeat_the_code_still_gets_it(self) -> None:
        got = self._combine(["5701929"], ["UNIDADE MISTA DE SAUDE"])
        assert got == ["5701929 – UNIDADE MISTA DE SAUDE"]

    def test_a_shared_prefix_is_not_a_repeated_code(self) -> None:
        """`12` against `120001 Acrelândia` starts-with, and is not the code."""
        got = self._combine(["12"], ["120001 Acrelândia"])
        assert got == ["12 – 120001 Acrelândia"]

    def test_a_banded_label_opening_with_its_code_is_not_doubled(self) -> None:
        got = self._combine(["1"], ["1 a 3 vezes"])
        assert got == ["1 a 3 vezes"]

    def test_nulls_survive_on_either_side(self) -> None:
        got = self._combine(["1", None, None], ["1 a 3 vezes", "orphan label", None])
        assert got == ["1 a 3 vezes", "orphan label", None]


def test_the_dictionary_still_finds_curation_after_a_profile_renamed_headers(docs) -> None:
    """The `report` profile translates headers, and it is the CLI's default.

    The dictionary is built from the RENDERED table, so by then the column is
    "Municipality of residence" and curation is keyed on CODMUNRES. Without the
    rename map the dictionary described nothing on exactly the path a person is
    most likely to read — every entry a bare heading with no prose.
    """
    report = RenderReport()
    report.renamed_headers["Municipality of residence"] = "CODMUNRES"
    report.codelist_used["CODMUNRES"] = "BR_MUNICIPALFA"
    report.labelled.append("CODMUNRES")

    book = build_dictionary(
        _Catalog(), "SINASC", ["Municipality of residence"], render_report=report
    )
    row = book.rows[0]
    assert row["column"] == "Municipality of residence"
    assert row["original_column"] == "CODMUNRES", "the DATASUS name must survive"
    assert row["description"], "curation was not found through the rename map"
    assert row["codelist"] == "BR_MUNICIPALFA"
