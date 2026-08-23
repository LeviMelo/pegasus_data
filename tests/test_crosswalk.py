from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq

from pegasus_data import crosswalk


def test_cnpj_enrichment_is_additive_and_never_multiplies(monkeypatch) -> None:
    monkeypatch.setattr(
        crosswalk,
        "_crosswalk_slice",
        lambda *_args, **_kwargs: {"2001578": [("12345678000195", "202001", "", "CADGERBR")]},
    )
    table = pa.table({"CNES": ["2001578"], "CNPJ": ["00000000000000"], "_competencia": [202401]})
    enriched, report = crosswalk.enrich_cnpj(table)
    assert enriched.num_rows == table.num_rows
    assert enriched["CNPJ"].to_pylist() == ["00000000000000"]
    assert enriched["CNPJ_resolved"].to_pylist() == ["12345678000195"]
    assert enriched["CNPJ_resolution_status"].to_pylist() == ["crosswalk_fallback"]
    assert report.rows_before == report.rows_after == 1


def test_ambiguous_temporal_crosswalk_returns_null_not_extra_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        crosswalk,
        "_crosswalk_slice",
        lambda *_args, **_kwargs: {"1": [("12345678000195", "202001", "", "A"), ("11222333000181", "202001", "", "B")]},
    )
    enriched, report = crosswalk.enrich_cnpj(pa.table({"CNES": ["1"], "_competencia": [202401]}))
    assert enriched.num_rows == 1
    assert enriched["CNPJ_resolved"].to_pylist() == [None]
    assert enriched["CNPJ_resolution_status"].to_pylist() == ["ambiguous_crosswalk"]
    assert report.ambiguous == 1


def test_competence_selects_historical_relation(monkeypatch) -> None:
    monkeypatch.setattr(
        crosswalk,
        "_crosswalk_slice",
        lambda *_args, **_kwargs: {"1": [("12345678000195", "202001", "202012", "A"), ("11222333000181", "202101", "", "A")]},
    )
    table = pa.table({"CNES": ["1", "1"], "_competencia": [202006, 202201]})
    enriched, _ = crosswalk.enrich_cnpj(table)
    assert enriched["CNPJ_resolved"].to_pylist() == ["12345678000195", "11222333000181"]


def test_explicit_explode_is_required_to_multiply_rows(monkeypatch) -> None:
    monkeypatch.setattr(
        crosswalk,
        "_crosswalk_slice",
        lambda *_args, **_kwargs: {"1": [("12345678000195", "", "", "A"), ("11222333000181", "", "", "B")]},
    )
    source = pa.table({"CNES": ["1"]})
    safe, _ = crosswalk.enrich_cnpj(source)
    exploded, report = crosswalk.enrich_cnpj(source, explode=True)
    assert safe.num_rows == 1
    assert exploded.num_rows == 2
    assert set(exploded["CNPJ_resolved"].to_pylist()) == {"12345678000195", "11222333000181"}
    assert report.rows_after == 2


def test_reverse_lookup_is_one_to_many_and_safe_by_default(monkeypatch) -> None:
    monkeypatch.setattr(
        crosswalk,
        "_crosswalk_slice",
        lambda *_args, **_kwargs: {
            "12345678000195": [("1", "", "", "A"), ("2", "", "", "B")],
        },
    )
    safe, report = crosswalk.enrich_cnes(pa.table({"CNPJ": ["12345678000195"]}))
    assert safe.num_rows == 1
    assert safe["CNES_resolved"].to_pylist() == [None]
    assert report.cardinality == "one-to-many per validity window"


def test_valid_observed_cnpj_is_preserved_confirmed_or_conflicted(monkeypatch) -> None:
    monkeypatch.setattr(
        crosswalk,
        "_crosswalk_slice",
        lambda *_args, **_kwargs: {
            "agree": [("12345678000195", "", "", "A")],
            "conflict": [("11222333000181", "", "", "B")],
        },
    )
    source = pa.table(
        {
            "CNES": ["absent", "agree", "conflict"],
            "CNPJ": ["12345678000195", "12345678000195", "12345678000195"],
        }
    )
    enriched, report = crosswalk.enrich_cnpj(source)
    assert enriched["CNPJ"].to_pylist() == ["12345678000195"] * 3
    assert enriched["CNPJ_resolved"].to_pylist() == [
        "12345678000195",
        "12345678000195",
        None,
    ]
    assert enriched["CNPJ_resolution_status"].to_pylist() == [
        "observed",
        "observed_confirmed",
        "conflict",
    ]
    assert report.confirmed == report.conflicts == 1


def test_columnar_slice_filters_identifiers_and_validity_before_materialising(tmp_path) -> None:
    path = tmp_path / "crosswalk.parquet"
    pq.write_table(
        pa.table(
            {
                "source_code": ["wanted", "wanted", "other"],
                "target_code": ["current", "old", "irrelevant"],
                "valid_from": ["202001", "199001", ""],
                "valid_to": ["", "199912", ""],
                "source_codelist": ["A", "A", "B"],
            }
        ),
        path,
    )
    result = crosswalk._crosswalk_slice(
        {"wanted"}, [202401], resource_path=path
    )
    assert result == {"wanted": [("current", "202001", "", "A")]}
