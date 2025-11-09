import json
from pathlib import Path

import yaml

from dativo_ingest.config import AssetDefinition
from dativo_ingest.metadata_exporter import MetadataExporter


def load_person_contract() -> AssetDefinition:
    contract_path = Path("tests/fixtures/specs/csv/v1.0/person.yaml")
    return AssetDefinition.from_yaml(contract_path)


def test_build_odcs_payload_includes_governance_elements() -> None:
    asset = load_person_contract()
    exporter = MetadataExporter(asset, base_dir="metadata_test")

    payload = exporter.build_odcs_payload()

    assert payload["$schema"] == "schemas/odcs/dativo-odcs-3.0.2-extended.schema.json"
    assert payload["team"]["owner"] == asset.team.owner
    assert payload["finops"]["cost_center"] == asset.finops.cost_center
    assert payload["lineage"][0]["contract_version"] == asset.version
    assert payload["compliance"]["classification"]


def test_build_dbt_payload_preserves_classification_and_owner() -> None:
    asset = load_person_contract()
    exporter = MetadataExporter(asset, base_dir="metadata_test")

    dbt_payload = exporter.build_dbt_payload()

    assert dbt_payload["version"] == 2
    source = dbt_payload["sources"][0]
    assert source["meta"]["owner"] == asset.team.owner
    assert asset.compliance.classification[0] in source["meta"]["classification"]
    assert asset.compliance.classification[0] in source["tags"]

    table = source["tables"][0]
    required_fields = [field["name"] for field in asset.schema if field.get("required")]
    for column in table["columns"]:
        if column["name"] in required_fields:
            assert "tests" in column
            assert "not_null" in column["tests"]

    exposure = dbt_payload["exposures"][0]
    assert exposure["meta"]["cost_center"] == asset.finops.cost_center
    assert exposure["meta"]["governance_status"] == asset.governance_status


def test_write_emits_files_and_manifest(tmp_path: Path) -> None:
    asset = load_person_contract()
    exporter = MetadataExporter(asset, base_dir=tmp_path)

    paths = exporter.write()

    assert paths.odcs.exists()
    assert paths.dbt.exists()

    odcs_data = json.loads(paths.odcs.read_text())
    assert odcs_data["name"] == asset.name
    assert odcs_data["version"] == asset.version

    dbt_data = yaml.safe_load(paths.dbt.read_text())
    assert dbt_data["sources"][0]["name"] == asset.name

    manifest_path = tmp_path / "manifest.json"
    assert manifest_path.exists()
    manifest = json.loads(manifest_path.read_text())
    assert asset.id in manifest["contracts"]
    entry = manifest["contracts"][asset.id]
    assert entry["paths"]["odcs"] == str(Path(paths.odcs).relative_to(tmp_path))
    assert entry["version"] == asset.version
