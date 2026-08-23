from __future__ import annotations

import json
from pathlib import Path

import pytest

from pegasus_data._resources import (
    RESOURCE_SCHEMA_VERSION,
    ResourceIntegrityError,
    ResourceManager,
)
from pegasus_data.config import Settings
from pegasus_data.ontology import DatasetNode, Ontology, SystemNode
from pegasus_data.semantics.dictionary import DictionaryEntry, persist_entries


def test_resource_manifest_accounts_for_every_packaged_runtime_artifact(tmp_path: Path) -> None:
    status = ResourceManager(Settings(root=tmp_path)).status()
    resources = Path(__file__).parents[1] / "src" / "pegasus_data" / "resources"
    assert status.schema_version == RESOURCE_SCHEMA_VERSION
    packaged = {path.name for path in resources.glob("*.parquet")}
    packaged.add("query_capabilities.json")
    assert {Path(item.path).name for item in status.resources} == packaged | {
        "CNES", "cnes_registry.parquet"
    }
    assert all(item.available and item.sha256 for item in status.resources if item.bundled)
    assert next(item for item in status.resources if item.name == "cnes_registry").tier == "D"


def test_query_capabilities_are_compiled_from_curation() -> None:
    from pegasus_data._query_engine.capabilities import compile_capability_payload

    resources = Path(__file__).parents[1] / "src" / "pegasus_data" / "resources"
    compiled = json.loads((resources / "query_capabilities.json").read_text(encoding="utf-8"))
    assert compiled == compile_capability_payload()
    assert all("time" not in body and "geography" not in body for body in compiled["datasets"].values())


def test_resource_budget_covers_current_artifacts() -> None:
    resources = Path(__file__).parents[1] / "src" / "pegasus_data" / "resources"
    manifest = json.loads((resources / "manifest.json").read_text(encoding="utf-8"))
    actual = sum(path.stat().st_size for path in resources.glob("*.parquet"))
    assert actual <= manifest["budgets"]["aggregate_bytes"]
    for body in manifest["resources"].values():
        path = resources / body["file"]
        assert path.stat().st_size <= body["bytes"] * manifest["budgets"]["growth_ratio"]


def test_ontology_refuses_two_datasets_claiming_one_alias() -> None:
    systems = {"SIM": SystemNode("SIM")}
    datasets = {
        "SIM.DO": DatasetNode("SIM.DO", "SIM", observed_as=("MORT",)),
        "SIM.DOINF": DatasetNode("SIM.DOINF", "SIM", observed_as=("MORT",)),
    }
    with pytest.raises(ValueError, match="claimed by both"):
        Ontology(systems, datasets)


def test_optional_cnes_name_registry_builds_from_catalog_evidence(settings) -> None:
    from pegasus_data.catalog.store import Catalog
    from pegasus_data.providers import provider

    store = Catalog(settings.catalog_path)
    try:
        persist_entries(
            store,
            [
                DictionaryEntry(
                    system="CNES",
                    value_raw="2001578",
                    value_label="CNPJ 12.345.678/0001-95-HOSPITAL TESTE",
                    value_group="CADGERBR",
                    source="dbf_lookup",
                    source_ref="TAB_CNES.zip!CADGERBR.DBF",
                    confidence=0.95,
                    valid_from="202401",
                )
            ],
        )
    finally:
        store.close()
    result = ResourceManager(settings).build("cnes_names", years=[2024])
    assert result["rows"] == 1
    assert ResourceManager(settings).ensure("cnes_names").available
    assert ResourceManager(settings).ensure(
        "cnes_names", period="2024-01:2024-12"
    ).available
    assert provider("cnes_names").describe(settings, (202401, 202412)).local
    assert not provider("cnes_names").describe(settings, (202301, 202312)).local
    manifest_path = settings.root / "resources" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["resources"]["cnes_names"]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ResourceIntegrityError, match="checksum"):
        ResourceManager(settings).ensure("cnes_names")


def test_optional_name_coverage_does_not_fill_holes_between_built_years(settings) -> None:
    from pegasus_data.catalog.store import Catalog
    from pegasus_data.providers import provider

    store = Catalog(settings.catalog_path)
    try:
        persist_entries(
            store,
            [
                DictionaryEntry(
                    system="CNES", value_raw="2001578",
                    value_label="CNPJ 12.345.678/0001-95-HOSPITAL TESTE",
                    value_group="CADGERBR", source="dbf_lookup",
                    source_ref="TAB_CNES.zip!CADGERBR.DBF", confidence=0.95,
                )
            ],
        )
    finally:
        store.close()
    ResourceManager(settings).build("cnes_names", years=[2022, 2024])
    assert provider("cnes_names").describe(settings, (202201, 202212)).local
    assert not provider("cnes_names").describe(settings, (202301, 202312)).local
    assert provider("cnes_names").describe(settings, (202401, 202412)).local
    with pytest.raises(ResourceIntegrityError, match="coverage hole"):
        ResourceManager(settings).ensure("cnes_names", period=(202301, 202312))


def test_all_years_name_build_persists_discovered_coverage(settings) -> None:
    import pyarrow.parquet as pq

    from pegasus_data.catalog.store import Catalog
    from pegasus_data.providers import provider

    store = Catalog(settings.catalog_path)
    try:
        persist_entries(
            store,
            [
                DictionaryEntry(
                    system="CNES", value_raw="2001578",
                    value_label="CNPJ 12.345.678/0001-95-HOSPITAL TESTE",
                    value_group="CADGERBR", source="dbf_lookup",
                    source_ref="TAB_CNES_202201.zip!CADGERBR.DBF", confidence=0.95,
                    valid_from="202201", valid_to="202312",
                )
            ],
        )
    finally:
        store.close()
    ResourceManager(settings).build("cnes_names")
    path = settings.root / "resources" / "cnes_registry.parquet"
    metadata = pq.ParquetFile(path).schema_arrow.metadata or {}
    assert metadata[b"pegasus_covered_years"] == b"2022,2023"
    assert provider("cnes_names").describe(settings, (202201, 202312)).local


def test_optional_resource_rejects_incompatible_content_version(settings) -> None:
    from pegasus_data.catalog.store import Catalog

    store = Catalog(settings.catalog_path)
    try:
        persist_entries(
            store,
            [
                DictionaryEntry(
                    system="CNES", value_raw="2001578",
                    value_label="CNPJ 12.345.678/0001-95-HOSPITAL TESTE",
                    value_group="CADGERBR", source="dbf_lookup",
                    source_ref="TAB_CNES.zip!CADGERBR.DBF", confidence=0.95,
                    valid_from="202401",
                )
            ],
        )
    finally:
        store.close()
    ResourceManager(settings).build("cnes_names", years=[2024])
    manifest_path = settings.root / "resources" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["resource_content_version"] = "incompatible"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ResourceIntegrityError, match="content version"):
        ResourceManager(settings).ensure("cnes_names", period=(202401, 202412))


def test_optional_name_resource_rejects_wrong_schema(settings) -> None:
    import hashlib

    import pyarrow as pa
    import pyarrow.parquet as pq

    resources = settings.root / "resources"
    resources.mkdir(parents=True)
    path = resources / "cnes_registry.parquet"
    pq.write_table(pa.table({"cnes": ["1"]}), path)
    bundled = json.loads(
        (
            Path(__file__).parents[1]
            / "src"
            / "pegasus_data"
            / "resources"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    (resources / "manifest.json").write_text(
        json.dumps(
            {
                "resource_schema_version": RESOURCE_SCHEMA_VERSION,
                "resource_content_version": bundled["resource_content_version"],
                "resources": {
                    "cnes_names": {
                        "file": path.name,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ResourceIntegrityError, match="pegasus_resource_schema"):
        ResourceManager(settings).ensure("cnes_names")


def test_unmanifested_local_override_is_not_trusted(settings) -> None:
    resources = settings.root / "resources"
    resources.mkdir(parents=True)
    (resources / "labels_crosswalk.parquet").write_bytes(b"not the declared artifact")
    with pytest.raises(ResourceIntegrityError, match="no resources/manifest"):
        ResourceManager(settings).ensure("cnes_cnpj")
