"""Unit tests for Google Sheets extractor."""

import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
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
        "dativo_ingest.connectors.google_sheets_extractor.Path",
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
@patch("dativo_ingest.connectors.engine_config.ConnectorRegistry")
def test_sheets_airbyte_extractor_initialization(
    mock_registry_class,
    mock_docker,
    sheets_source_config,
    sheets_connector_recipe_airbyte,
):
    """Test Google Sheets extractor with Airbyte engine."""
    # Mock registry resolution to return docker_image from recipe
    mock_registry = MagicMock()
    mock_resolved = MagicMock()
    mock_resolved.docker_image = "airbyte/source-google-sheets:latest"
    mock_resolved.version = "latest"
    mock_registry.resolve_connector.return_value = mock_resolved
    mock_registry_class.from_default_paths.return_value = mock_registry

    extractor = GoogleSheetsExtractor(
        sheets_source_config, sheets_connector_recipe_airbyte
    )

    assert extractor._use_engine
    assert extractor._engine_extractor is not None


def test_sheets_extract_metadata(sheets_source_config, sheets_connector_recipe_native):
    """Test Google Sheets metadata extraction."""
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
        "dativo_ingest.connectors.google_sheets_extractor.Path",
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


@pytest.mark.skip(reason="Complex Google API mocking - logic verified by CSV test")
def test_extract_with_incremental_empty_spreadsheet(sheets_connector_recipe_native):
    """Test that incremental state is updated even for empty spreadsheets to prevent infinite reprocessing."""
    import tempfile as tf

    from dativo_ingest.validator import IncrementalStateManager

    # Create state directory
    state_dir = tf.mkdtemp()
    state_path = Path(state_dir) / "test.state.json"

    config = SourceConfig(
        type="google_sheets",
        sheets=[{"id": "empty_sheet123", "object": "test_sheet"}],
        credentials={"file_template": "/secrets/test_tenant/gsheets.json"},
        incremental={
            "strategy": "spreadsheet_modified_time",
            "lookback_days": 0,
            "state_path": str(state_path),
        },
    )
    # The extractor checks for 'spreadsheets' attribute first, but SourceConfig uses 'sheets'
    # Set spreadsheets to match what extractor expects
    config.spreadsheets = config.sheets

    # Create a mock Path that returns instances with exists() = True
    def mock_path_constructor(*args, **kwargs):
        mock_path = MagicMock(spec=Path)
        mock_path.exists.return_value = True
        mock_path.__str__ = lambda: str(args[0]) if args else ""
        mock_path.__fspath__ = lambda: str(args[0]) if args else ""
        return mock_path

    # Mock Path in the module where it's used
    with patch(
        "dativo_ingest.connectors.google_sheets_extractor.Path",
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

        # Mock the service and spreadsheet API
        mock_service = MagicMock()
        mock_spreadsheets = MagicMock()
        mock_values = MagicMock()
        mock_files = MagicMock()
        mock_get = MagicMock()

        # Mock empty spreadsheet (no rows returned)
        mock_get.execute.return_value = {"values": []}  # Empty spreadsheet
        mock_values.get.return_value = mock_get
        mock_spreadsheets.values.return_value = mock_values

        # Mock file metadata with modification time
        mock_file_metadata = MagicMock()
        mock_file_metadata.execute.return_value = {
            "modifiedTime": "2025-01-01T10:00:00Z"
        }
        mock_files.get.return_value = mock_file_metadata

        mock_service.spreadsheets.return_value = mock_spreadsheets
        mock_service.files.return_value = mock_files
        sys.modules["googleapiclient.discovery.build"] = MagicMock(
            return_value=mock_service
        )

        try:
            extractor = GoogleSheetsExtractor(config, sheets_connector_recipe_native)

            # First run - should process spreadsheet (even though it's empty)
            all_records = []
            for batch in extractor.extract():
                all_records.extend(batch)

            # Spreadsheet is empty, so no records
            assert len(all_records) == 0

            # Verify state was updated (this is the key fix - state should be updated even for empty spreadsheets)
            state = IncrementalStateManager.read_state(state_path)
            spreadsheet_id = "empty_sheet123"
            sheet_key = f"spreadsheet_{spreadsheet_id}"
            assert (
                sheet_key in state
            ), "State should be updated even for empty spreadsheets"
            assert "last_modified" in state[sheet_key]
            assert state[sheet_key]["spreadsheet_id"] == spreadsheet_id

            # Second run - should skip spreadsheet (already processed)
            all_records2 = []
            for batch in extractor.extract():
                all_records2.extend(batch)

            # Should be empty (spreadsheet skipped)
            assert len(all_records2) == 0

        finally:
            # Clean up sys.modules
            for key in list(sys.modules.keys()):
                if key.startswith("google"):
                    del sys.modules[key]
            shutil.rmtree(state_dir, ignore_errors=True)
