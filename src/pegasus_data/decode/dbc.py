"""``.dbc`` reader — DATASUS's compressed DBF.

A ``.dbc`` is a DBF header followed by a PKWare-imploded/deflated payload. The
compression is a stream over the whole record block, so a byte range cannot be
decoded without inflating everything before it: **parallelise across files, never
within one** (§7.2). That property is also the architectural reason a ``.dbc`` is
slow to query and Parquet is not.

Decompression is delegated to ``datasus_dbc`` (a Rust extension wrapping the
original ``blast``-style decoder). It insists on filesystem paths, so callers
working from the blob store hand it a materialised path.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from .base import DecodedTable, DecodeError, UnsupportedContainer
from .dbf import read_dbf_bytes, read_dbf_file


def _decompress(src: Path, dst: Path) -> None:
    try:
        import datasus_dbc
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise UnsupportedContainer("datasus-dbc is required to read .dbc files") from exc
    try:
        datasus_dbc.decompress(str(src), str(dst))
    except Exception as exc:
        raise DecodeError(f"dbc decompression failed for {src.name}: {exc}") from exc


def read_dbc(
    path: str | Path,
    *,
    member: str = "",
    logical_path: str | None = None,
    columns: frozenset[str] | None = None,
    **kwargs: object,
) -> DecodedTable:
    """Decompress a ``.dbc`` FILE and read the result without a RAM copy of either.

    The cached path used to be: blob on disk -> whole compressed file into RAM
    -> written back out to a temp file -> inflated to a temp DBF -> whole
    inflated DBF into RAM. Four full copies of a file that never needed to
    leave the filesystem, and the inflated one is several times the size of the
    blob.

    Here the caller hands over a path (a hardlink to the blob costs nothing),
    the decompressor writes the DBF, and the DBF is read in blocks. The
    temporary directory has to outlive this call because of that last part, so
    it is attached to the table and removed when the table is dropped.
    """
    source = Path(path)
    tmp = tempfile.TemporaryDirectory(prefix="pegasus_dbc_")
    try:
        target = Path(tmp.name) / (source.stem + ".dbf")
        _decompress(source, target)
        if not target.exists() or target.stat().st_size == 0:
            raise DecodeError(f"dbc decompressed to an empty payload: {source}")
        table = read_dbf_file(
            target,
            logical_path=logical_path or str(source),
            member=member,
            reader="dbc",
            columns=columns,
            **kwargs,  # type: ignore[arg-type]
        )
    except BaseException:
        tmp.cleanup()
        raise
    table.retains = tmp
    return table


def read_dbc_bytes(data: bytes, *, path: str, member: str = "", **kwargs: object) -> DecodedTable:
    """Decode a ``.dbc`` held in memory by staging it on disk for the decoder."""
    with tempfile.TemporaryDirectory(prefix="pegasus_dbc_") as tmp:
        staged = Path(tmp) / "payload.dbc"
        staged.write_bytes(data)
        target = Path(tmp) / "payload.dbf"
        _decompress(staged, target)
        inflated = target.read_bytes()
    if not inflated:
        raise DecodeError(f"dbc decompressed to an empty payload: {path}")
    return read_dbf_bytes(inflated, path=path, member=member, reader="dbc", **kwargs)  # type: ignore[arg-type]
