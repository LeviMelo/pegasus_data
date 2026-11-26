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


def _register(path, months=6, people=4000):
    """A register republished whole each month: every person once a month, a few fields changing."""
    draw = random.Random(2)
    base = [(f"{draw.randrange(10**11):011d}", f"{draw.randrange(400):07d}", f"N{draw.randrange(10**6)}") for _ in range(people)]
    rows = {"_source_path": [], "_row": [], "CPF": [], "CNES": [], "NAME": [], "HOURS": []}
    for m in range(months):
        for i, (cpf, cnes, name) in enumerate(base):
            rows["_source_path"].append(f"CNES/PF/PFAL23{m + 1:02d}.dbc")
            rows["_row"].append(i)
            rows["CPF"].append(cpf)
            rows["CNES"].append(cnes)
            rows["NAME"].append(name)
            rows["HOURS"].append(str(20 + (i % 3 == 0 and m > 3) * 20))
    table = pa.table({k: pa.array(v, pa.int64() if k == "_row" else pa.string()) for k, v in rows.items()})
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = parquet_writer(path, table.schema)
    groups = RowGroups(writer)
    for batch in table.to_batches(max_chunksize=4000):
        groups.write(batch)
    groups.flush()
    writer.close()
    return table


def test_a_register_is_ordered_by_its_found_key_and_keeps_every_row(tmp_path):
    import duckdb

    from pegasus_data.persist.cluster import ORDER_META, choose_order

    path = tmp_path / "CNES" / "CNES_PF_x" / "schema_signature=x" / "uf=AL" / "year=2023" / "part-00000.parquet"
    original = _register(path)
    choice = choose_order(path, duckdb.connect())
    assert choice["order"] is not None and choice["order"][-1] == "_source_path"
    assert set(choice["key"]) >= {"CPF"}
    before = path.stat().st_size
    done = _reencode_file(str(path), False, "zstd", True, choice["order"])
    assert done["state"] == "rewritten" and done["after"] < before
    back = pq.read_table(path)
    assert back.schema.metadata[ORDER_META]
    key = lambda t: sorted(zip(*[t.column(c).to_pylist() for c in original.column_names]))
    assert key(back) == key(original)                         # the same rows, as a multiset
    assert _reencode_file(str(path), False, "zstd", True, choice["order"])["state"] == "current"
    assert _reencode_file(str(path), False, "zstd", True, None)["state"] == "rewritten"   # order dropped: rewritten


def test_event_records_keep_their_file_order(tmp_path):
    import duckdb

    from pegasus_data.persist.cluster import choose_order

    path = tmp_path / "SIM" / "SIM_DO_x" / "schema_signature=x" / "uf=AL" / "year=2023" / "part-00000.parquet"
    path.parent.mkdir(parents=True)
    _partition(path)
    table = pq.read_table(path)
    table = table.append_column("_source_path", pa.array([f"DOAL{i % 2}.dbc" for i in range(table.num_rows)]))
    pq.write_table(table, path)
    assert choose_order(path, duckdb.connect())["order"] is None
