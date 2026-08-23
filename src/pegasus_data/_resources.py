"""Versioned runtime resources and optional local registry state."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from .config import Settings, load_settings

RESOURCE_SCHEMA_VERSION = 2


@dataclass(frozen=True, slots=True)
class ResourceRecord:
    name: str
    path: str
    tier: str
    bundled: bool
    available: bool
    bytes: int = 0
    sha256: str | None = None


@dataclass(frozen=True, slots=True)
class ResourceStatus:
    schema_version: int
    content_version: str
    built_at: str | None
    source_build_id: str | None
    resources: tuple[ResourceRecord, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "content_version": self.content_version,
            "built_at": self.built_at,
            "source_build_id": self.source_build_id,
            "resources": [asdict(item) for item in self.resources],
            "total_bytes": sum(item.bytes for item in self.resources if item.available),
        }


class ResourceIntegrityError(RuntimeError):
    """A runtime artifact does not match its declared schema/content identity."""


class ResourceManager:
    """Inspect bundled semantic artifacts and optional user-local registries."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()

    @property
    def bundled_dir(self) -> Path:
        # Convert a concrete child, not the namespace-package MultiplexedPath
        # itself (whose repr is not a filesystem path on Windows).
        return Path(str(files("pegasus_data.resources") / "manifest.json")).parent

    @property
    def local_dir(self) -> Path:
        return self.settings.root / "resources"

    def status(self) -> ResourceStatus:
        manifest_path = self.bundled_dir / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        declared = manifest.get("resources") or {}
        records: list[ResourceRecord] = []
        for name, body in sorted(declared.items()):
            body = body or {}
            bundled_path = self.bundled_dir / str(body.get("file", name))
            local_path = self.local_dir / str(body.get("file", name))
            path = local_path if local_path.is_file() else bundled_path
            records.append(
                ResourceRecord(
                    name=name,
                    path=str(path),
                    tier=str(body.get("tier", "B")),
                    bundled=path == bundled_path,
                    available=path.is_file(),
                    bytes=path.stat().st_size if path.is_file() else 0,
                    sha256=_digest(path) if path.is_file() else None,
                )
            )
        cnes_path = self.settings.lake_dir / "system=CNES"
        records.append(
            ResourceRecord(
                name="cnes_registry",
                path=str(cnes_path),
                tier="D",
                bundled=False,
                available=cnes_path.exists() and any(cnes_path.rglob("*.parquet")),
                bytes=sum(path.stat().st_size for path in cnes_path.rglob("*.parquet")) if cnes_path.exists() else 0,
            )
        )
        names_path = self.local_dir / "cnes_registry.parquet"
        records.append(
            ResourceRecord(
                name="cnes_names",
                path=str(names_path),
                tier="D",
                bundled=False,
                available=names_path.is_file(),
                bytes=names_path.stat().st_size if names_path.is_file() else 0,
                sha256=_digest(names_path) if names_path.is_file() else None,
            )
        )
        return ResourceStatus(
            schema_version=int(manifest.get("resource_schema_version", 1)),
            content_version=str(manifest.get("resource_content_version", "unknown")),
            built_at=manifest.get("built_at"),
            source_build_id=manifest.get("source_build_id") or manifest.get("crawled_at"),
            resources=tuple(records),
        )

    def ensure(self, name: str, *, period: object = None, policy: str = "local") -> ResourceRecord:
        """Return an available resource or name the smallest missing requirement.

        Network acquisition is intentionally not implicit. Only the implemented
        ``local`` policy is exposed; callers build/install a bounded slice explicitly.
        """
        if policy != "local":
            raise ValueError("policy currently supports only 'local'")
        wanted = str(name).upper()
        for item in self.status().resources:
            if item.name.upper() == wanted:
                if item.available:
                    self._validate(item)
                    return item
                break
        suffix = f" for period {period}" if period is not None else ""
        raise FileNotFoundError(
            f"resource {name!r}{suffix} is not available locally; "
            "build or install the required bounded slice first"
        )

    def _validate(self, record: ResourceRecord) -> None:
        """Validate bundled digests or a local bundle's compatibility manifest."""
        if record.name == "cnes_registry":
            return  # lake integrity is owned by lake verification/fingerprints
        if record.name == "cnes_names":
            import pyarrow.parquet as pq

            metadata = pq.ParquetFile(record.path).schema_arrow.metadata or {}
            if metadata.get(b"pegasus_resource_schema") != b"1":
                raise ResourceIntegrityError(
                    "cnes_names resource has no compatible pegasus_resource_schema=1"
                )
            return
        bundled_manifest = json.loads(
            (self.bundled_dir / "manifest.json").read_text(encoding="utf-8")
        )
        if record.bundled:
            expected = (bundled_manifest.get("resources") or {}).get(record.name) or {}
            if expected.get("sha256") and record.sha256 != expected["sha256"]:
                raise ResourceIntegrityError(
                    f"bundled resource {record.name!r} failed its manifest checksum"
                )
            return
        local_manifest_path = self.local_dir / "manifest.json"
        if not local_manifest_path.is_file():
            raise ResourceIntegrityError(
                f"local override {record.name!r} has no resources/manifest.json compatibility record"
            )
        local_manifest = json.loads(local_manifest_path.read_text(encoding="utf-8"))
        if int(local_manifest.get("resource_schema_version", -1)) != RESOURCE_SCHEMA_VERSION:
            raise ResourceIntegrityError(
                f"local resource schema {local_manifest.get('resource_schema_version')!r} "
                f"is incompatible with required {RESOURCE_SCHEMA_VERSION}"
            )
        expected = (local_manifest.get("resources") or {}).get(record.name) or {}
        if not expected or expected.get("sha256") != record.sha256:
            raise ResourceIntegrityError(
                f"local resource {record.name!r} is absent from its manifest or failed checksum"
            )

    def build(self, name: str, *, years: list[int] | None = None) -> dict[str, Any]:
        """Compile a bounded optional slice from local maintainer evidence.

        This is not remote acquisition. The CNES names compiler refuses clearly
        when the local catalog lacks the documentary registry evidence.
        """
        wanted = str(name).upper().replace("-", "_")
        if wanted in {"CNES_NAMES", "CNES_NAME"}:
            from .catalog.store import Catalog
            from .labelpack import build_cnes_registry_pack

            store = Catalog(self.settings.catalog_path)
            try:
                rows, bytes_out = build_cnes_registry_pack(
                    store, self.local_dir / "cnes_registry.parquet", years=years
                )
            finally:
                store.close()
            return {"resource": "cnes_names", "rows": rows, "bytes": bytes_out}
        if wanted != "CNES":
            raise KeyError("optional builders: CNES (history) or cnes_names (directory)")
        from .build import Builder
        from .pipeline import Pipeline

        pipeline = Pipeline(self.settings)
        try:
            return Builder(pipeline).build(systems=["CNES"], years=years).counts
        finally:
            pipeline.close()


def _digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resource_manager(*, root: str | Path | None = None, settings: Settings | None = None) -> ResourceManager:
    """Create the resource lifecycle facade for one Pegasus installation."""
    resolved = settings or load_settings(root=Path(root) if root else None)
    return ResourceManager(resolved)
