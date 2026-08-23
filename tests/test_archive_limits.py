"""Archives are remote input; a corrupt one exhausts the same resources as a hostile one.

Two gaps. Members were materialised whole with no ceiling on how many, how
large, or how far they expand — so a bad header and a decompression bomb produce
the same outcome. And RAR/7z containment was checked AFTER extraction, which is
too late: a member path that escapes has already been written by then.
"""

from __future__ import annotations

import gzip
import io
import tarfile
import zipfile

import pytest

from pegasus_data.decode.archives import (
    MAX_EXPANSION_RATIO,
    MAX_MEMBERS,
    Archive,
    ArchiveQuotaExceeded,
    safe_member_path,
)
from pegasus_data.decode.base import DecodeError


def _zip(members: dict[str, bytes], **kw) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", **kw) as zf:
        for name, payload in members.items():
            zf.writestr(name, payload)
    return buffer.getvalue()


class TestQuotas:
    def test_an_ordinary_archive_opens(self):
        archive = Archive(_zip({"a.dbf": b"x" * 100}), path="/x/a.zip")
        assert [m.name for m in archive.members()] == ["a.dbf"]

    def test_too_many_members_is_refused(self):
        payload = _zip({f"m{i}.dbf": b"x" for i in range(MAX_MEMBERS + 1)})
        with pytest.raises(ArchiveQuotaExceeded, match="exceeds"):
            Archive(payload, path="/x/many.zip")

    def test_an_implausible_expansion_ratio_is_refused(self):
        """What a decompression bomb looks like, and what a corrupt header
        looks like. Both deserve the same refusal."""
        payload = _zip(
            {"bomb.dbf": b"\0" * (50 * 1024 * 1024)}, compression=zipfile.ZIP_DEFLATED
        )
        with pytest.raises(ArchiveQuotaExceeded, match="expands"):
            Archive(payload, path="/x/bomb.zip")

    def test_the_limits_are_stated_as_numbers(self):
        assert MAX_MEMBERS > 0 and MAX_EXPANSION_RATIO > 1

    def test_a_real_sized_member_is_not_refused(self):
        """Generous enough that no real DATASUS member comes close."""
        archive = Archive(
            _zip({"big.dbf": bytes(range(256)) * 4000}), path="/x/real.zip"
        )
        assert archive.members()

    def test_gzip_is_bounded_before_and_during_inflation(self, monkeypatch):
        import pegasus_data.decode.archives as archives

        monkeypatch.setattr(archives, "MAX_EXPANSION_RATIO", 2.0)
        payload = gzip.compress(b"x" * 10_000)
        with pytest.raises(ArchiveQuotaExceeded, match="expands"):
            Archive(payload, path="/x/bomb.dbf.gz")

    def test_tar_member_count_uses_the_same_quota(self, monkeypatch):
        import pegasus_data.decode.archives as archives

        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w") as tf:
            for name in ("a.dbf", "b.dbf"):
                info = tarfile.TarInfo(name)
                info.size = 1
                tf.addfile(info, io.BytesIO(b"x"))
        monkeypatch.setattr(archives, "MAX_MEMBERS", 1)
        with pytest.raises(ArchiveQuotaExceeded, match="members exceeds"):
            Archive(buffer.getvalue(), path="/x/many.tar")

    def test_lha_declared_sizes_use_the_same_quota(self, monkeypatch):
        import pegasus_data.decode.archives as archives

        payload = b"x" * 100
        name = b"TEST.DBF"
        header = bytearray([0, 0])
        header += b"-lh0-"
        header += len(payload).to_bytes(4, "little") * 2
        header += (0).to_bytes(4, "little")
        header += bytes([0x20, 0x00, len(name)]) + name + (0).to_bytes(2, "little")
        header[0] = len(header) - 2
        sfx = b"MZ" + b"\0" * 200 + b"LHA's SFX 2.13S" + bytes(header) + payload + b"\0"
        monkeypatch.setattr(archives, "MAX_UNCOMPRESSED_BYTES", 10)
        with pytest.raises(ArchiveQuotaExceeded, match="uncompressed"):
            Archive(sfx, path="/x/big.exe")


class TestContainmentIsCheckedBeforeExtraction:
    def test_a_parent_escape_is_refused(self):
        payload = _zip({"../escaped.dbf": b"x"})
        with pytest.raises(DecodeError, match="outside the extraction directory"):
            Archive(payload, path="/x/evil.zip")

    def test_an_absolute_member_is_refused(self):
        payload = _zip({"/etc/passwd": b"x"})
        with pytest.raises(DecodeError, match="outside the extraction directory"):
            Archive(payload, path="/x/evil.zip")

    def test_a_deep_but_contained_member_is_allowed(self):
        archive = Archive(_zip({"a/b/c/data.dbf": b"x"}), path="/x/ok.zip")
        assert [m.name for m in archive.members()] == ["a/b/c/data.dbf"]

    @pytest.mark.parametrize(
        "name", ["../x", "../../x", "/abs/x", "C:/Windows/x", "a/../../x"]
    )
    def test_the_name_check_itself_rejects_every_escape_shape(self, name, tmp_path):
        assert safe_member_path(name, tmp_path) is None

    @pytest.mark.parametrize("name", ["x", "a/b/x", "./x"])
    def test_the_name_check_allows_contained_shapes(self, name, tmp_path):
        assert safe_member_path(name, tmp_path) is not None


class TestSevenZipListingIsParsedNotTrusted:
    def test_names_and_sizes_come_out_of_the_listing(self):
        from pegasus_data.decode.archives import _parse_7z_listing

        text = (
            "Path = archive.7z\n\n"
            "Path = one.dbf\nSize = 100\n\n"
            "Path = two.dbf\nSize = 250\n"
        )
        names, sizes = _parse_7z_listing(text)
        assert names == ["one.dbf", "two.dbf"]
        assert sizes == [100, 250]

    def test_a_listing_with_no_members_is_harmless(self):
        from pegasus_data.decode.archives import _parse_7z_listing

        assert _parse_7z_listing("") == ([], [])
