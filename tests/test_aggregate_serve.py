"""Serving cells: pushforward, Total, and the refusals.

An axis you do not name is **marginalised**, and that is not a special case —
"Total" is the pushforward to a one-point space, the same operation as
municipality → health region with a smaller target
(`docs/AGGREGATE_ALGEBRA.md` §10a).

These build a small artifact by hand rather than fetching. The behaviour under
real volume was verified against live SIH-RD/AC/2022: Total over sex equalled
the sum of its categories exactly (49,547), mean length of stay served from
state matched `sum/n` to the last decimal, and rolling up to
`metropolitan_region` reported 49,477 of 49,547 unmapped rather than returning
70 admissions as if it were a national figure.
"""

from __future__ import annotations

import json

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from pegasus_data._aggregate import aggregate, artifact_dir, spec_named
from pegasus_data.measures import AggregationRefused

pytestmark = pytest.mark.filterwarnings("ignore")

#: Two Acre municipalities in one health region, one São Paulo, two months.
CELLS = [
    # municipality, competencia, SEXO, RACA_COR, adm, deaths, los_n, los_sum, cost
    ("120040", "202201", "1", "01", 10.0, 1.0, 10.0, 40.0, 1000.0),
    ("120040", "202201", "3", "01", 6.0, 0.0, 6.0, 12.0, 600.0),
    ("120040", "202202", "1", "02", 4.0, 1.0, 4.0, 8.0, 400.0),
    ("120020", "202201", "1", "01", 5.0, 0.0, 5.0, 25.0, 500.0),
    ("355030", "202202", "3", "01", 2.0, 0.0, 0.0, 0.0, 200.0),
]
KEYS = ("municipality", "competencia", "SEXO", "RACA_COR")
STATES = ("admissions_n", "deaths_sum", "los_n", "los_sum", "cost_sum")


@pytest.fixture
def settings(tmp_path):
    from pegasus_data.config import load_settings

    resolved = load_settings(root=tmp_path)
    target = artifact_dir("sih_rd_municipality_month", resolved)
    target.mkdir(parents=True, exist_ok=True)
    table = pa.table({
        **{name: pa.array([r[i] for r in CELLS], pa.string())
           for i, name in enumerate(KEYS)},
        **{name: pa.array([r[len(KEYS) + i] for r in CELLS], pa.float64())
           for i, name in enumerate(STATES)},
    })
    pq.write_table(table, target / "cells.parquet")
    (target / "manifest.json").write_text(json.dumps({
        "name": "sih_rd_municipality_month", "fingerprint": "test",
        "cells": len(CELLS), "years": [2022],
        "support": {"2022": {"SEXO": "present", "RACA_COR": "present"}},
        "key_columns": list(KEYS),
    }), encoding="utf-8")
    return resolved


N = "sih_rd_municipality_month"


def _one(table, **where):
    rows = [r for r in table.to_pylist()
            if all(str(r[k]) == str(v) for k, v in where.items())]
    assert len(rows) == 1, f"expected one row for {where}, got {len(rows)}"
    return rows[0]


class TestMarginalisingIsTotal:
    """The SIDRA property: an axis you do not name is aggregated away."""

    def test_total_over_every_axis_is_one_cell(self, settings) -> None:
        table = aggregate(N, measures=["admissions"], settings=settings)
        assert table.num_rows == 1
        assert table.to_pylist()[0]["admissions"] == 27.0

    def test_total_equals_the_sum_of_its_categories(self, settings) -> None:
        """If this fails the table contradicts itself and nothing on it is trusted."""
        total = aggregate(N, measures=["admissions"], settings=settings)
        parts = aggregate(N, by=["SEXO"], measures=["admissions"], settings=settings)
        assert (sum(r["admissions"] for r in parts.to_pylist())
                == total.to_pylist()[0]["admissions"])

    def test_the_same_holds_for_a_second_axis(self, settings) -> None:
        total = aggregate(N, measures=["cost"], settings=settings)
        parts = aggregate(N, by=["RACA_COR"], measures=["cost"], settings=settings)
        assert (pytest.approx(sum(r["cost"] for r in parts.to_pylist()))
                == total.to_pylist()[0]["cost"])

    def test_marginalising_one_axis_leaves_the_others(self, settings) -> None:
        table = aggregate(N, by=["municipality"], measures=["admissions"], settings=settings)
        assert _one(table, municipality="120040")["admissions"] == 20.0


class TestGeographicPushforward:
    def test_uf_comes_from_the_existing_code_rule(self, settings) -> None:
        table = aggregate(N, by=["uf"], measures=["admissions"], settings=settings)
        assert _one(table, uf="AC")["admissions"] == 25.0
        assert _one(table, uf="SP")["admissions"] == 2.0

    def test_rolling_up_to_uf_equals_aggregating_the_municipalities(self, settings) -> None:
        fine = aggregate(N, by=["municipality"], measures=["admissions"], settings=settings)
        acre = sum(r["admissions"] for r in fine.to_pylist()
                   if r["municipality"].startswith("12"))
        coarse = aggregate(N, by=["uf"], measures=["admissions"], settings=settings)
        assert _one(coarse, uf="AC")["admissions"] == acre

    def test_health_region_uses_the_compiled_geography(self, settings) -> None:
        """120040 and 120020 are both Acre health regions, and different ones."""
        table = aggregate(N, by=["health_region"], measures=["admissions"], settings=settings)
        labels = {r["health_region"] for r in table.to_pylist()}
        assert any("Baixo Acre" in label for label in labels), labels
        assert sum(r["admissions"] for r in table.to_pylist()) == 27.0

    def test_national_level_collapses_geography(self, settings) -> None:
        table = aggregate(N, by=["brazil"], measures=["admissions"], settings=settings)
        assert table.num_rows == 1
        assert table.to_pylist()[0]["admissions"] == 27.0

    def test_a_partial_classification_reports_the_mass_it_dropped(self, settings) -> None:
        """`metropolitan_region` covers 1,325 of ~5,570 municipalities.

        The rolled-up figure is a SUBSET total. Returning it silently is how a
        number that looks national turns out not to be.
        """
        table, report = aggregate(N, by=["metropolitan_region"], measures=["admissions"],
                                  settings=settings, return_report=True)
        served = sum(r["admissions"] for r in table.to_pylist())
        assert report.unmapped, "a partial map dropped mass and did not say so"
        assert served + report.unmapped["admissions"] == 27.0
        assert any("subset total" in w for w in report.warnings)


class TestTimePushforward:
    def test_month_is_the_base_level(self, settings) -> None:
        table = aggregate(N, by=["month"], measures=["admissions"], settings=settings)
        assert _one(table, month="202201")["admissions"] == 21.0

    def test_year_coarsens_the_months(self, settings) -> None:
        table = aggregate(N, by=["year"], measures=["admissions"], settings=settings)
        assert _one(table, year="2022")["admissions"] == 27.0

    def test_an_unknown_time_level_is_refused(self, settings) -> None:
        with pytest.raises(AggregationRefused, match="unknown level"):
            aggregate(N, by=["fortnight"], settings=settings)


class TestFinalizeHappensLast:
    def test_a_mean_is_derived_from_state_at_the_level_asked_for(self, settings) -> None:
        """4 stays over 25 days in one place; the mean must not be an average
        of per-cell means."""
        table = aggregate(N, by=["municipality"], measures=["los"], settings=settings)
        # 120040: n = 10+6+4 = 20, sum = 40+12+8 = 60
        assert _one(table, municipality="120040")["los"] == pytest.approx(3.0)

    def test_the_national_mean_is_not_the_mean_of_the_local_means(self, settings) -> None:
        national = aggregate(N, measures=["los"], settings=settings).to_pylist()[0]["los"]
        per_place = [r["los"] for r in
                     aggregate(N, by=["municipality"], measures=["los"],
                               settings=settings).to_pylist() if r["los"] is not None]
        assert national == pytest.approx(85 / 25)
        assert national != pytest.approx(sum(per_place) / len(per_place))

    def test_a_cell_with_no_observed_stay_yields_no_mean(self, settings) -> None:
        """São Paulo has los_n = 0. 0/0 is undefined, not zero."""
        table = aggregate(N, by=["municipality"], measures=["los"], settings=settings)
        assert _one(table, municipality="355030")["los"] is None


class TestFiltering:
    def test_filtering_by_year(self, settings) -> None:
        table = aggregate(N, measures=["admissions"], where={"year": "2022"},
                          settings=settings)
        assert table.to_pylist()[0]["admissions"] == 27.0

    def test_filtering_by_period_narrows_to_one_month(self, settings) -> None:
        table = aggregate(N, measures=["admissions"], where={"period": "202202"},
                          settings=settings)
        assert table.to_pylist()[0]["admissions"] == 6.0

    def test_filtering_by_uf(self, settings) -> None:
        table = aggregate(N, measures=["admissions"], where={"uf": "SP"},
                          settings=settings)
        assert table.to_pylist()[0]["admissions"] == 2.0

    def test_filtering_by_a_dimension(self, settings) -> None:
        table = aggregate(N, measures=["admissions"], where={"SEXO": "1"},
                          settings=settings)
        assert table.to_pylist()[0]["admissions"] == 19.0

    def test_filtering_on_something_absent_is_refused(self, settings) -> None:
        with pytest.raises(AggregationRefused, match="cannot filter on"):
            aggregate(N, where={"DIAG_PRINC": "I219"}, settings=settings)


class TestRefusals:
    def test_an_unknown_measure_names_what_is_available(self, settings) -> None:
        with pytest.raises(AggregationRefused, match="has no measure"):
            aggregate(N, measures=["mortality_rate"], settings=settings)

    def test_a_semi_additive_measure_refuses_to_be_summed_over_time(
        self, settings, monkeypatch
    ) -> None:
        """The bed-months rule, enforced at the point of service.

        A stock summed across months is 'thing-months'. The artifact here holds
        flows, so this substitutes a stock measure to prove the guard fires
        before any arithmetic happens.
        """
        from pegasus_data import _aggregate
        from pegasus_data.measures import measure_from_declaration

        spec = spec_named(N)
        stock = measure_from_declaration("admissions", {
            "kind": "count", "unit": "admission",
            "additive_over": ["geography", "dimensions"], "time_reducer": "mean",
        })
        patched = _aggregate.AggregateSpec(
            name=spec.name, dataset=spec.dataset,
            geography_binding=spec.geography_binding, time_binding=spec.time_binding,
            time_grain=spec.time_grain, dimensions=spec.dimensions, measures=(stock,),
        )
        monkeypatch.setattr(_aggregate, "spec_named", lambda name, root=None: patched)
        with pytest.raises(AggregationRefused, match="not additive over time"):
            aggregate(N, by=["year"], measures=["admissions"], settings=settings)

    def test_the_same_stock_still_serves_at_its_own_time_grain(
        self, settings, monkeypatch
    ) -> None:
        """Refusing the roll-up must not refuse the un-rolled-up question."""
        from pegasus_data import _aggregate
        from pegasus_data.measures import measure_from_declaration

        spec = spec_named(N)
        stock = measure_from_declaration("admissions", {
            "kind": "count", "unit": "admission",
            "additive_over": ["geography", "dimensions"], "time_reducer": "mean",
        })
        patched = _aggregate.AggregateSpec(
            name=spec.name, dataset=spec.dataset,
            geography_binding=spec.geography_binding, time_binding=spec.time_binding,
            time_grain=spec.time_grain, dimensions=spec.dimensions, measures=(stock,),
        )
        monkeypatch.setattr(_aggregate, "spec_named", lambda name, root=None: patched)
        table = aggregate(N, by=["month", "municipality"], measures=["admissions"],
                          settings=settings)
        assert table.num_rows > 0


class TestTheReport:
    def test_it_carries_the_support_mask_from_the_manifest(self, settings) -> None:
        _, report = aggregate(N, measures=["admissions"], settings=settings,
                              return_report=True)
        assert report.support["2022"]["SEXO"] == "present"

    def test_it_carries_the_artifact_identity(self, settings) -> None:
        _, report = aggregate(N, measures=["admissions"], settings=settings,
                              return_report=True)
        assert report.fingerprint == "test"
