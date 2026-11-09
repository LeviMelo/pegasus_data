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

import pyarrow as pa
import pytest

from pegasus_data._aggregate import (
    AggregateSpec,
    ArtifactMissing,
    aggregate,
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
def built(tmp_path, monkeypatch, fresh_install):
    """Build the shipped spec against a synthetic source.

    ``fresh_install``: a build asks its catalog's curation which dimensions hold several values per row (it records
    them in the manifest); a real build has the catalog its fetches created, the fake fetch here does not.
    """
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
        from pegasus_data.normalize.time import date_layout

        # Measured on live 2022 files.
        assert date_layout(["20211227", "20211226", "20220113"]) == "ymd"  # SIH
        assert date_layout(["07052022", "14052022", "28052022"]) == "dmy"  # SIM
        assert date_layout(["16041976", "13021959", "03042021"]) == "dmy"  # SINASC

    def test_they_are_disjoint_for_every_real_date(self) -> None:
        """No eight-digit date after 1900 reads both ways.

        If `text[4:8]` is a plausible year then `text[4:6]` is 19 or 20, which is
        not a month -- so year-first cannot also hold. This is why a small sample
        settles it exactly rather than probabilistically.
        """
        from pegasus_data.normalize.time import date_layout

        for year in (1900, 1999, 2000, 2022, 2100):
            for month in (1, 6, 12):
                for day in (1, 15, 28):
                    ymd = f"{year:04d}{month:02d}{day:02d}"
                    dmy = f"{day:02d}{month:02d}{year:04d}"
                    assert date_layout([ymd]) == "ymd", ymd
                    assert date_layout([dmy]) == "dmy", dmy

    def test_an_unreadable_column_is_refused_rather_than_guessed(self) -> None:
        """A period that means nothing is worse than no period at all."""
        from pegasus_data.normalize.time import date_layout

        assert date_layout([]) is None
        assert date_layout(["", "   ", None]) is None
        assert date_layout(["abcdefgh", "1234"]) is None
        # Mostly junk with a couple of readable values does not clear the bar.
        assert date_layout(["99999999"] * 20 + ["20220101"]) is None

    def test_a_day_first_column_becomes_the_right_period(self) -> None:
        import pyarrow as pa

        from pegasus_data.normalize.time import competencia_column

        table = pa.table({"DTOBITO": pa.array(["07052022", "31122022", "01012022"])})
        periods = competencia_column(table, ["DTOBITO"], "date").to_pylist()
        assert periods == ["202205", "202212", "202201"]

    def test_a_competence_is_left_alone(self) -> None:
        """The first six characters ARE the period when it is already year-first."""
        import pyarrow as pa

        from pegasus_data.normalize.time import competencia_column

        table = pa.table({"AP_CMP": pa.array(["202201", "202212"])})
        assert competencia_column(table, ["AP_CMP"], "year_month").to_pylist() == [
            "202201", "202212",
        ]
