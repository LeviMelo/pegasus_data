"""One durability model for every derived artifact.

The lake and the reference warehouse are both rebuildable from the catalog and
the blob store, and both had independently worked out how not to destroy the old
copy before the new one existed. Two implementations of one rule is how they
drift, so the rule lives in one place now — and the failure paths, which are the
entire reason it exists, are asserted here rather than assumed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pegasus_data.persist.staging import staged_file, staged_tree


class TestStagedFile:
    def test_the_target_appears_only_when_the_write_finishes(self, tmp_path):
        target = tmp_path / "part-00000.parquet"
        with staged_file(target) as staged:
            staged.write_bytes(b"partial")
            assert not target.exists(), "nothing partial is visible at the target"
        assert target.read_bytes() == b"partial"

    def test_the_staging_name_cannot_be_picked_up_by_a_reader(self, tmp_path):
        """A half-written .parquet in a Hive partition is a file ds.dataset()
        will happily try to read."""
        target = tmp_path / "part-00000.parquet"
        with staged_file(target) as staged:
            staged.write_bytes(b"x")
            assert not staged.name.endswith(".parquet")
            assert list(tmp_path.glob("*.parquet")) == []

    def test_a_failed_write_leaves_the_old_artifact_intact(self, tmp_path):
        target = tmp_path / "part-00000.parquet"
        target.write_bytes(b"the good one")
        with pytest.raises(RuntimeError), staged_file(target) as staged:
            staged.write_bytes(b"the bad one")
            raise RuntimeError("writer died")
        assert target.read_bytes() == b"the good one"

    def test_a_failed_write_leaves_no_debris(self, tmp_path):
        target = tmp_path / "part-00000.parquet"
        with pytest.raises(RuntimeError), staged_file(target) as staged:
            staged.write_bytes(b"junk")
            raise RuntimeError("writer died")
        assert list(tmp_path.iterdir()) == [], "the next run must not trip over it"

    def test_an_empty_write_is_refused_rather_than_swapped_in(self, tmp_path):
        """A zero-byte file replacing a good partition reads as an empty
        dataset rather than as a failure, which is worse than not writing."""
        target = tmp_path / "part-00000.parquet"
        target.write_bytes(b"the good one")
        with pytest.raises(OSError, match="empty"), staged_file(target) as staged:
            staged.write_bytes(b"")
        assert target.read_bytes() == b"the good one"

    def test_a_stale_staging_file_does_not_block_the_next_write(self, tmp_path):
        target = tmp_path / "part-00000.parquet"
        (tmp_path / f".{target.name}.staging").write_bytes(b"left by a killed run")
        with staged_file(target) as staged:
            staged.write_bytes(b"fresh")
        assert target.read_bytes() == b"fresh"


class TestStagedTree:
    def _tree(self, root, names):
        for name in names:
            (root / name).mkdir(parents=True, exist_ok=True)
            (root / name / "part-0.parquet").write_bytes(name.encode())

    def test_the_old_tree_stays_readable_until_the_swap(self, tmp_path):
        root = tmp_path / "reference"
        self._tree(root, ["CID10", "SEXO"])
        with staged_tree(root) as staging:
            self._tree(staging, ["CID10"])
            assert (root / "SEXO").exists(), "the old tree is complete until the swap"
        assert sorted(p.name for p in root.iterdir()) == ["CID10"]

    def test_a_failed_rebuild_leaves_the_old_tree_whole(self, tmp_path):
        root = tmp_path / "reference"
        self._tree(root, ["CID10", "SEXO"])
        with pytest.raises(RuntimeError), staged_tree(root) as staging:
            self._tree(staging, ["CID10"])
            raise RuntimeError("rebuild died")
        assert sorted(p.name for p in root.iterdir()) == ["CID10", "SEXO"]

    def test_a_failed_rebuild_leaves_no_staging_directory(self, tmp_path):
        root = tmp_path / "reference"
        self._tree(root, ["CID10"])
        with pytest.raises(RuntimeError), staged_tree(root) as staging:
            self._tree(staging, ["CID10"])
            raise RuntimeError("rebuild died")
        assert [p.name for p in tmp_path.iterdir()] == ["reference"]

    def test_a_scoped_rebuild_does_not_delete_what_it_was_not_asked_about(
        self, tmp_path
    ):
        """Swapping here would silently drop every table outside the scope."""
        root = tmp_path / "reference"
        self._tree(root, ["CID10", "SEXO", "MUNIC"])
        with staged_tree(root, merge=True) as staging:
            self._tree(staging, ["SEXO"])
        assert sorted(p.name for p in root.iterdir()) == ["CID10", "MUNIC", "SEXO"]

    def test_a_scoped_rebuild_still_replaces_what_it_did_produce(self, tmp_path):
        root = tmp_path / "reference"
        self._tree(root, ["SEXO"])
        (root / "SEXO" / "stale.parquet").write_bytes(b"stale")
        with staged_tree(root, merge=True) as staging:
            self._tree(staging, ["SEXO"])
        assert sorted(p.name for p in (root / "SEXO").iterdir()) == ["part-0.parquet"]

    def test_it_works_when_there_is_nothing_to_replace(self, tmp_path):
        root = tmp_path / "reference"
        with staged_tree(root) as staging:
            self._tree(staging, ["CID10"])
        assert (root / "CID10" / "part-0.parquet").exists()

    def test_a_stale_staging_tree_does_not_block_the_next_rebuild(self, tmp_path):
        """Transaction names are unique, so a leftover cannot be in the way."""
        root = tmp_path / "reference"
        stale = tmp_path / "reference.__staging__.dead-1234"
        self._tree(stale, ["LEFTOVER"])
        with staged_tree(root) as staging:
            self._tree(staging, ["CID10"])
        assert sorted(p.name for p in root.iterdir()) == ["CID10"]

    def test_a_stale_staging_tree_can_be_reclaimed(self, tmp_path):
        """Unique names mean a killed rebuild leaves debris nothing reuses."""
        import os
        import time

        from pegasus_data.persist.staging import sweep_tree_staging

        root = tmp_path / "reference"
        self._tree(root, ["CID10"])
        stale = tmp_path / "reference.__staging__.dead-1234"
        self._tree(stale, ["LEFTOVER"])
        os.utime(stale, (time.time() - 200_000, time.time() - 200_000))
        fresh = tmp_path / "reference.__staging__.live-9999"
        self._tree(fresh, ["INFLIGHT"])

        assert sweep_tree_staging(root) == 1
        assert not stale.exists()
        assert fresh.exists(), "a rebuild in progress must not be swept"
        assert (root / "CID10").exists(), "the real tree is untouched"

    def test_two_rebuilds_do_not_share_a_staging_directory(self, tmp_path):
        """Deterministic names let one rebuild delete another's staged tree."""
        root = tmp_path / "reference"
        seen: list[str] = []
        with staged_tree(root) as first:
            seen.append(first.name)
            with staged_tree(root) as second:
                seen.append(second.name)
                self._tree(second, ["B"])
            self._tree(first, ["A"])
        assert seen[0] != seen[1]

    def test_a_failed_swap_puts_the_old_tree_back(self, tmp_path, monkeypatch):
        """There was no restore at all: a failure between the two renames left
        the target simply gone."""
        root = tmp_path / "reference"
        self._tree(root, ["CID10", "SEXO"])
        real = Path.rename
        calls = {"n": 0}

        def flaky(self, target):
            calls["n"] += 1
            if calls["n"] == 2:  # the staging -> target install
                raise OSError("disk went away")
            return real(self, target)

        monkeypatch.setattr(Path, "rename", flaky)
        with pytest.raises(OSError), staged_tree(root) as staging:
            self._tree(staging, ["CID10"])
        monkeypatch.setattr(Path, "rename", real)
        assert sorted(p.name for p in root.iterdir()) == ["CID10", "SEXO"], (
            "the old tree was not restored after a failed install"
        )


class TestMergeGranularity:
    """The unit of replacement has to be the unit of scope.

    The reference warehouse is `<codelist>/system=<sys>/window=<w>`, and a
    rebuild scoped to one system stages `<codelist>/system=SIHSUS` only. Merging
    at depth 1 replaces the whole `<codelist>` directory — deleting every OTHER
    system's copy of that codelist, which is the exact loss merging exists to
    prevent. The earlier test used a flat tree and could not see it.
    """

    def _warehouse(self, root, layout):
        for codelist, systems in layout.items():
            for system in systems:
                d = root / codelist / f"system={system}" / "window=current"
                d.mkdir(parents=True, exist_ok=True)
                (d / "part-0.parquet").write_bytes(f"{codelist}/{system}".encode())

    def _systems(self, root, codelist):
        base = root / codelist
        return sorted(p.name for p in base.iterdir()) if base.is_dir() else []

    def test_a_system_scoped_rebuild_keeps_the_other_systems_copies(self, tmp_path):
        root = tmp_path / "reference"
        self._warehouse(root, {"SEXO": ["SIHSUS", "SINASC", "SIM"], "CID10": ["SIHSUS"]})

        with staged_tree(root, merge_depth=2) as staging:
            self._warehouse(staging, {"SEXO": ["SIHSUS"]})

        assert self._systems(root, "SEXO") == ["system=SIHSUS", "system=SIM", "system=SINASC"], (
            "a rebuild scoped to SIHSUS deleted SINASC's and SIM's SEXO tables"
        )
        assert self._systems(root, "CID10") == ["system=SIHSUS"]

    def test_merging_at_depth_one_is_what_destroyed_them(self, tmp_path):
        """Kept as the counter-example, so the reason for merge_depth is visible."""
        root = tmp_path / "reference"
        self._warehouse(root, {"SEXO": ["SIHSUS", "SINASC", "SIM"]})
        with staged_tree(root, merge_depth=1) as staging:
            self._warehouse(staging, {"SEXO": ["SIHSUS"]})
        assert self._systems(root, "SEXO") == ["system=SIHSUS"]

    def test_the_scoped_system_is_still_refreshed(self, tmp_path):
        root = tmp_path / "reference"
        self._warehouse(root, {"SEXO": ["SIHSUS", "SINASC"]})
        stale = root / "SEXO" / "system=SIHSUS" / "window=old"
        stale.mkdir(parents=True)
        (stale / "part-0.parquet").write_bytes(b"stale")

        with staged_tree(root, merge_depth=2) as staging:
            self._warehouse(staging, {"SEXO": ["SIHSUS"]})

        windows = sorted(p.name for p in (root / "SEXO" / "system=SIHSUS").iterdir())
        assert windows == ["window=current"], "the stale window survived the rebuild"
        assert (root / "SEXO" / "system=SINASC").is_dir()

    def test_a_codelist_the_scope_did_not_touch_is_untouched(self, tmp_path):
        root = tmp_path / "reference"
        self._warehouse(root, {"SEXO": ["SIHSUS"], "MUNIC": ["SINASC"]})
        with staged_tree(root, merge_depth=2) as staging:
            self._warehouse(staging, {"SEXO": ["SIHSUS"]})
        assert (root / "MUNIC" / "system=SINASC" / "window=current").is_dir()

    def test_a_tree_flatter_than_the_merge_depth_still_contributes(self, tmp_path):
        """Otherwise a staged unit shallower than the depth is silently dropped."""
        root = tmp_path / "reference"
        (root / "KEEP").mkdir(parents=True)
        (root / "KEEP" / "x.parquet").write_bytes(b"keep")
        with staged_tree(root, merge_depth=2) as staging:
            (staging / "FLAT").mkdir()
            (staging / "FLAT" / "y.parquet").write_bytes(b"flat")
        assert (root / "FLAT" / "y.parquet").read_bytes() == b"flat"
        assert (root / "KEEP" / "x.parquet").exists()
