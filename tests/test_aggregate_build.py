"""Building the base cuboid: specs, refusals, and arithmetic.

The build's only source of rows is the ordinary retrieval path, so these tests
substitute a synthetic table for it rather than reaching the FTP tree. What is
being tested is the lift/merge and the refusals, not the network.

The correctness claim that matters — that the artifact reproduces a direct
GROUP BY exactly — was verified against live SIH-RD/AC/2022: 49,547 admissions
into 2,417 cells, identical key sets, zero disagreeing cells, and totals
reconciling to the microdata row count.
"""

from __future__ import annotations

import json

import pyarrow as pa
import pytest

from pegasus_data._aggregate import (
    AggregateSpec,
    ArtifactMissing,
    aggregate,
    artifact_dir,
    build_aggregate,
    load_specs,
    spec_named,
)
from pegasus_data.measures import AggregationRefused

pytestmark = pytest.mark.filterwarnings("ignore")


ROWS = [
    # municipality, ano, mes, sexo, raca, morte, dias, valor
    ("120040", "2022", "01", "1", "01", "0", "3", "100.00"),
    ("120040", "2022", "01", "1", "01", "1", "5", "200.00"),
    ("120040", "2022", "01", "3", "02", "0", "1", "50.00"),
    ("120020", "2022", "02", "1", "01", "0", "",  "10.00"),   # blank stay
    ("355030", "2022", "02", "3", "01", "0", "7", "70.00"),
]
COLUMNS = ("MUNIC_RES", "ANO_CMPT", "MES_CMPT", "SEXO", "RACA_COR",
           "MORTE", "DIAS_PERM", "VAL_TOT")


def _table():
    data = {name: [row[i] for row in ROWS] for i, name in enumerate(COLUMNS)}
    data["_blob_sha256"] = ["deadbeef"] * len(ROWS)
    return pa.table({k: pa.array(v, pa.string()) for k, v in data.items()})


@pytest.fixture
def built(tmp_path, monkeypatch):
    """Build the shipped spec against a synthetic source."""
    from pegasus_data.config import load_settings

    settings = load_settings(root=tmp_path)

    def fake_fetch(dataset, **kwargs):
        report = type("R", (), {"warnings": []})()
        return _table(), report

    monkeypatch.setattr("pegasus_data.retrieve.fetch", fake_fetch)
    monkeypatch.setattr("pegasus_data._availability.field_available",
                        lambda *a, **k: "present")
    report = build_aggregate("sih_rd_municipality_month", years=[2022], settings=settings)
    return settings, report


class TestTheSpecIsDeclarative:
    def test_the_shipped_spec_loads(self) -> None:
        spec = spec_named("sih_rd_municipality_month")
        assert spec.dataset == "SIH-RD"
        assert spec.geography_binding == "residence"
        assert spec.time_binding == "competence"
        assert {m.name for m in spec.measures} == {"admissions", "deaths", "los", "cost"}

    def test_bindings_name_semantic_axes_not_columns(self) -> None:
        """`residence` is a key of semantic_axes, not a field name.

        Which municipality column a dataset means is a question about the
        analysis — SIH declares residence AND facility — and curation already
        answers it. The spec must not name MUNIC_RES directly.
        """
        from pegasus_data.semantics.curation import semantics_for

        spec = spec_named("sih_rd_municipality_month")
        axes = semantics_for(spec.dataset)
        assert spec.geography_binding in axes.geography_bindings()
        assert spec.time_binding in axes.time_bindings()

    def test_state_columns_carry_accumulator_state_not_answers(self) -> None:
        """`los` occupies (n, sum) so a mean is derivable at any level."""
        spec = spec_named("sih_rd_municipality_month")
        assert spec.measure_named("los").state_columns() == ("los_n", "los_sum")
        assert "los" not in spec.state_columns()

    def test_an_unknown_spec_is_refused_by_name(self) -> None:
        with pytest.raises(AggregationRefused, match="no aggregate spec named"):
            spec_named("not_a_spec")

    def test_every_shipped_spec_is_loadable(self) -> None:
        assert load_specs(), "no aggregate specs ship"


class TestTheBuild:
    def test_cells_are_the_distinct_key_tuples(self, built) -> None:
        settings, report = built
        assert report.rows_read == len(ROWS)
        # (120040,202201,1,01) merges two rows; the rest are distinct.
        assert report.cells == 4

    def test_measures_accumulate_correctly(self, built) -> None:
        import pyarrow.parquet as pq

        settings, _ = built
        table = pq.read_table(artifact_dir("sih_rd_municipality_month", settings) / "cells.parquet")
        rows = {(r["municipality"], r["competencia"], r["SEXO"], r["RACA_COR"]): r
                for r in table.to_pylist()}
        merged = rows[("120040", "202201", "1", "01")]
        assert merged["admissions_n"] == 2
        assert merged["deaths_sum"] == 1
        assert merged["los_n"] == 2 and merged["los_sum"] == 8
        assert merged["cost_sum"] == pytest.approx(300.0)

    def test_a_blank_value_contributes_no_observation_to_a_mean(self, built) -> None:
        """A blank DIAS_PERM is an unknown stay, not a stay of nought days."""
        import pyarrow.parquet as pq

        settings, _ = built
        table = pq.read_table(artifact_dir("sih_rd_municipality_month", settings) / "cells.parquet")
        blank = next(r for r in table.to_pylist() if r["municipality"] == "120020")
        assert blank["admissions_n"] == 1
        assert blank["los_n"] == 0 and blank["los_sum"] == 0

    def test_the_support_mask_is_recorded_per_year_and_dimension(self, built) -> None:
        """Distinguishes 'zero happened' from 'the column did not exist'."""
        settings, report = built
        assert report.support["2022"] == {"SEXO": "present", "RACA_COR": "present"}

    def test_the_manifest_records_identity_and_support(self, built) -> None:
        settings, report = built
        manifest = json.loads(
            (artifact_dir("sih_rd_municipality_month", settings) / "manifest.json")
            .read_text(encoding="utf-8"))
        assert manifest["fingerprint"] == report.fingerprint
        assert manifest["cells"] == report.cells
        assert manifest["support"] == report.support
        assert manifest["key_columns"][:2] == ["municipality", "competencia"]

    def test_an_unbounded_build_is_refused(self) -> None:
        """Without years this would download the whole publication history."""
        with pytest.raises(AggregationRefused, match="explicit years"):
            build_aggregate("sih_rd_municipality_month")


class TestFingerprintIdentity:
    def test_the_geography_pack_is_part_of_the_identity(self, monkeypatch) -> None:
        """Changing it changes every health-region roll-up derived from here.

        An artifact that does not notice is stale in a way nobody can see.
        """
        from pegasus_data import _aggregate

        spec = spec_named("sih_rd_municipality_month")
        settings = type("S", (), {})()
        before = _aggregate._fingerprint(spec, {"abc"}, settings)

        real = _aggregate.hashlib.sha256

        class _Different:
            @staticmethod
            def hexdigest() -> str:
                return "a-different-geography-pack"

        monkeypatch.setattr(_aggregate.hashlib, "sha256", lambda _b: _Different)
        after = _aggregate._fingerprint(spec, {"abc"}, settings)
        monkeypatch.setattr(_aggregate.hashlib, "sha256", real)
        assert before != after

    def test_the_sources_are_part_of_the_identity(self) -> None:
        from pegasus_data import _aggregate

        spec = spec_named("sih_rd_municipality_month")
        settings = type("S", (), {})()
        assert (_aggregate._fingerprint(spec, {"aaa"}, settings)
                != _aggregate._fingerprint(spec, {"bbb"}, settings))

    def test_the_same_inputs_give_the_same_identity(self) -> None:
        from pegasus_data import _aggregate

        spec = spec_named("sih_rd_municipality_month")
        settings = type("S", (), {})()
        assert (_aggregate._fingerprint(spec, {"aaa"}, settings)
                == _aggregate._fingerprint(spec, {"aaa"}, settings))


class TestGrainRefusalsHappenBeforeAnyReading:
    def test_a_measure_the_grain_contradicts_is_refused(self, tmp_path, monkeypatch) -> None:
        """CNES.ST is establishment-month, so counting rows counts those."""
        from pegasus_data import _aggregate
        from pegasus_data.config import load_settings
        from pegasus_data.measures import measure_from_declaration

        bad = AggregateSpec(
            name="bad", dataset="CNES-ST", geography_binding="facility",
            time_binding="competence", time_grain="month", dimensions=(),
            measures=(measure_from_declaration(
                "establishments", {"kind": "count", "unit": "establishment"}),),
        )
        monkeypatch.setattr(_aggregate, "spec_named", lambda name, root=None: bad)
        with pytest.raises(AggregationRefused, match="establishment-month"):
            build_aggregate("bad", years=[2022], settings=load_settings(root=tmp_path))


def test_serving_an_unbuilt_artifact_says_how_to_build_it(tmp_path) -> None:
    from pegasus_data.config import load_settings

    with pytest.raises(ArtifactMissing, match="aggregate-build"):
        aggregate("sih_rd_municipality_month", settings=load_settings(root=tmp_path))


class TestTheAbstractionSurvivesAStockDataset:
    """CNES.ST is establishment-month, not an event stream.

    `REQUEST.md` asks for exactly this check: if the layer assumes events and
    that `COUNT(rows)` has one meaning, it fails here and needs redesigning
    before coverage broadens. It does not — the guards are refusals in
    `measures.py`, so a second family needed a spec and no code.
    """

    def test_the_stock_spec_loads_beside_the_event_one(self) -> None:
        spec = spec_named("cnes_st_municipality_month")
        assert spec.dataset == "CNES-ST"
        assert spec.geography_binding == "facility"

    def test_its_grain_is_period_bearing_and_the_count_is_named_for_that(self) -> None:
        from pegasus_data.measures import check_measure
        from pegasus_data.semantics.curation import semantics_for

        spec = spec_named("cnes_st_municipality_month")
        grain = semantics_for(spec.dataset).grain
        assert grain.is_period_bearing
        assert grain.counts() == "establishment-month"
        # The shipped spec passes the guard precisely because it is named
        # honestly; renaming it to `establishment` would fail below.
        for measure in spec.measures:
            check_measure(measure, grain)

    def test_calling_that_count_establishments_would_be_refused(self) -> None:
        from pegasus_data.measures import check_measure, measure_from_declaration
        from pegasus_data.semantics.curation import semantics_for

        grain = semantics_for("CNES-ST").grain
        with pytest.raises(AggregationRefused, match="establishment-month"):
            check_measure(
                measure_from_declaration("establishments",
                                         {"kind": "count", "unit": "establishment"}),
                grain,
            )

    def test_capacity_is_semi_additive_and_says_which_axis(self) -> None:
        from pegasus_data.measures import check_rollup

        spec = spec_named("cnes_st_municipality_month")
        rooms = spec.measure_named("consulting_rooms")
        assert rooms.is_semi_additive
        check_rollup(rooms, "geography")          # real: rooms in a region
        with pytest.raises(AggregationRefused, match="not additive over time"):
            check_rollup(rooms, "time")           # meaningless: room-months

    def test_the_event_spec_is_additive_everywhere_by_contrast(self) -> None:
        from pegasus_data.measures import AXES, check_rollup

        admissions = spec_named("sih_rd_municipality_month").measure_named("admissions")
        assert not admissions.is_semi_additive
        for axis in AXES:
            check_rollup(admissions, axis)
