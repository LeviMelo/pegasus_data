"""One durability model for every derived artifact.

The lake and the reference warehouse are both rebuildable from the catalog and
the blob store, and both had independently worked out how not to destroy the old
copy before the new one existed. Two implementations of one rule is how they
drift, so the rule lives in one place now — and the failure paths, which are the
entire reason it exists, are asserted here rather than assumed.
"""

from __future__ import annotations

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
        root = tmp_path / "reference"
        stale = tmp_path / "reference.__staging__"
        self._tree(stale, ["LEFTOVER"])
        with staged_tree(root) as staging:
            self._tree(staging, ["CID10"])
        assert sorted(p.name for p in root.iterdir()) == ["CID10"]
        assert not stale.exists()
