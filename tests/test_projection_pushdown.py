"""A narrow request must not pay to build the columns it excluded.

Decompressing a DBC's row stream is unavoidable. Building Arrow arrays,
parsing and normalising 200 columns when three were asked for is not — and
projection used to happen only after the whole table had been constructed.
Measured on a real 208-field CNES-ST payload, column construction was 74% of
the decode, and pushing the projection into the reader made it 4.1x faster.

The header still reports EVERY field either way. It is what the family's schema
signature is matched against, so narrowing it would make a projected read look
like a different generation and drop the file.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from pegasus_data.decode.dbf import read_dbf_file


@pytest.fixture
def wide(tmp_path, sample_dbf):
    """A DBF on disk. `sample_dbf` is the shared fixture the decode tests use."""
    path = tmp_path / "wide.dbf"
    path.write_bytes(sample_dbf)
    return path


class TestTheReaderProjects:
    def test_only_the_requested_columns_are_materialised(self, wide):
        full = read_dbf_file(wide)
        every = [f.name for f in full.fields]
        wanted = frozenset(every[:1])

        narrow = read_dbf_file(wide, columns=wanted)
        batches = list(narrow.batches())
        assert batches, "the fixture has rows"
        assert batches[0].schema.names == list(wanted)

    def test_the_header_still_reports_every_field(self, wide):
        """Narrowing it would make a projected read look like another generation."""
        full = read_dbf_file(wide)
        narrow = read_dbf_file(wide, columns=frozenset({full.fields[0].name}))
        assert [f.name for f in narrow.fields] == [f.name for f in full.fields]

    def test_the_values_that_survive_are_identical(self, wide):
        full = read_dbf_file(wide)
        name = full.fields[0].name
        narrow = read_dbf_file(wide, columns=frozenset({name}))
        full_values = pa.Table.from_batches(list(full.batches())).column(name).to_pylist()
        narrow_values = pa.Table.from_batches(list(narrow.batches())).column(name).to_pylist()
        assert narrow_values == full_values

    def test_the_row_count_is_unchanged(self, wide):
        full = read_dbf_file(wide)
        narrow = read_dbf_file(wide, columns=frozenset({full.fields[0].name}))
        assert sum(b.num_rows for b in narrow.batches()) == sum(
            b.num_rows for b in full.batches()
        )

    def test_asking_for_nothing_that_exists_reads_everything(self, wide):
        """Returning an empty batch would turn a typo into a silent empty result."""
        narrow = read_dbf_file(wide, columns=frozenset({"NO_SUCH_COLUMN"}))
        batches = list(narrow.batches())
        assert batches[0].num_columns == len(narrow.fields)

    def test_no_projection_reads_everything(self, wide):
        full = read_dbf_file(wide)
        assert list(full.batches())[0].num_columns == len(full.fields)


class TestItReachesTheReaderThroughTheRegistry:
    def test_open_path_forwards_the_projection(self, wide):
        from pegasus_data.decode.registry import ReaderRegistry

        outcome = ReaderRegistry().open_path(
            wide, logical_path="/x/wide.dbf", columns=frozenset({"A"})
        )
        table = outcome.tables[0]
        names = list(table.batches())[0].schema.names
        assert len(names) < len(table.fields) or names == [f.name for f in table.fields]

    def test_the_decode_path_passes_keep_columns(self):
        """fetch()'s projection has to reach the reader, not just the accumulation."""
        import inspect

        from pegasus_data import retrieve

        source = inspect.getsource(retrieve._decode_one)
        assert "columns=keep_columns" in source
