"""Tests for Specs-as-Code contract generation utilities."""

from pathlib import Path

import pytest
import yaml

from dativo_ingest.contract_specs import generate_contract_artifacts


def _write_yaml(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle, sort_keys=False)


def test_generate_contract_artifacts_creates_asset_and_dbt(tmp_path: Path) -> None:
    spec_path = tmp_path / "specs" / "csv" / "v1.0" / "test_contract.yaml"
    asset_out = tmp_path / "generated" / "assets" / "csv" / "v1.0" / "test_contract.yaml"
    dbt_out = tmp_path / "generated" / "dbt" / "test_contract.yml"

    spec_payload = {
        "name": "csv_test_contract",
        "version": "1.2.0",
        "domain": "analytics",
        "data_product": "test_product",
        "status": "active",
        "description": {
            "purpose": "Sample contract for testing conversions",
            "usage": "Supports unit tests",
        },
        "tags": ["test", "demo"],
        "source": {"type": "csv", "object": "test_object"},
        "target": {"file_format": "parquet", "partitioning": ["ingest_date"], "mode": "strict"},
        "schema": {
            "fields": [
                {"name": "id", "type": "integer", "required": True, "classification": "INTERNAL"},
                {"name": "name", "type": "string", "required": True},
                {"name": "created_at", "type": "timestamp", "required": True},
            ]
        },
        "governance": {
            "owner": "test@example.com",
            "owner_email": "test@example.com",
            "cost_center": "FIN-UNIT-001",
            "classification": ["INTERNAL"],
            "retention_days": 180,
        },
        "lineage": [
            {"from_asset": "source.system.test_csv", "description": "Test lineage entry"},
        ],
        "audit": [
            {
                "author": "test@example.com",
                "timestamp": "2025-01-01T00:00:00Z",
                "hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
            }
        ],
        "change_management": {"policy": "non-breaking"},
        "dbt": {
            "source": {
                "name": "test_stage",
                "database": "analytics",
                "schema": "staging_test",
                "table_name": "csv_test_contract",
            },
            "model": {
                "name": "dim_test_contract",
                "materialized": "table",
                "tags": ["contract"],
            },
            "exposure": {
                "name": "test_dashboard",
                "type": "dashboard",
                "owner_name": "Analytics Team",
                "owner_email": "analytics@example.com",
                "url": "https://example.com/dashboards/test",
            },
        },
        "finops": {"tags": ["cost-monitoring"]},
    }

    _write_yaml(spec_path, spec_payload)

    generate_contract_artifacts(spec_path, asset_out, dbt_out)

    assert asset_out.exists()
    asset_data = yaml.safe_load(asset_out.read_text())
    assert asset_data["name"] == "csv_test_contract"
    assert asset_data["team"]["cost_center"] == "FIN-UNIT-001"
    assert asset_data["lineage"][0]["from_asset"] == "source.system.test_csv"
    assert asset_data["audit"][0]["hash"] == "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"

    assert dbt_out.exists()
    dbt_data = yaml.safe_load(dbt_out.read_text())
    assert dbt_data["sources"][0]["name"] == "test_stage"
    assert dbt_data["models"][0]["name"] == "dim_test_contract"
    assert dbt_data["exposures"][0]["owner"]["email"] == "analytics@example.com"


def test_version_policy_enforced_for_breaking_changes(tmp_path: Path) -> None:
    base_spec_payload = {
        "name": "csv_versioned",
        "version": "1.0.0",
        "domain": "analytics",
        "data_product": "versioned",
        "source": {"type": "csv", "object": "csv_versioned"},
        "target": {"file_format": "parquet"},
        "schema": {
            "fields": [
                {"name": "id", "type": "integer", "required": True},
            ]
        },
        "governance": {
            "owner": "owner@example.com",
            "cost_center": "FIN-UNIT-002",
            "classification": ["INTERNAL"],
            "retention_days": 90,
        },
        "lineage": [{"from_asset": "source.system.csv_versioned"}],
        "audit": [
            {
                "author": "owner@example.com",
                "timestamp": "2025-01-01T00:00:00Z",
                "hash": "abcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcdefabcd",
            }
        ],
        "change_management": {"policy": "non-breaking"},
        "dbt": {
            "source": {
                "name": "versioned_stage",
                "database": "analytics",
                "schema": "staging_versioned",
            }
        },
    }

    spec_path = tmp_path / "specs" / "csv" / "v1.0" / "versioned.yaml"
    asset_out = tmp_path / "generated" / "asset.yaml"
    dbt_out = tmp_path / "generated" / "dbt.yaml"
    _write_yaml(spec_path, base_spec_payload)
    generate_contract_artifacts(spec_path, asset_out, dbt_out)

    # Breaking change without major bump should fail
    breaking_spec = base_spec_payload.copy()
    breaking_spec["version"] = "1.1.0"
    breaking_spec["change_management"] = {"policy": "breaking"}
    breaking_spec_path = tmp_path / "specs" / "csv" / "v1.1" / "versioned.yaml"
    _write_yaml(breaking_spec_path, breaking_spec)

    with pytest.raises(ValueError, match="Breaking change requires a MAJOR version bump"):
        generate_contract_artifacts(
            breaking_spec_path,
            tmp_path / "generated" / "asset_breaking.yaml",
            tmp_path / "generated" / "dbt_breaking.yaml",
            existing_asset_path=asset_out,
        )
