"""The aggregation algebra, and the laws it has to obey.

These are monoid laws, not style preferences. If `merge` is not associative and
commutative then a roll-up depends on the order cells happen to arrive in, and
two runs of the same query disagree. `docs/AGGREGATE_ALGEBRA.md` §1 derives why.
"""

from __future__ import annotations

import pytest

from pegasus_data.measures import (
    AXES,
    COUNT,
    MAX,
    MEAN,
    MIN,
    RATIO,
    SUM,
    AggregationRefused,
    Measure,
    check_dimension,
    check_measure,
    check_rollup,
    finalize,
    kind_named,
    measure_from_declaration,
    merge_all,
)
from pegasus_data.semantics.curation import parse_grain

ALL_KINDS = (COUNT, SUM, MEAN, RATIO, MIN, MAX)
SAMPLE = (3.0, 1.0, 4.0, 1.0, 5.0, 9.0)


def _states(kind, values=SAMPLE):
    return [kind.lift(v) for v in values]


class TestTheMonoidLaws:
    """Associative, commutative, with an identity. Nothing else is negotiable."""

    @pytest.mark.parametrize("kind", ALL_KINDS, ids=lambda k: k.name)
    def test_identity_is_neutral(self, kind) -> None:
        for state in _states(kind):
            assert kind.merge(state, kind.identity()) == state
            assert kind.merge(kind.identity(), state) == state

    @pytest.mark.parametrize("kind", ALL_KINDS, ids=lambda k: k.name)
    def test_merge_is_commutative(self, kind) -> None:
        a, b = _states(kind)[:2]
        assert kind.merge(a, b) == kind.merge(b, a)

    @pytest.mark.parametrize("kind", ALL_KINDS, ids=lambda k: k.name)
    def test_merge_is_associative(self, kind) -> None:
        a, b, c = _states(kind)[:3]
        assert kind.merge(kind.merge(a, b), c) == kind.merge(a, kind.merge(b, c))

    @pytest.mark.parametrize("kind", ALL_KINDS, ids=lambda k: k.name)
    def test_grouping_does_not_change_the_answer(self, kind) -> None:
        """The property a roll-up actually depends on."""
        states = _states(kind)
        whole = merge_all(Measure("m", kind, "x"), states)
        left = merge_all(Measure("m", kind, "x"), states[:2])
        right = merge_all(Measure("m", kind, "x"), states[2:])
        assert kind.merge(left, right) == whole


class TestFinalizeSaysTheHonestThing:
    def test_mean_of_the_union_equals_merging_the_states(self) -> None:
        """The reason means are stored as (n, sum) and never as a number."""
        left, right = [1.0, 2.0, 3.0], [10.0, 20.0]
        measure = Measure("los", MEAN, "DIAS_PERM")
        combined = MEAN.merge(merge_all(measure, _states(MEAN, left)),
                              merge_all(measure, _states(MEAN, right)))
        assert finalize(measure, combined) == pytest.approx(sum(left + right) / 5)

    def test_an_empty_mean_is_undefined_not_zero(self) -> None:
        """0/0 is not 0. A cell nobody observed must not display a mean."""
        assert finalize(Measure("los", MEAN, "x"), MEAN.identity()) is None

    def test_an_empty_count_is_zero(self) -> None:
        """Nothing happened IS a number, unlike an unobserved average."""
        assert finalize(Measure("n", COUNT), COUNT.identity()) == 0

    def test_a_blank_value_does_not_drag_the_mean_down(self) -> None:
        """A blank DIAS_PERM is a stay of unknown length, not a stay of 0 days."""
        measure = Measure("los", MEAN, "DIAS_PERM")
        states = [MEAN.lift(v) for v in (4.0, "", None, "  ", 6.0)]
        assert finalize(measure, merge_all(measure, states)) == pytest.approx(5.0)

    def test_a_rate_combines_as_summed_parts_not_as_a_mean_of_rates(self) -> None:
        """The combined rate of two places is not the mean of their rates."""
        measure = Measure("r", RATIO, "x")
        big = (90.0, 100.0)      # 0.9 over a large denominator
        small = (0.0, 1.0)       # 0.0 over a tiny one
        assert finalize(measure, RATIO.merge(big, small)) == pytest.approx(90 / 101)
        assert finalize(measure, RATIO.merge(big, small)) != pytest.approx(0.45)

    def test_an_unobserved_extreme_is_undefined(self) -> None:
        assert finalize(Measure("m", MIN, "x"), MIN.identity()) is None
        assert finalize(Measure("m", MAX, "x"), MAX.identity()) is None


class TestMeasuresThatCannotExist:
    @pytest.mark.parametrize("name", ["median", "p95", "percentile", "mode"])
    def test_non_mergeable_kinds_are_refused_at_declaration(self, name) -> None:
        """Not an implementation gap — no bounded associative merge exists."""
        with pytest.raises(AggregationRefused, match="associative merge"):
            kind_named(name)

    def test_an_unknown_kind_is_refused(self) -> None:
        with pytest.raises(AggregationRefused, match="unknown measure kind"):
            kind_named("summ")

    def test_a_sum_without_a_source_field_is_refused(self) -> None:
        with pytest.raises(AggregationRefused, match="names no source field"):
            measure_from_declaration("cost", {"kind": "sum"})

    def test_count_needs_no_field(self) -> None:
        assert measure_from_declaration("n", {"kind": "count"}).source_field is None


class TestAdditivityIsPerAxis:
    """The bed-months rule. A stock does not accumulate over time."""

    @staticmethod
    def _beds():
        return measure_from_declaration("beds", {
            "kind": "sum", "field": "QTLEITOS", "unit": "bed",
            "additive_over": ["geography", "dimensions"], "time_reducer": "mean",
        })

    def test_a_stock_sums_across_geography(self) -> None:
        check_rollup(self._beds(), "geography")

    def test_a_stock_refuses_to_sum_across_time(self) -> None:
        with pytest.raises(AggregationRefused, match="not additive over time"):
            check_rollup(self._beds(), "time")

    def test_the_refusal_names_the_reducer_that_would_work(self) -> None:
        with pytest.raises(AggregationRefused, match="time_reducer='mean'"):
            check_rollup(self._beds(), "time")

    def test_a_flow_sums_across_every_axis(self) -> None:
        admissions = measure_from_declaration("admissions", {"kind": "count", "unit": "admission"})
        for axis in AXES:
            check_rollup(admissions, axis)

    def test_declaring_non_additivity_without_a_reducer_is_refused(self) -> None:
        with pytest.raises(AggregationRefused, match="names no time_reducer"):
            measure_from_declaration("beds", {
                "kind": "sum", "field": "Q", "additive_over": ["geography"],
            })

    def test_an_unknown_axis_is_refused(self) -> None:
        with pytest.raises(AggregationRefused, match="unknown axes"):
            measure_from_declaration("x", {"kind": "count", "additive_over": ["colour"]})


class TestTheGrainTypesTheMeasure:
    """`COUNT(*)` on CNES.ST counts establishment-months, not establishments."""

    def test_counting_the_entity_of_a_period_grain_is_refused(self) -> None:
        grain = parse_grain("establishment-month")
        assert grain.is_period_bearing
        measure = measure_from_declaration("establishments", {
            "kind": "count", "unit": "establishment"})
        with pytest.raises(AggregationRefused, match="establishment-month"):
            check_measure(measure, grain)

    def test_the_refusal_names_both_honest_alternatives(self) -> None:
        grain = parse_grain("establishment-month")
        measure = measure_from_declaration("establishments", {
            "kind": "count", "unit": "establishment"})
        with pytest.raises(AggregationRefused) as caught:
            check_measure(measure, grain)
        message = str(caught.value)
        assert "establishment-month" in message
        assert "distinct-count" in message

    def test_counting_the_period_grain_itself_is_allowed(self) -> None:
        check_measure(
            measure_from_declaration("establishment_months",
                                     {"kind": "count", "unit": "establishment-month"}),
            parse_grain("establishment-month"),
        )

    def test_an_event_grain_counts_freely(self) -> None:
        check_measure(
            measure_from_declaration("admissions", {"kind": "count", "unit": "admission"}),
            parse_grain("admission"),
        )

    def test_a_sum_is_not_constrained_by_the_grain(self) -> None:
        """Summing a column is not counting rows, so the rule does not apply."""
        check_measure(
            measure_from_declaration("cost", {"kind": "sum", "field": "V", "unit": "brl"}),
            parse_grain("establishment-month"),
        )


class TestMultiValuedDimensions:
    """A birth with three anomalies sits in three cells."""

    def test_a_grain_count_over_a_multi_valued_dimension_is_refused(self) -> None:
        births = measure_from_declaration("births", {"kind": "count", "unit": "live birth"})
        with pytest.raises(AggregationRefused, match="several values per row"):
            check_dimension(births, dimension_is_multi_valued=True)

    def test_a_single_valued_dimension_is_fine(self) -> None:
        births = measure_from_declaration("births", {"kind": "count", "unit": "live birth"})
        check_dimension(births, dimension_is_multi_valued=False)

    def test_a_sum_over_a_multi_valued_dimension_is_allowed(self) -> None:
        """Counting mentions is additive; it is simply a different measure."""
        mentions = measure_from_declaration("mentions", {"kind": "sum", "field": "N"})
        check_dimension(mentions, dimension_is_multi_valued=True)


class TestGrainParsing:
    @pytest.mark.parametrize(
        "prose,components,period",
        [
            ("admission", ("admission",), None),
            ("establishment-month", ("establishment", "month"), "month"),
            ("professional-establishment-month",
             ("professional", "establishment", "month"), "month"),
            ("establishment-bed type-month",
             ("establishment", "bed type", "month"), "month"),
            ("area-year", ("area", "year"), "year"),
        ],
    )
    def test_the_prose_already_names_the_components(self, prose, components, period) -> None:
        """39 grains across 132 datasets, and the hyphen is nearly always right."""
        grain = parse_grain(prose)
        assert grain.components == components
        assert grain.period_component == period

    def test_unanalysable_prose_yields_no_components_rather_than_a_guess(self) -> None:
        for prose in ("none (not a dataset)", "varies by block; the patient block is one"):
            assert not parse_grain(prose).analysable

    def test_an_explicit_declaration_overrides_the_prose(self) -> None:
        grain = parse_grain("municipality-vaccine-dose-period",
                            {"components": ["municipality", "vaccine", "dose", "month"],
                             "period_component": "month"})
        assert grain.declared
        assert grain.period_component == "month"
        assert grain.entity_components == ("municipality", "vaccine", "dose")
