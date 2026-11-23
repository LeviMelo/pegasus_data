"""What the query planner says of the resources a route requires (``curation/joins.yml`` ``requires:``)."""

from __future__ import annotations

from dataclasses import dataclass

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


class ResourceProvider:
    """One declared resource (``curation/resources.yml``): whether it is held for a period, and how large it is."""

    def __init__(self, name: str, declaration: dict[str, object]) -> None:
        self.name = name
        self.declaration = declaration

    def describe(self, settings: Settings, period: tuple[int, int] | None = None) -> ResourceRequirement:
        from ._resources import ResourceIntegrityError, ResourceManager

        local = dict(self.declaration.get("local") or {})  # type: ignore[call-overload]
        try:
            record = ResourceManager(settings).ensure(self.name, period=period)
            available, estimate = True, record.bytes
        except FileNotFoundError:
            available, estimate = False, None
        except ResourceIntegrityError as exc:
            if "coverage hole" not in str(exc):
                raise
            available, estimate = False, None
        if estimate is None and local:
            path = settings.root / "resources" / str(local["file"])
            estimate = path.stat().st_size if path.is_file() else None
            sizing = local.get("estimate")
            if estimate is None and sizing and settings.catalog_path.is_file():
                from .catalog.store import CatalogStore

                store = CatalogStore.shared(settings.catalog_path)
                try:
                    row = store.query(
                        "SELECT COUNT(*) count FROM dictionary WHERE value_group LIKE ?", (str(sizing["groups"]),)
                    )
                    estimate = int(row[0]["count"] or 0) * int(sizing["bytes_per_row"]) if row else None
                finally:
                    store.close()
        return ResourceRequirement(
            self.name, str(self.declaration["authority"]), period, available, estimate,
            str(self.declaration["temporal"]), str(self.declaration["namespace"]),
        )


def provider(name: str) -> ResourceProvider:
    from ._resources import resource_declarations

    declared = resource_declarations()
    key = name.lower()
    if key not in declared:
        raise KeyError(f"unknown resource provider {name!r}; known: {sorted(declared)}")
    return ResourceProvider(key, declared[key])
