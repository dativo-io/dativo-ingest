"""Google Drive CSV extractor supporting native, Airbyte, and Meltano engines."""

import os
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from ..config import ConnectorRecipe, SourceConfig
from ..validator import IncrementalStateManager
from .engine_framework import AirbyteExtractor, BaseEngineExtractor


class GDriveCSVExtractor:
    """Extracts data from CSV files stored in Google Drive."""

    def __init__(
        self,
        source_config: SourceConfig,
        connector_recipe: Optional[ConnectorRecipe] = None,
        tenant_id: Optional[str] = None,
    ):
        """Initialize Google Drive CSV extractor.

        Args:
            source_config: Source configuration with files and credentials
            connector_recipe: Optional connector recipe (for engine selection)
            tenant_id: Optional tenant ID for credential path resolution
        """
        self.source_config = source_config
        self.connector_recipe = connector_recipe
        self.tenant_id = tenant_id

        # Determine engine type
        if connector_recipe:
            from .engine_config import EngineConfigParser

            config_parser = EngineConfigParser(
                source_config, connector_recipe, tenant_id
            )
            engine_type = config_parser.engine_type

            # Use engine framework if not native
            if engine_type == "airbyte":
                self._engine_extractor = AirbyteExtractor(
                    source_config, connector_recipe, tenant_id
                )
                self._use_engine = True
            elif engine_type in ["meltano", "singer"]:
                # TODO: Implement Meltano/Singer support
                raise NotImplementedError(
                    f"{engine_type} engine not yet implemented for gdrive_csv"
                )
            else:
                self._use_engine = False
        else:
            self._use_engine = False

        if not self._use_engine:
            # Use native implementation
            self.engine_options = self._get_engine_options()
            self.credentials_path = self._get_credentials_path()
            self._init_google_client()

    def _get_engine_options(self) -> Dict[str, Any]:
        """Get engine options from source config.

        Returns:
            Dictionary of engine options
        """
        if self.source_config.engine:
            native_opts = self.source_config.engine.get("options", {}).get("native", {})
            if native_opts:
                return native_opts

        # Default options
        return {
            "api_version": "v3",
            "mime_type": "text/csv",
            "chunk_size": 10000,
            "encoding": "utf-8",
            "delimiter": ",",
            "quote_char": '"',
        }

    def _get_credentials_path(self) -> str:
        """Get Google service account credentials path.

        Returns:
            Path to service account JSON file

        Raises:
            ValueError: If credentials path is not found
        """
        # Check credentials dict
        if self.source_config.credentials:
            if isinstance(self.source_config.credentials, dict):
                # Try common key names
                for key in ["credentials_path", "service_account_file", "file", "path"]:
                    if key in self.source_config.credentials:
                        path = str(self.source_config.credentials[key])
                        if Path(path).exists():
                            return path

        # Check for file_template pattern
        if self.source_config.credentials:
            if isinstance(self.source_config.credentials, dict):
                file_template = self.source_config.credentials.get("file_template")
                if file_template:
                    # Expand tenant placeholder if present
                    tenant_id = self.tenant_id or "default"
                    path = file_template.replace("{tenant}", tenant_id)
                    # Also try without replacement if tenant_id is not set
                    if not self.tenant_id:
                        path = file_template
                    if Path(path).exists():
                        return path

        # Check environment variable
        creds_path = os.getenv("GDRIVE_CREDENTIALS_PATH") or os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS"
        )
        if creds_path and Path(creds_path).exists():
            return creds_path

        raise ValueError(
            "Google Drive service account credentials not found. "
            "Provide credentials_path in config or set GDRIVE_CREDENTIALS_PATH environment variable."
        )

    def _init_google_client(self) -> None:
        """Initialize Google Drive API client."""
        try:
            from google.oauth2 import service_account as service_account_module
            from googleapiclient.discovery import build as build_func
            from googleapiclient.http import MediaIoBaseDownload
        except ImportError:
            raise ImportError(
                "google-api-python-client and google-auth are required for Google Drive extraction. "
                "Install with: pip install google-api-python-client google-auth"
            )

        # Store modules for testing
        self.service_account = service_account_module
        self.build = build_func

        # Load service account credentials
        credentials = service_account_module.Credentials.from_service_account_file(
            self.credentials_path,
            scopes=["https://www.googleapis.com/auth/drive.readonly"],
        )

        # Build Drive API client
        self.drive_service = build_func(
            "drive",
            self.engine_options.get("api_version", "v3"),
            credentials=credentials,
        )
        self.MediaIoBaseDownload = MediaIoBaseDownload

    def _list_csv_files(
        self, folder_id: Optional[str] = None, query: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """List CSV files from Google Drive.

        Args:
            folder_id: Optional folder ID to search in
            query: Optional search query

        Returns:
            List of file metadata dictionaries
        """
        mime_type = self.engine_options.get("mime_type", "text/csv")

        # Build query
        if query:
            search_query = f"mimeType='{mime_type}' and ({query})"
        else:
            search_query = f"mimeType='{mime_type}'"

        if folder_id:
            search_query += f" and '{folder_id}' in parents"

        files = []
        page_token = None

        while True:
            try:
                response = (
                    self.drive_service.files()
                    .list(
                        q=search_query,
                        fields="nextPageToken, files(id, name, modifiedTime, size, mimeType)",
                        pageToken=page_token,
                        pageSize=100,
                    )
                    .execute()
                )

                files.extend(response.get("files", []))
                page_token = response.get("nextPageToken")

                if not page_token:
                    break

            except Exception as e:
                raise RuntimeError(
                    f"Failed to list Google Drive files: {str(e)}"
                ) from e

        return files

    def _download_file(self, file_id: str, file_path: Path) -> None:
        """Download a file from Google Drive.

        Args:
            file_id: Google Drive file ID
            file_path: Local path to save the file
        """
        try:
            request = self.drive_service.files().get_media(fileId=file_id)
            with open(file_path, "wb") as f:
                downloader = self.MediaIoBaseDownload(f, request)
                done = False
                while not done:
                    status, done = downloader.next_chunk()
        except Exception as e:
            raise RuntimeError(f"Failed to download file {file_id}: {str(e)}") from e

    def _get_files_to_extract(self) -> List[Dict[str, Any]]:
        """Get list of files to extract from source config.

        Returns:
            List of file configurations
        """
        if self.source_config.files:
            return self.source_config.files

        # If no files specified, list all CSV files (or from specified folder)
        folder_id = getattr(self.source_config, "folder_id", None)
        query = getattr(self.source_config, "query", None)

        drive_files = self._list_csv_files(folder_id=folder_id, query=query)

        # Convert to file config format
        return [
            {
                "id": f["id"],
                "name": f["name"],
                "path": f["id"],  # Use file ID as path identifier
                "modifiedTime": f.get("modifiedTime"),
            }
            for f in drive_files
        ]

    def _get_file_modified_time(
        self, file_metadata: Dict[str, Any]
    ) -> Optional[datetime]:
        """Get file modification time from metadata.

        Args:
            file_metadata: File metadata dictionary

        Returns:
            Datetime object or None
        """
        modified_time_str = file_metadata.get("modifiedTime")
        if not modified_time_str:
            return None

        try:
            # Google Drive returns ISO 8601 format
            return datetime.fromisoformat(modified_time_str.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None

    def extract(
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from Google Drive CSV files.

        Args:
            state_manager: Optional incremental state manager for tracking file state

        Yields:
            Batches of records as dictionaries
        """
        # Delegate to engine extractor if using non-native engine
        if self._use_engine:
            yield from self._engine_extractor.extract(state_manager)
            return

        # Use native implementation
        files = self._get_files_to_extract()
        if not files:
            raise ValueError(
                "Google Drive CSV source requires 'files' configuration or folder_id"
            )

        chunk_size = self.engine_options.get("chunk_size", 10000)
        encoding = self.engine_options.get("encoding", "utf-8")
        delimiter = self.engine_options.get("delimiter", ",")
        quote_char = self.engine_options.get("quote_char", '"')

        # Get incremental configuration
        incremental = self.source_config.incremental or {}
        strategy = incremental.get("strategy", "file_modified_time")
        lookback_days = incremental.get("lookback_days", 0)
        state_path_str = incremental.get("state_path", "")
        state_path = Path(state_path_str) if state_path_str else None

        # Process each file
        for file_config in files:
            file_id = file_config.get("id") or file_config.get("path")
            if not file_id:
                continue

            # Check incremental state if enabled
            if strategy == "file_modified_time" and state_path:
                file_metadata = file_config
                modified_time = self._get_file_modified_time(file_metadata)

                if modified_time:
                    file_id_str = str(file_id)
                    modified_time_iso = modified_time.isoformat()

                    if IncrementalStateManager.should_skip_file(
                        file_id=file_id_str,
                        current_modified_time=modified_time_iso,
                        state_path=state_path,
                        lookback_days=lookback_days,
                    ):
                        continue  # Skip this file

            # Download file to temporary location
            with tempfile.NamedTemporaryFile(
                mode="w+b", suffix=".csv", delete=False
            ) as tmp_file:
                tmp_path = Path(tmp_file.name)
                try:
                    self._download_file(file_id, tmp_path)

                    # Read CSV file in chunks using pandas
                    try:
                        import pandas as pd
                    except ImportError:
                        raise ImportError(
                            "pandas is required for CSV extraction. Install with: pip install pandas"
                        )

                    # Read CSV with specified options
                    for chunk_df in pd.read_csv(
                        tmp_path,
                        chunksize=chunk_size,
                        encoding=encoding,
                        sep=delimiter,
                        quotechar=quote_char,
                        dtype=str,  # Read all as strings initially
                        na_values=["", "NULL", "null", "None"],
                        keep_default_na=False,
                    ):
                        # Convert DataFrame to list of dictionaries
                        records = chunk_df.to_dict("records")
                        if records:
                            yield records

                    # Update state after successful processing
                    if state_path and modified_time:
                        file_id_str = str(file_id)
                        modified_time_iso = modified_time.isoformat()
                        IncrementalStateManager.update_file_state(
                            file_id=file_id_str,
                            modified_time=modified_time_iso,
                            state_path=state_path,
                        )

                finally:
                    # Clean up temporary file
                    if tmp_path.exists():
                        tmp_path.unlink()

    def extract_metadata(self) -> Dict[str, Any]:
        """Extract naturally available metadata from Google Drive CSV files.

        Extracts metadata that is naturally available:
        - Column names from CSV headers
        - File metadata (name, size, modification time)

        Returns:
            Dictionary with "tags" key containing field_name -> metadata mapping
        """
        if not self.source_config.files:
            return {"tags": {}}

        source_tags = {}

        try:
            import pandas as pd
        except ImportError:
            return {"tags": {}}

        files = self._get_files_to_extract()

        # Process first file to get column names
        for file_config in files[:1]:  # Just get schema from first file
            file_id = file_config.get("id") or file_config.get("path")
            if not file_id:
                continue

            try:
                # Download file temporarily
                with tempfile.NamedTemporaryFile(
                    mode="w+b", suffix=".csv", delete=False
                ) as tmp_file:
                    tmp_path = Path(tmp_file.name)
                    try:
                        self._download_file(file_id, tmp_path)

                        # Read just the header to get column names
                        encoding = self.engine_options.get("encoding", "utf-8")
                        delimiter = self.engine_options.get("delimiter", ",")
                        quote_char = self.engine_options.get("quote_char", '"')

                        df_header = pd.read_csv(
                            tmp_path,
                            nrows=0,  # Only read header
                            encoding=encoding,
                            sep=delimiter,
                            quotechar=quote_char,
                        )

                        # Extract column names as naturally available metadata
                        for col_name in df_header.columns:
                            source_tags[col_name] = "column"

                    finally:
                        if tmp_path.exists():
                            tmp_path.unlink()

            except Exception:
                # If reading fails, continue
                continue

        return {"tags": source_tags}
