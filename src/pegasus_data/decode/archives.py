"""Archive handling: zip, gzip, rar, 7z, and LHA self-extracting ``.exe`` (D1, D7).

Two rules, both learned from measured defects:

* **Return every member, with its role.** The prior implementation picked a
  single "best" member and discarded the rest. That is wrong twice over: an APAC
  ``.exe`` holds seven distinct schemas, and a ``TAB_*.zip`` kit holds ``.DEF``,
  ``.CNV`` and ``.DBF`` members *simultaneously* — the entire semantic layer would
  be thrown away to keep one lookup table.
* **Never let the suffix decide.** ``.exe`` is not an executable to skip, it is an
  LHA container holding an entire information system. Classification is by probe.
"""

from __future__ import annotations

import gzip
import io
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .base import DecodeError, UnsupportedContainer
from .lha import LhaArchive, LhaError, find_lha_offset

#: Member roles that steer downstream handling. A kit member is not "data".
ROLE_BY_SUFFIX: dict[str, str] = {
    ".dbc": "data", ".dbf": "lookup", ".csv": "data", ".txt": "data",
    ".json": "data", ".xml": "data", ".parquet": "data", ".xls": "data",
    ".xlsx": "data", ".duck": "data",
    ".def": "def", ".cnv": "cnv",
    ".pdf": "doc", ".doc": "doc", ".docx": "doc", ".hlp": "doc", ".cnt": "doc",
    ".htm": "doc", ".html": "doc", ".rtf": "doc",
    ".dll": "binary", ".exe": "binary", ".ini": "binary", ".bat": "binary",
}


@dataclass(slots=True)
class ArchiveMember:
    name: str
    size: int
    container: str
    role: str

    @property
    def suffix(self) -> str:
        return PurePosixPath(self.name.lower()).suffix


def classify_member(name: str) -> str:
    suffix = PurePosixPath(name.lower()).suffix
    return ROLE_BY_SUFFIX.get(suffix, "unknown")


def detect_container(data: bytes) -> str | None:
    """Identify the container from its magic bytes, not from its name."""
    if data[:4] == b"PK\x03\x04" or data[:4] == b"PK\x05\x06":
        return "zip"
    if data[:2] == b"\x1f\x8b":
        return "gzip"
    if data[:7] == b"Rar!\x1a\x07\x00" or data[:8] == b"Rar!\x1a\x07\x01\x00":
        return "rar"
    if data[:6] == b"7z\xbc\xaf\x27\x1c":
        return "7z"
    if data[257:262] == b"ustar":
        return "tar"
    if data[:2] == b"MZ":
        # A PE stub. What follows decides: LHA SFX (DATASUS APAC), or a zip SFX.
        if find_lha_offset(data) is not None:
            return "lha_sfx"
        if data.find(b"PK\x03\x04") != -1:
            return "zip_sfx"
        return "pe_unknown"
    if find_lha_offset(data[:4096]) is not None:
        return "lha"
    return None


class Archive:
    """Uniform read access over every archive container DATASUS actually uses."""

    def __init__(self, data: bytes, *, path: str) -> None:
        self.data = data
        self.path = path
        self.container = detect_container(data)
        if self.container is None:
            raise DecodeError(f"not a recognised archive container: {path}")
        self._zip: zipfile.ZipFile | None = None
        self._lha: LhaArchive | None = None
        self._tar: tarfile.TarFile | None = None
        self._tmp: tempfile.TemporaryDirectory[str] | None = None
        self._extracted: dict[str, Path] = {}
        self._open()

    # ------------------------------------------------------------------ setup

    def _open(self) -> None:
        kind = self.container
        if kind in {"zip", "zip_sfx"}:
            try:
                # ZipFile scans back from EOF for the central directory, so a
                # prepended SFX stub is transparent to it.
                self._zip = zipfile.ZipFile(io.BytesIO(self.data))
            except zipfile.BadZipFile as exc:
                raise DecodeError(f"zip open failed for {self.path}: {exc}") from exc
        elif kind in {"lha", "lha_sfx"}:
            try:
                self._lha = LhaArchive(self.data)
            except LhaError as exc:
                raise DecodeError(f"lha open failed for {self.path}: {exc}") from exc
        elif kind == "tar":
            self._tar = tarfile.open(fileobj=io.BytesIO(self.data))
        elif kind in {"rar", "7z"}:
            self._extract_external()
        elif kind == "gzip":
            pass
        else:
            raise DecodeError(f"unsupported container {kind} for {self.path}")

    def _extract_external(self) -> None:
        """RAR and 7z go through an external tool; both are rare and small here."""
        suffix = ".rar" if self.container == "rar" else ".7z"
        if self.container == "rar":
            try:
                import rarfile

                staged = self._stage(suffix)
                with rarfile.RarFile(str(staged)) as rf:
                    out = Path(self._tmpdir()) / "members"
                    out.mkdir(exist_ok=True)
                    rf.extractall(str(out))
                    self._collect(out)
                    return
            except Exception:
                pass  # fall through to 7z, which handles rar too
        exe = _find_7z()
        if exe is None:
            raise UnsupportedContainer(
                f"{self.container} archive needs 7-Zip (or `rarfile` with unrar) on PATH: {self.path}"
            )
        staged = self._stage(suffix)
        out = Path(self._tmpdir()) / "members"
        out.mkdir(exist_ok=True)
        proc = subprocess.run(
            [exe, "x", "-y", f"-o{out}", str(staged)], capture_output=True, timeout=900, check=False
        )
        if proc.returncode != 0 and not any(out.rglob("*")):
            raise DecodeError(
                f"7z failed on {self.path}: {proc.stderr.decode(errors='replace')[:400]}"
            )
        self._collect(out)

    def _tmpdir(self) -> str:
        if self._tmp is None:
            self._tmp = tempfile.TemporaryDirectory(prefix="pegasus_arc_")
        return self._tmp.name

    def _stage(self, suffix: str) -> Path:
        staged = Path(self._tmpdir()) / f"payload{suffix}"
        if not staged.exists():
            staged.write_bytes(self.data)
        return staged

    def _collect(self, root: Path) -> None:
        for p in sorted(root.rglob("*")):
            if p.is_file():
                self._extracted[str(p.relative_to(root)).replace("\\", "/")] = p

    # ---------------------------------------------------------------- members

    def members(self) -> list[ArchiveMember]:
        kind = self.container or ""
        out: list[ArchiveMember] = []
        if self._zip is not None:
            out = [
                ArchiveMember(i.filename, i.file_size, kind, classify_member(i.filename))
                for i in self._zip.infolist()
                if not i.is_dir()
            ]
        elif self._lha is not None:
            out = [
                ArchiveMember(m.name, m.original_size, kind, classify_member(m.name))
                for m in self._lha.members
                if not m.is_directory
            ]
        elif self._tar is not None:
            out = [
                ArchiveMember(m.name, m.size, kind, classify_member(m.name))
                for m in self._tar.getmembers()
                if m.isfile()
            ]
        elif self._extracted:
            out = [
                ArchiveMember(name, p.stat().st_size, kind, classify_member(name))
                for name, p in self._extracted.items()
            ]
        elif kind == "gzip":
            inner = _gzip_inner_name(self.path)
            out = [ArchiveMember(inner, 0, kind, classify_member(inner))]
        return out

    def read(self, name: str) -> bytes:
        if self._zip is not None:
            return self._zip.read(name)
        if self._lha is not None:
            return self._lha.read(name)
        if self._tar is not None:
            handle = self._tar.extractfile(name)
            if handle is None:
                raise KeyError(name)
            return handle.read()
        if self._extracted:
            return self._extracted[name].read_bytes()
        if self.container == "gzip":
            try:
                return gzip.decompress(self.data)
            except OSError as exc:
                raise DecodeError(f"gzip decompression failed for {self.path}: {exc}") from exc
        raise KeyError(name)

    def iter_members(self) -> Iterator[tuple[ArchiveMember, bytes]]:
        for member in self.members():
            try:
                yield member, self.read(member.name)
            except (KeyError, DecodeError, LhaError):
                continue

    # --------------------------------------------------------------- lifecycle

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()
        if self._tar is not None:
            self._tar.close()
        if self._tmp is not None:
            self._tmp.cleanup()
            self._tmp = None

    def __enter__(self) -> Archive:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _gzip_inner_name(path: str) -> str:
    name = PurePosixPath(path).name
    return name[:-3] if name.lower().endswith(".gz") else name


def _find_7z() -> str | None:
    exe = shutil.which("7z") or shutil.which("7za") or shutil.which("7zz")
    if exe:
        return exe
    for candidate in (r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if Path(candidate).is_file():
            return candidate
    return None
