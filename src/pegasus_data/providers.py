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
                family_rows = store.query(
                    "SELECT family_id FROM families WHERE system='CNES' AND series='ST'"
                )
                family_ids = [str(row["family_id"]) for row in family_rows]
                requested_years = (
                    set(range(period[0] // 100, period[1] // 100 + 1))
                    if period else set()
                )
                held_years: set[int] = set()
                covered_paths: set[str] = set()
                if family_ids:
                    marks = ",".join("?" for _ in family_ids)
                    for row in store.query(
                        f"SELECT year, source_paths FROM lake_partitions "
                        f"WHERE family_id IN ({marks})",
                        tuple(family_ids),
                    ):
                        held_years.add(int(row["year"]))
                        import json

                        try:
                            covered_paths.update(json.loads(row["source_paths"] or "[]"))
                        except (TypeError, json.JSONDecodeError):
                            pass
                    publication_rows = [
                        dict(row)
                        for row in store.query(
                            f"SELECT ff.path, ff.member, fa.logical_id, fa.container_format, "
                            f"files.size FROM family_files ff JOIN file_facts fa "
                            f"ON fa.path=ff.path LEFT JOIN files ON files.path=ff.path "
                            f"WHERE ff.family_id IN ({marks}) "
                            + ("AND fa.normalized_date BETWEEN ? AND ?" if period else ""),
                            (*family_ids, *period) if period else tuple(family_ids),
                        )
                    ]
                    from .representations import choose_representations

                    expected = {
                        str(row.get("logical_id") or row["path"])
                        for row in choose_representations(store, publication_rows).selected
                    }
                    covered_identities: set[str] = set()
                    if covered_paths:
                        path_marks = ",".join("?" for _ in covered_paths)
                        known_paths: set[str] = set()
                        for row in store.query(
                            f"SELECT path, logical_id FROM file_facts WHERE path IN ({path_marks})",
                            tuple(sorted(covered_paths)),
                        ):
                            known_paths.add(str(row["path"]))
                            covered_identities.add(str(row["logical_id"] or row["path"]))
                        covered_identities.update(covered_paths - known_paths)
                    available = bool(held_years) and (
                        not requested_years or requested_years <= held_years
                    ) and bool(expected) and expected <= covered_identities
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
            covered = {
                int(value)
                for value in metadata.get(b"pegasus_covered_years", b"").decode().split(",")
                if value
            }
            requested = set(range(period[0] // 100, period[1] // 100 + 1))
            available = bool(covered) and requested <= covered
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
