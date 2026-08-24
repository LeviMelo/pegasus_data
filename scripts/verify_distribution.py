"""Verify that Pegasus distribution archives contain their runtime control plane.

Repository tests can pass while a wheel silently omits SQL, curation or compiled
semantic resources. This check compares both wheel and sdist contents with the
runtime data in ``src/pegasus_data`` and validates the resource manifest inside
each archive. It intentionally uses only the standard library so it can run
before the distribution is installed.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import tarfile
import zipfile
from email import policy
from email.parser import BytesParser
from pathlib import Path, PurePosixPath
from typing import Protocol

RUNTIME_SUFFIXES = {".json", ".parquet", ".sql", ".yaml", ".yml"}
FORBIDDEN_PARTS = {
    ".cache_dl",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "pegasus_data_home",
}
FORBIDDEN_SUFFIXES = {".db", ".dbc", ".duckdb", ".sqlite", ".zip"}


class ArchiveReader(Protocol):
    def names(self) -> list[str]: ...

    def read(self, name: str) -> bytes: ...

    def close(self) -> None: ...


class _WheelReader:
    def __init__(self, path: Path) -> None:
        self.archive = zipfile.ZipFile(path)

    def names(self) -> list[str]:
        return self.archive.namelist()

    def read(self, name: str) -> bytes:
        return self.archive.read(name)

    def close(self) -> None:
        self.archive.close()


class _SdistReader:
    def __init__(self, path: Path) -> None:
        self.archive = tarfile.open(path, "r:gz")

    def names(self) -> list[str]:
        return self.archive.getnames()

    def read(self, name: str) -> bytes:
        member = self.archive.extractfile(name)
        if member is None:
            raise ValueError(f"archive member is not a file: {name}")
        return member.read()

    def close(self) -> None:
        self.archive.close()


def _reader(path: Path) -> tuple[ArchiveReader, str]:
    if path.suffix == ".whl":
        return _WheelReader(path), "wheel"
    if path.name.endswith(".tar.gz"):
        return _SdistReader(path), "sdist"
    raise ValueError(f"unsupported distribution archive: {path}")


def _package_members(names: list[str], kind: str) -> dict[str, str]:
    marker = "pegasus_data/" if kind == "wheel" else "/src/pegasus_data/"
    members: dict[str, str] = {}
    for name in names:
        normal = name.replace("\\", "/")
        if kind == "wheel" and normal.startswith(marker):
            relative = normal[len(marker) :]
        elif kind == "sdist" and marker in normal:
            relative = normal.split(marker, 1)[1]
        else:
            continue
        if relative and not relative.endswith("/"):
            if relative in members:
                raise ValueError(f"duplicate package member {relative!r}")
            members[relative] = name
    return members


def _expected_runtime_files(source_root: Path) -> set[str]:
    if not source_root.is_dir():
        raise ValueError(f"package source directory does not exist: {source_root}")
    return {
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*")
        if path.is_file() and path.suffix.lower() in RUNTIME_SUFFIXES
    }


def _verify_runtime_data(
    reader: ArchiveReader,
    package_members: dict[str, str],
    expected: set[str],
) -> None:
    present = set(package_members)
    missing = sorted(expected - present)
    if missing:
        raise ValueError("missing runtime package data:\n  " + "\n  ".join(missing))

    manifest_member = package_members.get("resources/manifest.json")
    if manifest_member is None:
        raise ValueError("resources/manifest.json is absent")
    manifest = json.loads(reader.read(manifest_member))
    declared = manifest.get("resources") or {}
    if not declared:
        raise ValueError("resources/manifest.json declares no resources")
    for resource_name, body in sorted(declared.items()):
        relative = f"resources/{body.get('file', '')}"
        member = package_members.get(relative)
        if member is None:
            raise ValueError(f"manifest resource {resource_name!r} is absent: {relative}")
        payload = reader.read(member)
        expected_bytes = body.get("bytes")
        if expected_bytes is not None and len(payload) != int(expected_bytes):
            raise ValueError(
                f"manifest resource {resource_name!r} has {len(payload)} bytes, "
                f"expected {expected_bytes}"
            )
        expected_digest = body.get("sha256")
        actual_digest = hashlib.sha256(payload).hexdigest()
        if expected_digest and actual_digest != expected_digest:
            raise ValueError(f"manifest resource {resource_name!r} failed its SHA-256 check")


def _verify_no_repository_payload(names: list[str]) -> None:
    offenders: list[str] = []
    for name in names:
        path = PurePosixPath(name.replace("\\", "/"))
        if FORBIDDEN_PARTS.intersection(path.parts) or path.suffix.lower() in FORBIDDEN_SUFFIXES:
            offenders.append(name)
    if offenders:
        raise ValueError("repository/runtime payload leaked into archive:\n  " + "\n  ".join(offenders))


def _one_matching(names: list[str], suffix: str) -> str:
    matched = [name for name in names if name.replace("\\", "/").endswith(suffix)]
    if len(matched) != 1:
        raise ValueError(f"expected one *{suffix} member, found {len(matched)}")
    return matched[0]


def _sdist_root_member(names: list[str], filename: str) -> str:
    matched = [
        name
        for name in names
        if (path := PurePosixPath(name.replace("\\", "/"))).name == filename
        and len(path.parts) == 2
    ]
    if len(matched) != 1:
        raise ValueError(f"expected one sdist-root {filename!r}, found {len(matched)}")
    return matched[0]


def _verify_wheel(
    reader: ArchiveReader,
    names: list[str],
    path: Path,
    expected_version: str | None,
) -> str:
    metadata_name = _one_matching(names, ".dist-info/METADATA")
    metadata = BytesParser(policy=policy.default).parsebytes(reader.read(metadata_name))
    if str(metadata["Name"]).lower().replace("_", "-") != "pegasus-data":
        raise ValueError(f"unexpected distribution name: {metadata['Name']!r}")
    version = str(metadata["Version"])
    if expected_version is not None and version != expected_version:
        raise ValueError(f"wheel version {version!r} does not match {expected_version!r}")
    if str(metadata["Requires-Python"]) != ">=3.11":
        raise ValueError(f"unexpected Requires-Python: {metadata['Requires-Python']!r}")
    if not path.name.endswith("-py3-none-any.whl"):
        raise ValueError(f"wheel is not tagged as platform-independent: {path.name}")

    entry_points = reader.read(_one_matching(names, ".dist-info/entry_points.txt")).decode()
    if "pegasus-data = pegasus_data.cli:main" not in entry_points:
        raise ValueError("wheel does not declare the pegasus-data CLI entry point")
    _one_matching(names, ".dist-info/licenses/LICENSE")
    return version


def _verify_sdist(reader: ArchiveReader, names: list[str], expected_version: str | None) -> str:
    for filename in ("pyproject.toml", "README.md", "LICENSE", "PKG-INFO"):
        _sdist_root_member(names, filename)
    metadata = BytesParser(policy=policy.default).parsebytes(
        reader.read(_sdist_root_member(names, "PKG-INFO"))
    )
    version = str(metadata["Version"])
    if expected_version is not None and version != expected_version:
        raise ValueError(f"sdist version {version!r} does not match {expected_version!r}")
    return version


def verify(path: Path, source_root: Path, expected_version: str | None = None) -> str:
    reader, kind = _reader(path)
    try:
        names = reader.names()
        _verify_no_repository_payload(names)
        package_members = _package_members(names, kind)
        if "__init__.py" not in package_members:
            raise ValueError("pegasus_data/__init__.py is absent")
        _verify_runtime_data(reader, package_members, _expected_runtime_files(source_root))
        version = (
            _verify_wheel(reader, names, path, expected_version)
            if kind == "wheel"
            else _verify_sdist(reader, names, expected_version)
        )
    finally:
        reader.close()
    print(f"verified {kind}: {path.name} (pegasus-data {version})")
    return version


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archives", nargs="+", type=Path)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "src" / "pegasus_data",
        help="package source used as the expected runtime-data inventory",
    )
    parser.add_argument("--expected-version")
    args = parser.parse_args()
    archives: list[Path] = []
    for value in args.archives:
        # POSIX shells expand globs before starting Python; PowerShell does not.
        # Expanding here keeps the release command identical on both platforms.
        matches = [Path(match) for match in glob.glob(str(value))]
        archives.extend(matches or [value])
    versions = {
        verify(path.resolve(), args.source_root.resolve(), args.expected_version)
        for path in archives
    }
    if len(versions) != 1:
        raise SystemExit(f"distribution archives disagree on version: {sorted(versions)}")


if __name__ == "__main__":
    main()
