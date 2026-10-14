"""Fast, vectorised dBase III/IV/7 and FoxPro reader.

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
from collections.abc import Iterable, Iterator
from pathlib import Path

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc

from ..textenc import best_effort_decode
from .base import DecodedTable, DecodeError, FieldMeta
from .header import descriptor_layout, descriptor_widths

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
        pos, size, name_len, type_at = descriptor_layout(self.version)
        order = 0
        while pos + size <= self.header_len and data[pos] != _TERMINATOR:
            raw_name = bytes(data[pos : pos + name_len]).split(b"\x00", 1)[0]
            name = raw_name.decode("ascii", errors="replace").strip().upper()
            type_letter = chr(data[pos + type_at])
            width, decimals = descriptor_widths(bytes(data[pos : pos + size]), 0, self.version, type_at)
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
            pos += size
        if not self.fields:
            raise DecodeError("DBF header declares no fields")
        # a payload of another format read as a header (Parquet's PAR1, 2026-10-09: 88 "records" and a zero-width field
        # that crashed the batch): every field has a width, and the widths fit in the record after its deletion byte
        if any(not f.width for f in self.fields):
            raise DecodeError("a DBF field has width 0: not a DBF")
        if sum(f.width or 0 for f in self.fields) + 1 > self.record_len:
            raise DecodeError(f"the fields' widths exceed the record length {self.record_len}: not a DBF")

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
    strict_size: bool = False,
) -> DecodedTable:
    """Decode a whole DBF held in memory.

    ``columns`` restricts which fields are MATERIALISED, exactly as in
    :func:`read_dbf_file`. This path is taken by every archive member and every
    ladder fallback, so leaving it unprojected meant a narrow request still
    built all 200 columns whenever the source was not a loose file.
    """
    view = memoryview(data)
    header = DbfHeader(view)
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

    if strict_size and declared > available:
        raise _short_body(declared, available)

    if row_limit is not None:
        n_records = min(n_records, row_limit)

    encoding = encoding or _sniff_encoding(data, header, n_records, warnings)

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


#: Records scanned per block when looking for the first non-ASCII byte (a block of this many records, ~8 MiB at
#: 128-byte records, costs one vectorised comparison).
_SCAN_ROWS = 1 << 16
#: Records carrying non-ASCII bytes that settle the codepage.
_SAMPLE_RECORDS = 512


def _accented_sample(blocks: Iterable[np.ndarray], record_len: int) -> bytes:
    """The records of the file that hold a byte above 127, up to `_SAMPLE_RECORDS` of them.

    The codepage matters only where a byte above 127 occurs, so the whole file is scanned (one comparison per block)
    and the evidence is taken wherever it first appears, not from the first 512 records: a file sorted so that its
    accents start at record 1,501 decoded `JOSÉ AÇÃO` as `JOS╔ AÃ├O` (the sample was ASCII, so cp850 was assumed for
    the whole file)."""
    gathered: list[bytes] = []
    have = 0
    for flat in blocks:
        if flat.size == 0:
            continue
        high = flat > 127
        if not high.any():
            continue
        rows = np.unique(np.flatnonzero(high) // record_len)[: _SAMPLE_RECORDS - have]
        gathered.append(flat.reshape(-1, record_len)[rows].tobytes())
        have += len(rows)
        if have >= _SAMPLE_RECORDS:
            break
    return b"".join(gathered)


def _file_encoding(blocks: Iterable[np.ndarray], record_len: int, warnings: list[str]) -> str:
    """One codepage for the whole file, scored on the records that show it; recorded when it mattered."""
    sample = _accented_sample(blocks, record_len)
    if not sample:
        return "cp850"  # every byte is ASCII: all candidates agree
    _, encoding = best_effort_decode(sample, candidates=DEFAULT_ENCODINGS)
    warnings.append(f"encoding:{encoding}")
    return encoding


def _sniff_encoding(
    data: bytes, header: DbfHeader, n_records: int | None = None, warnings: list[str] | None = None
) -> str:
    """The codepage of a DBF held in memory, from the records that show one (the whole body is scanned)."""
    record_len = header.record_len
    rows = (len(data) - header.header_len) // record_len
    rows = rows if n_records is None else min(rows, n_records)
    body = np.frombuffer(data, dtype=np.uint8, count=max(rows, 0) * record_len, offset=header.header_len)
    step = _SCAN_ROWS * record_len
    return _file_encoding(
        (body[at : at + step] for at in range(0, body.size, step)), record_len, [] if warnings is None else warnings
    )


def _short_body(declared: int, available: int) -> DecodeError:
    return DecodeError(
        f"the header declares {declared} records and the body holds {available}: a payload read after a failed "
        "inflation is the compressed stream, not records"
    )


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
    strict_size: bool = False,
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
    if strict_size and declared > available:
        raise _short_body(declared, available)
    if row_limit is not None:
        n_records = min(n_records, row_limit)

    if encoding is None:
        def _blocks() -> Iterator[np.ndarray]:
            with src.open("rb") as scan:
                scan.seek(body_start)
                left = n_records
                while left > 0:
                    raw = scan.read(min(left, _SCAN_ROWS) * record_len)
                    rows = len(raw) // record_len
                    if rows == 0:
                        return
                    left -= rows
                    yield np.frombuffer(raw, dtype=np.uint8, count=rows * record_len)

        encoding = _file_encoding(_blocks(), record_len, warnings)

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
