"""One call, DATASUS to a table — the microdatasus-shaped door.

Most people arriving at DATASUS want one thing: *SIH admissions for Alagoas in
2023*. ``fetch()`` is that request, and these tests hold the three properties
that make the shortcut trustworthy rather than merely short.

**It must not answer a narrower question than it was asked.** A filter that
matches nothing, a file that fails to decode, a year DATASUS never published —
each has to be visible in the result. An empty or short table returned quietly
is the single easiest way to publish a wrong number, and it is why almost every
test here checks the report as well as the rows.

**It must not invent paths.** microdatasus builds the FTP path from a template,
which works until DATASUS moves something. Here every path comes from the
catalog, and discovery is a bounded crawl of one system's directory that records
what it saw.

**It must render through the same code as everything else.** A second labelling
implementation is a second set of labels to keep true.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.inventory.families import schema_signature
from pegasus_data.normalize.engine import MissingColumnError
from pegasus_data.retrieve import (
    DatasetUnknown,
    NothingPublished,
    _month_of,
    fetch,
    parse_dataset,
)
from tests.conftest import make_dbf

FIELDS = [("N_AIH", "C", 6, 0), ("SEXO", "C", 1, 0), ("DIAG_PRINC", "C", 4, 0)]
NAMES = [f[0] for f in FIELDS]
SIGNATURE = schema_signature(NAMES)


def one_file(rows: int = 2) -> bytes:
    return make_dbf(
        FIELDS, [[f"A{n:05d}", "1" if n % 2 else "3", "I10"] for n in range(rows)]
    )


class FakeFetcher:
    """Stands in for the FTP fetcher: every path resolves to the same bytes.

    ``missing`` names paths that fail, which is how the undecoded-file reporting
    is exercised without needing a broken file on a real server.
    """

    def __init__(self, missing: set[str] | None = None) -> None:
        self.missing = missing or set()
        self.asked: list[str] = []

    def ensure(self, paths):
        self.asked.extend(paths)
        return {p: f"sha-{p}" for p in paths if p not in self.missing}


class FakeBlobs:
    def __init__(self, payload_for=None) -> None:
        self.payload_for = payload_for or (lambda _digest: one_file())

    def read(self, digest: str) -> bytes:
        return self.payload_for(digest)


@pytest.fixture
def seeded(settings, monkeypatch):
    """A catalog that already knows one SIH-RD family across two states/years."""
    catalog = Catalog(settings.catalog_path)
    catalog.execute(
        "INSERT INTO families (family_id, system, series, schema_signature, field_count) "
        "VALUES ('F1','SIHSUS','RD',?,3)",
        (SIGNATURE,),
    )
    for path, uf, year, date in (
        ("/p/RDAL2301.dbc", "AL", 2023, 202301),
        ("/p/RDAL2302.dbc", "AL", 2023, 202302),
        ("/p/RDSP2401.dbc", "SP", 2024, 202401),
    ):
        catalog.execute(
            "INSERT INTO files (path, directory, filename, first_seen, last_seen) "
            "VALUES (?,?,?,'2026-01-01T00:00:00Z','2026-01-01T00:00:00Z')",
            (path, "/p", path.rsplit("/", 1)[-1]),
        )
        catalog.execute(
            "INSERT INTO file_facts (path, system, series_prefix, geo_code, year, "
            "normalized_date, role) VALUES (?,'SIHSUS','RD',?,?,?,'data')",
            (path, uf, year, date),
        )
        catalog.execute(
            "INSERT INTO family_files (family_id, path, member) VALUES ('F1', ?, '')", (path,)
        )
    catalog.close()

    import pegasus_data.retrieve as retrieve

    state: dict[str, object] = {"fetcher": FakeFetcher(), "blobs": FakeBlobs()}

    real_pipeline = retrieve.Pipeline

    def make(settings_arg, *args, **kwargs):
        pipeline = real_pipeline(settings_arg, *args, **kwargs)
        pipeline.fetcher = state["fetcher"]
        pipeline.blobs = state["blobs"]
        return pipeline

    monkeypatch.setattr(retrieve, "Pipeline", make)
    return state


class TestNamingADataset:
    @pytest.mark.parametrize(
        "spec", ["SIH-RD", "SIH/RD", "sih_rd", "SIHSUS RD", "SIHSUS.RD"]
    )
    def test_the_forms_people_actually_type_all_resolve(self, spec):
        assert parse_dataset(spec) == ("SIHSUS", "RD")

    def test_a_bare_system_means_every_series_in_it(self):
        assert parse_dataset("SIM") == ("SIM", None)

    def test_an_explicit_series_argument_wins(self):
        assert parse_dataset("SIHSUS", "rd") == ("SIHSUS", "RD")

    def test_an_unknown_system_is_passed_through_not_guessed_at(self):
        """The catalog decides what exists; the alias table is typing sugar."""
        assert parse_dataset("WHATEVER-XX") == ("WHATEVER", "XX")

    def test_an_empty_name_is_refused(self):
        with pytest.raises(DatasetUnknown):
            parse_dataset("   ")


class TestItReturnsData:
    def test_a_dataset_comes_back_as_rows(self, settings, seeded):
        table = fetch("SIH-RD", settings=settings)
        assert table.num_rows == 6, "three files of two rows"
        assert "SEXO" in table.column_names

    def test_a_uf_filter_narrows_what_is_downloaded(self, settings, seeded):
        table, report = fetch("SIH-RD", uf="AL", settings=settings, report=True)
        assert report.files_matched == 2
        assert table.num_rows == 4
        assert all("AL" in p for p in seeded["fetcher"].asked)

    def test_a_year_filter_narrows_it_too(self, settings, seeded):
        _, report = fetch("SIH-RD", years=2024, settings=settings, report=True)
        assert report.files_matched == 1
        assert report.years_returned == [2024]

    def test_a_month_filter_picks_one_competence(self, settings, seeded):
        _, report = fetch("SIH-RD", months=2, settings=settings, report=True)
        assert report.files_matched == 1

    def test_max_files_bounds_a_speculative_call(self, settings, seeded):
        _, report = fetch("SIH-RD", max_files=1, settings=settings, report=True)
        assert report.files_matched == 1

    def test_columns_selects_without_reordering_into_something_else(self, settings, seeded):
        table = fetch("SIH-RD", columns=["SEXO"], settings=settings)
        assert table.column_names == ["SEXO"]


class TestItSaysWhatItCouldNotDo:
    def test_a_year_nobody_published_is_named_as_such(self, settings, seeded):
        with pytest.raises(NothingPublished, match="publishes nothing"):
            fetch("SIH-RD", years=1990, settings=settings)

    def test_the_message_names_the_filter_that_emptied_the_result(self, settings, seeded):
        with pytest.raises(NothingPublished, match=r"uf=\['RR'\]"):
            fetch("SIH-RD", uf="RR", settings=settings)

    def test_a_file_that_could_not_be_fetched_is_named_not_skipped(self, settings, seeded):
        seeded["fetcher"] = FakeFetcher(missing={"/p/RDAL2301.dbc"})
        table, report = fetch("SIH-RD", uf="AL", settings=settings, report=True)
        assert report.undecoded == ["/p/RDAL2301.dbc"]
        assert report.files_read == 1 and table.num_rows == 2

    def test_a_file_whose_schema_does_not_fit_its_family_is_counted(self, settings, seeded):
        """The zero-row signature: the family claims a file it cannot normalise."""
        other = make_dbf([("SOMETHING", "C", 3, 0)], [["abc"]])
        seeded["blobs"] = FakeBlobs(lambda _d: other)
        with pytest.raises(NothingPublished, match="did not match their family's schema"):
            fetch("SIH-RD", settings=settings)

    def test_a_missing_year_is_reported_beside_the_ones_returned(self, settings, seeded):
        _, report = fetch("SIH-RD", years=[2023, 2024], settings=settings, report=True)
        assert report.years_returned == [2023, 2024] and report.years_missing == []

    def test_a_column_this_generation_lacks_raises_rather_than_vanishing(
        self, settings, seeded
    ):
        with pytest.raises(MissingColumnError):
            fetch("SIH-RD", columns=["IDADE"], settings=settings)

    def test_the_report_counts_what_was_downloaded(self, settings, seeded):
        _, report = fetch("SIH-RD", uf="SP", settings=settings, report=True)
        assert report.bytes_downloaded == len(one_file())
        assert report.ufs_returned == ["SP"]


class TestDiscovery:
    def test_an_uncatalogued_system_is_refused_when_discovery_is_off(self, settings, seeded):
        """Better than a silent 'nothing published' when the network is absent."""
        with pytest.raises(DatasetUnknown, match="discovery is off"):
            fetch("SINASC-DN", discover=False, settings=settings)

    def test_a_catalogued_system_never_touches_the_network(self, settings, seeded, monkeypatch):
        import pegasus_data.retrieve as retrieve

        def explode(*_args, **_kwargs):
            raise AssertionError("discovery ran for a system already in the catalog")

        monkeypatch.setattr(retrieve, "_discover", explode)
        assert fetch("SIH-RD", settings=settings).num_rows == 6


class TestRendering:
    def test_labels_are_joined_through_the_shared_render_path(self, settings, seeded):
        catalog = Catalog(settings.catalog_path)
        for code, label in (("1", "Masculino"), ("3", "Feminino")):
            catalog.execute(
                "INSERT INTO dictionary (system, value_group, field_name, value_raw, "
                "value_label, source, source_ref, confidence) "
                "VALUES ('SIHSUS','SEXO','SEXO',?,?,'cnv','SEXO.CNV',0.9)",
                (code, label),
            )
        catalog.execute(
            "INSERT INTO field_codelists (system, family_id, field_name, codelist, source, "
            "source_ref, confidence) VALUES ('SIHSUS','','SEXO','SEXO','def','x',0.9)"
        )
        catalog.execute(
            "INSERT INTO variable_docs (system, field_name, code_system, codelist, source) "
            "VALUES ('SIHSUS','SEXO','internal','SEXO','manual')"
        )
        catalog.close()
        table = fetch("SIH-RD", settings=settings)
        assert set(table.column("SEXO").to_pylist()) == {"Masculino", "Feminino"}

    def test_labels_false_returns_the_codes_as_filed(self, settings, seeded):
        table = fetch("SIH-RD", labels=False, settings=settings)
        assert set(table.column("SEXO").to_pylist()) == {"1", "3"}


class TestOffline:
    """The whole point of the bundle, exercised through the whole point of fetch.

    A machine that has never parsed a ``.CNV`` in its life, with DATASUS
    unreachable, still has to be able to say that ``SEXO=3`` is Feminino.
    """

    def test_a_bundle_is_enough_to_label_a_freshly_fetched_table(
        self, settings, seeded, tmp_path, fresh_catalog
    ):
        from pegasus_data.bundle import pack, unpack

        # Somewhere else, once, with a network: parse the codelists and pack
        # them. `fresh_catalog` is a different machine, not this one — packing
        # out of the catalog we are about to fetch through would prove nothing.
        catalog = fresh_catalog
        catalog.execute(
            "INSERT INTO dictionary (system, value_group, field_name, value_raw, value_label, "
            "source, source_ref, confidence) VALUES "
            "('SIHSUS','SEXO','SEXO','1','Masculino','cnv','SEXO.CNV',0.9)"
        )
        catalog.execute(
            "INSERT INTO dictionary (system, value_group, field_name, value_raw, value_label, "
            "source, source_ref, confidence) VALUES "
            "('SIHSUS','SEXO','SEXO','3','Feminino','cnv','SEXO.CNV',0.9)"
        )
        catalog.execute(
            "INSERT INTO field_codelists (system, family_id, field_name, codelist, source, "
            "source_ref, confidence) VALUES ('SIHSUS','','SEXO','SEXO','def','SEXO.DEF',0.9)"
        )
        catalog.execute(
            "INSERT INTO variable_docs (system, field_name, code_system, codelist, source) "
            "VALUES ('SIHSUS','SEXO','internal','SEXO','manual')"
        )
        bundle = pack(catalog, tmp_path / "semantics.pgsb").path

        # Here, with nothing: the codes come back as codes.
        assert set(fetch("SIH-RD", settings=settings).column("SEXO").to_pylist()) == {"1", "3"}

        # The bundle arrives on a memory stick. No network is touched.
        target = Catalog(settings.catalog_path)
        unpack(target, bundle)
        target.close()

        table = fetch("SIH-RD", settings=settings)
        assert set(table.column("SEXO").to_pylist()) == {"Masculino", "Feminino"}

    def test_with_no_codelists_at_all_it_says_so_rather_than_returning_codes_silently(
        self, settings, seeded
    ):
        _, report = fetch("SIH-RD", settings=settings, report=True)
        assert any("nothing can be labelled" in w for w in report.warnings)


class TestMonthOfACompetence:
    def test_a_monthly_file_yields_its_month(self):
        assert _month_of(202301) == 1

    def test_an_annual_file_has_no_month(self):
        """Month 00 treated as January would pull whole years into months=[1]."""
        assert _month_of(202300) is None

    def test_an_unknown_date_has_no_month(self):
        assert _month_of(None) is None


class TestTheReportIsSerialisable:
    def test_it_renders_to_plain_data_for_a_cli_or_a_log(self, settings, seeded):
        import json

        _, report = fetch("SIH-RD", uf="AL", settings=settings, report=True)
        payload = json.loads(json.dumps(report.as_dict()))
        assert payload["system"] == "SIHSUS" and payload["rows"] == 4


class TestArrowOutput:
    def test_the_result_is_an_arrow_table(self, settings, seeded):
        assert isinstance(fetch("SIH-RD", settings=settings), pa.Table)
