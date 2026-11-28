"""Spreadsheet sources, listed links and name aliases of the intake (SENATRAN's fleet, IBGE's death pairing, 2026-11-27)."""
from __future__ import annotations

import zipfile

import pyarrow.parquet as pq
import pytest

from pegasus_data import intake


@pytest.mark.parametrize("name, month", [
    ("frota_munic_dezembro_2017.xls", 12),
    ("FrotaporMunicipioeTipoNovembro20242.xlsx", 11),
    ("frota_por_municipio_e_tipo-dez_15.rar", 12),
    ("frota-munic-modelo-o7-marco-2021.xls", 3),
    ("FrotaporMunicpioeTipoMARO2024.xls", 3),
    ("copy_of_FrotaporMunicpioeTipoJUL2024.xlsx", 7),
    ("frota_munic_modelo_2021.xls", None),
])
def test_a_file_name_states_its_month(name, month):
    assert intake._month_in(name) == month


def test_a_listing_finds_one_link_a_month_and_refuses_two(monkeypatch):
    page = ('<a href="/f/frota_munic_janeiro_2017.xls/@@download/file">x</a>'
            '<a href="/f/frota_munic_fevereiro_2017.xls/@@download/file">x</a>'
            '<a href="/f/Frota_por_UF_Municipio_CEP_Janeiro_2017.xlsx/@@download/file">x</a>')
    monkeypatch.setattr(intake, "_listing_page", lambda url: page)
    listing = {"page": "https://example.gov.br/frota-{year}", "years": "2017", "by": "month",
               "match": "frota[-_]?munic", "exclude": "uf[-_]?munic|cep"}
    units = intake._listed_units(listing, None)
    assert [(u["key"], u["extension"]) for u in units] == [("201701", "xls"), ("201702", "xls")]
    assert units[0]["url"] == "https://example.gov.br/f/frota_munic_janeiro_2017.xls/@@download/file"
    monkeypatch.setattr(intake, "_listing_page", lambda url: page + '<a href="/f/frota_munic_janeiro_2017b.xls">x</a>')
    with pytest.raises(ValueError, match="two links for month 1"):
        intake._listed_units(listing, None)


def _sheet(path, rows):
    import openpyxl

    book = openpyxl.Workbook()
    glossary = book.active
    glossary.title = "Glossario"
    glossary.append(["Termos e Definicoes"])
    data = book.create_sheet("JUL_2015")
    for row in rows:
        data.append(row)
    book.save(path)


def test_an_excel_table_is_found_by_its_header_and_checked_against_its_total(tmp_path):
    rows = [["Frota de veiculos"], [None, None, 30], ["UF", "MUNICIPIO", "TOTAL"], ["UF", "MUNICIPIO", "TOTAL"],
            ["AC", "ACRELANDIA", 10], ["AC", "BUJARI", 20], [None], ["Fonte: SENATRAN"]]
    path = tmp_path / "201512.xlsx"
    _sheet(path, rows)
    spec = {"header": "^UF$", "stop": "^Fonte", "total": {"cell": [1, 2], "column": "TOTAL"}}
    out = pq.read_table(intake._excel_to_parquet(path, spec, {"year": 2015}))
    assert out.column_names == ["UF", "MUNICIPIO", "TOTAL"]
    assert out.column("TOTAL").to_pylist() == ["10", "20"]           # whole numbers as the sheet shows them, header once
    rows[1][2] = 31
    _sheet(path, rows)
    with pytest.raises(intake._LostRecords):
        intake._excel_to_parquet(path, spec, {"year": 2015})


def test_a_zipped_table_is_read_by_its_member_and_positional_names(tmp_path):
    inner = tmp_path / "Tabela 2.2.xlsx"
    _sheet(inner, [["Tabela 2.2"], ["Codigo da Unidade", "Municipio", "Apenas IBGE"], [11, "Cabixi", "."]])
    archive = tmp_path / "2024.zip"
    with zipfile.ZipFile(archive, "w") as z:
        z.write(inner, "Tabela 2.2.xlsx")
        z.writestr("Tabela 2.1.xlsx", b"not this one")
    spec = {"member": r"Tabela 2\.2\.xlsx$", "header": "^C.digo da Unidade", "names": ["UF_CODE", "NAME", "ONLY"]}
    out = pq.read_table(intake._excel_to_parquet(archive, spec, {"year": 2024}))
    assert out.to_pylist() == [{"UF_CODE": "11", "NAME": "Cabixi", "ONLY": "."}]


def test_a_declared_zero_sign_reads_as_zero():
    import duckdb

    sql = intake._typed("x", {"type": "integer", "zero_tokens": ["."]})
    assert duckdb.sql(f"SELECT {sql} AS v FROM (VALUES ('.'), ('7'), (NULL)) t(x)").fetchall() == [(0,), (7,), (None,)]


def test_municipality_name_aliases_resolve_to_one_code_each():
    from pegasus_data.geography import municipalities, municipality_name_aliases

    if not municipalities():
        pytest.skip("no municipality pack in this home")
    aliases = municipality_name_aliases()
    assert aliases[("SP", "EMBU")] == "351500" and aliases[("RR", "SAO LUIZ")] == "140060"
