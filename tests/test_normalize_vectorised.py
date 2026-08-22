"""ME-08: the vectorised paths must give exactly what the scalar rules give.

`to_seven_digit`, `uf_array` and `epi_week_array` ran Python loops over
`to_pylist()` behind docstrings that said "vectorised". Replacing them is only
safe if the answers are identical, including on the inputs DATASUS actually
contains — wrong widths, letters in numeric fields, padding, and blanks.
"""

from __future__ import annotations

from datetime import date, timedelta

import pyarrow as pa
import pytest

from pegasus_data.normalize.geo import (
    UF_NUMERIC,
    MunicipalityIndex,
    check_digit,
    check_digit_array,
    to_seven_digit,
    uf_array,
)
from pegasus_data.normalize.time import epi_week, epi_week_array, parse_date_array

MESSY = [
    "355030", "  355030 ", "3550308", "", "   ", None,
    "35A030", "12345", "12345678", "0", "999999", "110001",
]


def _scalar_to_seven(values, index):
    out = []
    for v in values:
        v = v.strip() if v else v
        if not v:
            out.append(None)
        elif index is not None:
            out.append(index.to_seven(v))
        elif len(v) == 7:
            out.append(v)
        elif len(v) == 6 and v.isdigit():
            out.append(v + str(check_digit(v)))
        else:
            out.append(None)
    return out


class TestCheckDigit:
    def test_the_array_form_matches_the_scalar_form(self):
        codes = [f"{n:06d}" for n in range(110000, 111000)]
        got = check_digit_array(pa.array(codes, type=pa.string())).to_pylist()
        assert got == [str(check_digit(c)) for c in codes]

    def test_anything_that_is_not_six_digits_stays_null(self):
        got = check_digit_array(pa.array([None, None], type=pa.string())).to_pylist()
        assert got == [None, None]


class TestToSevenDigit:
    @pytest.mark.parametrize("with_index", [False, True])
    def test_it_agrees_with_the_scalar_rule_on_messy_input(self, with_index):
        index = (
            MunicipalityIndex(six_to_seven={"355030": "3550308", "110001": "1100015"})
            if with_index
            else None
        )
        got = to_seven_digit(pa.array(MESSY, type=pa.string()), index).to_pylist()
        assert got == _scalar_to_seven(MESSY, index)

    def test_the_table_beats_the_algorithm_where_it_has_an_entry(self):
        """A handful of real codes fail the check digit; the table is the authority."""
        index = MunicipalityIndex(six_to_seven={"355030": "3550309"})
        assert to_seven_digit(pa.array(["355030"]), index).to_pylist() == ["3550309"]
        assert to_seven_digit(pa.array(["355030"])).to_pylist() == [
            "355030" + str(check_digit("355030"))
        ]

    def test_a_code_the_table_does_not_know_is_still_expanded(self):
        """Dropping it would delete data."""
        index = MunicipalityIndex(six_to_seven={"355030": "3550308"})
        assert to_seven_digit(pa.array(["110001"]), index).to_pylist() == [
            "110001" + str(check_digit("110001"))
        ]

    def test_six_characters_with_a_letter_is_not_expanded(self):
        assert to_seven_digit(pa.array(["35A030"])).to_pylist() == [None]

    def test_an_empty_column_is_fine(self):
        assert to_seven_digit(pa.array([], type=pa.string())).to_pylist() == []


class TestUfArray:
    def test_it_agrees_with_the_scalar_lookup(self):
        got = uf_array(pa.array(MESSY, type=pa.string())).to_pylist()
        want = [
            UF_NUMERIC.get((c.strip() if c else "")[:2]) if c and c.strip() else None
            for c in MESSY
        ]
        assert got == want

    def test_every_federal_unit_resolves(self):
        codes = pa.array([f"{k}0000" for k in sorted(UF_NUMERIC)], type=pa.string())
        assert uf_array(codes).to_pylist() == [UF_NUMERIC[k] for k in sorted(UF_NUMERIC)]

    def test_an_unknown_prefix_is_null_not_a_guess(self):
        assert uf_array(pa.array(["990000"])).to_pylist() == [None]


class TestEpiWeekArray:
    def test_it_agrees_with_the_scalar_rule_across_every_year_boundary(self):
        """The last days of December and first of January are the whole problem."""
        days = [
            date(y, 12, 28) + timedelta(days=d)
            for y in range(1995, 2031)
            for d in range(8)
        ]
        dates = parse_date_array(pa.array([d.strftime("%Y%m%d") for d in days]))
        years, weeks = epi_week_array(dates)
        assert list(zip(years.to_pylist(), weeks.to_pylist())) == [
            (epi_week(d).year, epi_week(d).week) for d in days
        ]

    def test_it_agrees_over_a_span_wider_than_one_lookup_chunk(self):
        days = [date(1979, 1, 1) + timedelta(days=i * 97) for i in range(400)]
        dates = parse_date_array(pa.array([d.strftime("%Y%m%d") for d in days]))
        years, weeks = epi_week_array(dates)
        assert list(zip(years.to_pylist(), weeks.to_pylist())) == [
            (epi_week(d).year, epi_week(d).week) for d in days
        ]

    def test_nulls_stay_null(self):
        dates = parse_date_array(pa.array(["20200115", "notadate", "20200122"]))
        years, weeks = epi_week_array(dates)
        assert years.to_pylist()[1] is None and weeks.to_pylist()[1] is None

    def test_an_all_null_column_does_not_explode(self):
        years, weeks = epi_week_array(pa.array([None, None], type=pa.date32()))
        assert years.to_pylist() == [None, None]
        assert weeks.to_pylist() == [None, None]

    def test_an_empty_column_is_fine(self):
        years, weeks = epi_week_array(pa.array([], type=pa.date32()))
        assert years.to_pylist() == [] and weeks.to_pylist() == []
