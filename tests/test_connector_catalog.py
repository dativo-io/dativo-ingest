"""Unit tests for connector_catalog sync + normalization."""

import json

import pytest

from src.dativo_ingest.connector_catalog import (
    CatalogSyncError,
    normalize_airbyte_catalog_index,
    slugify_connector_name,
)


def test_slugify_connector_name():
    assert slugify_connector_name("Stripe") == "stripe"
    assert slugify_connector_name("Google Sheets") == "google_sheets"
    assert slugify_connector_name("File (CSV)") == "file_csv"


def test_normalize_airbyte_catalog_index_happy_path():
    airbyte_index = {
        "sources": [
            {
                "sourceDefinitionId": "id-123",
                "name": "Stripe",
                "dockerRepository": "airbyte/source-stripe",
                "dockerImageTag": "1.2.3",
                "documentationUrl": "https://docs.example/stripe",
                "supportLevel": "certified",
            }
        ]
    }

    normalized = normalize_airbyte_catalog_index(airbyte_index)
    assert normalized["catalog_name"] == "airbyte"
    assert "last_updated" in normalized
    assert isinstance(normalized["connectors"], list)
    assert len(normalized["connectors"]) == 1

    c = normalized["connectors"][0]
    assert c["name"] == "stripe"
    assert c["id"] == "id-123"
    assert c["docker_image_default"] == "airbyte/source-stripe:1.2.3"
    assert c["version_default"] == "1.2.3"
    assert "support:certified" in c["capabilities"]


def test_normalize_airbyte_catalog_index_missing_sources():
    with pytest.raises(CatalogSyncError):
        normalize_airbyte_catalog_index({"connectors": []})

