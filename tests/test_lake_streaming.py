"""The storage boundary must never hold a whole partition.

`Lake.write_batches` opened a ParquetWriter and streamed into it — after
`collected = [b for b in batches if b.num_rows]` had already materialised
everything it was about to stream. The comment described the writer; the line
above it paid the entire state-year partition in memory. For SIH/SIA at larger
geographies that is the difference that matters.

Asserted as a property rather than as an RSS measurement, because the test
lakes have partitions of a few thousand rows and resident-set noise swamps the
signal at that size.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from pegasus_data.persist.lake import Lake


def _batch(n: int, tag: int) -> pa.RecordBatch:
    return pa.record_batch({"a": pa.array([str(tag)] * n), "b": pa.array(list(range(n)))})


class TestItDoesNotMaterialiseThePartition:
    def test_a_batch_is_written_before_the_next_is_produced(self, tmp_path, monkeypatch):
        """How many batches existed when each write happened.

        This is the measurement that distinguishes the two designs. Counting
        how many are "alive" around a `yield` does not: a list comprehension
        drains the generator while that count still goes 1 -> 0 each time. What
        separates streaming from collecting is whether the FIRST write happens
        after one batch has been produced or after all fifty have.
        """
        import pyarrow.parquet as pq

        produced = 0
        produced_at_write: list[int] = []

        def source():
            nonlocal produced
            for i in range(50):
                produced += 1
                yield _batch(100, i)

        real = pq.ParquetWriter.write_batch

        def watched(self, batch, **kw):
            produced_at_write.append(produced)
            return real(self, batch, **kw)

        monkeypatch.setattr(pq.ParquetWriter, "write_batch", watched)

        lake = Lake(tmp_path / "lake")
        written = lake.write_batches(
            source(), system="SIHSUS", family_id="F1",
            schema_signature="sig", uf="AL", year=2023,
        )
        assert written is not None and written.row_count == 5000
        assert produced_at_write[0] == 1, (
            f"{produced_at_write[0]} batches were produced before the first was "
            "written; the partition was materialised before streaming"
        )
        assert produced_at_write == list(range(1, 51)), (
            "each batch must be written before the next is produced"
        )

    def test_it_is_lazy_before_the_first_batch_is_needed(self, tmp_path):
        started = False

        def source():
            nonlocal started
            started = True
            yield _batch(10, 0)

        lake = Lake(tmp_path / "lake")
        generator = source()
        assert not started, "the generator ran before write_batches was even called"
        lake.write_batches(
            generator, system="SIHSUS", family_id="F1",
            schema_signature="sig", uf="AL", year=2023,
        )
        assert started

    def test_an_empty_stream_writes_nothing(self, tmp_path):
        lake = Lake(tmp_path / "lake")
        assert lake.write_batches(
            iter(()), system="SIHSUS", family_id="F1",
            schema_signature="sig", uf="AL", year=2023,
        ) is None

    def test_a_stream_of_only_empty_batches_writes_nothing(self, tmp_path):
        lake = Lake(tmp_path / "lake")
        assert lake.write_batches(
            iter([_batch(0, 0), _batch(0, 1)]), system="SIHSUS", family_id="F1",
            schema_signature="sig", uf="AL", year=2023,
        ) is None

    def test_leading_empty_batches_do_not_lose_the_rest(self, tmp_path):
        """The schema is taken from the first NON-empty batch."""
        lake = Lake(tmp_path / "lake")
        written = lake.write_batches(
            iter([_batch(0, 0), _batch(7, 1), _batch(3, 2)]),
            system="SIHSUS", family_id="F1",
            schema_signature="sig", uf="AL", year=2023,
        )
        assert written is not None and written.row_count == 10


class TestReplacementNeverLeavesNeitherPartition:
    def test_the_old_partition_survives_until_the_new_one_lands(self, tmp_path):
        """Clearing used to happen INSIDE the staging context, so there was an
        interval with the old files deleted and the new one not yet renamed. A
        crash there lost the partition outright — the failure staging exists to
        prevent."""
        lake = Lake(tmp_path / "lake")
        kw = dict(system="SIHSUS", family_id="F1", schema_signature="sig", uf="AL", year=2023)
        first = lake.write_batches(iter([_batch(5, 0)]), **kw)
        assert first is not None
        target = lake.root / first.relative_path

        seen: list[bool] = []

        def watching():
            # Mid-write: the replacement is not yet in place, so the OLD
            # partition must still be readable.
            seen.append(target.exists())
            yield _batch(9, 1)
            seen.append(target.exists())

        second = lake.write_batches(watching(), **kw)
        assert second is not None and second.row_count == 9
        assert all(seen), "the old partition vanished while the new one was being written"

    def test_the_replacement_is_not_swept_away_by_its_own_clear(self, tmp_path):
        lake = Lake(tmp_path / "lake")
        kw = dict(system="SIHSUS", family_id="F1", schema_signature="sig", uf="AL", year=2023)
        lake.write_batches(iter([_batch(5, 0)]), **kw)
        written = lake.write_batches(iter([_batch(9, 1)]), **kw)
        assert written is not None
        assert (lake.root / written.relative_path).is_file(), (
            "clearing after the swap deleted the file it had just written"
        )

    def test_only_one_parquet_remains_after_a_rebuild(self, tmp_path):
        """A stale part beside a new one is read as a union and doubles rows."""
        lake = Lake(tmp_path / "lake")
        kw = dict(system="SIHSUS", family_id="F1", schema_signature="sig", uf="AL", year=2023)
        lake.write_batches(iter([_batch(5, 0)]), **kw)
        written = lake.write_batches(iter([_batch(9, 1)]), **kw)
        directory = (lake.root / written.relative_path).parent
        assert len(list(directory.glob("*.parquet"))) == 1
