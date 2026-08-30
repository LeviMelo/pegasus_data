"""First-party ``.dbc`` decompression: the container, and PKWare DCL explode.

Two engines for ONE algorithm, both in this repository:

* ``pegasus_blast.c`` — the native engine, compiled on demand into a DLL
  beside the source and loaded with ctypes. Memory to memory, no I/O, no
  printf, hard output bounds. This is what production decodes run on.
* :func:`_explode_py` — the same algorithm in Python, line for line. It is
  the engine on a machine with no C compiler, and the cross-check in tests:
  both engines must produce byte-identical output or the build fails.

This replaced two third-party decompressors and the pile of guards they
needed: one was 42x too slow (unbuffered byte I/O), the other printf()'d its
errors into what is an IPC pipe inside a decode worker and signalled failure
by silently writing a truncated file. Owning the 200 lines is cheaper than
guarding someone else's.
"""

from __future__ import annotations

import ctypes
import os
import struct
import subprocess
from pathlib import Path

_HERE = Path(__file__).resolve().parent
_SOURCE = _HERE / "pegasus_blast.c"
_DLL = _HERE / "pegasus_blast.dll"

#: Known self-contained MSVC installs to try, cheapest first. A full VS
#: install exposes cl.exe on PATH via vcvars; the ScopeCppSDK copy ships with
#: VS Community even when the C++ workload was never installed.
_SCOPE_SDK = Path(
    r"C:\Program Files\Microsoft Visual Studio\2022\Community\SDK\ScopeCppSDK\vc15"
)


class DbcError(ValueError):
    """The input is not a readable .dbc, and the message says why."""


_ERRORS = {
    -1: "literal-mode byte is not 0 or 1 — not a DCL stream",
    -2: "dictionary size byte outside 4..6 — not a DCL stream",
    -3: "back-reference before the start of output — corrupt stream",
    -4: "compressed stream ended mid-symbol — truncated input",
    -5: "stream expands past what the DBF header promised — corrupt stream",
    -6: "bit pattern matches no symbol — corrupt stream",
}


def _build_dll() -> bool:
    """Compile the native engine beside its source. True when a DLL is ready."""
    if _DLL.exists() and _DLL.stat().st_mtime >= _SOURCE.stat().st_mtime:
        return True
    compilers: list[tuple[str, dict[str, str]]] = []
    if (_SCOPE_SDK / "VC" / "bin" / "cl.exe").exists():
        compilers.append((
            str(_SCOPE_SDK / "VC" / "bin" / "cl.exe"),
            {
                # cl.exe needs its own bin on PATH for mspdb DLLs, and the
                # ucrt/shared/um SDK splits spelled out: this is the layout the
                # ScopeCppSDK actually ships, not the vcvars one.
                "PATH": str(_SCOPE_SDK / "VC" / "bin") + ";" + os.environ.get("PATH", ""),
                "INCLUDE": ";".join((
                    str(_SCOPE_SDK / "VC" / "include"),
                    str(_SCOPE_SDK / "SDK" / "include" / "ucrt"),
                    str(_SCOPE_SDK / "SDK" / "include" / "shared"),
                    str(_SCOPE_SDK / "SDK" / "include" / "um"),
                )),
                "LIB": ";".join((
                    str(_SCOPE_SDK / "VC" / "lib"),
                    str(_SCOPE_SDK / "SDK" / "lib"),
                )),
            },
        ))
    compilers.append(("cl.exe", {}))  # a vcvars shell, if the user runs in one
    for exe, extra in compilers:
        env = {**os.environ, **extra}
        try:
            result = subprocess.run(
                [exe, "/nologo", "/O2", "/LD",
                 str(_SOURCE), f"/Fe:{_DLL}", f"/Fo:{_HERE / 'pegasus_blast.obj'}"],
                capture_output=True, env=env, cwd=str(_HERE), timeout=120,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if result.returncode == 0 and _DLL.exists():
            return True
    return False


_native = None
_native_tried = False


def _load_native():
    global _native, _native_tried
    if _native_tried:
        return _native
    _native_tried = True
    try:
        if _build_dll():
            lib = ctypes.CDLL(str(_DLL))
            lib.pegasus_explode.restype = ctypes.c_int
            lib.pegasus_explode.argtypes = [
                ctypes.c_char_p, ctypes.c_size_t,
                ctypes.POINTER(ctypes.c_ubyte), ctypes.c_size_t,
                ctypes.POINTER(ctypes.c_size_t),
            ]
            _native = lib
    except OSError:
        _native = None
    return _native


# ------------------------------------------------------------ the algorithm
# The Python engine. Kept structurally identical to pegasus_blast.c so a reader
# can diff the two; see the C file for the format commentary.

_MAXBITS = 13
_LITLEN = bytes([
    11, 124, 8, 7, 28, 7, 188, 13, 76, 4, 10, 8, 12, 10, 12, 10, 8, 23, 8,
    9, 7, 6, 7, 8, 7, 6, 55, 8, 23, 24, 12, 11, 7, 9, 11, 12, 6, 7, 22, 5,
    7, 24, 6, 11, 9, 6, 7, 22, 7, 11, 38, 7, 9, 8, 25, 11, 8, 11, 9, 12,
    8, 12, 5, 38, 5, 38, 5, 11, 7, 5, 6, 21, 6, 10, 53, 8, 7, 24, 10, 27,
    44, 253, 253, 253, 252, 252, 252, 13, 12, 45, 12, 45, 12, 61, 12, 45,
    44, 173])
_LENLEN = bytes([2, 35, 36, 53, 38, 23])
_DISTLEN = bytes([2, 20, 53, 230, 247, 151, 248])
_BASE = (3, 2, 4, 5, 6, 7, 8, 9, 10, 12, 16, 24, 40, 72, 136, 264)
_EXTRA = (0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8)


def _construct(rep: bytes) -> tuple[list[int], list[int]]:
    lengths: list[int] = []
    for byte in rep:
        lengths.extend([byte & 15] * ((byte >> 4) + 1))
    count = [0] * (_MAXBITS + 1)
    for item in lengths:
        count[item] += 1
    left = 1
    for length in range(1, _MAXBITS + 1):
        left = (left << 1) - count[length]
        if left < 0:
            raise DbcError("internal: over-subscribed Huffman table")
    if left != 0:
        raise DbcError("internal: incomplete Huffman table")
    offs = [0] * (_MAXBITS + 2)
    for length in range(1, _MAXBITS):
        offs[length + 1] = offs[length] + count[length]
    symbol = [0] * len(lengths)
    for index, length in enumerate(lengths):
        if length:
            symbol[offs[length]] = index
            offs[length] += 1
    return count, symbol


_LITCODE = _construct(_LITLEN)
_LENCODE = _construct(_LENLEN)
_DISTCODE = _construct(_DISTLEN)
#: The three fixed codes built without complaint at import.
_CONSTRUCTED_OK = True


def _explode_py(data: bytes, outcap: int) -> bytes:
    pos = 0
    n = len(data)
    bitbuf = 0
    bitcnt = 0
    out = bytearray()

    def bits(need: int) -> int:
        nonlocal pos, bitbuf, bitcnt
        val = bitbuf
        while bitcnt < need:
            if pos >= n:
                raise DbcError(_ERRORS[-4])
            val |= data[pos] << bitcnt
            pos += 1
            bitcnt += 8
        bitbuf = val >> need
        bitcnt -= need
        return val & ((1 << need) - 1)

    def decode(code: tuple[list[int], list[int]]) -> int:
        nonlocal pos, bitbuf, bitcnt
        count, symbol = code
        length = 1
        codeword = first = index = 0
        buf = bitbuf
        left = bitcnt
        while True:
            while left:
                left -= 1
                codeword |= (buf & 1) ^ 1
                buf >>= 1
                cnt = count[length]
                if codeword - cnt < first:
                    bitbuf = buf
                    bitcnt = (bitcnt - length) & 7
                    return symbol[index + (codeword - first)]
                index += cnt
                first = (first + cnt) << 1
                codeword <<= 1
                length += 1
            left = (_MAXBITS + 1) - length
            if left == 0:
                raise DbcError(_ERRORS[-6])
            if pos >= n:
                raise DbcError(_ERRORS[-4])
            buf = data[pos]
            pos += 1
            left = min(left, 8)

    lit = bits(8)
    if lit > 1:
        raise DbcError(_ERRORS[-1])
    dict_size = bits(8)
    if dict_size < 4 or dict_size > 6:
        raise DbcError(_ERRORS[-2])

    while True:
        if bits(1):
            symbol = decode(_LENCODE)
            length = _BASE[symbol] + bits(_EXTRA[symbol])
            if length == 519:
                break
            low = 2 if length == 2 else dict_size
            dist = (decode(_DISTCODE) << low) + bits(low) + 1
            if dist > len(out):
                raise DbcError(_ERRORS[-3])
            if len(out) + length > outcap:
                raise DbcError(_ERRORS[-5])
            for _ in range(length):
                out.append(out[-dist])
        else:
            if len(out) >= outcap:
                raise DbcError(_ERRORS[-5])
            out.append(decode(_LITCODE) if lit else bits(8))
    return bytes(out)


def explode(data: bytes, outcap: int) -> bytes:
    """Decompress one DCL stream into at most ``outcap`` bytes."""
    lib = _load_native()
    if lib is None:
        return _explode_py(data, outcap)
    out = (ctypes.c_ubyte * outcap)()
    outlen = ctypes.c_size_t(0)
    rc = lib.pegasus_explode(data, len(data), out, outcap, ctypes.byref(outlen))
    if rc != 0:
        raise DbcError(_ERRORS.get(rc, f"explode failed with code {rc}"))
    return bytes(out[: outlen.value])


# -------------------------------------------------------------- the container


def dbc_to_dbf_bytes(data: bytes) -> bytes:
    """One .dbc's bytes -> the DBF it contains.

    Layout: the first ``header_len`` bytes are the DBF header stored RAW
    (``header_len`` read from the DBF's own field at offset 8), then a 4-byte
    CRC, then the DCL stream of the records. The header's arithmetic bounds
    the output — a stream that wants more than
    ``n_records * record_len (+ EOF byte)`` is corrupt by definition.
    """
    if len(data) < 12:
        raise DbcError("shorter than a DBF header prefix — not a .dbc")
    n_records, header_len, record_len = struct.unpack_from("<IHH", data, 4)
    if header_len < 32 or header_len > len(data):
        raise DbcError("stored header length is impossible — not a .dbc")
    body_cap = n_records * max(record_len, 1) + 1  # records + optional 0x1A EOF
    stream = data[header_len + 4 :]  # skip the 4-byte CRC after the header
    body = explode(stream, body_cap)
    if len(body) < n_records * max(record_len, 1):
        raise DbcError(
            f"stream inflated to {len(body)} bytes; the header promises "
            f"{n_records} records of {record_len} — truncated input"
        )
    header = bytearray(data[:header_len])
    # The container sometimes stores 0x00 where the DBF field-descriptor
    # terminator (0x0D) belongs, at header_len - 1. Every reference
    # implementation normalises it on the way out; a reader that trusts the
    # terminator would otherwise walk past the descriptors. Measured on
    # CNES-ST, whose stored headers carry the 0x00.
    header[header_len - 1] = 0x0D
    return bytes(header) + body


def dbc_file_to_dbf(src: str | Path, dst: str | Path) -> None:
    """File-level convenience with the same guarantees."""
    payload = Path(src).read_bytes()
    Path(dst).write_bytes(dbc_to_dbf_bytes(payload))
