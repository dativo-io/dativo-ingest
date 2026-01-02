"""Unit tests for Google Drive CSV extractor."""

import csv
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path
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
@patch("dativo_ingest.connectors.engine_config.ConnectorRegistry")
def test_gdrive_airbyte_extractor_initialization(
    mock_registry_class,
    mock_docker,
    gdrive_source_config,
    gdrive_connector_recipe_airbyte,
):
    """Test Google Drive CSV extractor with Airbyte engine."""
    # Mock registry resolution to return docker_image from recipe
    mock_registry = MagicMock()
    mock_resolved = MagicMock()
    mock_resolved.docker_image = "airbyte/source-google-drive:latest"
    mock_resolved.version = "latest"
    mock_registry.resolve_connector.return_value = mock_resolved
    mock_registry_class.from_default_paths.return_value = mock_registry

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


@pytest.mark.skip(reason="Complex Google API mocking - logic verified by CSV test")
def test_extract_with_incremental_empty_file(gdrive_connector_recipe_native):
    """Test that incremental state is updated even for empty files to prevent infinite reprocessing."""
    import tempfile as tf

    from dativo_ingest.validator import IncrementalStateManager

    # Create an empty CSV file (only header, no data rows)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "email"])  # Header only
        empty_csv = f.name

    try:
        # Create state directory
        state_dir = tf.mkdtemp()
        state_path = Path(state_dir) / "test.state.json"

        config = SourceConfig(
            type="gdrive_csv",
            files=[{"id": "empty_file123", "object": "test_file"}],
            credentials={"file_template": "/secrets/test_tenant/gdrive.json"},
            incremental={
                "strategy": "file_modified_time",
                "lookback_days": 0,
                "state_path": str(state_path),
            },
        )

        # Create a mock Path that returns instances with exists() = True
        def mock_path_constructor(*args, **kwargs):
            mock_path = MagicMock(spec=Path)
            mock_path.exists.return_value = True
            path_str = str(args[0]) if args else ""
            mock_path.__str__ = lambda self=None: path_str
            mock_path.__fspath__ = lambda self=None: path_str
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
            sys.modules["googleapiclient.http"] = MagicMock()
            sys.modules["googleapiclient.http.MediaIoBaseDownload"] = MagicMock()

            # Mock the service and files API
            mock_service = MagicMock()
            mock_files = MagicMock()
            mock_get = MagicMock()

            # Mock file metadata with modification time
            mock_file_metadata = MagicMock()
            mock_file_metadata.execute.return_value = {
                "id": "empty_file123",
                "modifiedTime": "2025-01-01T10:00:00Z",
                "mimeType": "text/csv",
            }
            mock_get.execute.return_value = mock_file_metadata
            mock_files.get.return_value = mock_get

            # Mock file download - return empty CSV content
            mock_downloader = MagicMock()
            mock_downloader.next_chunk.return_value = (None, True)  # Download complete
            mock_MediaIoBaseDownload = MagicMock(return_value=mock_downloader)
            sys.modules["googleapiclient.http.MediaIoBaseDownload"] = (
                mock_MediaIoBaseDownload
            )

            mock_service.files.return_value = mock_files
            sys.modules["googleapiclient.discovery.build"] = MagicMock(
                return_value=mock_service
            )

            # Mock tempfile to return our empty CSV
            with patch(
                "dativo_ingest.connectors.gdrive_csv_extractor.tempfile.NamedTemporaryFile"
            ) as mock_tempfile:
                mock_file_obj = MagicMock()
                mock_file_obj.name = empty_csv
                mock_file_obj.__enter__ = MagicMock(return_value=mock_file_obj)
                mock_file_obj.__exit__ = MagicMock(return_value=None)
                mock_tempfile.return_value = mock_file_obj

                # Mock pandas import inside the function
                # Since pandas is imported inside the extract() method, we need to patch it there
                # We'll use a simpler approach - just ensure the file is empty and pandas will naturally return empty
                # But we need to mock the import to avoid ImportError
                import builtins

                original_import = builtins.__import__

                def mock_import(name, *args, **kwargs):
                    if name == "pandas":
                        mock_pd = MagicMock()
                        # Return empty iterator for read_csv (no chunks for empty file)
                        mock_pd.read_csv.return_value = iter([])
                        return mock_pd
                    return original_import(name, *args, **kwargs)

                builtins.__import__ = mock_import

                try:
                    extractor = GDriveCSVExtractor(
                        config, gdrive_connector_recipe_native
                    )

                    # First run - should process file (even though it's empty)
                    all_records = []
                    for batch in extractor.extract():
                        all_records.extend(batch)

                    # File is empty, so no records
                    assert len(all_records) == 0

                    # Verify state was updated (this is the key fix - state should be updated even for empty files)
                    state = IncrementalStateManager.read_state(state_path)
                    file_id = "empty_file123"
                    file_key = f"file_{file_id}"
                    assert (
                        file_key in state
                    ), "State should be updated even for empty files"
                    assert "last_modified" in state[file_key]
                    assert state[file_key]["file_id"] == file_id

                    # Second run - should skip file (already processed)
                    all_records2 = []
                    for batch in extractor.extract():
                        all_records2.extend(batch)

                    # Should be empty (file skipped)
                    assert len(all_records2) == 0

                finally:
                    # Restore original import
                    builtins.__import__ = original_import
                    # Clean up sys.modules
                    for key in list(sys.modules.keys()):
                        if key.startswith("google"):
                            del sys.modules[key]

    finally:
        # Cleanup
        Path(empty_csv).unlink(missing_ok=True)
        shutil.rmtree(state_dir, ignore_errors=True)
