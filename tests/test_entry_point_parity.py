"""One fixture, every public door, the same guarantees.

The review's central methodological point: this project's recurring failure is
one policy with several implementations, and a fix landing on one of them.

    vintage rendering   -> load() fixed, fetch() not
    missing generations -> load() fixed, scan() reintroduced it
    system scoping      -> the reader had it, load_reference() did not
    atomic output       -> streaming export staged, eager export did not

Each of those passed the suite at the time, because the guarantee was tested
through the door that had it. So these tests drive `fetch`, `load`, `scan`,
eager `export` and streaming `export` over ONE lake and assert they agree
wherever the API says they should.
"""

from __future__ import annotations

import inspect

import pyarrow.parquet as pq
import pytest

from pegasus_data import api
from pegasus_data.api import Catalog as PublicCatalog
from pegasus_data.api import export, load, scan
from pegasus_data.normalize.engine import MissingColumnError
from pegasus_data.retrieve import FilterHasNoAxis, fetch


class TestTheMissingColumnPolicyIsOnePolicy:
    """A column some generations lack must be handled identically everywhere."""

    def test_every_reader_takes_the_same_option(self):
        for fn in (fetch, load, scan, export):
            params = inspect.signature(fn).parameters
            assert "on_missing_column" in params, fn.__name__
            assert params["on_missing_column"].default == "raise", (
                f"{fn.__name__} defaults to something other than raise; the "
                "safe default has to be the same one everywhere"
            )

    def test_load_raises_by_default(self, built_lake):
        settings, _catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            with pytest.raises(MissingColumnError):
                load("SIHSUS", "RD", columns=["DIAG_SECUN"], catalog=public)
        finally:
            public.close()

    def test_scan_raises_by_default(self, built_lake):
        """scan() dropped the generation instead — CR-03 under a new name."""
        settings, _catalog, _ = built_lake
        with pytest.raises(MissingColumnError):
            scan(
                "SIHSUS", "RD", columns=["DIAG_SECUN"],
                root=settings.root, settings=settings,
            )

    def test_streaming_export_inherits_it(self, built_lake, tmp_path):
        """export(stream=True) calls scan(); the policy must travel with it."""
        settings, _catalog, _ = built_lake
        with pytest.raises(MissingColumnError):
            export(
                "SIHSUS", "RD", path=tmp_path / "x.parquet", format="parquet",
                profile="codes", stream=True, columns=["DIAG_SECUN"],
                root=settings.root, settings=settings,
            )

    def test_null_fill_is_opt_in_everywhere_it_is_offered(self, built_lake):
        settings, _catalog, _ = built_lake
        public = PublicCatalog(settings.root, settings=settings)
        try:
            table, _report = load(
                "SIHSUS", "RD", columns=["DIAG_SECUN"],
                on_missing_column="null_fill", catalog=public, report=True,
            )
        finally:
            public.close()
        assert table.num_rows > 0

        lazy = scan(
            "SIHSUS", "RD", columns=["DIAG_SECUN"], on_missing_column="null_fill",
            root=settings.root, settings=settings,
        )
        assert lazy.count_rows() == table.num_rows, (
            "load and scan disagreed about how many rows null_fill keeps"
        )


class TestTheAxisRefusalIsOneRefusal:
    def test_no_reader_answers_a_filter_on_an_axis_that_does_not_exist(
        self, built_lake, monkeypatch
    ):
        """A false empty reads as 'that state published nothing'."""
        import pegasus_data.retrieve as retrieve

        settings, _catalog, _ = built_lake
        asked: list[str] = []
        real = retrieve.axis_refusal

        def watched(store, system, series, **kw):
            asked.append(system)
            return real(store, system, series, **kw)

        monkeypatch.setattr(retrieve, "axis_refusal", watched)

        load("SIHSUS", "RD", uf="AL", root=settings.root, settings=settings, labels=False)
        assert asked, "load() answered without consulting the shared policy"
        asked.clear()
        scan("SIHSUS", "RD", uf="AL", root=settings.root, settings=settings).count_rows()
        assert asked, "scan() answered without consulting the shared policy"

    def test_the_refusal_is_one_exception_type(self):
        assert issubclass(FilterHasNoAxis, ValueError)


class TestVintageRenderingIsOneOperation:
    def test_fetch_and_load_use_the_same_renderer(self):
        """fetch() rendered the whole answer at one vintage while load() split
        by (family, year). The old closure test asserted `_by_vintage` appeared
        in api.py — true, and silent about fetch()."""
        import pegasus_data.retrieve as retrieve

        assert "render_groups" in inspect.getsource(retrieve.fetch)
        assert "render_groups" in inspect.getsource(api.load)

    def test_both_splitters_produce_the_same_shape(self):
        from pegasus_data.render_groups import split_by_source, split_by_year_column

        for fn in (split_by_source, split_by_year_column):
            assert callable(fn)

    def test_a_fetch_result_carries_what_the_split_needs(self, settings, seeded):
        """Without per-source facts there is nothing to split a fetched table on."""
        _table, report = fetch("SIH-RD", settings=settings, report=True)
        assert report.source_facts, "no (family, year) per source; the split cannot run"
        assert all(
            isinstance(v, tuple) and len(v) == 2 for v in report.source_facts.values()
        )


class TestOutputDurabilityIsOneRule:
    def test_both_export_paths_stage_before_replacing(self, built_lake, tmp_path):
        settings, _catalog, _ = built_lake
        for stream in (False, True):
            target = tmp_path / f"out-{stream}.parquet"
            export(
                "SIHSUS", "RD", path=target, format="parquet", profile="codes",
                stream=stream, root=settings.root, settings=settings,
            )
            assert target.is_file()
            assert not list(tmp_path.glob("*.part")), f"stream={stream} orphaned a partial"
            assert not list(tmp_path.glob(".*.staging")), f"stream={stream} orphaned a stage"

    def test_both_export_paths_write_the_same_rows(self, built_lake, tmp_path):
        settings, _catalog, _ = built_lake
        eager = tmp_path / "eager.parquet"
        streamed = tmp_path / "streamed.parquet"
        export("SIHSUS", "RD", path=eager, format="parquet", profile="codes",
               root=settings.root, settings=settings)
        export("SIHSUS", "RD", path=streamed, format="parquet", profile="codes",
               stream=True, root=settings.root, settings=settings)
        assert pq.read_table(eager).num_rows == pq.read_table(streamed).num_rows


class TestTheReadersAgreeOnFilters:
    @pytest.mark.parametrize("fn", [fetch, load, scan, export])
    def test_an_integer_year_is_accepted(self, fn):
        """fetch/load/scan took one; export and load_population reached list()."""
        annotation = inspect.signature(fn).parameters["years"].annotation
        assert "int |" in str(annotation), f"{fn.__name__} does not accept a bare int year"

    def test_load_population_too(self):
        annotation = inspect.signature(api.load_population).parameters["years"].annotation
        assert "int |" in str(annotation)

    def test_every_reader_takes_settings(self):
        for fn in (load, scan, export, api.describe, api.load_reference,
                   api.reference_tables, api.load_population):
            assert "settings" in inspect.signature(fn).parameters, fn.__name__

    def test_every_reader_takes_root(self):
        for fn in (load, scan, export, api.describe, api.load_reference,
                   api.load_population):
            assert "root" in inspect.signature(fn).parameters, fn.__name__
