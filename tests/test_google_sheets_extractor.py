"""Unit tests for Google Sheets extractor."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from dativo_ingest.config import ConnectorRecipe, SourceConfig
from dativo_ingest.connectors.google_sheets_extractor import GoogleSheetsExtractor

# Mock Google API modules if they don't exist
if "google.oauth2" not in sys.modules:
    mock_google_oauth2 = MagicMock()
    mock_google_oauth2.service_account = MagicMock()
    mock_google_oauth2.service_account.Credentials = MagicMock()
    sys.modules["google.oauth2"] = mock_google_oauth2
    sys.modules["google.oauth2.service_account"] = mock_google_oauth2.service_account

if "googleapiclient.discovery" not in sys.modules:
    mock_discovery = MagicMock()
    sys.modules["googleapiclient"] = MagicMock()
    sys.modules["googleapiclient.discovery"] = mock_discovery


@pytest.fixture
def sheets_connector_recipe_native():
    """Create Google Sheets connector recipe with native engine."""
    return ConnectorRecipe(
        name="google_sheets",
        type="google_sheets",
        roles=["source", "target"],
        default_engine={"type": "native", "options": {"native": {"api_version": "v4"}}},
        credentials={
            "type": "service_account",
            "file_template": "/secrets/{tenant}/gsheets.json",
        },
    )


@pytest.fixture
def sheets_connector_recipe_airbyte():
    """Create Google Sheets connector recipe with Airbyte engine."""
    return ConnectorRecipe(
        name="google_sheets",
        type="google_sheets",
        roles=["source", "target"],
        default_engine={
            "type": "airbyte",
            "options": {
                "airbyte": {
                    "docker_image": "airbyte/source-google-sheets:latest",
                    "streams_default": ["spreadsheets"],
                }
            },
        },
        credentials={
            "type": "service_account",
            "file_template": "/secrets/{tenant}/gsheets.json",
        },
    )


@pytest.fixture
def sheets_source_config():
    """Create Google Sheets source config."""
    return SourceConfig(
        type="google_sheets",
        sheets=[{"id": "sheet123", "object": "test_sheet"}],
        credentials={"file_template": "/secrets/test_tenant/gsheets.json"},
        incremental={"strategy": "spreadsheet_modified_time"},
    )


def test_sheets_native_extractor_initialization(
    sheets_source_config, sheets_connector_recipe_native
):
    """Test Google Sheets extractor with native engine."""
    from pathlib import Path as PathOriginal

    # Create a mock Path class that always returns True for exists()
    class MockPath(PathOriginal):
        def exists(self):
            return True

    # Mock the Google API imports BEFORE the extractor tries to import them
    with patch("dativo_ingest.connectors.google_sheets_extractor.Path", MockPath):
        import sys

        mock_google_oauth2 = MagicMock()
        mock_google_oauth2.service_account = MagicMock()
        mock_google_oauth2.service_account.Credentials = MagicMock()
        mock_google_oauth2.service_account.Credentials.from_service_account_file = (
            MagicMock(return_value=MagicMock())
        )
        sys.modules["google"] = MagicMock()
        sys.modules["google.oauth2"] = mock_google_oauth2
        sys.modules["google.oauth2.service_account"] = (
            mock_google_oauth2.service_account
        )
        sys.modules["googleapiclient"] = MagicMock()
        sys.modules["googleapiclient.discovery"] = MagicMock()
        sys.modules["googleapiclient.discovery.build"] = MagicMock(
            return_value=MagicMock()
        )

        try:
            extractor = GoogleSheetsExtractor(
                sheets_source_config, sheets_connector_recipe_native
            )

            assert not extractor._use_engine
            assert extractor.engine_options is not None
        finally:
            # Clean up sys.modules
            for key in list(sys.modules.keys()):
                if key.startswith("google"):
                    del sys.modules[key]


@patch("dativo_ingest.connectors.engine_framework.docker")
def test_sheets_airbyte_extractor_initialization(
    mock_docker, sheets_source_config, sheets_connector_recipe_airbyte
):
    """Test Google Sheets extractor with Airbyte engine."""
    extractor = GoogleSheetsExtractor(
        sheets_source_config, sheets_connector_recipe_airbyte
    )

    assert extractor._use_engine
    assert extractor._engine_extractor is not None


def test_sheets_extract_metadata(sheets_source_config, sheets_connector_recipe_native):
    """Test Google Sheets metadata extraction."""
    from pathlib import Path as PathOriginal

    # Create a mock Path class that always returns True for exists()
    class MockPath(PathOriginal):
        def exists(self):
            return True

    # Mock the Google API imports BEFORE the extractor tries to import them
    with patch("dativo_ingest.connectors.google_sheets_extractor.Path", MockPath):
        import sys

        mock_google_oauth2 = MagicMock()
        mock_google_oauth2.service_account = MagicMock()
        mock_google_oauth2.service_account.Credentials = MagicMock()
        mock_google_oauth2.service_account.Credentials.from_service_account_file = (
            MagicMock(return_value=MagicMock())
        )
        sys.modules["google"] = MagicMock()
        sys.modules["google.oauth2"] = mock_google_oauth2
        sys.modules["google.oauth2.service_account"] = (
            mock_google_oauth2.service_account
        )
        sys.modules["googleapiclient"] = MagicMock()
        sys.modules["googleapiclient.discovery"] = MagicMock()
        sys.modules["googleapiclient.discovery.build"] = MagicMock(
            return_value=MagicMock()
        )

        try:
            extractor = GoogleSheetsExtractor(
                sheets_source_config, sheets_connector_recipe_native
            )
            metadata = extractor.extract_metadata()

            assert "tags" in metadata
        finally:
            # Clean up sys.modules
            for key in list(sys.modules.keys()):
                if key.startswith("google"):
                    del sys.modules[key]
