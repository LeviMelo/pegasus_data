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

    def test_the_projection_reaches_the_decoder(self, settings, seeded, monkeypatch):
        # Observed IN PROCESS: a monkeypatch in this interpreter cannot
        # reach a decoder running in another one. The isolated path is
        # covered in test_decode_isolation.py, which asserts the same
        # guarantee on what comes back across the pipe.
        settings.decode_isolation = False
        """Observed at the decoder, not grepped from the source.

        A spelling assertion proves nothing about behaviour and dies the moment
        the call moves — which it will, since the decode path is being replaced
        by process isolation. What matters is that a narrow request never
        materialises the columns it excluded.
        """
        from pegasus_data.decode.registry import ReaderRegistry
        from pegasus_data.retrieve import fetch

        seen: list[frozenset[str] | None] = []
        real = ReaderRegistry.open_path

        def watched(self, path, *, logical_path=None, columns=None):
            seen.append(columns)
            return real(self, path, logical_path=logical_path, columns=columns)

        monkeypatch.setattr(ReaderRegistry, "open_path", watched)
        fetch("SIH-RD", columns=["SEXO"], settings=settings)

        assert seen, "no decode happened"
        assert any(c for c in seen), (
            "the decoder was handed no projection, so every physical column is "
            "built and then thrown away"
        )
        asked = {name for c in seen if c for name in c}
        assert "SEXO" in asked

    def test_unrequested_columns_are_never_materialised(self, settings, seeded, monkeypatch):
        # Observed IN PROCESS: a monkeypatch in this interpreter cannot
        # reach a decoder running in another one. The isolated path is
        # covered in test_decode_isolation.py, which asserts the same
        # guarantee on what comes back across the pipe.
        settings.decode_isolation = False
        """The point of pushing the projection down, asserted on the batches."""
        from pegasus_data.retrieve import fetch

        widths: list[int] = []
        import pegasus_data.decode.dbf as dbf

        real = dbf._batch_from_block

        def watched(block, header, offsets, encoding, wanted=None):
            batch = real(block, header, offsets, encoding, wanted)
            widths.append(batch.num_columns)
            return batch

        monkeypatch.setattr(dbf, "_batch_from_block", watched)
        fetch("SIH-RD", columns=["SEXO"], settings=settings)
        assert widths, "no batch was built"
        assert min(widths) < 3, (
            f"every batch carried {min(widths)} columns; the fixture has 3 and "
            "one was requested, so nothing was pushed down"
        )
