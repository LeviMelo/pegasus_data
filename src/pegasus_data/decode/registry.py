"""Reader dispatch by probe result, not by suffix (D1).

    open(path):
        candidates = readers_ordered_by_suffix_hint(path)
        for reader in candidates:
            try:  return reader(path)
            except: continue
        record as undecodable, with all attempts logged

The suffix is a hint that *orders the probe attempts* and nothing more. This is
the rule that stops an entire information system from disappearing because
someone put ``"exe"`` in a list of things to ignore.

Archives are expanded recursively, and **every** member is returned with its
role, so a ``TAB_*.zip`` kit yields its ``.DEF``, ``.CNV`` and ``.DBF`` members
together rather than one arbitrarily-chosen "best" file.
"""

from __future__ import annotations

import tempfile
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from .archives import Archive, ArchiveMember, detect_container
from .base import DecodedTable, DecodeError, UnsupportedContainer
from .dbc import read_dbc_bytes
from .dbf import read_dbf_bytes
from .duckdb_ import DuckStorageVersionError, read_duckdb
from .text_ import read_csv_bytes, read_json_bytes, read_parquet, read_xlsx, read_xml_bytes

#: Reader names in the order a probe should try them, keyed by suffix hint.
#: Anything not listed gets the full ladder, because "unknown suffix" is not
#: evidence of "not data".
SUFFIX_HINTS: dict[str, tuple[str, ...]] = {
    ".dbc": ("dbc", "dbf", "archive"),
    ".dbf": ("dbf", "dbc", "archive"),
    ".csv": ("csv", "json", "xml", "archive"),
    ".txt": ("csv", "json", "xml"),
    ".json": ("json", "csv"),
    ".xml": ("xml", "csv"),
    ".parquet": ("parquet",),
    ".xls": ("xlsx", "csv"),
    ".xlsx": ("xlsx", "csv"),
    ".duck": ("duckdb", "archive"),
    ".zip": ("archive",),
    ".gz": ("archive",),
    ".rar": ("archive",),
    ".7z": ("archive",),
    ".exe": ("archive",),
    ".tar": ("archive",),
    ".def": ("semantic",),
    ".cnv": ("semantic",),
    ".pdf": ("document",),
    ".hlp": ("document",),
    ".cnt": ("document",),
    ".dll": ("skip",),
}

FULL_LADDER: tuple[str, ...] = ("archive", "dbc", "dbf", "parquet", "csv", "json", "xml", "duckdb", "xlsx")

#: Members inside archives that are never tabular payloads.
NON_TABULAR_ROLES = {"def", "cnv", "doc", "binary"}


@dataclass(slots=True)
class DecodeAttempt:
    reader: str
    ok: bool
    error: str | None = None


@dataclass(slots=True)
class DecodeOutcome:
    """Everything a probe found in one physical file."""

    path: str
    tables: list[DecodedTable] = field(default_factory=list)
    members: list[ArchiveMember] = field(default_factory=list)
    attempts: list[DecodeAttempt] = field(default_factory=list)
    container: str | None = None
    open_questions: list[tuple[str, str]] = field(default_factory=list)

    @property
    def decoded(self) -> bool:
        return bool(self.tables)

    @property
    def semantic_members(self) -> list[ArchiveMember]:
        return [m for m in self.members if m.role in {"def", "cnv"}]


def suffix_of(path: str) -> str:
    lower = PurePosixPath(path).name.lower()
    for composite in (".duck.zip", ".csv.gz", ".json.gz", ".xml.gz", ".dbf.gz", ".dbc.gz", ".tar.gz"):
        if lower.endswith(composite):
            return composite
    return PurePosixPath(lower).suffix


def readers_ordered_by_suffix_hint(path: str) -> tuple[str, ...]:
    suffix = suffix_of(path)
    if suffix in {".duck.zip", ".csv.gz", ".json.gz", ".xml.gz", ".dbf.gz", ".dbc.gz", ".tar.gz"}:
        return ("archive",) + FULL_LADDER
    hinted = SUFFIX_HINTS.get(suffix)
    if hinted is None:
        return FULL_LADDER
    if hinted == ("skip",):
        return ()
    rest = tuple(r for r in FULL_LADDER if r not in hinted)
    return hinted + rest


class ReaderRegistry:
    """Probes a payload with every plausible reader until one produces a table."""

    def __init__(self, *, row_limit: int | None = None, max_archive_depth: int = 3) -> None:
        self.row_limit = row_limit
        self.max_archive_depth = max_archive_depth
        #: Members that could not be read during the current open_bytes() call.
        #: Collected here because the archive handler cannot reach the outcome
        #: it is contributing to, and drained into it when the call returns.
        self._failed_members: list[tuple[str, str]] = []

    # ------------------------------------------------------------------ entry

    def open_bytes(self, data: bytes, *, path: str, depth: int = 0) -> DecodeOutcome:
        outcome = DecodeOutcome(path=path, container=detect_container(data))
        if depth == 0:
            self._failed_members = []
        if not data:
            outcome.attempts.append(DecodeAttempt("<empty>", False, "zero-length payload"))
            return outcome
        for name in readers_ordered_by_suffix_hint(path):
            handler = self._handlers().get(name)
            if handler is None:
                continue
            try:
                produced = handler(data, path, depth)
            except UnsupportedContainer as exc:
                outcome.attempts.append(DecodeAttempt(name, False, f"unsupported: {exc}"))
                outcome.open_questions.append((f"decode.optional_dependency.{name}", str(exc)))
                continue
            except DuckStorageVersionError as exc:
                outcome.attempts.append(DecodeAttempt(name, False, str(exc)))
                outcome.open_questions.append(
                    (
                        "decode.duckdb_storage_version",
                        f"{path}: written by DuckDB storage version {exc.observed_version}; "
                        "the installed library cannot open it. Pin or upgrade duckdb and re-run.",
                    )
                )
                continue
            except Exception as exc:
                outcome.attempts.append(DecodeAttempt(name, False, f"{type(exc).__name__}: {exc}"))
                continue
            if produced is None:
                outcome.attempts.append(DecodeAttempt(name, False, "reader returned nothing"))
                continue
            tables, members = produced
            outcome.attempts.append(DecodeAttempt(name, True))
            outcome.tables.extend(tables)
            outcome.members.extend(members)
            if tables or members:
                self._drain_member_failures(outcome)
                return outcome
        self._drain_member_failures(outcome)
        return outcome

    def _drain_member_failures(self, outcome: DecodeOutcome) -> None:
        """Name every archive member that could not be read.

        These used to disappear on a bare `continue`: no attempt, no warning,
        nothing in the outcome — while the package guarantees that anything it
        could not read is named. A silently skipped member is indistinguishable
        from an archive that never contained it.
        """
        for name, reason in self._failed_members:
            outcome.attempts.append(DecodeAttempt(f"archive-member:{name}", False, reason))
        self._failed_members = []

    def open_path(self, path: str | Path, *, logical_path: str | None = None) -> DecodeOutcome:
        p = Path(path)
        return self.open_bytes(p.read_bytes(), path=logical_path or str(p))

    # --------------------------------------------------------------- handlers

    def _handlers(self) -> dict[str, Callable[[bytes, str, int], tuple[list[DecodedTable], list[ArchiveMember]] | None]]:
        return {
            "archive": self._read_archive,
            "dbc": self._read_dbc,
            "dbf": self._read_dbf,
            "parquet": self._read_parquet,
            "csv": self._read_csv,
            "json": self._read_json,
            "xml": self._read_xml,
            "duckdb": self._read_duckdb,
            "xlsx": self._read_xlsx,
            "semantic": self._read_semantic,
            "document": self._read_document,
        }

    def _read_dbc(self, data: bytes, path: str, depth: int) -> tuple[list[DecodedTable], list[ArchiveMember]] | None:
        return ([read_dbc_bytes(data, path=path, row_limit=self.row_limit)], [])

    def _read_dbf(self, data: bytes, path: str, depth: int) -> tuple[list[DecodedTable], list[ArchiveMember]] | None:
        return ([read_dbf_bytes(data, path=path, row_limit=self.row_limit)], [])

    def _read_csv(self, data: bytes, path: str, depth: int) -> tuple[list[DecodedTable], list[ArchiveMember]] | None:
        return ([read_csv_bytes(data, path=path, row_limit=self.row_limit)], [])

    def _read_json(self, data: bytes, path: str, depth: int) -> tuple[list[DecodedTable], list[ArchiveMember]] | None:
        return ([read_json_bytes(data, path=path, row_limit=self.row_limit)], [])

    def _read_xml(self, data: bytes, path: str, depth: int) -> tuple[list[DecodedTable], list[ArchiveMember]] | None:
        return ([read_xml_bytes(data, path=path, row_limit=self.row_limit)], [])

    def _read_parquet(self, data: bytes, path: str, depth: int) -> tuple[list[DecodedTable], list[ArchiveMember]] | None:
        with _staged(data, ".parquet") as staged:
            table = read_parquet(staged, row_limit=self.row_limit)
            materialised = table.to_table()
        from .base import batches_from_table

        table.path = path
        table.batches = batches_from_table(materialised)
        table.row_count = materialised.num_rows
        return ([table], [])

    def _read_xlsx(self, data: bytes, path: str, depth: int) -> tuple[list[DecodedTable], list[ArchiveMember]] | None:
        with _staged(data, ".xlsx") as staged:
            table = read_xlsx(staged, row_limit=self.row_limit)
        table.path = path
        return ([table], [])

    def _read_duckdb(self, data: bytes, path: str, depth: int) -> tuple[list[DecodedTable], list[ArchiveMember]] | None:
        # DuckDB needs a real file and keeps it open for the duration of the
        # read, so the directory has to outlive `read_duckdb` — but not the
        # process. mkdtemp() registers no cleanup and nothing here retained an
        # owner, so every `.duck` decoded leaked a directory holding a full copy
        # of the database until the OS got around to it.
        staging = tempfile.TemporaryDirectory(prefix="pegasus_duck_")
        try:
            staged = Path(staging.name) / "db.duck"
            staged.write_bytes(data)
            tables = read_duckdb(staged, row_limit=self.row_limit)
            for t in tables:
                t.path = path
            # Materialised before the directory goes: read_duckdb returns tables
            # already in memory, so the file is no longer needed.
            return (tables, [])
        finally:
            try:
                staging.cleanup()
            except OSError:  # pragma: no cover - Windows may still hold a handle
                pass

    def _read_semantic(self, data: bytes, path: str, depth: int) -> tuple[list[DecodedTable], list[ArchiveMember]] | None:
        """`.DEF`/`.CNV` are dictionary sources, not tables — hand them on untouched."""
        role = "def" if suffix_of(path) == ".def" else "cnv"
        return ([], [ArchiveMember(PurePosixPath(path).name, len(data), "loose", role)])

    def _read_document(self, data: bytes, path: str, depth: int) -> tuple[list[DecodedTable], list[ArchiveMember]] | None:
        return ([], [ArchiveMember(PurePosixPath(path).name, len(data), "loose", "doc")])

    def _read_archive(
        self, data: bytes, path: str, depth: int
    ) -> tuple[list[DecodedTable], list[ArchiveMember]] | None:
        if depth >= self.max_archive_depth:
            raise DecodeError(f"archive nesting deeper than {self.max_archive_depth}: {path}")
        with Archive(data, path=path) as archive:
            # Iterate a SNAPSHOT of the direct members and collect what recursion
            # discovers separately. Extending the list while iterating it meant
            # the loop re-entered synthetic nested names like "outer!inner" as
            # though they were direct members of the outer archive, producing
            # redundant failed reads and confusing traversal.
            direct = list(archive.members())
            discovered: list[ArchiveMember] = []
            tables: list[DecodedTable] = []
            for member in direct:
                if member.role in NON_TABULAR_ROLES:
                    continue
                try:
                    payload = archive.read(member.name)
                except Exception as exc:  # noqa: BLE001 - recorded, not swallowed
                    # A member that cannot be read used to vanish with a bare
                    # `continue`: no DecodeAttempt, no warning, nothing in the
                    # outcome. That contradicts the package guarantee that every
                    # file or member which could not be read is NAMED.
                    self._failed_members.append(
                        (f"{path}!{member.name}", f"{type(exc).__name__}: {exc}")
                    )
                    continue
                if not payload:
                    self._failed_members.append(
                        (f"{path}!{member.name}", "member is empty")
                    )
                    continue
                inner = self.open_bytes(payload, path=member.name, depth=depth + 1)
                for table in inner.tables:
                    table.path = path
                    table.member = (
                        member.name if not table.member else f"{member.name}!{table.member}"
                    )
                    table.container = archive.container or ""
                    tables.append(table)
                discovered.extend(
                    ArchiveMember(f"{member.name}!{m.name}", m.size, m.container, m.role)
                    for m in inner.members
                )
            return (tables, direct + discovered)


class _staged:
    """Write bytes to a temp file so path-only readers can see them."""

    def __init__(self, data: bytes, suffix: str) -> None:
        self.data = data
        self.suffix = suffix
        self._dir: tempfile.TemporaryDirectory[str] | None = None

    def __enter__(self) -> Path:
        self._dir = tempfile.TemporaryDirectory(prefix="pegasus_stage_")
        target = Path(self._dir.name) / f"payload{self.suffix}"
        target.write_bytes(self.data)
        return target

    def __exit__(self, *exc: object) -> None:
        if self._dir is not None:
            self._dir.cleanup()
            self._dir = None


def iter_tables(outcome: DecodeOutcome) -> Iterator[DecodedTable]:
    yield from outcome.tables
