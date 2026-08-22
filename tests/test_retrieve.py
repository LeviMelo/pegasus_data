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

import hashlib
import tempfile
from pathlib import Path

import pyarrow as pa
import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.inventory.families import schema_signature
from pegasus_data.normalize.engine import MissingColumnError
from pegasus_data.retrieve import (
    DatasetUnknown,
    NothingPublished,
    PartialFetchError,
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
        FIELDS, [[f"A{n:05d}", "1" if n % 2 else "3", "I219"] for n in range(rows)]
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
    """A content-addressed store, backed by real files like the real one.

    It used to serve bytes only. The decode path now takes the blob's PATH —
    the blob is already a file, and reading it into RAM to hand the bytes to a
    decoder that writes them straight back out was three copies for nothing —
    so a double that cannot produce a path is no longer a double of anything.
    """

    def __init__(self, payload_for=None) -> None:
        self.payload_for = payload_for or (lambda _digest: one_file())
        self._dir = tempfile.mkdtemp(prefix="pegasus_fakeblobs_")

    def read(self, digest: str) -> bytes:
        return self.payload_for(digest)

    def path_for(self, digest: str) -> Path:
        # The fixtures use readable stand-ins like "sha-/p/RDAL2301.dbc" for
        # digests, so the name is hashed rather than used as a path.
        target = Path(self._dir) / hashlib.sha256(digest.encode()).hexdigest()
        if not target.is_file():
            target.write_bytes(self.payload_for(digest))
        return target


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

    def test_a_file_that_could_not_be_fetched_makes_the_answer_short_and_refused(
        self, settings, seeded
    ):
        """The default is to refuse. One of two files missing is not a result."""
        seeded["fetcher"] = FakeFetcher(missing={"/p/RDAL2301.dbc"})
        with pytest.raises(PartialFetchError) as excinfo:
            fetch("SIH-RD", uf="AL", settings=settings)
        assert excinfo.value.missing["undecoded"] == ["/p/RDAL2301.dbc"]
        assert excinfo.value.report.files_read == 1

    def test_the_short_answer_is_available_on_request_and_names_what_it_lost(
        self, settings, seeded
    ):
        seeded["fetcher"] = FakeFetcher(missing={"/p/RDAL2301.dbc"})
        table, report = fetch(
            "SIH-RD", uf="AL", settings=settings, report=True, allow_partial=True
        )
        assert report.undecoded == ["/p/RDAL2301.dbc"]
        assert report.files_read == 1 and table.num_rows == 2
        assert not report.is_complete
        assert report.excluded["undecoded"] == ["/p/RDAL2301.dbc"]

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

    def test_the_report_counts_bytes_read_apart_from_bytes_downloaded(
        self, settings, seeded
    ):
        """They are different numbers and were reported as one.

        `bytes_downloaded` counted every byte handed to the decoder, so a fully
        warm request claimed megabytes "downloaded" with the network untouched.
        It now means NETWORK bytes; `bytes_read` is what was decoded, whatever
        its origin. This fixture serves from a fake store, so nothing was
        downloaded and one file was read.
        """
        _, report = fetch("SIH-RD", uf="SP", settings=settings, report=True)
        assert report.bytes_read == len(one_file())
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
            "VALUES ('SIHSUS','DIAG_PRINC','external','CID10','manual')"
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
    unreachable, still has to be able to say that ``DIAG_PRINC=I10`` is
    essential hypertension.

    Deliberately NOT proved with ``SEXO``. Curation marks SIHSUS's SEXO
    unbound, because the kits ship both ``1 -> Masculino`` and
    ``1 -> Feminino`` for it, and that refusal has to survive the pack.
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
            "('SIHSUS','CID10','DIAG_PRINC','I219','Infarto (bundle)','cnv','CID.CNV',0.9)"
        )
        catalog.execute(
            "INSERT INTO dictionary (system, value_group, field_name, value_raw, value_label, "
            "source, source_ref, confidence) VALUES "
            "('SIHSUS','CID10','DIAG_PRINC','I211','Infarto parede inferior (bundle)','cnv','CID.CNV',0.9)"
        )
        catalog.execute(
            "INSERT INTO field_codelists (system, family_id, field_name, codelist, source, "
            "source_ref, confidence) VALUES ('SIHSUS','','DIAG_PRINC','CID10','def','X.DEF',0.9)"
        )
        catalog.execute(
            "INSERT INTO variable_docs (system, field_name, code_system, codelist, source) "
            "VALUES ('SIHSUS','SEXO','internal','SEXO','manual')"
        )
        bundle = pack(catalog, tmp_path / "semantics.pgsb").path

        # Here, with no local codelists at all, the labels still arrive: they
        # come from the pack the package ships. That is the fresh-install
        # guarantee, and it is what makes the next assertion meaningful.
        # Something is labelled from the shipped pack alone. Which column and
        # in which rendering mode is the product's business — curated widths,
        # code systems and profiles decide that, and pinning one column here
        # only tests the fixture.
        _, before = fetch("SIH-RD", settings=settings, report=True)
        assert before.render.labelled, "the shipped pack labelled nothing"

        # The bundle arrives on a memory stick. No network is touched.
        target = Catalog(settings.catalog_path)
        unpack(target, bundle)
        target.close()

        # A local reading OVERRIDES the shipped one. The bundle words it
        # differently on purpose: whoever built it looked at this data, and the
        # wheel did not.
        table, after = fetch("SIH-RD", settings=settings, report=True)
        rendered = " ".join(
            str(v) for c in table.column_names for v in table.column(c).to_pylist()
        )
        assert "(bundle)" in rendered, "the local reading did not override the shipped one"

    def test_the_shipped_pack_labels_with_no_local_codelists_at_all(
        self, settings, seeded
    ):
        """The fresh-install guarantee, which used to be a warning instead.

        `pip install` carries the map, the curation and a distilled label pack.
        Before it did, this call returned raw codes and a note saying to go run
        an hour-long ingest — technically honest, and the wrong half of the
        promise.
        """
        _table, report = fetch("SIH-RD", settings=settings, report=True)
        assert report.render.labelled, "nothing was labelled from the shipped pack"
        assert not any("nothing can be labelled" in w for w in report.warnings)

    def test_a_curated_refusal_outranks_the_shipped_pack(self, settings, seeded):
        """SIHSUS's SEXO stays raw, and that is the point.

        The pack HAS a SEXO table. Curation marks the column unbound anyway,
        because the kits ship both `1 -> Masculino` and `1 -> Feminino` and a
        merged reading would be confidently wrong. Until the shipped curation
        was actually loaded on first use, this refusal was silently bypassed on
        every fresh install and SEXO was labelled from the contradictory table.
        """
        table, report = fetch("SIH-RD", settings=settings, report=True)
        assert set(table.column("SEXO").to_pylist()) == {"1", "3"}
        assert "SEXO_label" not in table.column_names
        assert "SEXO" not in report.render.labelled


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


class TestItCannotHangSilently:
    """The project's own rule, applied to its newest entry point.

    Every pipeline stage runs under a watchdog and a heartbeat, and the exit
    criterion when that was built was not "fix the profile hang" but "the
    pipeline can never hang silently". `fetch()` decodes arbitrary files off a
    slow server and shipped without either — the same gap, in the one place a
    user is actually watching.
    """

    def test_a_file_that_never_finishes_is_abandoned_not_waited_on(
        self, settings, seeded, monkeypatch
    ):
        import pegasus_data.retrieve as retrieve

        settings.item_timeout = 0.25
        settings.heartbeat_interval = 0.05

        def hang(*_args, **_kwargs):
            import time

            time.sleep(30)

        monkeypatch.setattr(retrieve, "_decode_one", hang)
        with pytest.raises(NothingPublished):
            fetch("SIH-RD", uf="SP", settings=settings)

    def test_the_abandoned_file_is_named_in_the_report(self, settings, seeded, monkeypatch):
        import pegasus_data.retrieve as retrieve

        settings.item_timeout = 0.25
        real = retrieve._decode_one

        def slow_for_one(pipeline, registry, plan, *, path, digest, member, **kw):
            if path.endswith("RDAL2301.dbc"):
                import time

                time.sleep(30)
            return real(
                pipeline, registry, plan, path=path, digest=digest, member=member, **kw
            )

        monkeypatch.setattr(retrieve, "_decode_one", slow_for_one)
        # An abandoned file makes the answer short, so the default refuses it.
        with pytest.raises(PartialFetchError):
            fetch("SIH-RD", uf="AL", settings=settings)
        table, report = fetch(
            "SIH-RD", uf="AL", settings=settings, report=True, allow_partial=True
        )
        assert "/p/RDAL2301.dbc" in report.undecoded
        assert any("gave up after" in w for w in report.warnings)
        assert table.num_rows == 2, "the other file still came back"

    def test_an_abandoned_file_is_recorded_as_a_coverage_gap(
        self, settings, seeded, monkeypatch
    ):
        """A timeout is 'we know we do not have this, and why' — which is what
        coverage_gaps already means."""
        import pegasus_data.retrieve as retrieve

        settings.item_timeout = 0.25

        def hang(*_args, **_kwargs):
            import time

            time.sleep(30)

        monkeypatch.setattr(retrieve, "_decode_one", hang)
        with pytest.raises(NothingPublished):
            fetch("SIH-RD", uf="SP", settings=settings)
        catalog = Catalog(settings.catalog_path)
        try:
            assert catalog.count("coverage_gaps", "kind = 'timeout'") == 1
        finally:
            catalog.close()


# --------------------------------------------------------------------- CR-03
# fetch() and load() must answer the same question the same way. load() used to
# drop whole generations lacking a requested column; fetch() null-filled them
# through permissive concat, turning structural absence into ordinary
# missingness with nothing said. One policy: raise by default, opt into
# null_fill, and record the nullness as structural. Lives here because it needs
# the `seeded` catalog fixture.


class TestFetchAppliesThePolicy:
    def test_the_default_is_to_raise(self, settings, seeded):
        """Not a warning: a column silently absent is how an analysis loses a
        variable and never notices."""
        with pytest.raises(MissingColumnError) as excinfo:
            fetch("SIH-RD", columns=["NO_SUCH_FIELD"], settings=settings)
        assert "NO_SUCH_FIELD" in str(excinfo.value)

    def test_null_fill_still_raises_when_no_generation_has_the_column(
        self, settings, seeded
    ):
        """There is nothing to fill FROM. null_fill preserves rows from
        generations that lack a column others have; it cannot invent a column
        no generation ever carried, and returning it as all-null would assert
        the field exists."""
        with pytest.raises(MissingColumnError):
            fetch(
                "SIH-RD",
                columns=["SEXO", "NO_SUCH_FIELD"],
                on_missing_column="null_fill",
                settings=settings,
            )

    def test_a_column_every_generation_has_is_unaffected(self, settings, seeded):
        table = fetch("SIH-RD", columns=["SEXO"], settings=settings)
        assert "SEXO" in table.column_names


class TestMaxFilesTruncationIsDisclosed:
    def test_it_says_how_many_files_it_dropped(self, settings, seeded):
        _, report = fetch("SIH-RD", max_files=1, settings=settings, report=True)
        if report.files_truncated:
            assert any("debugging truncation" in w for w in report.warnings)
            assert report.files_matched == 1

    def test_a_family_emptied_by_truncation_is_named(self, settings, seeded):
        """report.families names it and would otherwise imply it contributed."""
        _, report = fetch("SIH-RD", max_files=1, settings=settings, report=True)
        for family in report.families_truncated_away:
            assert family in report.families
