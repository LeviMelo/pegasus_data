"""Surviving a reorganised FTP tree: identity, gone-ness, and moves."""

from __future__ import annotations

import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.discovery.reconcile import (
    FileState,
    classify,
    detect_moves,
    mark_gone,
    snapshot,
)
from pegasus_data.inventory.naming import logical_identity, parse_filename
from pegasus_data.inventory.systems import (
    learn_prefix_systems,
    load_prefix_systems,
    persist_prefix_systems,
    resolve_system,
)


def _file(catalog: Catalog, path: str, *, size=100, modified="2024-01-01T00:00:00+00:00"):
    catalog.upsert_files(
        [
            {
                "path": path,
                "directory": path.rsplit("/", 1)[0],
                "filename": path.rsplit("/", 1)[-1],
                "size": size,
                "modified": modified,
            }
        ]
    )


class TestLogicalIdentity:
    def test_identity_comes_from_the_name_not_the_path(self):
        parsed = parse_filename("RDAL2401.dbc")
        a = logical_identity(parsed, system="SIHSUS", path="/dissemin/publicos/SIHSUS/200801_/Dados/RDAL2401.dbc")
        b = logical_identity(parsed, system="SIHSUS", path="/dissemin/publicos/SIHSUS/NOVO/RDAL2401.dbc")
        assert a == b == "SIHSUS|RD|AL|2401"

    def test_an_unparsed_name_still_gets_a_location_independent_identity(self):
        parsed = parse_filename("base_aih1.duck")
        a = logical_identity(parsed, system="SIHSUS", path="/x/a/base_aih1.duck")
        b = logical_identity(parsed, system="SIHSUS", path="/x/b/base_aih1.duck")
        assert a == b
        assert "/x/" not in a

    def test_different_competencias_are_different_identities(self):
        one = logical_identity(parse_filename("RDAL2401.dbc"), system="SIHSUS")
        two = logical_identity(parse_filename("RDAL2402.dbc"), system="SIHSUS")
        assert one != two


class TestPrefixSystems:
    def test_learns_the_majority_and_reports_agreement(self):
        learned = learn_prefix_systems(
            [("RD", "SIHSUS")] * 99 + [("RD", "TABWIN")] + [("DO", "SIM")] * 20
        )
        by_prefix = {p.series_prefix: p for p in learned}
        assert by_prefix["RD"].system == "SIHSUS"
        assert by_prefix["RD"].agreement == pytest.approx(0.99)
        assert by_prefix["RD"].trustworthy
        assert by_prefix["DO"].system == "SIM"

    def test_an_ambiguous_prefix_is_not_trusted(self):
        learned = learn_prefix_systems([("XX", "A")] * 10 + [("XX", "B")] * 10)
        assert not learned[0].trustworthy

    def test_the_name_wins_over_the_path_once_the_prefix_is_known(self, catalog: Catalog):
        persist_prefix_systems(catalog, learn_prefix_systems([("RD", "SIHSUS")] * 500))
        learned = load_prefix_systems(catalog)
        # DATASUS reorganises and RD files turn up under a new tree.
        resolved, disagreement = resolve_system(
            series_prefix="RD", system_by_path="SIHSUS_NOVO", learned=learned
        )
        assert resolved == "SIHSUS", "identity must survive the move"
        assert disagreement == "SIHSUS_NOVO", "and the disagreement is a finding"

    def test_an_untrusted_prefix_leaves_the_path_authoritative(self, catalog: Catalog):
        persist_prefix_systems(catalog, learn_prefix_systems([("ZZ", "A"), ("ZZ", "B")]))
        resolved, disagreement = resolve_system(
            series_prefix="ZZ", system_by_path="SIHSUS", learned=load_prefix_systems(catalog)
        )
        assert resolved == "SIHSUS" and disagreement is None

    def test_an_established_mapping_is_held_against_a_reorganisation(self, catalog: Catalog):
        """The property the whole design rests on.

        If the map were relearned each crawl, a wholesale move would teach it the
        new answer and identity would travel with the files — re-deriving every
        stratum and family under fresh ids, silently.
        """
        persist_prefix_systems(catalog, learn_prefix_systems([("RD", "SIHSUS")] * 12000))
        # The entire tree moves: every RD file is now under a new system segment.
        stats = persist_prefix_systems(catalog, learn_prefix_systems([("RD", "SIH_NOVO")] * 12000))
        assert load_prefix_systems(catalog)["RD"].system == "SIHSUS"
        assert stats["contradictions"] == 1
        assert catalog.count("open_questions", "key LIKE 'inventory.prefix_system_changed:%'") == 1

    def test_agreeing_evidence_refreshes_the_counts(self, catalog: Catalog):
        persist_prefix_systems(catalog, learn_prefix_systems([("RD", "SIHSUS")] * 10))
        persist_prefix_systems(catalog, learn_prefix_systems([("RD", "SIHSUS")] * 500))
        assert load_prefix_systems(catalog)["RD"].file_count == 500


class TestClassify:
    def test_new_and_unchanged(self):
        assert classify(None, 10, "t") == "new"
        before = FileState("/x/a", 10, "t", None)
        assert classify(before, 10, "t") == "unchanged"

    def test_size_or_mtime_change_is_a_change(self):
        before = FileState("/x/a", 10, "t", None)
        assert classify(before, 11, "t") == "changed"
        assert classify(before, 10, "u") == "changed"

    def test_no_change_signal_is_unresolved_not_unchanged(self):
        """NLST gives neither size nor mtime; claiming 'unchanged' would be a guess."""
        before = FileState("/x/a", None, None, None)
        assert classify(before, None, None) == "unresolved"


class TestGoneAt:
    def test_a_successful_listing_that_omits_a_file_marks_it_gone(self, catalog: Catalog):
        _file(catalog, "/d/a.dbc")
        _file(catalog, "/d/b.dbc")
        vanished = mark_gone(catalog, "/d", {"/d/a.dbc"})
        assert vanished == ["/d/b.dbc"]
        rows = {r["path"]: r["gone_at"] for r in catalog.query("SELECT path, gone_at FROM files")}
        assert rows["/d/a.dbc"] is None
        assert rows["/d/b.dbc"] is not None

    def test_seeing_a_file_again_clears_the_gone_mark(self, catalog: Catalog):
        _file(catalog, "/d/a.dbc")
        mark_gone(catalog, "/d", set())
        assert catalog.query("SELECT gone_at FROM files")[0]["gone_at"] is not None
        _file(catalog, "/d/a.dbc")
        assert catalog.query("SELECT gone_at FROM files")[0]["gone_at"] is None

    def test_a_gone_file_leaves_the_snapshot(self, catalog: Catalog):
        _file(catalog, "/d/a.dbc")
        mark_gone(catalog, "/d", set())
        assert snapshot(catalog) == {}


class TestMoveDetection:
    def test_same_fingerprint_in_a_new_directory_is_a_move(self, catalog: Catalog):
        _file(catalog, "/old/RDAL2401.dbc", size=500, modified="2024-02-01T00:00:00+00:00")
        _file(catalog, "/new/RDAL2401.dbc", size=500, modified="2024-02-01T00:00:00+00:00")
        gone = mark_gone(catalog, "/old", set())
        moves = detect_moves(catalog, gone, "run1")
        assert moves == [("/old/RDAL2401.dbc", "/new/RDAL2401.dbc", "filename+size+mtime")]
        assert catalog.count("file_moves") == 1

    def test_a_genuine_deletion_is_not_reported_as_a_move(self, catalog: Catalog):
        _file(catalog, "/old/RDAL2401.dbc")
        gone = mark_gone(catalog, "/old", set())
        assert detect_moves(catalog, gone, "run1") == []

    def test_an_ambiguous_match_is_left_unrecorded(self, catalog: Catalog):
        """Two identical candidates mean the fingerprint does not identify it."""
        _file(catalog, "/old/X.dbc", size=10, modified="t")
        _file(catalog, "/a/X.dbc", size=10, modified="t")
        _file(catalog, "/b/X.dbc", size=10, modified="t")
        gone = mark_gone(catalog, "/old", set())
        assert detect_moves(catalog, gone, "run1") == []
        assert catalog.count("file_moves") == 0

    def test_a_different_size_is_not_a_move(self, catalog: Catalog):
        _file(catalog, "/old/X.dbc", size=10, modified="t")
        _file(catalog, "/new/X.dbc", size=999, modified="t")
        gone = mark_gone(catalog, "/old", set())
        assert detect_moves(catalog, gone, "run1") == []


class TestFailedListingSafety:
    def test_nothing_marks_files_gone_without_a_successful_listing(self, catalog: Catalog):
        """The safety property: one dropped connection must not read as deletion.

        `mark_gone` is only ever reached from the success path in the crawler; a
        directory whose listing raised goes to the retry queue and then to
        `coverage_gaps`, which touches no file rows at all.
        """
        _file(catalog, "/d/a.dbc")
        catalog.record_gap("/d", methods=("list", "nlst"), error="550")
        still_here = catalog.query("SELECT gone_at FROM files WHERE path = '/d/a.dbc'")[0]
        assert still_here["gone_at"] is None
        assert catalog.count("coverage_gaps", "resolved = 0") == 1


class TestSurvivingAReorganisation:
    """The end-to-end property: a moved tree keeps its lineage.

    DATASUS reorganises. Before this, a directory rename re-derived every
    `stratum_id` and `family_id` beneath it — because both are hashes of
    `(system, series, year)` and `system` was read out of the path — so thirty-five
    years of continuity would restart under fresh identifiers with no error raised
    anywhere. This test is the guard on that.
    """

    OLD = "/dissemin/publicos/SIHSUS/200801_/Dados"
    NEW = "/dissemin/publicos/SIH_NOVO/Dados"
    NAMES = [f"RDAC24{m:02d}.dbc" for m in range(1, 13)]

    def _crawl(self, catalog: Catalog, directory: str) -> None:
        catalog.upsert_files(
            [
                {
                    "path": f"{directory}/{n}", "directory": directory, "filename": n,
                    "extension": ".dbc", "size": 500 + i,
                    "modified": "2024-03-01T00:00:00+00:00",
                }
                for i, n in enumerate(self.NAMES)
            ]
        )
        catalog.upsert_directories([{"path": directory, "file_count": len(self.NAMES)}])

    def test_identity_strata_and_lineage_all_survive(self, catalog: Catalog):
        from pegasus_data.inventory.build import build_inventory

        self._crawl(catalog, self.OLD)
        build_inventory(catalog)
        before = catalog.query("SELECT system, logical_id FROM file_facts LIMIT 1")[0]
        strata_before = {r["stratum_id"] for r in catalog.query("SELECT stratum_id FROM strata")}

        # The tree is reorganised: same files, new location, new system segment.
        self._crawl(catalog, self.NEW)
        gone = mark_gone(catalog, self.OLD, set())
        moves = detect_moves(catalog, gone, "run2")
        build_inventory(catalog)

        after = catalog.query(
            "SELECT system, logical_id FROM file_facts WHERE path LIKE ? LIMIT 1", (f"{self.NEW}%",)
        )[0]
        strata_after = {
            r["stratum_id"] for r in catalog.query("SELECT DISTINCT stratum_id FROM stratum_members")
        }

        assert len(moves) == 12, "every file should be recognised as moved, not deleted"
        assert after["logical_id"] == before["logical_id"], "identity must not follow the path"
        assert after["system"] == before["system"] == "SIHSUS"
        assert strata_after == strata_before, "stratum ids must survive the move"
        # And the disagreement between name and path is on record, not swallowed.
        assert catalog.count("system_disagreements") == 12
        assert catalog.count("files", "gone_at IS NOT NULL") == 12

    def test_a_gone_file_does_not_drive_inference(self, catalog: Catalog):
        """Old and new paths coexist after a move; counting both breaks the map.

        With both present every prefix looks evenly split between two systems,
        which is exactly the evidence that stops it being trusted — at the moment
        its stability matters most.
        """
        from pegasus_data.inventory.build import build_inventory

        self._crawl(catalog, self.OLD)
        build_inventory(catalog)
        self._crawl(catalog, self.NEW)
        mark_gone(catalog, self.OLD, set())
        build_inventory(catalog)
        assert load_prefix_systems(catalog)["RD"].trustworthy
        assert catalog.count("file_facts", "path LIKE ?", (f"{self.OLD}%",)) == 12, (
            "history is kept; it simply stops voting"
        )
