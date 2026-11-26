"""The closed encoding (ADR-0238): a closed partition is rewritten value for value at zstd 22 in 1M-row groups, with the
dictionary only where a probe finds it smaller, and is never written back to the open encoding."""

from __future__ import annotations

import random

import pyarrow as pa
import pyarrow.parquet as pq

from pegasus_data.persist.kept import CLOSED_ENCODING, ENCODING
from pegasus_data.persist.lake import RowGroups, _reencode_file, parquet_writer, probe_dictionary


def _partition(path, n=20000):
    draw = random.Random(1)
    table = pa.table({
        "_row": pa.array(range(n), pa.int64()),
        "CODE": pa.array([f"C{draw.randrange(61):07d}" for _ in range(n)]),   # 61 codes in random order
        "UNIQUE": pa.array([f"{i * 7919:012d}x{i}" for i in range(n)]),          # near-unique: plain pays
        "AMOUNT": pa.array([f"{i % 97}.{i % 10}0" for i in range(n)]),
    })
    writer = parquet_writer(path, table.schema)
    groups = RowGroups(writer, 5000)
    for batch in table.to_batches(max_chunksize=500):
        groups.write(batch)
    groups.flush()
    writer.close()
    return table


def test_closed_rewrite_keeps_every_value_and_stamps_the_encoding(tmp_path):
    path = tmp_path / "part-0.parquet"
    original = _partition(path)
    assert pq.ParquetFile(path).schema_arrow.metadata[b"pegasus.encoding"] == ENCODING.encode()
    done = _reencode_file(str(path), False, "zstd", True)
    assert done["state"] == "rewritten"
    back = pq.ParquetFile(path)
    assert back.schema_arrow.metadata[b"pegasus.encoding"] == CLOSED_ENCODING.encode()
    assert back.metadata.num_row_groups == 1                      # 20,000 rows fit one 1M-row group
    assert back.read().select(original.column_names).equals(original)
    assert _reencode_file(str(path), False, "zstd", True)["state"] == "current"
    assert _reencode_file(str(path), False, "zstd", False)["state"] == "current"   # never back to open


def test_probe_keeps_the_dictionary_where_it_pays(tmp_path):
    path = tmp_path / "part-0.parquet"
    _partition(path)
    chosen = probe_dictionary(pq.ParquetFile(path), ["_row", "CODE", "UNIQUE", "AMOUNT"])
    assert "CODE" in chosen and "UNIQUE" not in chosen and "_row" not in chosen
