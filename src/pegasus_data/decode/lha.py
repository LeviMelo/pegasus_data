"""LHA / LZH archive reader, including self-extracting ``.exe`` stubs (D1).

Why this exists
---------------
The architecture brief predicted DATASUS's ``SIASUS/APAC/*.EXE`` files were "a PE
stub with a standard archive appended", to be opened with ``zipfile``, then
``rarfile``, then ``7z``. **Measured 2026-08:** they are none of those. The stub
identifies itself as ``LHA's SFX 2.13S (c) Yoshi, 1991`` and the payload is an
LHA archive using method ``-lh5-``. ``zipfile`` and ``rarfile`` both reject it.

``acac0202.exe`` (21,354 bytes) contains **seven** DBF members, not one::

    ACAC0202.DBF  75066   19 fields   APAC master record (APA_*)
    COAC0202.DBF  55498   14 fields   billed procedures (COB_*)
    PCAC0202.DBF   7204   21 fields   patient, chemotherapy (PAC_*)
    PFAC0202.DBF  11536   21 fields   patient, radiotherapy (PAF_*)
    OPAC0202.DBF  31715   17 fields   other procedures (OPC_*)
    EXAC0202.DBF   3756   13 fields   serology (EXA_*)
    UDAC0202.DBF   4092   66 fields   dialysis unit (UDI_*)

so one archive is seven logical datasets with seven distinct schemas. This is
also why the brief's "expected payload: one or more ``.dbc`` or ``.dbf``" needed
widening in the family model: archive members are first-class rows, not a single
"best member" (the prior ``choose_archive_member`` would have discarded six of
the seven).

This module implements ``-lh0-``/``-lhd-``/``-lz4-`` (stored) and
``-lh4-``/``-lh5-``/``-lh6-``/``-lh7-`` (LZSS + static Huffman) in pure Python,
so the package does not depend on an external binary being installed. ``7z`` is
used only as a fallback for the methods not implemented here (notably ``-lh1-``),
and its absence degrades to a recorded decode gap rather than a crash.
"""

from __future__ import annotations

import re
import shutil
import struct
import subprocess
import tempfile
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

__all__ = ["LhaError", "LhaMember", "LhaArchive", "is_lha", "find_lha_offset"]

_METHOD_RE = re.compile(rb"-(?:lh[0-7d]|lz[s45])-")

STORED_METHODS = {b"-lh0-", b"-lhd-", b"-lz4-"}
#: dictionary bits per Huffman method
_DICBIT = {b"-lh4-": 12, b"-lh5-": 13, b"-lh6-": 15, b"-lh7-": 16}

_MAXMATCH = 256
_THRESHOLD = 3
_NC = 255 + _MAXMATCH - _THRESHOLD + 1   # 509
_CBIT = 9
_NT = 19
_TBIT = 5


class LhaError(Exception):
    """The payload is not a usable LHA archive, or uses a method we cannot decode."""


# --------------------------------------------------------------------- bit IO


class _BitReader:
    """MSB-first bit reader that pads with zero bits past the end of the stream.

    Padding rather than raising matches the reference implementation: the final
    Huffman symbol of a block routinely peeks past the last byte.
    """

    __slots__ = ("data", "pos", "buf", "nbits")

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.pos = 0
        self.buf = 0
        self.nbits = 0

    def _fill(self, need: int) -> None:
        while self.nbits < need:
            byte = self.data[self.pos] if self.pos < len(self.data) else 0
            self.pos += 1
            self.buf = (self.buf << 8) | byte
            self.nbits += 8

    def peek(self, k: int) -> int:
        if k == 0:
            return 0
        self._fill(k)
        return (self.buf >> (self.nbits - k)) & ((1 << k) - 1)

    def skip(self, k: int) -> None:
        if k == 0:
            return
        self._fill(k)
        self.nbits -= k
        self.buf &= (1 << self.nbits) - 1

    def get(self, k: int) -> int:
        value = self.peek(k)
        self.skip(k)
        return value


# ----------------------------------------------------------- Huffman machinery


class _HuffmanTables:
    """Canonical Huffman decode tables in the layout LHA's ``make_table`` builds.

    Short codes resolve in one array lookup; codes longer than ``tablebits`` walk
    a ``left``/``right`` binary tree whose nodes are allocated past ``nchar``.
    """

    __slots__ = ("left", "right", "avail")

    def __init__(self) -> None:
        size = 2 * _NC
        self.left = [0] * size
        self.right = [0] * size
        self.avail = 0

    def make_table(
        self, nchar: int, bitlen: list[int], tablebits: int, table: list[int]
    ) -> None:
        count = [0] * 17
        start = [0] * 18
        weight = [0] * 17
        for i in range(nchar):
            length = bitlen[i]
            if length > 16:
                raise LhaError("bad code length in Huffman table")
            count[length] += 1
        count[0] = 0
        start[1] = 0
        for i in range(1, 17):
            start[i + 1] = start[i] + (count[i] << (16 - i))
        if start[17] != (1 << 16):
            raise LhaError("malformed Huffman table (lengths do not sum to a full code space)")

        jutbits = 16 - tablebits
        for i in range(1, tablebits + 1):
            start[i] >>= jutbits
            weight[i] = 1 << (tablebits - i)
        for i in range(tablebits + 1, 17):
            weight[i] = 1 << (16 - i)

        i = start[tablebits + 1] >> jutbits
        if i != (1 << tablebits):
            k = 1 << tablebits
            while i != k:
                table[i] = 0
                i += 1

        self.avail = nchar
        mask = 1 << (15 - tablebits)
        for ch in range(nchar):
            length = bitlen[ch]
            if length == 0:
                continue
            nextcode = start[length] + weight[length]
            if length <= tablebits:
                for idx in range(start[length], min(nextcode, 1 << tablebits)):
                    table[idx] = ch
            else:
                k = start[length]
                index = k >> jutbits
                container = table
                remaining = length - tablebits
                while remaining:
                    node = container[index]
                    if node == 0:
                        if self.avail >= len(self.left):
                            raise LhaError("Huffman tree overflow")
                        self.left[self.avail] = 0
                        self.right[self.avail] = 0
                        container[index] = self.avail
                        node = self.avail
                        self.avail += 1
                    container = self.right if (k & mask) else self.left
                    index = node
                    k = (k << 1) & 0xFFFF
                    remaining -= 1
                container[index] = ch
            start[length] = nextcode


class _StaticHuffmanDecoder:
    """LHA's ``decode_st1``: the block-structured coder used by -lh4- … -lh7-."""

    def __init__(self, reader: _BitReader, dicbit: int) -> None:
        self.br = reader
        self.dicbit = dicbit
        self.np = dicbit + 1
        self.pbit = 4 if dicbit <= 13 else 5
        self.blocksize = 0
        self.c_len = [0] * _NC
        self.pt_len = [0] * max(self.np, _NT)
        self.c_table = [0] * 4096
        self.pt_table = [0] * 256
        self.tables = _HuffmanTables()

    # ------------------------------------------------------------ table reads

    def _read_pt_len(self, nn: int, nbit: int, i_special: int) -> None:
        br = self.br
        n = br.get(nbit)
        if n == 0:
            c = br.get(nbit)
            for i in range(nn):
                self.pt_len[i] = 0
            for i in range(256):
                self.pt_table[i] = c
            return
        i = 0
        while i < n:
            c = br.peek(3)
            if c != 7:
                br.skip(3)
            else:
                br.skip(3)
                # A run of 1 bits extends the length beyond 7.
                while br.peek(1):
                    br.skip(1)
                    c += 1
                    if c > 16:
                        raise LhaError("code length run too long")
                br.skip(1)
            self.pt_len[i] = c
            i += 1
            if i == i_special:
                c = br.get(2)
                while c > 0 and i < nn:
                    self.pt_len[i] = 0
                    i += 1
                    c -= 1
        while i < nn:
            self.pt_len[i] = 0
            i += 1
        self.tables.make_table(nn, self.pt_len, 8, self.pt_table)

    def _read_c_len(self) -> None:
        br = self.br
        n = br.get(_CBIT)
        if n == 0:
            c = br.get(_CBIT)
            for i in range(_NC):
                self.c_len[i] = 0
            for i in range(4096):
                self.c_table[i] = c
            return
        i = 0
        while i < n:
            c = self.pt_table[br.peek(8)]
            if c >= _NT:
                mask = 1 << 7
                while c >= _NT:
                    c = self.tables.right[c] if (br.peek(8) & mask) else self.tables.left[c]
                    mask >>= 1
                    if mask == 0:
                        raise LhaError("corrupt code-length tree")
            br.skip(self.pt_len[c])
            if c <= 2:
                if c == 0:
                    c = 1
                elif c == 1:
                    c = br.get(4) + 3
                else:
                    c = br.get(_CBIT) + 20
                while c > 0 and i < _NC:
                    self.c_len[i] = 0
                    i += 1
                    c -= 1
            else:
                self.c_len[i] = c - 2
                i += 1
        while i < _NC:
            self.c_len[i] = 0
            i += 1
        self.tables.make_table(_NC, self.c_len, 12, self.c_table)

    # ------------------------------------------------------------- symbol read

    def decode_c(self) -> int:
        br = self.br
        if self.blocksize == 0:
            self.blocksize = br.get(16)
            self._read_pt_len(_NT, _TBIT, 3)
            self._read_c_len()
            self._read_pt_len(self.np, self.pbit, -1)
        self.blocksize -= 1
        j = self.c_table[br.peek(12)]
        if j >= _NC:
            mask = 1 << 3
            while j >= _NC:
                j = self.tables.right[j] if (br.peek(16) & mask) else self.tables.left[j]
                mask >>= 1
                if mask == 0:
                    raise LhaError("corrupt literal/length tree")
        br.skip(self.c_len[j])
        return j

    def decode_p(self) -> int:
        br = self.br
        j = self.pt_table[br.peek(8)]
        if j >= self.np:
            mask = 1 << 7
            while j >= self.np:
                j = self.tables.right[j] if (br.peek(16) & mask) else self.tables.left[j]
                mask >>= 1
                if mask == 0:
                    raise LhaError("corrupt distance tree")
        br.skip(self.pt_len[j])
        if j != 0:
            j = (1 << (j - 1)) + br.get(j - 1)
        return j


def _decode_lh(data: bytes, original_size: int, dicbit: int) -> bytes:
    """LZSS + static Huffman decode of one member's compressed payload."""
    br = _BitReader(data)
    dec = _StaticHuffmanDecoder(br, dicbit)
    out = bytearray()
    while len(out) < original_size:
        c = dec.decode_c()
        if c <= 255:
            out.append(c)
            continue
        length = c - 256 + _THRESHOLD
        distance = dec.decode_p()
        start = len(out) - distance - 1
        if start < 0:
            raise LhaError("back-reference before start of output")
        for _ in range(length):
            if len(out) >= original_size:
                break
            out.append(out[start])
            start += 1
    return bytes(out[:original_size])


# ------------------------------------------------------------------- headers


@dataclass(slots=True)
class LhaMember:
    name: str
    method: str
    compressed_size: int
    original_size: int
    modified: datetime | None
    offset: int          # offset of compressed data within the container
    crc: int | None
    header_level: int

    @property
    def is_directory(self) -> bool:
        return self.method == "-lhd-"


def _dos_time(value: int) -> datetime | None:
    try:
        second = (value & 0x1F) * 2
        minute = (value >> 5) & 0x3F
        hour = (value >> 11) & 0x1F
        day = (value >> 16) & 0x1F
        month = (value >> 21) & 0x0F
        year = ((value >> 25) & 0x7F) + 1980
        return datetime(year, month, day, hour, minute, min(second, 59))
    except ValueError:
        return None


def find_lha_offset(data: bytes, *, search_limit: int = 1 << 20) -> int | None:
    """Locate the first plausible LHA header, skipping any SFX stub.

    Validated by reading the candidate header and checking that its declared
    sizes stay inside the container — a raw method-string match alone would
    happily fire on the string ``-lh5-`` appearing inside the stub's own code.
    """
    for match in _METHOD_RE.finditer(data, 0, min(len(data), search_limit)):
        offset = match.start() - 2
        if offset < 0:
            continue
        try:
            member, _ = _parse_header(data, offset)
        except LhaError:
            continue
        if member is None:
            continue
        end = member.offset + member.compressed_size
        if end <= len(data):
            return offset
    return None


def is_lha(data: bytes) -> bool:
    return find_lha_offset(data) is not None


def _parse_header(data: bytes, pos: int) -> tuple[LhaMember | None, int]:
    """Parse one header at `pos`; return (member, next_header_pos)."""
    if pos + 21 >= len(data):
        return None, len(data)
    if data[pos] == 0 and data[pos + 1] == 0:
        return None, len(data)  # end-of-archive marker

    level = data[pos + 20]
    method = bytes(data[pos + 2 : pos + 7])
    if not _METHOD_RE.fullmatch(method):
        raise LhaError(f"unknown compression method {method!r} at offset {pos}")

    if level == 0:
        header_size = data[pos]
        if header_size == 0:
            return None, len(data)
        compressed, original, stamp = struct.unpack_from("<III", data, pos + 7)
        name_len = data[pos + 21]
        name = data[pos + 22 : pos + 22 + name_len].decode("cp850", errors="replace")
        crc_at = pos + 22 + name_len
        crc = struct.unpack_from("<H", data, crc_at)[0] if crc_at + 2 <= len(data) else None
        data_offset = pos + header_size + 2
        modified = _dos_time(stamp)
        next_pos = data_offset + compressed
    elif level == 1:
        base_size = data[pos]
        compressed, original, stamp = struct.unpack_from("<III", data, pos + 7)
        name_len = data[pos + 21]
        name = data[pos + 22 : pos + 22 + name_len].decode("cp850", errors="replace")
        crc_at = pos + 22 + name_len
        crc = struct.unpack_from("<H", data, crc_at)[0] if crc_at + 2 <= len(data) else None
        # Level 1 chains extension headers; their bytes are counted inside the
        # "compressed size" field, so walk them to find where the payload starts.
        ext_pos = pos + base_size + 2
        skip = compressed
        while ext_pos + 2 <= len(data):
            ext_size = struct.unpack_from("<H", data, ext_pos)[0]
            if ext_size == 0:
                ext_pos += 2
                break
            if ext_size < 2 or ext_pos + ext_size > len(data):
                raise LhaError("corrupt level-1 extension header")
            skip -= ext_size
            ext_pos += ext_size
        data_offset = ext_pos
        modified = _dos_time(stamp)
        compressed = max(0, skip)
        next_pos = data_offset + compressed
    elif level == 2:
        total_size = struct.unpack_from("<H", data, pos)[0]
        if total_size == 0:
            return None, len(data)
        compressed, original, stamp = struct.unpack_from("<III", data, pos + 7)
        crc = struct.unpack_from("<H", data, pos + 21)[0]
        name = ""
        ext_pos = pos + 24
        while ext_pos + 2 <= len(data):
            ext_size = struct.unpack_from("<H", data, ext_pos - 2)[0] if ext_pos >= 2 else 0
            if ext_size == 0:
                break
            ext_type = data[ext_pos]
            body = data[ext_pos + 1 : ext_pos + ext_size - 2]
            if ext_type == 0x01:
                name = body.decode("cp850", errors="replace")
            elif ext_type == 0x02 and name:
                directory = body.replace(b"\xff", b"/").decode("cp850", errors="replace")
                name = f"{directory.rstrip('/')}/{name}"
            ext_pos += ext_size
        data_offset = pos + total_size
        modified = datetime.fromtimestamp(stamp) if stamp else None
        next_pos = data_offset + compressed
    else:
        raise LhaError(f"unsupported LHA header level {level}")

    member = LhaMember(
        name=name.replace("\\", "/"),
        method=method.decode("ascii"),
        compressed_size=compressed,
        original_size=original,
        modified=modified,
        offset=data_offset,
        crc=crc,
        header_level=level,
    )
    return member, next_pos


class LhaArchive:
    """Read-only LHA archive, tolerant of a prepended self-extracting stub."""

    def __init__(self, data: bytes) -> None:
        self.data = data
        self.base = find_lha_offset(data)
        if self.base is None:
            raise LhaError("no LHA header found (not an LHA or LHA-SFX container)")
        self.sfx = self.base > 0
        self._members: list[LhaMember] | None = None

    @classmethod
    def from_path(cls, path: str | Path) -> LhaArchive:
        return cls(Path(path).read_bytes())

    # ---------------------------------------------------------------- members

    @property
    def members(self) -> list[LhaMember]:
        if self._members is None:
            found: list[LhaMember] = []
            pos = self.base or 0
            while pos < len(self.data):
                try:
                    member, next_pos = _parse_header(self.data, pos)
                except LhaError:
                    break
                if member is None:
                    break
                found.append(member)
                if next_pos <= pos:
                    break
                pos = next_pos
            self._members = found
        return self._members

    def namelist(self) -> list[str]:
        return [m.name for m in self.members if not m.is_directory]

    def __iter__(self) -> Iterator[LhaMember]:
        return iter(self.members)

    # ------------------------------------------------------------------- read

    def read(self, name: str) -> bytes:
        for member in self.members:
            if member.name == name:
                return self.read_member(member)
        raise KeyError(name)

    def read_member(self, member: LhaMember) -> bytes:
        raw = self.data[member.offset : member.offset + member.compressed_size]
        method = member.method.encode("ascii")
        if method in STORED_METHODS:
            return raw[: member.original_size]
        dicbit = _DICBIT.get(method)
        if dicbit is None:
            # -lh1-, -lh2-, -lh3-, -lzs- use different coders. Rather than emit a
            # wrong payload we hand off to 7z, and if that is absent we say so.
            return _extract_via_7z(self.data, member.name)
        return _decode_lh(raw, member.original_size, dicbit)

    def extractall(self, dest: str | Path) -> list[Path]:
        out = Path(dest)
        out.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for member in self.members:
            if member.is_directory:
                continue
            target = out / Path(member.name).name
            target.write_bytes(self.read_member(member))
            written.append(target)
        return written


def _extract_via_7z(container: bytes, member_name: str) -> bytes:
    """Fallback for LHA methods this module does not implement."""
    exe = shutil.which("7z") or shutil.which("7za") or shutil.which("7zz")
    if exe is None:
        for candidate in (r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"):
            if Path(candidate).is_file():
                exe = candidate
                break
    if exe is None:
        raise LhaError(
            "member uses an LHA method not implemented in pure Python and 7z is not on PATH; "
            "install 7-Zip or p7zip to decode it"
        )
    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "payload.lzh"
        archive.write_bytes(container)
        proc = subprocess.run(
            [exe, "x", "-y", f"-o{tmp}", str(archive), member_name],
            capture_output=True,
            timeout=300,
            check=False,
        )
        extracted = Path(tmp) / member_name
        if not extracted.is_file():
            matches = list(Path(tmp).rglob(Path(member_name).name))
            if not matches:
                raise LhaError(f"7z could not extract {member_name}: {proc.stderr.decode(errors='replace')[:400]}")
            extracted = matches[0]
        return extracted.read_bytes()
