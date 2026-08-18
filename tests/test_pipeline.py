"""Catalog behaviour, the blob store, verification checks, and the CLI surface."""

from __future__ import annotations

import io
import zipfile

import pytest
from typer.testing import CliRunner

from pegasus_data.acquire.cache import BlobStore, sha256_bytes
from pegasus_data.catalog.store import Catalog
from pegasus_data.cli import app
from pegasus_data.config import Settings
from pegasus_data.verify import run_all, summarise
from tests.conftest import make_dbf


class TestCatalogStore:
    def test_migrates_and_reports_its_tables(self, catalog: Catalog):
        counts = catalog.table_counts()
        for required in (
            "files", "coverage_gaps", "strata", "families", "representations",
            "dictionary", "field_codelists", "ledger", "open_questions", "lake_partitions",
        ):
            assert required in counts

    def test_first_seen_survives_a_recrawl(self, catalog: Catalog):
        row = {"path": "/x/a.dbc", "directory": "/x", "filename": "a.dbc", "size": 1}
        catalog.upsert_files([row])
        first = catalog.query("SELECT first_seen FROM files")[0]["first_seen"]
        catalog.upsert_files([{**row, "size": 2}])
        after = catalog.query("SELECT first_seen, size FROM files")[0]
        assert after["first_seen"] == first
        assert after["size"] == 2

    def test_a_known_size_is_not_overwritten_by_a_null(self, catalog: Catalog):
        catalog.upsert_files([{"path": "/x/a", "directory": "/x", "filename": "a", "size": 99}])
        catalog.upsert_files([{"path": "/x/a", "directory": "/x", "filename": "a"}])
        assert catalog.query("SELECT size FROM files")[0]["size"] == 99

    def test_gaps_accumulate_attempts_and_can_resolve(self, catalog: Catalog):
        catalog.record_gap("/x/dir", methods=("list", "nlst"), error="550")
        catalog.record_gap("/x/dir", methods=("list",), error="550 again")
        assert catalog.query("SELECT attempts FROM coverage_gaps")[0]["attempts"] == 2
        assert len(catalog.open_gaps()) == 1
        catalog.resolve_gap("/x/dir")
        assert catalog.open_gaps() == []

    def test_open_questions_round_trip(self, catalog: Catalog):
        catalog.note_question("V1", area="discovery", question="does X hold?")
        catalog.resolve_question("V1", resolution="no", evidence='{"probe": 1}')
        row = catalog.query("SELECT * FROM open_questions WHERE key='V1'")[0]
        assert row["status"] == "resolved" and row["resolution"] == "no"


class TestBlobStore:
    def test_identical_bytes_produce_one_blob_and_two_fetches(self, settings: Settings, catalog: Catalog):
        store = BlobStore(settings.blobs_dir, catalog)
        payload = b"some bytes"
        a = store.put_bytes(payload, source_path="/x/a")
        b = store.put_bytes(payload, source_path="/x/a")
        assert a == b == sha256_bytes(payload)
        assert catalog.count("blobs") == 1
        assert catalog.count("fetches") == 2, "the history keeps both fetches"
        assert catalog.query("SELECT fetch_count FROM blobs")[0]["fetch_count"] == 2

    def test_changed_content_creates_a_second_blob_for_the_same_path(
        self, settings: Settings, catalog: Catalog
    ):
        """DATASUS republishes old competências silently; the hash is the signal."""
        store = BlobStore(settings.blobs_dir, catalog)
        store.put_bytes(b"v1", source_path="/x/a")
        store.put_bytes(b"v2", source_path="/x/a")
        assert catalog.count("blobs") == 2
        assert store.known_for("/x/a") == sha256_bytes(b"v2")

    def test_materialize_gives_a_usable_suffix(self, settings: Settings, catalog: Catalog):
        store = BlobStore(settings.blobs_dir, catalog)
        digest = store.put_bytes(b"payload", source_path="/x/a.dbf")
        path = store.materialize(digest, ".dbf", work_dir=settings.work_dir)
        assert path.suffix == ".dbf" and path.read_bytes() == b"payload"


class TestVerify:
    def test_every_check_reports_a_status_on_an_empty_catalog(
        self, catalog: Catalog, settings: Settings
    ):
        checks = run_all(catalog, settings)
        assert len(checks) >= 10
        assert all(c.status in {"pass", "fail", "skip"} for c in checks)
        summary = summarise(checks)
        assert summary["fail"] == 0, "an empty catalog has nothing to fail, only to skip"
        assert summary["ok"] is True

    def test_a_scoped_crawl_skips_the_whole_tree_floor(self, catalog: Catalog, settings: Settings):
        catalog.upsert_files(
            [
                {"path": f"/dissemin/publicos/X/f{i}.dbc", "directory": "/dissemin/publicos/X",
                 "filename": f"f{i}.dbc", "size": 10}
                for i in range(2000)
            ]
        )
        catalog.upsert_directories([{"path": "/dissemin/publicos/X", "file_count": 2000}])
        check = next(c for c in run_all(catalog, settings) if c.step == 2)
        assert check.status == "skip"
        assert check.evidence["whole_tree_crawl"] is False

    def test_checks_carry_evidence(self, catalog: Catalog, settings: Settings):
        for check in run_all(catalog, settings):
            assert isinstance(check.evidence, dict)
            assert check.detail


class TestCli:
    runner = CliRunner()

    def test_help_lists_the_documented_commands(self):
        result = self.runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        for command in ("crawl", "inventory", "sample", "fetch", "profile",
                        "semantics", "normalize", "build", "report", "verify"):
            assert command in result.stdout

    def test_report_runs_against_a_fresh_root(self, tmp_path):
        result = self.runner.invoke(app, ["report", "--root", str(tmp_path / "home"), "--json"])
        assert result.exit_code == 0
        assert "files" in result.stdout

    def test_verify_exits_zero_when_nothing_fails(self, tmp_path):
        result = self.runner.invoke(app, ["verify", "--root", str(tmp_path / "home")])
        assert result.exit_code == 0

    def test_inventory_is_offline_and_idempotent(self, tmp_path):
        root = str(tmp_path / "home")
        first = self.runner.invoke(app, ["inventory", "--root", root])
        second = self.runner.invoke(app, ["inventory", "--root", root])
        assert first.exit_code == 0 and second.exit_code == 0


class TestSemanticsStage:
    def test_kit_ingestion_through_the_pipeline(self, settings: Settings, monkeypatch):
        """A kit already in the blob store is ingested without touching the network."""
        from pegasus_data.pipeline import Pipeline

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("SEXO.CNV", b"2 1\r\n      1  Masculino  1\r\n      2  Feminino   2\r\n")
            z.writestr("RD.DEF", b";t\r\nARD*.DBC\r\nLSexo,SEXO,1,SEXO.CNV\r\n")
            z.writestr("CID10.DBF", make_dbf([("CID10", "C", 4, 0), ("DESCR", "C", 8, 0)], [["A00", "Colera"]]))
        kit = buf.getvalue()
        kit_path = "/dissemin/publicos/SIHSUS/200801_/Auxiliar/TAB_SIH.zip"

        pipeline = Pipeline(settings)
        try:
            pipeline.catalog.upsert_files(
                [{"path": kit_path, "directory": kit_path.rsplit("/", 1)[0],
                  "filename": "TAB_SIH.zip", "extension": ".zip", "size": len(kit)}]
            )
            digest = pipeline.blobs.put_bytes(kit, source_path=kit_path)
            monkeypatch.setattr(pipeline.fetcher, "ensure", lambda paths: {
                p: digest for p in paths if p == kit_path
            })
            result = pipeline.semantics()
            assert result.counts["kits_ingested"] == 1
            assert result.counts["dictionary_entries"] >= 3

            from pegasus_data.semantics.dictionary import lookup

            assert lookup(pipeline.catalog, system="SIHSUS", field_name="SEXO")["1"] == "Masculino"
            # And the [V] it closes is recorded as resolved, with evidence.
            row = pipeline.catalog.query(
                "SELECT status, resolution FROM open_questions WHERE key='V3.cnv_def_grammar'"
            )[0]
            assert row["status"] == "resolved" and "LAST match wins" in row["resolution"]
        finally:
            pipeline.close()


@pytest.mark.network
class TestLive:
    def test_the_server_still_speaks_the_msdos_dialect(self):
        """Guards the D4 fix against a server-side change."""
        from pegasus_data.discovery.ftp_client import FtpClient

        with FtpClient("ftp.datasus.gov.br", timeout=60) as client:
            entries, method = client.list_directory("/dissemin/publicos/PNI/AUXILIARES")
        assert method == "list"
        assert entries and all(e.size is not None for e in entries if e.is_dir is False)
        assert any(e.modified for e in entries)
