"""The first-party .dbc decompressor, held to its own claims.

The algorithm ships twice — C and Python, structurally identical — and the
tests are what make that a guarantee rather than a hope: both engines must
produce byte-identical output on real files, and both must REFUSE garbage
with a reason instead of writing a truncated file (the failure mode of the
third-party reader this replaced).
"""

from __future__ import annotations

import pathlib

import pytest

from pegasus_data.decode._native import (
    DbcError,
    _CONSTRUCTED_OK,
    _explode_py,
    _load_native,
    dbc_to_dbf_bytes,
    explode,
)

pytestmark = pytest.mark.filterwarnings("ignore")


def _one_real_blob():
    """A real SIH file from the lake, or None on a machine without one."""
    try:
        from pegasus_data.acquire.cache import BlobStore
        from pegasus_data.catalog.store import Catalog
        from pegasus_data.config import load_settings

        # The suite's conftest points settings at an isolated tmp root; the
        # goldens want the REPO's real lake, named explicitly.
        root = pathlib.Path(__file__).resolve().parents[1] / "pegasus_data_home"
        if not root.is_dir():
            return None
        settings = load_settings(root=root)
        if not settings.catalog_path.is_file():
            return None
        catalog = Catalog(settings.catalog_path, read_only=True)
        try:
            rows = catalog.query(
                "SELECT sha256 AS d FROM fetches WHERE source_path LIKE '%.dbc' LIMIT 1")
        finally:
            catalog.close()
        if not rows:
            return None
        path = BlobStore(settings.blobs_dir).path_for(rows[0]["d"])
        return path.read_bytes() if path.is_file() else None
    except Exception:  # noqa: BLE001 - absence of a lake is not a failure
        return None


class TestRefusals:
    def test_garbage_is_refused_with_a_reason(self) -> None:
        with pytest.raises(DbcError):
            dbc_to_dbf_bytes(b"not a dbc at all" * 10)

    def test_a_truncated_stream_is_refused_not_truncated_output(self) -> None:
        blob = _one_real_blob()
        if blob is None:
            pytest.skip("no lake on this machine")
        with pytest.raises(DbcError, match="truncated|mid-symbol"):
            dbc_to_dbf_bytes(blob[: len(blob) // 2])

    def test_an_overflowing_stream_is_an_error_not_an_allocation(self) -> None:
        blob = _one_real_blob()
        if blob is None:
            pytest.skip("no lake on this machine")
        import struct

        n_records, header_len, record_len = struct.unpack_from("<IHH", blob, 4)
        stream = blob[header_len + 4 :]
        with pytest.raises(DbcError, match="expands|promises|truncated"):
            explode(stream, 100)  # far less than the stream inflates to


class TestTheTwoEnginesAgree:
    def test_native_and_python_are_byte_identical(self) -> None:
        blob = _one_real_blob()
        if blob is None:
            pytest.skip("no lake on this machine")
        if _load_native() is None:
            pytest.skip("no compiler on this machine")
        import struct

        n_records, header_len, record_len = struct.unpack_from("<IHH", blob, 4)
        cap = n_records * max(record_len, 1) + 1
        stream = blob[header_len + 4 :]
        assert explode(stream, cap) == _explode_py(stream, cap)


class TestTheTables:
    def test_all_three_huffman_codes_are_complete(self) -> None:
        # _construct raises on an incomplete or oversubscribed table, and it
        # runs at import for all three — reaching here means they built. The
        # flag exists so a future edit to the tables fails THIS test by name.
        assert _CONSTRUCTED_OK
