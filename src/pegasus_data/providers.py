"""Small internal provider interface for query-planned resources."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .config import Settings


@dataclass(frozen=True, slots=True)
class ResourceRequirement:
    identity: str
    authority: str
    period: tuple[int, int] | None
    local: bool
    estimated_bytes: int | None
    temporal_semantics: str
    primary_namespace: str


class ResourceProvider(Protocol):
    name: str

    def describe(self, settings: Settings, period: tuple[int, int] | None = None) -> ResourceRequirement: ...


class CompactCnesCnpjProvider:
    name = "cnes_cnpj"

    def describe(self, settings: Settings, period: tuple[int, int] | None = None) -> ResourceRequirement:
        from ._resources import ResourceManager

        record = next(
            (item for item in ResourceManager(settings).status().resources if item.name == self.name),
            None,
        )
        return ResourceRequirement(
            self.name, "Ministério da Saúde / DATASUS", period,
            bool(record and record.available), record.bytes if record else None,
            "validity-window as-of competence", "CNES",
        )


class LocalCnesRegistryProvider:
    name = "cnes_registry"

    def describe(self, settings: Settings, period: tuple[int, int] | None = None) -> ResourceRequirement:
        available = False
        estimate = None
        if settings.catalog_path.is_file():
            from .catalog.store import Catalog

            store = Catalog(settings.catalog_path, read_only=True)
            try:
                available = bool(
                    store.query(
                        "SELECT 1 FROM lake_partitions lp JOIN families f "
                        "ON f.family_id=lp.family_id "
                        "WHERE f.system='CNES' AND f.series='ST' "
                        + ("AND lp.year BETWEEN ? AND ? " if period else "")
                        + "LIMIT 1",
                        ([period[0] // 100, period[1] // 100] if period else []),
                    )
                )
                where = "WHERE file_facts.system='CNES' AND file_facts.series_prefix='ST' "
                parameters: list[int] = []
                if period:
                    where += "AND file_facts.year BETWEEN ? AND ? "
                    parameters = [period[0] // 100, period[1] // 100]
                row = store.query(
                    "SELECT COALESCE(SUM(files.size),0) total FROM files "
                    "JOIN file_facts ON file_facts.path=files.path "
                    f"{where}AND file_facts.role='data'",
                    parameters,
                )
                estimate = int(row[0]["total"] or 0) if row else None
            finally:
                store.close()
        return ResourceRequirement(
            self.name, "Ministério da Saúde / CNES", period, available, estimate,
            "monthly registry snapshot", "CNES",
        )


class LocalCnesNamesProvider:
    name = "cnes_names"

    def describe(self, settings: Settings, period: tuple[int, int] | None = None) -> ResourceRequirement:
        path = settings.root / "resources" / "cnes_registry.parquet"
        available = path.is_file()
        estimate = path.stat().st_size if available else None
        if available and period:
            import pyarrow.parquet as pq

            metadata = pq.ParquetFile(path).schema_arrow.metadata or {}
            first = int(metadata.get(b"pegasus_period_start", b"0"))
            last = int(metadata.get(b"pegasus_period_end", b"999912"))
            available = first <= period[0] and last >= period[1]
        if estimate is None and settings.catalog_path.is_file():
            from .catalog.store import Catalog

            store = Catalog(settings.catalog_path, read_only=True)
            try:
                row = store.query(
                    "SELECT COUNT(*) count FROM dictionary WHERE value_group LIKE 'CADGER%'"
                )
                # Conservative compressed-pack planning estimate. The builder
                # reports the exact artifact size once it exists.
                estimate = int(row[0]["count"] or 0) * 32 if row else None
            finally:
                store.close()
        return ResourceRequirement(
            self.name,
            "Ministério da Saúde / DATASUS registry codelists",
            period,
            available,
            estimate,
            "validity-window as-of competence",
            "CNES",
        )


PROVIDERS: dict[str, ResourceProvider] = {
    "cnes_cnpj": CompactCnesCnpjProvider(),
    "cnes_registry": LocalCnesRegistryProvider(),
    "cnes_names": LocalCnesNamesProvider(),
}


def provider(name: str) -> ResourceProvider:
    try:
        return PROVIDERS[name.lower()]
    except KeyError as exc:
        raise KeyError(f"unknown resource provider {name!r}; known: {sorted(PROVIDERS)}") from exc
