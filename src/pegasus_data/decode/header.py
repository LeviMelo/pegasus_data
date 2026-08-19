"""Read a table's *schema* from the first few hundred bytes of the file.

Cataloguing every schema on the tree by decoding every file is not affordable:
the cheapest member of each of the 4,228 strata still totals **183 GiB**, and
63% of strata hold a single file, so choosing a smaller one is not an option
either. Downloading that to learn field names would be absurd, and it is why the
schema catalogue had stayed a sample rather than a census.

It is also unnecessary. A DBF declares its entire schema in a header of a few
hundred bytes — and a ``.dbc``, DATASUS's compressed DBF, stores that header
**uncompressed** ahead of the compressed payload. Measured on
``RDAC9201.dbc``: all 35 field names, types and widths read from the first 1,153
bytes of a 91,967-byte file, 1.25% of it. Across the tree that is roughly 17 MB
instead of 183 GiB.

What this deliberately does *not* do is read data. No row counts you can trust
beyond the header's own claim, no value distributions, no semantic detection —
those need the payload and are what the profile stage is for. This answers one
question only, and answers it for everything: **what columns does this file
have?**
"""

from __future__ import annotations

import struct
from dataclasses import dataclass

#: Field descriptors start here in every DBF variant this tree uses.
_DESCRIPTOR_START = 32
_DESCRIPTOR_SIZE = 32
#: Terminates the descriptor array.
_HEADER_TERMINATOR = 0x0D

#: DBF field type codes. Anything outside this set means the bytes are not a
#: descriptor array, which is the cheapest way to notice we are reading garbage.
_FIELD_TYPES = frozenset("CNLDMFBGPYTI@O+")

#: How much of a file to ask for. Generous against the largest header seen
#: (a 113-column SIH-RD file needs ~3.7 KB) while staying trivial to transfer.
DEFAULT_PREFIX_BYTES = 65536


class HeaderUnreadable(ValueError):
    """The prefix does not contain a parseable DBF header."""


@dataclass(frozen=True, slots=True)
class HeaderField:
    name: str
    type_code: str
    width: int
    decimals: int

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "type": self.type_code,
            "width": self.width,
            "decimals": self.decimals,
        }


@dataclass(slots=True)
class TableHeader:
    """What a file's header states about its own shape."""

    fields: list[HeaderField]
    declared_records: int
    header_length: int
    record_length: int
    version: int

    @property
    def field_names(self) -> list[str]:
        return [f.name for f in self.fields]

    @property
    def consistent(self) -> bool:
        """Do the field widths add up to the declared record length?

        One byte of slack for the deletion flag that starts every DBF record.
        A header that fails this is not necessarily wrong — some writers pad —
        but it is the signal that the descriptors were misread, and it is worth
        recording rather than trusting silently.
        """
        return sum(f.width for f in self.fields) + 1 == self.record_length

    def as_dict(self) -> dict[str, object]:
        return {
            "fields": [f.as_dict() for f in self.fields],
            "field_count": len(self.fields),
            "declared_records": self.declared_records,
            "record_length": self.record_length,
            "header_length": self.header_length,
            "version": self.version,
            "widths_consistent": self.consistent,
        }


def read_table_header(data: bytes) -> TableHeader:
    """Parse a DBF header from a prefix. Works for ``.dbf`` and ``.dbc`` alike.

    Raises :class:`HeaderUnreadable` rather than returning a partial answer: a
    half-read descriptor array yields plausible-looking field names that are not
    the file's columns, and that is worse than admitting the prefix was too
    short.
    """
    if len(data) < _DESCRIPTOR_START + _DESCRIPTOR_SIZE:
        raise HeaderUnreadable(f"only {len(data)} bytes; too short for any DBF header")

    version = data[0]
    declared_records, header_length, record_length = struct.unpack("<IHH", data[4:12])

    # A header shorter than one descriptor is not a DBF at all — it is a zip, a
    # PDF, a CSV. A header LONGER than the prefix is fine here and handled below,
    # where we report how much more was needed.
    if header_length <= _DESCRIPTOR_START:
        raise HeaderUnreadable(
            f"header_length={header_length} is too small to hold any field descriptor"
        )

    fields: list[HeaderField] = []
    limit = min(header_length if header_length <= len(data) else len(data), len(data))
    offset = _DESCRIPTOR_START
    while offset + _DESCRIPTOR_SIZE <= limit:
        if data[offset] == _HEADER_TERMINATOR:
            break
        raw_name = data[offset : offset + 11]
        name = raw_name.split(b"\x00", 1)[0].decode("latin-1", "replace").strip()
        type_code = chr(data[offset + 11])
        width = data[offset + 16]
        decimals = data[offset + 17]
        if not name or type_code not in _FIELD_TYPES:
            # A descriptor that is not a descriptor means the offsets are wrong.
            # Stop rather than accumulate noise.
            break
        fields.append(
            HeaderField(name=name.upper(), type_code=type_code, width=width, decimals=decimals)
        )
        offset += _DESCRIPTOR_SIZE

    if not fields:
        raise HeaderUnreadable(
            f"no field descriptors found (version=0x{version:02x}, "
            f"header_length={header_length}, prefix={len(data)} bytes)"
        )
    expected = (header_length - _DESCRIPTOR_START - 1) // _DESCRIPTOR_SIZE
    if expected > len(fields) and header_length > len(data):
        raise HeaderUnreadable(
            f"prefix holds {len(fields)} of about {expected} descriptors; "
            f"need {header_length} bytes, got {len(data)}"
        )
    return TableHeader(
        fields=fields,
        declared_records=declared_records,
        header_length=header_length,
        record_length=record_length,
        version=version,
    )


def prefix_bytes_needed(data: bytes) -> int:
    """How many bytes the header actually needs, read from the header itself.

    Lets a caller fetch a small speculative prefix and only widen it when the
    file says so, instead of always paying for the worst case.
    """
    if len(data) < 12:
        return DEFAULT_PREFIX_BYTES
    header_length = struct.unpack("<H", data[8:10])[0]
    return max(header_length, _DESCRIPTOR_START + _DESCRIPTOR_SIZE)
