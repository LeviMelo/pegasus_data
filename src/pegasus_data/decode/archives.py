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
import re
import shutil
import subprocess
import tarfile
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from ..formats import SUFFIXES
from ..locate import scratch_dir
from .base import DecodeError, UnsupportedContainer
from .lha import LhaArchive, LhaError, find_lha_offset

#: Budgets an archive may not exceed. Not a hypothetical: a corrupt archive and
#: a hostile one exhaust the same resources in the same way, and DATASUS
#: archives are remote input that nobody here produced. Generous enough that no
#: real DATASUS member comes close — the largest observed uncompressed member is
#: a few hundred MB — and finite, which is the point.
MAX_MEMBERS = 10_000
MAX_UNCOMPRESSED_BYTES = 8 * 1024**3
MAX_EXPANSION_RATIO = 200.0


class ArchiveQuotaExceeded(DecodeError):
    """An archive claims more than the decoder will spend on it."""


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
    return (SUFFIXES[suffix].member_role if suffix in SUFFIXES else None) or "unknown"


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
        #: Members refused during extraction, so a skipped file is named rather
        #: than silently absent.
        self.warnings: list[str] = []
        self._open()

    # ------------------------------------------------------------------ setup

    def _open(self) -> None:
        kind = self.container
        if kind in {"zip", "zip_sfx"}:
            try:
                # ZipFile scans back from EOF for the central directory, so a
                # prepended SFX stub is transparent to it.
                self._zip = zipfile.ZipFile(io.BytesIO(self.data))
                self._refuse_unsafe_names([i.filename for i in self._zip.infolist()])
                self._check_quota([i.file_size for i in self._zip.infolist()])
            except zipfile.BadZipFile as exc:
                raise DecodeError(f"zip open failed for {self.path}: {exc}") from exc
        elif kind in {"lha", "lha_sfx"}:
            try:
                self._lha = LhaArchive(self.data)
                members = [m for m in self._lha.members if not m.is_directory]
                self._refuse_unsafe_names([m.name for m in members])
                self._check_quota([m.original_size for m in members])
            except LhaError as exc:
                raise DecodeError(f"lha open failed for {self.path}: {exc}") from exc
        elif kind == "tar":
            self._tar = tarfile.open(fileobj=io.BytesIO(self.data))
            tar_members = [m for m in self._tar.getmembers() if m.isfile()]
            self._refuse_unsafe_names([m.name for m in tar_members])
            self._check_quota([m.size for m in tar_members])
        elif kind in {"rar", "7z"}:
            self._extract_external()
        elif kind == "gzip":
            # RFC 1952 stores the uncompressed size modulo 2**32 in ISIZE.
            # It is enough to reject ordinary bombs before inflation; the
            # bounded streaming reader below also covers wraparound and lies.
            claimed = int.from_bytes(self.data[-4:], "little") if len(self.data) >= 4 else 0
            self._check_quota([claimed])
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
                    # BEFORE extraction, not after. Checking containment once
                    # the files are on disk is too late: a hostile member path
                    # has already been written outside the staging directory by
                    # then, and rarfile/7z sanitising is not ours to assume.
                    self._refuse_unsafe_names(
                        [getattr(i, "filename", "") for i in rf.infolist()]
                    )
                    self._check_quota(
                        [getattr(i, "file_size", 0) or 0 for i in rf.infolist()]
                    )
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
        # LIST first, so an unsafe member name or an implausible expansion is
        # refused before anything is written. `7z l -slt` names every member
        # without extracting one.
        listing = subprocess.run(
            [exe, "l", "-slt", str(staged)], capture_output=True, timeout=300, check=False
        )
        if listing.returncode == 0:
            names, sizes = _parse_7z_listing(listing.stdout.decode(errors="replace"))
            self._refuse_unsafe_names(names)
            self._check_quota(sizes)
        proc = subprocess.run(
            [exe, "x", "-y", f"-o{out}", str(staged)], capture_output=True, timeout=900, check=False
        )
        if proc.returncode != 0 and not any(out.rglob("*")):
            raise DecodeError(
                f"7z failed on {self.path}: {proc.stderr.decode(errors='replace')[:400]}"
            )
        self._collect(out)

    def _refuse_unsafe_names(self, names: list[str]) -> None:
        """Reject a member path that would escape the extraction root.

        `safe_member_path` is applied to what came OUT of extraction as well.
        This is the half that has to happen first: by the time a file exists,
        an absolute path or a `..` has already been honoured.
        """
        root = Path(self._tmpdir()).resolve()
        for name in names:
            if not name:
                continue
            if safe_member_path(name, root) is None:
                raise DecodeError(
                    f"{self.path}: archive member {name!r} would be written outside "
                    "the extraction directory; refusing to extract this archive"
                )

    def _check_quota(self, sizes: list[int]) -> None:
        """Refuse an archive that claims more than we will spend on it."""
        if len(sizes) > MAX_MEMBERS:
            raise ArchiveQuotaExceeded(
                f"{self.path}: {len(sizes):,} members exceeds the {MAX_MEMBERS:,} limit"
            )
        total = sum(s for s in sizes if s and s > 0)
        if total > MAX_UNCOMPRESSED_BYTES:
            raise ArchiveQuotaExceeded(
                f"{self.path}: members declare {total / 1024**3:.1f} GiB uncompressed, "
                f"over the {MAX_UNCOMPRESSED_BYTES / 1024**3:.0f} GiB limit"
            )
        compressed = max(1, len(self.data))
        if total and total / compressed > MAX_EXPANSION_RATIO:
            raise ArchiveQuotaExceeded(
                f"{self.path}: expands {total / compressed:.0f}x, over the "
                f"{MAX_EXPANSION_RATIO:.0f}x limit; this is what a decompression "
                "bomb looks like and also what a corrupt header looks like"
            )

    def _tmpdir(self) -> str:
        if self._tmp is None:
            self._tmp = tempfile.TemporaryDirectory(prefix="pegasus_arc_", dir=scratch_dir())
        return self._tmp.name

    def _stage(self, suffix: str) -> Path:
        staged = Path(self._tmpdir()) / f"payload{suffix}"
        if not staged.exists():
            staged.write_bytes(self.data)
        return staged

    def _collect(self, root: Path) -> None:
        # Re-checked against the resolved root, not trusted. RAR and 7z
        # extraction is handed to external tools whose sanitising we neither
        # control nor should assume, and DATASUS archives are remote input. A
        # member that resolves outside the extraction directory — through
        # ``..`` or a symlink the backend followed — is skipped and named.
        anchor = root.resolve()
        for p in sorted(root.rglob("*")):
            if not p.is_file():
                continue
            try:
                p.resolve().relative_to(anchor)
            except ValueError:
                self.warnings.append(
                    f"refused an extracted member outside the extraction root: {p.name}"
                )
                continue
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
                source = io.BytesIO(self.data)
                chunks: list[bytes] = []
                total = 0
                ratio_limit = max(1, int(len(self.data) * MAX_EXPANSION_RATIO))
                ceiling = min(MAX_UNCOMPRESSED_BYTES, ratio_limit)
                with gzip.GzipFile(fileobj=source) as stream:
                    while chunk := stream.read(1024 * 1024):
                        total += len(chunk)
                        if total > ceiling:
                            raise ArchiveQuotaExceeded(
                                f"{self.path}: gzip expansion exceeded the configured "
                                f"{MAX_EXPANSION_RATIO:.0f}x/{MAX_UNCOMPRESSED_BYTES / 1024**3:.0f} GiB limits"
                            )
                        chunks.append(chunk)
                return b"".join(chunks)
            except OSError as exc:
                raise DecodeError(f"gzip decompression failed for {self.path}: {exc}") from exc
        raise KeyError(name)

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


class ArchiveFile:
    """An archive on disk read one member at a time, never held in memory: zip, and RAR through 7-Zip.

    `Archive` above takes an archive's bytes and returns every member with its role, which is what a DATASUS file needs
    (an APAC ``.exe`` holds seven schemas). An intake source is the other case: a file of megabytes to gigabytes whose one
    table is streamed out to disk. Both are archives, so both live here: the container is told by its first bytes, never
    its suffix, and a member whose name would leave the folder is refused. Before 2026-11-28 `intake.py` opened zips in
    four places of its own and RARs in a fifth, each choosing "the one member" its own way."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        with self.path.open("rb") as handle:
            self.container = detect_container(handle.read(4096))
        if self.container in ("zip", "zip_sfx"):
            self._archive: zipfile.ZipFile | object = zipfile.ZipFile(self.path)
        elif self.container == "rar":
            import rarfile

            tool = _find_7z()
            if tool is None:
                raise UnsupportedContainer(f"{self.path.name}: a RAR archive needs 7-Zip (7z on PATH or in Program Files)")
            rarfile.SEVENZIP_TOOL = tool
            rarfile.tool_setup(unrar=False, unar=False, bsdtar=False, sevenzip=True, sevenzip2=False, force=True)
            self._archive = rarfile.RarFile(self.path)
        else:
            raise UnsupportedContainer(f"{self.path.name}: not a zip or RAR archive ({self.container or 'unknown container'})")

    def names(self) -> list[str]:
        """The members that are files. A name that escapes the archive's folder refuses the whole archive."""
        names = [n for n in self._archive.namelist() if not n.endswith("/")]  # type: ignore[attr-defined]
        unsafe = [n for n in names if safe_member_path(n, self.path.parent) is None]
        if unsafe:
            raise DecodeError(f"{self.path.name}: member names leave the archive's folder: {unsafe[:3]}")
        return names

    def one(self, *, match: str | None = None, endswith: tuple[str, ...] = ()) -> str:
        """The single member whose name matches ``match`` (a regex, case ignored) and ends with one of ``endswith``.
        None or several: an error naming what the archive holds, never a guess at the "best" one."""
        names = self.names()
        chosen = [n for n in names if (not match or re.search(match, n, re.I)) and (not endswith or n.lower().endswith(endswith))]
        if len(chosen) != 1:
            asked = " and ".join(x for x in (f"matching {match!r}" if match else "", f"ending in {endswith}" if endswith else "") if x)
            raise ValueError(f"{self.path.name}: expected one member {asked}, found {chosen or names}")
        return chosen[0]

    def open(self, name: str):
        """A member as a binary stream."""
        return self._archive.open(name)  # type: ignore[attr-defined]

    def extract(self, name: str, dest: str | Path) -> Path:
        """A member streamed to ``dest`` (16 MiB at a time), which is returned."""
        dest = Path(dest)
        with self.open(name) as src, dest.open("wb") as dst:
            shutil.copyfileobj(src, dst, 1 << 24)
        return dest

    def close(self) -> None:
        self._archive.close()  # type: ignore[attr-defined]

    def __enter__(self) -> ArchiveFile:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def _gzip_inner_name(path: str) -> str:
    name = PurePosixPath(path).name
    return name[:-3] if name.lower().endswith(".gz") else name


def safe_member_path(name: str, root: Path) -> Path | None:
    """Resolve an archive member under ``root``, or ``None`` if it escapes.

    DATASUS archives are REMOTE input, and RAR/7z extraction is handed to
    external tools whose sanitising we do not control and should not assume. A
    member named ``../../etc/x`` or ``C:/Windows/x`` must not be collected
    whatever the backend did with it, so membership is re-checked here against
    the resolved extraction root rather than trusted.
    """
    from pathlib import Path as _Path

    candidate = _Path(name)
    if candidate.is_absolute() or candidate.drive:
        return None
    resolved = (root / candidate).resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError:
        return None
    return resolved


def _parse_7z_listing(text: str) -> tuple[list[str], list[int]]:
    """Member names and uncompressed sizes from ``7z l -slt`` output.

    Parsed rather than trusted: the point is to know what an archive claims
    before letting an external tool act on it.
    """
    names: list[str] = []
    sizes: list[int] = []
    for line in text.splitlines():
        if line.startswith("Path = "):
            names.append(line[7:].strip())
        elif line.startswith("Size = "):
            raw = line[7:].strip()
            sizes.append(int(raw) if raw.isdigit() else 0)
    # The first `Path =` is the archive itself in 7z's own output.
    if len(names) > len(sizes):
        names = names[1:]
    return names, sizes


def _find_7z() -> str | None:
    exe = shutil.which("7z") or shutil.which("7za") or shutil.which("7zz")
    if exe:
        return exe
    for candidate in (r"C:\Program Files\7-Zip\7z.exe", r"C:\Program Files (x86)\7-Zip\7z.exe"):
        if Path(candidate).is_file():
            return candidate
    return None
