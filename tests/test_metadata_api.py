"""Tests for AI context metadata API and persistence utilities."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from dativo_ingest import api
from dativo_ingest.config import AssetDefinition
from dativo_ingest.metadata_store import load_asset_metadata, update_asset_metadata


def _load_asset_definition() -> AssetDefinition:
    asset_path = Path("assets") / "csv" / "v1.0" / "employee.yaml"
    return AssetDefinition.from_yaml(asset_path)


def test_metadata_store_round_trip(tmp_path: Path) -> None:
    asset = _load_asset_definition()
    metadata_payload = {
        "validation_status": "passed",
        "finops": {
            "cpu_time_sec": 12.5,
            "data_bytes": 1024,
            "cost_estimate_usd": 0.001,
        },
        "lineage": [{"from_asset": "source.hr.employees_csv", "to_asset": asset.name, "contract_version": asset.version}],
        "metadata_source": "unit-test",
    }

    update_asset_metadata(asset, metadata=metadata_payload, metadata_dir=tmp_path)

    loaded = load_asset_metadata(asset.name, metadata_dir=tmp_path)
    assert loaded["asset"]["name"] == asset.name
    assert loaded["metrics"]["validation_status"] == "passed"
    assert loaded["metrics"]["finops"]["data_bytes"] == 1024


def test_ai_context_endpoint_enforces_token(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    asset = _load_asset_definition()
    metadata_payload = {
        "validation_status": "passed",
        "finops": {
            "cpu_time_sec": 5.0,
            "data_bytes": 4096,
            "cost_estimate_usd": 0.002,
        },
        "lineage": [{"from_asset": "source.hr.employees_csv", "to_asset": asset.name, "contract_version": asset.version}],
        "metadata_source": "unit-test",
    }
    update_asset_metadata(asset, metadata=metadata_payload, metadata_dir=tmp_path)

    monkeypatch.setenv("AI_CONTEXT_API_TOKEN", "secret-token")
    monkeypatch.setattr(api, "load_asset_metadata", lambda name: load_asset_metadata(name, metadata_dir=tmp_path))

    client = TestClient(api.app)

    # Missing token
    response = client.get("/api/v1/metadata/ai_context", params={"asset_name": asset.name})
    assert response.status_code == 401

    # Wrong token
    response = client.get(
        "/api/v1/metadata/ai_context",
        params={"asset_name": asset.name},
        headers={"Authorization": "Bearer wrong-token"},
    )
    assert response.status_code == 403

    # Correct token
    response = client.get(
        "/api/v1/metadata/ai_context",
        params={"asset_name": asset.name},
        headers={"Authorization": "Bearer secret-token"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["asset_name"] == asset.name
    assert payload["finops"]["data_bytes"] == 4096
    assert payload["validation_status"] == "passed"
