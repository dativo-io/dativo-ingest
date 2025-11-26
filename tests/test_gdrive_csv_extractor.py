"""Unit tests for Google Drive CSV extractor."""

import sys
from unittest.mock import MagicMock, patch

import pytest

from dativo_ingest.config import ConnectorRecipe, SourceConfig
from dativo_ingest.connectors.gdrive_csv_extractor import GDriveCSVExtractor

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
def gdrive_connector_recipe_native():
    """Create Google Drive CSV connector recipe with native engine."""
    return ConnectorRecipe(
        name="gdrive_csv",
        type="gdrive_csv",
        roles=["source"],
        default_engine={"type": "native", "options": {"native": {"api_version": "v3"}}},
        credentials={
            "type": "service_account",
            "file_template": "/secrets/{tenant}/gdrive.json",
        },
    )


@pytest.fixture
def gdrive_connector_recipe_airbyte():
    """Create Google Drive CSV connector recipe with Airbyte engine."""
    return ConnectorRecipe(
        name="gdrive_csv",
        type="gdrive_csv",
        roles=["source"],
        default_engine={
            "type": "airbyte",
            "options": {
                "airbyte": {
                    "docker_image": "airbyte/source-google-drive:latest",
                    "streams_default": ["files"],
                }
            },
        },
        credentials={
            "type": "service_account",
            "file_template": "/secrets/{tenant}/gdrive.json",
        },
    )


@pytest.fixture
def gdrive_source_config():
    """Create Google Drive CSV source config."""
    return SourceConfig(
        type="gdrive_csv",
        files=[{"id": "file123", "object": "test_file"}],
        credentials={"file_template": "/secrets/test_tenant/gdrive.json"},
        incremental={"strategy": "file_modified_time"},
    )


def test_gdrive_native_extractor_initialization(
    gdrive_source_config, gdrive_connector_recipe_native
):
    """Test Google Drive CSV extractor with native engine."""
    from pathlib import Path

    # Create a mock Path that returns instances with exists() = True
    def mock_path_constructor(*args, **kwargs):
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        # Preserve string representation
        mock_path.__str__ = lambda: str(args[0]) if args else ""
        mock_path.__fspath__ = lambda: str(args[0]) if args else ""
        return mock_path

    # Mock Path in the module where it's used
    with patch(
        "dativo_ingest.connectors.gdrive_csv_extractor.Path",
        side_effect=mock_path_constructor,
    ):
        # Mock sys.modules to fake the Google API modules
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
        sys.modules["googleapiclient.http"] = MagicMock()
        sys.modules["googleapiclient.http.MediaIoBaseDownload"] = MagicMock()

        try:
            extractor = GDriveCSVExtractor(
                gdrive_source_config, gdrive_connector_recipe_native
            )

            assert not extractor._use_engine
            assert extractor.engine_options is not None
        finally:
            # Clean up sys.modules
            for key in list(sys.modules.keys()):
                if key.startswith("google"):
                    del sys.modules[key]


@patch("dativo_ingest.connectors.engine_framework.docker")
def test_gdrive_airbyte_extractor_initialization(
    mock_docker, gdrive_source_config, gdrive_connector_recipe_airbyte
):
    """Test Google Drive CSV extractor with Airbyte engine."""
    extractor = GDriveCSVExtractor(
        gdrive_source_config, gdrive_connector_recipe_airbyte
    )

    assert extractor._use_engine
    assert extractor._engine_extractor is not None


def test_gdrive_extract_metadata(gdrive_source_config, gdrive_connector_recipe_native):
    """Test Google Drive CSV metadata extraction."""
    from pathlib import Path

    # Create a mock Path that returns instances with exists() = True
    def mock_path_constructor(*args, **kwargs):
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        # Preserve string representation
        mock_path.__str__ = lambda: str(args[0]) if args else ""
        mock_path.__fspath__ = lambda: str(args[0]) if args else ""
        return mock_path

    # Mock Path in the module where it's used
    with patch(
        "dativo_ingest.connectors.gdrive_csv_extractor.Path",
        side_effect=mock_path_constructor,
    ):
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
        sys.modules["googleapiclient.http"] = MagicMock()
        sys.modules["googleapiclient.http.MediaIoBaseDownload"] = MagicMock()

        try:
            extractor = GDriveCSVExtractor(
                gdrive_source_config, gdrive_connector_recipe_native
            )
            metadata = extractor.extract_metadata()

            assert "tags" in metadata
        finally:
            # Clean up sys.modules
            for key in list(sys.modules.keys()):
                if key.startswith("google"):
                    del sys.modules[key]
