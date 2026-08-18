"""Normalisation: types, sentinels, geo, epidemiological time, missing columns."""

from __future__ import annotations

from datetime import date

import pyarrow as pa
import pytest

from pegasus_data.normalize.engine import (
    FieldPlan,
    MissingColumnError,
    NormalizePlan,
    normalize_batch,
    require_columns,
)
from pegasus_data.normalize.geo import (
    MunicipalityIndex,
    check_digit,
    to_seven_digit,
    uf_array,
    validate_check_digit,
)
from pegasus_data.normalize.time import (
    SOURCE_EPI_WEEK_FIELDS,
    build_calendar,
    competencia_to_year_month,
    epi_week,
    epi_year_weeks,
    parse_date_array,
)
from pegasus_data.normalize.types import arrow_type_for, cast_boolean, cast_numeric


class TestEpiWeek:
    @pytest.mark.parametrize(
        ("day", "expected"),
        [
            (date(2015, 1, 3), (2014, 53)),
            (date(2015, 1, 4), (2015, 1)),
            (date(2016, 1, 2), (2015, 52)),
            (date(2016, 1, 3), (2016, 1)),
            (date(2020, 12, 26), (2020, 52)),
            (date(2021, 1, 2), (2020, 53)),
            (date(2021, 1, 3), (2021, 1)),
        ],
    )
    def test_year_boundaries(self, day, expected):
        got = epi_week(day)
        assert (got.year, got.week) == expected

    def test_53_week_years_exist(self):
        """A year with 53 epi weeks is why year(date), week(date) drifts."""
        long_years = [y for y in range(2000, 2031) if epi_year_weeks(y) == 53]
        assert long_years == [2003, 2008, 2014, 2020, 2025]

    def test_source_published_weeks_are_never_recomputed(self):
        assert "SEM_PRI" in SOURCE_EPI_WEEK_FIELDS
        assert "SEM_NOT" in SOURCE_EPI_WEEK_FIELDS

    def test_calendar_dimension(self):
        calendar = build_calendar(2020, 2020)
        assert calendar.num_rows == 366
        assert set(calendar.column("epi_year_total_weeks").to_pylist()) <= {52, 53}

    def test_competencia(self):
        assert competencia_to_year_month("202401") == (2024, 1)
        assert competencia_to_year_month("202413") is None  # month 13 is not a month
        assert competencia_to_year_month("abc") is None


class TestDates:
    def test_parses_yyyymmdd(self):
        got = parse_date_array(pa.array(["20200115", "19921231"]))
        assert got.to_pylist() == [date(2020, 1, 15), date(1992, 12, 31)]

    def test_impossible_dates_become_null_without_killing_the_column(self):
        got = parse_date_array(pa.array(["20150230", "20200115"]))
        assert got.to_pylist() == [None, date(2020, 1, 15)]

    def test_sentinels_are_nulled_only_when_named(self):
        kept = parse_date_array(pa.array(["00000000", "20200115"]))
        nulled = parse_date_array(pa.array(["00000000", "20200115"]), sentinels=("00000000",))
        assert kept.to_pylist()[0] is None  # not a valid date anyway
        assert nulled.to_pylist() == [None, date(2020, 1, 15)]

    def test_ddmmyyyy_order(self):
        got = parse_date_array(pa.array(["15012020"]), order="DDMMYYYY")
        assert got.to_pylist() == [date(2020, 1, 15)]


class TestGeo:
    def test_check_digit_is_secondary_validation(self):
        assert validate_check_digit("3550308")  # São Paulo
        assert check_digit("355030") == 8

    def test_six_to_seven_prefers_the_reference_table(self):
        index = MunicipalityIndex(six_to_seven={"355030": "3550308"}, labels={"355030": "São Paulo"})
        assert index.to_seven("355030") == "3550308"
        # A code the table does not know is still expanded, by algorithm.
        assert index.to_seven("110001") == "1100015"

    def test_vectorised_expansion(self):
        got = to_seven_digit(pa.array(["355030", "3550308", "bad", None]))
        assert got.to_pylist() == ["3550308", "3550308", None, None]

    def test_uf_from_code(self):
        assert uf_array(pa.array(["355030", "310620", "999999"])).to_pylist() == ["SP", "MG", None]


class TestTypes:
    def test_declared_decimals_drive_the_arrow_type(self):
        assert arrow_type_for("N", 10, 2) == pa.decimal128(10, 2)
        assert arrow_type_for("N", 6, 0) == pa.int32()
        assert arrow_type_for("C", 20, 0) == pa.string()
        assert arrow_type_for("D", 8, 0) == pa.date32()

    def test_implied_decimal_point(self):
        """Old SIH money is an integer string with the point implied by the header."""
        got = cast_numeric(pa.array(["123456"]), pa.float64(), decimals=2)
        assert got.to_pylist() == [1234.56]

    def test_explicit_decimal_point_is_respected(self):
        got = cast_numeric(pa.array(["1234.56"]), pa.float64(), decimals=2)
        assert got.to_pylist() == [1234.56]

    def test_logical_field(self):
        assert cast_boolean(pa.array(["T", "F", "1", "0", "?"])).to_pylist() == [
            True, False, True, False, None
        ]


class TestNormalizeBatch:
    def _plan(self, **fields: FieldPlan) -> NormalizePlan:
        return NormalizePlan(family_id="F", system="S", schema_signature="sig", fields=fields)

    def test_raw_is_kept_alongside_the_label(self):
        """§13: never discard the raw value when writing a decoded label."""
        batch = pa.RecordBatch.from_arrays([pa.array(["1", "2"])], names=["SEXO"])
        plan = self._plan(
            SEXO=FieldPlan(name="SEXO", labels={"1": "Masculino", "2": "Feminino"})
        )
        out = normalize_batch(batch, plan)
        assert out.column("SEXO").to_pylist() == ["1", "2"]
        assert out.column("SEXO_label").to_pylist() == ["Masculino", "Feminino"]

    def test_unmapped_values_get_no_invented_label(self):
        batch = pa.RecordBatch.from_arrays([pa.array(["1", "7"])], names=["SEXO"])
        plan = self._plan(SEXO=FieldPlan(name="SEXO", labels={"1": "Masculino"}))
        out = normalize_batch(batch, plan)
        assert out.column("SEXO_label").to_pylist() == ["Masculino", None]

    def test_sentinel_nulling_is_per_field(self):
        batch = pa.RecordBatch.from_arrays(
            [pa.array(["9", "1"]), pa.array(["9", "1"])], names=["SEXO", "ESCOLARIDADE"]
        )
        plan = self._plan(
            SEXO=FieldPlan(name="SEXO", sentinels=["9"]),
            ESCOLARIDADE=FieldPlan(name="ESCOLARIDADE"),
        )
        out = normalize_batch(batch, plan)
        assert out.column("SEXO").to_pylist() == [None, "1"]
        assert out.column("ESCOLARIDADE").to_pylist() == ["9", "1"], "no global sentinel rule"

    def test_municipality_gets_ibge7_and_uf_companions(self):
        batch = pa.RecordBatch.from_arrays([pa.array(["355030"])], names=["MUNIC_RES"])
        plan = self._plan(
            MUNIC_RES=FieldPlan(name="MUNIC_RES", semantic_type="municipality_code_6")
        )
        out = normalize_batch(batch, plan)
        assert out.column("MUNIC_RES_ibge7").to_pylist() == ["3550308"]
        assert out.column("MUNIC_RES_uf").to_pylist() == ["SP"]

    def test_dates_get_epi_columns_unless_the_source_publishes_them(self):
        batch = pa.RecordBatch.from_arrays(
            [pa.array(["20210102"]), pa.array(["20210102"])], names=["DT_NOTIFIC", "SEM_PRI"]
        )
        plan = self._plan(
            DT_NOTIFIC=FieldPlan(name="DT_NOTIFIC", semantic_type="date"),
            SEM_PRI=FieldPlan(name="SEM_PRI", semantic_type="date"),
        )
        out = normalize_batch(batch, plan)
        assert out.column("DT_NOTIFIC_epi_week").to_pylist() == [53]
        assert "SEM_PRI_epi_week" not in out.schema.names


class TestMissingColumns:
    def test_a_missing_column_raises_rather_than_returning_empty(self, catalog):
        catalog.executemany(
            "INSERT INTO families (family_id, system, series, schema_signature, field_count) VALUES (?,?,?,?,?)",
            [("F_new", "SIHSUS", "RD", "sig113", 113), ("F_old", "SIHSUS", "RD", "sig86", 86)],
        )
        catalog.executemany(
            "INSERT INTO schema_presence (schema_signature, field_name, field_order) VALUES (?,?,?)",
            [("sig113", "DIAGSEC1", 0), ("sig86", "DIAG_SECUN", 0)],
        )
        require_columns(catalog, "F_new", ["DIAGSEC1"])
        with pytest.raises(MissingColumnError) as excinfo:
            require_columns(catalog, "F_new", ["DIAG_SECUN"])
        assert "F_old" in str(excinfo.value), "the error names the generation that has it"
