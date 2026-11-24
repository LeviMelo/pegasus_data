"""rates.indirect_standardised on a population account given in full (no POPSVS read): expected counts at the study's
own rates sum to the observed, the ratio's interval is the exact Poisson one, groups pool places, a given reference
is applied as given, and events no ratio can hold are counted, not dropped."""
import pyarrow as pa
import pytest
from scipy.stats import chi2

from pegasus_data.rates import indirect_standardised

# two municipalities of Alagoas (real codes, so geography places them), two age bands, two sexes
POP = pa.table({"municipality": ["270030"] * 4 + ["270430"] * 4,
                "age": [10, 10, 70, 70] * 2,
                "sex": ["1", "2", "1", "2"] * 2,
                "population": [1000.0, 1000.0, 100.0, 100.0, 4000.0, 4000.0, 400.0, 400.0]})


def events(rows):
    mun, age, sex = zip(*rows)
    return pa.table({"mun": list(mun), "age": list(age), "sex": list(sex)})


def test_internal_reference_expected_sums_to_observed_and_interval_is_exact():
    rec = events([("270030", 12, "1")] * 3 + [("270030", 72, "3")] * 5 + [("270430", 72, "3")] * 10
                 + [("270430", 11, "1")] * 2 + [(None, 40, "1"), ("270030", None, "1"), ("270030", 12, "9")])
    t = indirect_standardised(rec, years=2022, by="mun", age="age", sex="sex", sex_codes={"1": "1", "3": "2"},
                              population=POP).to_pandas()
    places = t[t.group.notna()].set_index("group")
    assert places.observed.sum() == 20 and places.expected.sum() == pytest.approx(20)
    # rate of males 10-14: 5 / 5000; females 70+: 15 / 500; the others zero
    assert places.loc["270030", "expected"] == pytest.approx(1000 * 5 / 5000 + 100 * 15 / 500)
    o, e = places.loc["270030", "observed"], places.loc["270030", "expected"]
    assert places.loc["270030", "ci95_low"] == pytest.approx(chi2.ppf(0.025, 2 * o) / 2 / e)
    assert places.loc["270030", "ci95_high"] == pytest.approx(chi2.ppf(0.975, 2 * (o + 1)) / 2 / e)
    lost = t[t.group.isna()].iloc[0]
    assert (lost.unplaced, lost.unaged, lost.unsexed) == (1, 1, 1)


def test_groups_pool_places_and_given_reference_is_applied():
    rec = events([("270030", 72, "1")] * 4 + [("270430", 72, "1")] * 6)
    ref = pa.table({"band": [10, 10, 70, 70], "sex": ["1", "2", "1", "2"], "rate": [0.0, 0.0, 0.01, 0.0]})
    t = indirect_standardised(rec, years=2022, by="mun", age="age", sex="sex", sex_codes={"1": "1", "3": "2"},
                              population=POP, reference=ref, groups={"270030": "R1", "270430": "R1"}).to_pandas()
    assert list(t.group) == ["R1"]
    assert t.expected[0] == pytest.approx(0.01 * 500) and t.observed[0] == 10 and t.ratio[0] == pytest.approx(2.0)


def test_sex_codes_are_never_assumed():
    rec = events([("270030", 12, "1")])
    with pytest.raises(ValueError, match="sex codes differ by source"):
        indirect_standardised(rec, years=2022, by="mun", age="age", sex="sex", population=POP)


def test_events_in_cells_without_population_are_refused():
    rec = events([("270030", 40, "1")])          # band 40 has no person-years in POP
    with pytest.raises(ValueError, match="no population"):
        indirect_standardised(rec, years=2022, by="mun", age="age", sex="sex", sex_codes={"1": "1"}, population=POP)
