"""Shared fixtures.

Tests are offline by default. Anything needing ``ftp.datasus.gov.br`` or the
DEMAS API is marked ``network`` and skipped unless ``PEGASUS_TEST_NETWORK=1``.
"""

from __future__ import annotations

import os
import struct
from pathlib import Path

import pytest

from pegasus_data.catalog.store import Catalog
from pegasus_data.config import Settings


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("PEGASUS_TEST_NETWORK") == "1":
        return
    skip = pytest.mark.skip(reason="set PEGASUS_TEST_NETWORK=1 to run tests that hit the network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    s = Settings(root=tmp_path / "home")
    s.ensure_dirs()
    return s


@pytest.fixture
def catalog(settings: Settings) -> Catalog:
    cat = Catalog(settings.catalog_path)
    yield cat
    cat.close()


def make_dbf(
    fields: list[tuple[str, str, int, int]], rows: list[list[str]], *, encoding: str = "cp850"
) -> bytes:
    """Build a minimal dBase III file in memory.

    Used instead of a checked-in binary so the expectations are visible in the
    test itself: field widths, the deletion flag, and the record count in the
    header are all things the reader has to get right.
    """
    header_len = 32 + 32 * len(fields) + 1
    record_len = 1 + sum(f[2] for f in fields)
    out = bytearray()
    out += bytes([0x03])
    out += bytes([124, 1, 1])  # yy, mm, dd
    out += struct.pack("<IHH", len(rows), header_len, record_len)
    out += bytes(20)
    for name, ftype, width, decimals in fields:
        out += name.encode("ascii")[:11].ljust(11, b"\x00")
        out += ftype.encode("ascii")
        out += bytes(4)
        out += bytes([width, decimals])
        out += bytes(14)
    out += b"\x0d"
    for row in rows:
        out += b" "
        for (_, _, width, _), value in zip(fields, row, strict=True):
            out += str(value).encode(encoding, errors="replace")[:width].ljust(width, b" ")
    out += b"\x1a"
    return bytes(out)


@pytest.fixture
def sample_dbf() -> bytes:
    return make_dbf(
        [("CODE", "C", 4, 0), ("SEXO", "C", 1, 0), ("VALOR", "N", 8, 2), ("NOME", "C", 12, 0)],
        [
            ["A001", "1", "00012345", "MARIA"],
            ["B992", "2", "00000099", "JOÃO"],
            ["C500", "1", "00500000", "ANTÔNIO"],
        ],
    )
