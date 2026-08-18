"""The FTP listing parsers — the root cause of defect D4."""

from __future__ import annotations

import pytest

from pegasus_data.discovery.listing import (
    normalize_path,
    parse_list_lines,
    parse_msdos_line,
    parse_nlst,
    parse_unix_line,
)

#: Verbatim from ftp.datasus.gov.br, 2026-08.
MSDOS_SAMPLE = [
    "05-29-15  04:10PM                18550 acac0201.exe",
    "02-24-18  07:38AM       <DIR>          199201_200712",
    "08-17-26  10:07PM              6005360 TAB_SIH.zip",
    "01-07-25  09:42AM                93560 PROJUF00.dbf",
]

UNIX_SAMPLE = [
    "drwxr-xr-x   2 ftp      ftp          4096 Feb 24  2018 199201_200712",
    "-rw-r--r--   1 ftp      ftp         18550 May 29  2015 acac0201.exe",
]


def test_msdos_file_carries_size_and_mtime():
    entry = parse_msdos_line(MSDOS_SAMPLE[0], "/dissemin/publicos/SIASUS/APAC/2002")
    assert entry is not None
    assert entry.name == "acac0201.exe"
    assert entry.is_dir is False
    assert entry.size == 18550
    assert entry.modified is not None and entry.modified.startswith("2015-05-29T16:10")
    assert entry.change_signal == "mtime"


def test_msdos_directory_has_no_size():
    entry = parse_msdos_line(MSDOS_SAMPLE[1], "/dissemin/publicos/SIHSUS")
    assert entry is not None
    assert entry.is_dir is True
    assert entry.size is None
    assert entry.path == "/dissemin/publicos/SIHSUS/199201_200712"


def test_msdos_dialect_is_the_one_that_broke_the_prior_scan():
    """The whole point of D4: a Unix-only regex sees none of these rows."""
    for line in MSDOS_SAMPLE:
        assert parse_unix_line(line, "/x") is None
        assert parse_msdos_line(line, "/x") is not None


def test_unix_dialect_still_parses():
    entries = parse_list_lines(UNIX_SAMPLE, "/dissemin/publicos/SIHSUS")
    assert len(entries) == 2
    assert entries[0].is_dir is True
    assert entries[1].size == 18550


def test_unparsed_listing_raises_rather_than_looking_empty():
    """Conflating 'unparseable' with 'empty' is how a subtree disappears."""
    with pytest.raises(ValueError, match="unrecognised dialect"):
        parse_list_lines(["!!! something we have never seen !!!"], "/x")


def test_genuinely_empty_listing_is_empty():
    assert parse_list_lines([], "/x") == []
    assert parse_list_lines(["total 0"], "/x") == []


def test_nlst_types_by_hint_and_flags_the_rest():
    entries = parse_nlst(["a.dbc", "SOMEDIR", "b.exe"], "/base")
    by_name = {e.name: e for e in entries}
    assert by_name["a.dbc"].is_dir is False
    assert by_name["b.exe"].is_dir is False           # .exe is data, not a skip
    assert by_name["SOMEDIR"].is_dir is None          # unknown stays unknown
    assert by_name["SOMEDIR"].change_signal == "content_hash"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/dissemin/publicos//IBGE/", "/dissemin/publicos/IBGE"),
        ("dissemin/publicos", "/dissemin/publicos"),
        ("\\dissemin\\publicos", "/dissemin/publicos"),
        # MSYS/Git-Bash mangles a leading-slash argument into a Windows path.
        ("/C:/Program Files/Git/dissemin/publicos/IBGE", "/dissemin/publicos/IBGE"),
    ],
)
def test_normalize_path(raw, expected):
    assert normalize_path(raw) == expected
