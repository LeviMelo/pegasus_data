"""The derived age-band dimension, against every convention it claims to read.

The claim in `_age.py` worth pinning: every unit below "years" is sub-year, so
the decode only needs to read the years and 100+ units precisely and may send
everything sub-year to the first band. And the honesty rule: an undecodable
age is a LEVEL, never a dropped row.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from pegasus_data._age import (
    UNKNOWN_CODE,
    AgeDimension,
    band_column,
    parse_age_dimension,
    years_column,
)

pytestmark = pytest.mark.filterwarnings("ignore")


def bands_of(age, table):
    return band_column(age, years_column(age, table)).to_pylist()


class TestSimPacking:
    AGE = AgeDimension(name="F", encoding="sim", fields=("IDADE",))

    def test_years_and_centenarians_read_precisely(self) -> None:
        t = pa.table({"IDADE": ["425", "480", "501"]})
        assert bands_of(self.AGE, t) == ["025", "080", "080"]

    def test_every_sub_year_unit_is_under_one(self) -> None:
        # Minutes, hours-or-days, months -- whichever assignment a vintage
        # uses, all are under a year and all land in the first band.
        t = pa.table({"IDADE": ["130", "215", "311"]})
        assert bands_of(self.AGE, t) == ["000", "000", "000"]

    def test_unknown_is_a_level_not_a_dropped_row(self) -> None:
        t = pa.table({"IDADE": ["999", "000", "", None, "abc"]})
        assert bands_of(self.AGE, t) == [UNKNOWN_CODE] * 5


class TestSihSeparateUnitColumn:
    AGE = AgeDimension(name="F", encoding="sih", fields=("IDADE", "COD_IDADE"))

    def test_the_unit_column_rules(self) -> None:
        t = pa.table({
            "IDADE": ["042", "005", "011", "003"],
            "COD_IDADE": ["4", "5", "3", "2"],
        })
        # 42 years; 105 years; 11 months -> under 1; 3 days -> under 1.
        assert bands_of(self.AGE, t) == ["040", "080", "000", "000"]

    def test_an_undocumented_unit_is_unknown(self) -> None:
        t = pa.table({"IDADE": ["042"], "COD_IDADE": ["0"]})
        assert bands_of(self.AGE, t) == [UNKNOWN_CODE]


class TestSinanPacking:
    AGE = AgeDimension(name="F", encoding="sinan", fields=("NU_IDADE_N",))

    def test_four_digit_packing(self) -> None:
        t = pa.table({"NU_IDADE_N": ["4025", "4007", "3010", "5002"]})
        assert bands_of(self.AGE, t) == ["025", "005", "000", "080"]


class TestDeclaration:
    def test_bands_must_start_at_zero_and_increase(self) -> None:
        with pytest.raises(ValueError):
            parse_age_dimension({"encoding": "sim", "fields": ["IDADE"], "bands": [5, 10]})
        with pytest.raises(ValueError):
            parse_age_dimension({"encoding": "sim", "fields": ["IDADE"], "bands": [0, 10, 10]})

    def test_field_arity_matches_the_encoding(self) -> None:
        with pytest.raises(ValueError):
            parse_age_dimension({"encoding": "sih", "fields": ["IDADE"]})
        with pytest.raises(ValueError):
            parse_age_dimension({"encoding": "sim", "fields": ["IDADE", "X"]})

    def test_band_levels_carry_the_words(self) -> None:
        age = parse_age_dimension({"encoding": "sim", "fields": ["IDADE"], "bands": [0, 1, 5]})
        assert age is not None
        levels = age.band_levels()
        assert levels["000"] == "menos de 1 ano"
        assert levels["001"] == "1–4"
        assert levels["005"] == "5+"
        assert levels[UNKNOWN_CODE] == "Idade ignorada"
        # The unknown code sorts after every numeric band, so the interface's
        # lexical ordering puts it last without special-casing it.
        assert sorted(levels)[-1] == UNKNOWN_CODE


class TestSpecIntegration:
    def test_the_declared_specs_fold_the_dimension_in(self) -> None:
        from pegasus_data._aggregate import load_specs

        specs = load_specs()
        sim = specs["sim_do_municipality_month"]
        assert "FAIXA_ETARIA" in sim.dimensions
        assert sim.dimension_labels["FAIXA_ETARIA"] == "Faixa etária"
        assert sim.level_labels["FAIXA_ETARIA"]["000"] == "menos de 1 ano"
        # The fingerprint carries the bands: changing them is a new artifact.
        assert sim.fingerprint_payload()["age"]["encoding"] == "sim"


class TestNumericBands:
    """`band_dimensions:` — the same derivation as age minus unit decoding."""

    def _peso(self):
        from pegasus_data._age import parse_band_dimensions

        (peso,) = parse_band_dimensions({
            "PESO_FAIXA": {"field": "PESO", "bands": [0, 1500, 2500, 4000], "unit": "g"},
        })
        return peso

    def test_who_cut_points_band_correctly(self) -> None:
        peso = self._peso()
        t = pa.table({"PESO": ["0985", "1500", "3200", "4100", "", "xx"]})
        assert peso.column(t).to_pylist() == [
            "0000", "1500", "2500", "4000", UNKNOWN_CODE, UNKNOWN_CODE,
        ]

    def test_codes_are_padded_to_the_widest_band_so_they_sort(self) -> None:
        peso = self._peso()
        levels = peso.band_levels()
        assert sorted(levels)[:-1] == ["0000", "1500", "2500", "4000"]
        assert levels["0000"] == "menos de 1.500 g"
        assert levels["4000"] == "4.000+ g"

    def test_bands_must_start_at_zero(self) -> None:
        from pegasus_data._age import parse_band_dimensions

        with pytest.raises(ValueError):
            parse_band_dimensions({"X": {"field": "X", "bands": [100, 200]}})

    def test_plain_years_encoding_reads_the_value_as_is(self) -> None:
        from pegasus_data._age import AgeDimension

        mae = AgeDimension(
            name="M", encoding="years", fields=("IDADEMAE",),
            bands=(0, 15, 20, 35),
        )
        t = pa.table({"IDADEMAE": ["14", "22", "36", "", "9x"]})
        assert bands_of(mae, t) == ["000", "020", "035", UNKNOWN_CODE, UNKNOWN_CODE]

    def test_the_sinasc_spec_folds_both_derivations_in(self) -> None:
        from pegasus_data._aggregate import spec_named

        spec = spec_named("sinasc_dn_municipality_month")
        assert "IDADEMAE_FAIXA" in spec.dimensions
        assert "PESO_FAIXA" in spec.dimensions
        payload = spec.fingerprint_payload()
        assert payload["band_dimensions"][0]["field"] == "PESO"
