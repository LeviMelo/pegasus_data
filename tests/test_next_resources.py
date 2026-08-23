from __future__ import annotations

import json
from pathlib import Path

import pytest

from pegasus_data._resources import RESOURCE_SCHEMA_VERSION, ResourceManager
from pegasus_data.config import Settings
from pegasus_data.ontology import DatasetNode, Ontology, SystemNode
from pegasus_data.semantics.dictionary import DictionaryEntry, persist_entries


def test_resource_manifest_accounts_for_every_packaged_parquet(tmp_path: Path) -> None:
    status = ResourceManager(Settings(root=tmp_path)).status()
    resources = Path(__file__).parents[1] / "src" / "pegasus_data" / "resources"
    assert status.schema_version == RESOURCE_SCHEMA_VERSION
    assert {Path(item.path).name for item in status.resources} == {
        path.name for path in resources.glob("*.parquet")
    } | {"system=CNES", "cnes_registry.parquet"}
    assert all(item.available and item.sha256 for item in status.resources if item.bundled)
    assert next(item for item in status.resources if item.name == "cnes_registry").tier == "D"


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
    assert provider("cnes_names").describe(settings, (202401, 202412)).local
    assert not provider("cnes_names").describe(settings, (202301, 202312)).local
