"""Readers: DBF, LHA/SFX, archives, and probe-ordered dispatch (D1)."""

from __future__ import annotations

import io
import zipfile

import pytest

from pegasus_data.decode.archives import Archive, classify_member, detect_container
from pegasus_data.decode.base import DecodeError
from pegasus_data.decode.dbf import read_dbf_bytes
from pegasus_data.decode.lha import LhaArchive, LhaError, find_lha_offset
from pegasus_data.decode.registry import ReaderRegistry, readers_ordered_by_suffix_hint
from tests.conftest import make_dbf


class TestDbf:
    def test_reads_values_and_declared_metadata(self, sample_dbf: bytes):
        table = read_dbf_bytes(sample_dbf, path="mem://x")
        assert table.field_names == ["CODE", "SEXO", "VALOR", "NOME"]
        meta = {f.name: f for f in table.fields}
        assert meta["VALOR"].physical_type == "N"
        assert meta["VALOR"].width == 8
        assert meta["VALOR"].decimals == 2
        arrow = table.to_table()
        assert arrow.num_rows == 3
        assert arrow.column("CODE").to_pylist() == ["A001", "B992", "C500"]

    def test_values_stay_strings_so_detectors_see_raw_bytes(self, sample_dbf: bytes):
        arrow = read_dbf_bytes(sample_dbf, path="mem://x").to_table()
        # Leading zeros survive: they are the signal that separates a code from
        # a measure, and parsing here would destroy them.
        assert arrow.column("VALOR").to_pylist()[0] == "00012345"

    def test_blank_padding_becomes_null_but_sentinels_do_not(self):
        raw = make_dbf([("A", "C", 3, 0), ("B", "C", 1, 0)], [["   ", "9"], ["ABC", "0"]])
        arrow = read_dbf_bytes(raw, path="mem://x").to_table()
        assert arrow.column("A").to_pylist() == [None, "ABC"]
        # '9' is a sentinel in some fields and a category in others: not our call.
        assert arrow.column("B").to_pylist() == ["9", "0"]

    def test_deleted_records_are_dropped(self):
        raw = bytearray(make_dbf([("A", "C", 2, 0)], [["aa"], ["bb"]]))
        header_len = raw[8] | (raw[9] << 8)
        raw[header_len] = 0x2A  # mark the first record deleted
        arrow = read_dbf_bytes(bytes(raw), path="mem://x").to_table()
        assert arrow.column("A").to_pylist() == ["bb"]

    def test_stale_record_count_is_reported_not_trusted(self):
        raw = bytearray(make_dbf([("A", "C", 2, 0)], [["aa"], ["bb"]]))
        raw[4:8] = (99).to_bytes(4, "little")  # header lies about the row count
        table = read_dbf_bytes(bytes(raw), path="mem://x")
        assert table.to_table().num_rows == 2
        assert any("header_declares_99" in w for w in table.warnings)

    def test_rejects_a_non_dbf(self):
        with pytest.raises(DecodeError):
            read_dbf_bytes(b"not a dbf at all, really", path="mem://x")


class TestLha:
    def _sfx(self, payload: bytes) -> bytes:
        """An LHA container with a stub in front, stored (-lh0-) for determinism."""
        name = b"TEST.DBF"
        header = bytearray()
        header += bytes([0, 0])  # size + checksum, filled below
        header += b"-lh0-"
        header += len(payload).to_bytes(4, "little")
        header += len(payload).to_bytes(4, "little")
        header += (0).to_bytes(4, "little")
        header += bytes([0x20, 0x00, len(name)])
        header += name
        header += (0).to_bytes(2, "little")
        header[0] = len(header) - 2
        return b"MZ" + b"\x00" * 200 + b"LHA's SFX 2.13S" + bytes(header) + payload + b"\x00"

    def test_finds_the_payload_behind_a_pe_stub(self, sample_dbf: bytes):
        container = self._sfx(sample_dbf)
        assert detect_container(container) == "lha_sfx"
        offset = find_lha_offset(container)
        assert offset is not None and offset > 0

    def test_reads_stored_members(self, sample_dbf: bytes):
        archive = LhaArchive(self._sfx(sample_dbf))
        assert archive.sfx is True
        assert archive.namelist() == ["TEST.DBF"]
        assert archive.read("TEST.DBF") == sample_dbf

    def test_rejects_a_non_lha(self):
        with pytest.raises(LhaError):
            LhaArchive(b"just some bytes")


class TestArchives:
    def _zip(self, members: dict[str, bytes]) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name, payload in members.items():
                z.writestr(name, payload)
        return buf.getvalue()

    def test_every_member_is_returned_with_its_role(self, sample_dbf: bytes):
        """A kit holds .DEF, .CNV and .DBF at once; picking one discards the layer."""
        raw = self._zip(
            {
                "SEXO.CNV": b"3 1\n      1  Masculino  1\n",
                "RD.DEF": b";title\nAX*.DBC\nLSexo,SEXO,1,SEXO.CNV\n",
                "CID10.DBF": sample_dbf,
                "TAB.HLP": b"help",
            }
        )
        with Archive(raw, path="mem://kit.zip") as archive:
            roles = {m.name: m.role for m in archive.members()}
        assert roles == {
            "SEXO.CNV": "cnv",
            "RD.DEF": "def",
            "CID10.DBF": "lookup",
            "TAB.HLP": "doc",
        }

    @pytest.mark.parametrize(
        ("name", "role"),
        [("x.dbc", "data"), ("x.exe", "binary"), ("x.cnv", "cnv"), ("x.pdf", "doc")],
    )
    def test_member_roles(self, name, role):
        assert classify_member(name) == role


class TestRegistry:
    def test_suffix_only_orders_the_probe(self):
        """.exe is not excluded — it is probed as an archive first (D1)."""
        order = readers_ordered_by_suffix_hint("/x/ACAC0202.EXE")
        assert order[0] == "archive"
        assert "dbf" in order and "dbc" in order

    def test_unknown_suffix_gets_the_full_ladder(self):
        order = readers_ordered_by_suffix_hint("/x/mystery.qqq")
        assert "archive" in order and "dbf" in order and "csv" in order

    def test_probes_a_dbf_with_a_misleading_name(self, sample_dbf: bytes):
        outcome = ReaderRegistry().open_bytes(sample_dbf, path="/x/looks_like.csv")
        assert outcome.decoded
        assert outcome.tables[0].reader == "dbf"

    def test_archive_yields_one_table_per_member(self, sample_dbf: bytes):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("A.DBF", sample_dbf)
            z.writestr("B.DBF", make_dbf([("Z", "C", 2, 0)], [["zz"]]))
        outcome = ReaderRegistry().open_bytes(buf.getvalue(), path="/x/kit.zip")
        assert {t.member for t in outcome.tables} == {"A.DBF", "B.DBF"}

    def test_archive_reads_only_selected_data_members(self, sample_dbf: bytes):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("A.DBF", sample_dbf)
            z.writestr("B.DBF", make_dbf([("Z", "C", 2, 0)], [["zz"]]))
        outcome = ReaderRegistry().open_bytes(
            buf.getvalue(), path="/x/kit.zip", members=frozenset({"B.DBF"})
        )
        assert [table.member for table in outcome.tables] == ["B.DBF"]

    def test_undecodable_payload_records_every_attempt(self):
        outcome = ReaderRegistry().open_bytes(b"\x00\x01\x02\x03", path="/x/thing.dbc")
        assert not outcome.decoded
        assert outcome.attempts
        assert all(not a.ok for a in outcome.attempts)
