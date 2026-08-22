"""Fast, vectorised dBase III/IV/FoxPro reader.

DBF is the backbone of DATASUS: every ``.dbc`` inflates to one, and every kit
lookup table is one. A row-at-a-time Python reader is the wrong tool at 12,000
files and a 113-column modern SIH schema, so this reader slices the record block
with NumPy and hands Arrow a zero-copy string array per column (P3).

Values come back as **strings, trimmed of the fixed-width padding**, with the
declared type letter, width and decimal count preserved in ``FieldMeta``. Blank
fields become nulls — that is padding, not a code. Sentinels like ``9`` or
``9999`` are emphatically *not* touched here; they are per-field and
ledger-driven at normalisation time (§13).
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

from ..textenc import best_effort_decode
from .base import DecodedTable, DecodeError, FieldMeta

#: DATASUS mixes DOS-era cp850 with Windows-era cp1252 across its 35 years and
#: marks neither; the choice is scored, not ordered (see ``pegasus_data.textenc``).
DEFAULT_ENCODINGS = ("cp850", "cp1252", "latin-1")

_TERMINATOR = 0x0D


class DbfHeader:
    __slots__ = ("version", "n_records", "header_len", "record_len", "fields", "has_memo")

    def __init__(self, data: memoryview) -> None:
        if len(data) < 32:
            raise DecodeError("file is too short to be a DBF")
        self.version = data[0]
        self.n_records, self.header_len, self.record_len = struct.unpack_from("<IHH", data, 4)
        if self.header_len < 33 or self.record_len < 1:
            raise DecodeError(f"implausible DBF header (header_len={self.header_len}, record_len={self.record_len})")
        self.has_memo = bool(self.version & 0x88) or self.version in (0x83, 0x8B, 0xF5, 0xFB)
        self.fields: list[FieldMeta] = []
        pos = 32
        order = 0
        while pos + 32 <= self.header_len and data[pos] != _TERMINATOR:
            raw_name = bytes(data[pos : pos + 11]).split(b"\x00", 1)[0]
            name = raw_name.decode("ascii", errors="replace").strip().upper()
            type_letter = chr(data[pos + 11])
            width = data[pos + 16]
            decimals = data[pos + 17]
            if not name:
                name = f"FIELD_{order + 1}"
            self.fields.append(
                FieldMeta(
                    name=name,
                    physical_type=type_letter,
                    width=width or None,
                    decimals=decimals or None,
                    order=order,
                )
            )
            order += 1
            pos += 32
        if not self.fields:
            raise DecodeError("DBF header declares no fields")

    @property
    def field_offsets(self) -> list[int]:
        offsets: list[int] = []
        cursor = 1
        for f in self.fields:
            offsets.append(cursor)
            cursor += f.width or 0
        return offsets


def _dedupe(names: list[str]) -> list[str]:
    """DBF permits duplicate column names; Arrow does not enjoy them."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for name in names:
        if name in seen:
            seen[name] += 1
            out.append(f"{name}_{seen[name]}")
        else:
            seen[name] = 0
            out.append(name)
    return out


def _string_array(block: np.ndarray, offset: int, width: int, encoding: str) -> pa.Array:
    """Build an Arrow string column from a fixed-width slice of the record block.

    The happy path is zero-copy: the slice's bytes become the values buffer and
    the offsets are pure arithmetic. Only when the bytes are not valid UTF-8 do we
    pay for a transcode, which is rare — DATASUS payloads are overwhelmingly
    digits and uppercase ASCII, with accents confined to name/description fields.
    """
    n = block.shape[0]
    if n == 0:
        return pa.array([], type=pa.string())
    sub = np.ascontiguousarray(block[:, offset : offset + width])
    values = sub.tobytes()
    offsets = np.arange(0, (n + 1) * width, width, dtype=np.int32)
    binary = pa.Array.from_buffers(
        pa.binary(), n, [None, pa.py_buffer(offsets), pa.py_buffer(values)]
    )
    try:
        arr = binary.cast(pa.string())
    except pa.ArrowInvalid:
        text = values.decode(encoding, errors="replace")
        arr = pa.array([text[i * width : (i + 1) * width] for i in range(n)], type=pa.string())
    arr = pc.utf8_trim(arr, characters=" \t\r\n\x00")
    return pc.if_else(pc.equal(arr, ""), pa.scalar(None, pa.string()), arr)


def _batch_from_block(
    block: np.ndarray,
    header: DbfHeader,
    offsets: list[int],
    encoding: str,
    wanted: list[int] | None = None,
) -> pa.RecordBatch:
    """One Arrow batch from one fixed-width record block.

    ``wanted`` restricts which fields are MATERIALISED. Decompressing the row
    stream is unavoidable, but building Arrow arrays for 200 columns when three
    were asked for is not: measured on a 208-field CNES-ST payload, column
    construction was 74% of the decode.
    """
    # Byte 0 of a record is ' ' for live rows and '*' for deleted ones.
    deleted = block[:, 0] == 0x2A
    indices = range(len(header.fields)) if wanted is None else wanted
    columns = [
        _string_array(block, offsets[i], header.fields[i].width or 0, encoding)
        for i in indices
    ]
    batch = pa.RecordBatch.from_arrays(
        columns, names=[header.fields[i].name for i in indices]
    )
    if deleted.any():
        keep = pa.array(~deleted)
        batch = pa.RecordBatch.from_struct_array(pc.filter(batch.to_struct_array(), keep))
    return batch


def read_dbf_bytes(
    data: bytes,
    *,
    path: str,
    member: str = "",
    reader: str = "dbf",
    encoding: str | None = None,
    batch_rows: int = 65_536,
    row_limit: int | None = None,
    columns: frozenset[str] | None = None,
) -> DecodedTable:
    """Decode a whole DBF held in memory.

    ``columns`` restricts which fields are MATERIALISED, exactly as in
    :func:`read_dbf_file`. This path is taken by every archive member and every
    ladder fallback, so leaving it unprojected meant a narrow request still
    built all 200 columns whenever the source was not a loose file.
    """
    view = memoryview(data)
    header = DbfHeader(view)
    encoding = encoding or _sniff_encoding(data, header)
    offsets = header.field_offsets
    names = _dedupe([f.name for f in header.fields])
    for f, name in zip(header.fields, names, strict=True):
        f.name = name

    body_start = header.header_len
    record_len = header.record_len
    available = max(0, (len(data) - body_start) // record_len)
    declared = header.n_records
    # MEASURED, because the direction of the staleness decides the rule and
    # guessing it wrong loses data either way.
    #
    # Over 132 real DBF payloads decoded from the blob cache: 116 agree,
    # **16 declare MORE records than the file physically holds, and none
    # declares fewer**. So the header errs high, and `min()` is what stops a
    # read running past the end of the buffer and manufacturing rows out of
    # whatever follows.
    #
    # An external review argued the opposite — that `min()` silently truncates
    # valid trailing records when the header is stale LOW — and asked for the
    # corpus to be characterised before changing anything. It was, and on this
    # corpus stale-low does not occur. The mismatch is reported either way, so a
    # file that does hold more than it admits is visible rather than silent.
    n_records = min(declared, available) if declared else available
    warnings: list[str] = []
    if declared and declared != available:
        direction = "more" if declared > available else "fewer"
        warnings.append(f"header_declares_{declared}_records_file_holds_{available}")
        warnings.append(f"header_declares_{direction}_than_the_file_holds")

    if row_limit is not None:
        n_records = min(n_records, row_limit)

    wanted_indices: list[int] | None = None
    if columns:
        upper = {c.upper() for c in columns}
        wanted_indices = [i for i, f in enumerate(header.fields) if f.name.upper() in upper]
        if not wanted_indices:
            wanted_indices = None  # nothing matched; read everything, not nothing

    def _iter_batches() -> Iterator[pa.RecordBatch]:
        produced = 0
        while produced < n_records:
            take = min(batch_rows, n_records - produced)
            start = body_start + produced * record_len
            block = np.frombuffer(data, dtype=np.uint8, count=take * record_len, offset=start)
            produced += take
            yield _batch_from_block(
                block.reshape(take, record_len), header, offsets, encoding, wanted_indices
            )

    return DecodedTable(
        path=path,
        member=member,
        reader=reader,
        fields=header.fields,
        batches=_iter_batches,
        row_count=n_records,
        warnings=warnings,
    )


def _encoding_from_sample(sample: bytes) -> str:
    """The half of :func:`_sniff_encoding` that only needs the sample."""
    if not sample or sample.isascii():
        return "cp850"
    _, encoding = best_effort_decode(sample, candidates=DEFAULT_ENCODINGS)
    return encoding


def _sniff_encoding(data: bytes, header: DbfHeader) -> str:
    """Pick the codepage whose decoding of a sample reads as Portuguese.

    "First codepage that does not raise" is useless here: cp850 and latin-1 both
    map all 256 byte values, so the first candidate always wins regardless of
    whether it is right (see ``pegasus_data.textenc``). The DBF language-driver
    byte at offset 29 is unreliable across DATASUS's 35 years, so it only breaks
    ties between equally-scoring candidates.
    """
    sample = data[header.header_len : header.header_len + 512 * (header.record_len or 1)]
    return _encoding_from_sample(bytes(sample))


def read_dbf(path: str | Path, **kwargs: object) -> DecodedTable:
    p = Path(path)
    return read_dbf_bytes(p.read_bytes(), path=str(p), **kwargs)  # type: ignore[arg-type]


def read_dbf_file(
    path: str | Path,
    *,
    logical_path: str | None = None,
    member: str = "",
    reader: str = "dbf",
    encoding: str | None = None,
    batch_rows: int = 65_536,
    row_limit: int | None = None,
    columns: frozenset[str] | None = None,
) -> DecodedTable:
    """Decode a DBF that is already a file, without ever holding it in RAM.

    `read_dbf_bytes` needs the whole payload resident because every batch is a
    view into one buffer. Here each batch is `pread` straight from the file, so
    peak memory is one block — 65,536 records — however large the file is. A
    CNES establishment DBF inflates past 150 MB; decoding one used to cost that
    much resident memory per worker, times the worker count.

    The blocks are copied into their own buffers (`np.frombuffer` over the bytes
    just read), so the Arrow arrays do NOT alias the file. That is what makes
    this safe where an mmap would not be: nothing dangles once the handle is
    closed, and the generator can be re-run.
    """
    src = Path(path)
    logical = logical_path or str(src)
    file_size = src.stat().st_size
    with src.open("rb") as fh:
        head = fh.read(min(file_size, 1 << 20))
        header = DbfHeader(memoryview(head))
        record_len = header.record_len
        body_start = header.header_len
        if encoding is None:
            fh.seek(body_start)
            encoding = _encoding_from_sample(fh.read(512 * (record_len or 1)))

    offsets = header.field_offsets
    names = _dedupe([f.name for f in header.fields])
    for f, name in zip(header.fields, names, strict=True):
        f.name = name

    available = max(0, (file_size - body_start) // record_len) if record_len else 0
    declared = header.n_records
    # Same rule, same evidence as read_dbf_bytes: measured over 132 real
    # payloads the header errs HIGH (16 declare more than the file holds, none
    # fewer), so min() is what stops a read running past the end.
    n_records = min(declared, available) if declared else available
    warnings: list[str] = []
    if declared and declared != available:
        direction = "more" if declared > available else "fewer"
        warnings.append(f"header_declares_{declared}_records_file_holds_{available}")
        warnings.append(f"header_declares_{direction}_than_the_file_holds")
    if row_limit is not None:
        n_records = min(n_records, row_limit)

    # WHICH fields to materialise. `fields` stays the full header either way:
    # it is what the family's schema is matched against, and narrowing it would
    # make a projected read look like a different generation.
    wanted_indices: list[int] | None = None
    if columns:
        upper = {c.upper() for c in columns}
        wanted_indices = [
            i for i, f in enumerate(header.fields) if f.name.upper() in upper
        ]
        if not wanted_indices:
            wanted_indices = None  # nothing matched; read everything rather than nothing

    def _iter_batches() -> Iterator[pa.RecordBatch]:
        produced = 0
        with src.open("rb") as handle:
            while produced < n_records:
                take = min(batch_rows, n_records - produced)
                handle.seek(body_start + produced * record_len)
                raw = handle.read(take * record_len)
                take = len(raw) // record_len
                if take == 0:
                    return
                block = np.frombuffer(raw, dtype=np.uint8, count=take * record_len)
                produced += take
                yield _batch_from_block(
                    block.reshape(take, record_len),
                    header,
                    offsets,
                    encoding or "cp850",
                    wanted_indices,
                )

    return DecodedTable(
        path=logical,
        member=member,
        reader=reader,
        fields=header.fields,
        batches=_iter_batches,
        row_count=n_records,
        warnings=warnings,
    )
