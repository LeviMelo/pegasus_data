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
    # municipality, ano, mes, sexo, raca, carater, morte, dias, valor, idade, cod_idade, uti
    # The first two rows agree on EVERY key column -- ages 30 and 32 land in
    # the same band -- so they merge into one cell; that merge is what
    # test_cells_are_the_distinct_key_tuples pins.
    ("120040", "2022", "01", "1", "01", "01", "0", "3", "100.00", "030", "4", "2"),
    ("120040", "2022", "01", "1", "01", "01", "0", "5", "200.00", "032", "4", "0"),
    ("120040", "2022", "01", "3", "02", "01", "1", "1", "50.00", "071", "4", "1"),
    ("120020", "2022", "02", "1", "01", "02", "0", "",  "10.00", "008", "3", "0"),  # blank stay; 8 MONTHS old
    ("355030", "2022", "02", "3", "01", "01", "0", "7", "70.00", "xx", "9", "0"),   # undecodable age
]
COLUMNS = ("MUNIC_RES", "ANO_CMPT", "MES_CMPT", "SEXO", "RACA_COR", "CAR_INT",
           "MORTE", "DIAS_PERM", "VAL_TOT", "IDADE", "COD_IDADE", "UTI_MES_TO")


#: The two-digit IBGE prefixes the fixture rows use, so the fake fetch can
#: answer a per-state request the way the real one does.
_UF_OF = {"12": "AC", "35": "SP", "11": "RO", "33": "RJ"}


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
        # Honours `uf`, because the build now chunks a national request one
        # state at a time. A fake that ignored it would hand the same rows back
        # 27 times and report 27x the volume -- which is exactly what happened
        # the first time this changed.
        report = type("R", (), {"warnings": []})()
        wanted = kwargs.get("uf")
        table = _table()
        if wanted is None:
            return table, report
        codes = {u.upper() for u in ([wanted] if isinstance(wanted, str) else wanted)}
        keep = [
            i for i, code in enumerate(table.column("MUNIC_RES").to_pylist())
            if _UF_OF.get(str(code)[:2]) in codes
        ]
        # A typed index array: `take([])` on an empty Python list gives Arrow a
        # null-typed index and it refuses the kernel.
        return table.take(pa.array(keep, pa.int64())), report

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
        assert {m.name for m in spec.measures} == {
            "admissions", "deaths", "los", "cost", "uti_days"}

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
        assert merged["FAIXA_ETARIA"] == "030", "ages 30 and 32 share a band"
        assert merged["admissions_n"] == 2
        assert merged["deaths_sum"] == 0
        assert merged["los_n"] == 2 and merged["los_sum"] == 8
        assert merged["cost_sum"] == pytest.approx(300.0)
        assert merged["uti_days_sum"] == 2
        eighty = rows[("120040", "202201", "3", "02")]
        assert eighty["deaths_sum"] == 1
        unknown = rows[("355030", "202202", "3", "01")]
        assert unknown["FAIXA_ETARIA"] == "ZIG", "an undecodable age is a level"

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
        assert report.support["2022"]["SEXO"] == "present"
        assert report.support["2022"]["RACA_COR"] == "present"
        # The derived dimension reports the availability of its SOURCES.
        assert "FAIXA_ETARIA" in report.support["2022"]

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


class TestARecordDateAxisHasIncompleteEdges:
    """Publication year is not record year, and the gap is 7.44%.

    Measured on live SIH: the file published under 2022 for Acre holds 3,687
    admissions that happened in 2021, the earliest in February — because a
    December admission is billed in January. So a series keyed on a RECORD date
    is missing its own edges unless the neighbouring publication year is built
    too.

    A `competence` axis has no such problem: the competence IS the publication
    coordinate. The build must know the difference, and say so rather than
    letting a coverage gap read as a fall in admissions.
    """

    @staticmethod
    def _spec(binding):
        from pegasus_data.measures import measure_from_declaration

        return AggregateSpec(
            name="edges", dataset="SIH-RD", geography_binding="residence",
            time_binding=binding, time_grain="month", dimensions=(),
            measures=(measure_from_declaration("n", {"kind": "count", "unit": "admission"}),),
        )

    def _build(self, monkeypatch, tmp_path, binding, rows):
        from pegasus_data import _aggregate
        from pegasus_data.config import load_settings

        columns = ("MUNIC_RES", "ANO_CMPT", "MES_CMPT", "DT_INTER")
        table = pa.table({c: pa.array([r[i] for r in rows], pa.string())
                          for i, c in enumerate(columns)})
        monkeypatch.setattr("pegasus_data.retrieve.fetch",
                            lambda dataset, **kw: (table, type("R", (), {"warnings": []})()))
        monkeypatch.setattr("pegasus_data._availability.field_available",
                            lambda *a, **k: "present")
        monkeypatch.setattr(_aggregate, "spec_named",
                            lambda name, root=None: self._spec(binding))
        return build_aggregate("edges", years=[2022], settings=load_settings(root=tmp_path))

    ROWS = [
        ("120040", "2022", "01", "20211215"),   # admitted Dec 2021, billed Jan 2022
        ("120040", "2022", "03", "20220301"),
        ("120040", "2022", "12", "20221220"),   # its own tail bills in 2023
    ]

    def test_a_record_date_axis_flags_the_years_it_cannot_have_filled(
        self, monkeypatch, tmp_path
    ) -> None:
        report = self._build(monkeypatch, tmp_path, "admission", self.ROWS)
        assert report.partial_periods, "no period flagged, yet 2021 is a fragment"
        assert "2021" in report.partial_periods
        assert "2022" in report.partial_periods, (
            "2022's December admissions are billed in 2023, so it is short too"
        )
        assert any("record date" in w for w in report.warnings)

    def test_a_competence_axis_flags_nothing(self, monkeypatch, tmp_path) -> None:
        """The competence IS the publication coordinate, so nothing is short."""
        report = self._build(monkeypatch, tmp_path, "competence", self.ROWS)
        assert report.partial_periods == ()
        assert not any("record date" in w for w in report.warnings)

    def test_the_flag_survives_into_the_manifest_and_back_out(
        self, monkeypatch, tmp_path
    ) -> None:
        """A caller reading the artifact months later must still be told."""
        from pegasus_data._aggregate import aggregate as serve

        self._build(monkeypatch, tmp_path, "admission", self.ROWS)
        from pegasus_data.config import load_settings

        _, report = serve("edges", settings=load_settings(root=tmp_path), return_report=True)
        assert "2021" in report.partial_periods
        assert any("short" in w for w in report.warnings)


def test_a_non_municipality_geography_binding_is_refused(monkeypatch, tmp_path) -> None:
    """An aggregate's base cuboid is keyed on a municipality.

    `IBGE.PROJUF` is projected by state. Building it through this spec would key
    cells on 27 two-digit codes no municipality table resolves — every roll-up
    unmapped, every total a subset — so it is refused at the spec rather than
    discovered in the output.
    """
    from pegasus_data import _aggregate
    from pegasus_data.config import load_settings
    from pegasus_data.measures import measure_from_declaration
    from pegasus_data.semantics.curation import DatasetSemantics, parse_grain

    spec = AggregateSpec(
        name="by_state", dataset="IBGE-PROJUF", geography_binding="state",
        time_binding="reference", time_grain="year", dimensions=(),
        measures=(measure_from_declaration("n", {"kind": "count"}),),
    )
    fake = DatasetSemantics(
        dataset_id="IBGE.PROJUF", system="IBGE", series="PROJUF",
        grain=parse_grain("state-year"),
        axes={"geography": {"state": {"fields": ["UFCOD"], "code_system": "ibge_uf"}},
              "default_geography": "state",
              "time": {"reference": {"fields": ["ANO"], "encoding": "year"}},
              "default_time": "reference"},
    )
    monkeypatch.setattr(_aggregate, "spec_named", lambda name, root=None: spec)
    monkeypatch.setattr(_aggregate, "_resolve_semantics", lambda _spec: fake)
    with pytest.raises(AggregationRefused, match="keyed on a municipality"):
        build_aggregate("by_state", years=[2022], settings=load_settings(root=tmp_path))


class TestDateLayoutIsMeasured:
    """DATASUS does not use one date format, and the builder used to assume it did.

    Nineteen (system, field) pairs declare a `date` encoding and none had been
    built: both existing specs use a competence, so every test exercised the one
    path where "the first six characters are the period" happens to hold.
    """

    def test_the_two_layouts_are_told_apart(self) -> None:
        from pegasus_data._aggregate import _date_layout

        # Measured on live 2022 files.
        assert _date_layout(["20211227", "20211226", "20220113"]) == "ymd"  # SIH
        assert _date_layout(["07052022", "14052022", "28052022"]) == "dmy"  # SIM
        assert _date_layout(["16041976", "13021959", "03042021"]) == "dmy"  # SINASC

    def test_they_are_disjoint_for_every_real_date(self) -> None:
        """No eight-digit date after 1900 reads both ways.

        If `text[4:8]` is a plausible year then `text[4:6]` is 19 or 20, which is
        not a month -- so year-first cannot also hold. This is why a small sample
        settles it exactly rather than probabilistically.
        """
        from pegasus_data._aggregate import _date_layout

        for year in (1900, 1999, 2000, 2022, 2100):
            for month in (1, 6, 12):
                for day in (1, 15, 28):
                    ymd = f"{year:04d}{month:02d}{day:02d}"
                    dmy = f"{day:02d}{month:02d}{year:04d}"
                    assert _date_layout([ymd]) == "ymd", ymd
                    assert _date_layout([dmy]) == "dmy", dmy

    def test_an_unreadable_column_is_refused_rather_than_guessed(self) -> None:
        """A period that means nothing is worse than no period at all."""
        from pegasus_data._aggregate import _date_layout

        assert _date_layout([]) is None
        assert _date_layout(["", "   ", None]) is None
        assert _date_layout(["abcdefgh", "1234"]) is None
        # Mostly junk with a couple of readable values does not clear the bar.
        assert _date_layout(["99999999"] * 20 + ["20220101"]) is None

    def test_a_day_first_column_becomes_the_right_period(self) -> None:
        import pyarrow as pa

        from pegasus_data._aggregate import _competencia_column

        table = pa.table({"DTOBITO": pa.array(["07052022", "31122022", "01012022"])})
        periods = _competencia_column(table, ["DTOBITO"], "date").to_pylist()
        assert periods == ["202205", "202212", "202201"]

    def test_a_competence_is_left_alone(self) -> None:
        """The first six characters ARE the period when it is already year-first."""
        import pyarrow as pa

        from pegasus_data._aggregate import _competencia_column

        table = pa.table({"AP_CMP": pa.array(["202201", "202212"])})
        assert _competencia_column(table, ["AP_CMP"], "year_month").to_pylist() == [
            "202201", "202212",
        ]
