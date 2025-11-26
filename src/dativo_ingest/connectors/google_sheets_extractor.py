"""Google Sheets extractor supporting native, Airbyte, and Meltano engines."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from ..config import ConnectorRecipe, SourceConfig
from ..validator import IncrementalStateManager
from .engine_framework import AirbyteExtractor, BaseEngineExtractor


class GoogleSheetsExtractor:
    """Extracts data from Google Sheets using Google Sheets API v4."""

    def __init__(
        self,
        source_config: SourceConfig,
        connector_recipe: Optional[ConnectorRecipe] = None,
        tenant_id: Optional[str] = None,
    ):
        """Initialize Google Sheets extractor.

        Args:
            source_config: Source configuration with spreadsheet IDs and credentials
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
                    f"{engine_type} engine not yet implemented for google_sheets"
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
            "api_version": "v4",
            "value_render_option": "UNFORMATTED_VALUE",
            "date_time_render_option": "SERIAL_NUMBER",
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
                    if Path(path).exists():
                        return path

        # Check environment variable
        creds_path = os.getenv("GSHEETS_CREDENTIALS_PATH") or os.getenv(
            "GOOGLE_APPLICATION_CREDENTIALS"
        )
        if creds_path and Path(creds_path).exists():
            return creds_path

        raise ValueError(
            "Google Sheets service account credentials not found. "
            "Provide credentials_path in config or set GSHEETS_CREDENTIALS_PATH environment variable."
        )

    def _init_google_client(self) -> None:
        """Initialize Google Sheets API client."""
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError(
                "google-api-python-client and google-auth are required for Google Sheets extraction. "
                "Install with: pip install google-api-python-client google-auth"
            )

        # Load service account credentials
        credentials = service_account.Credentials.from_service_account_file(
            self.credentials_path,
            scopes=[
                "https://www.googleapis.com/auth/spreadsheets.readonly",
                "https://www.googleapis.com/auth/spreadsheets",
            ],
        )

        # Build Sheets API client
        self.sheets_service = build(
            "sheets",
            self.engine_options.get("api_version", "v4"),
            credentials=credentials,
        )

    def _get_spreadsheets_to_extract(self) -> List[Dict[str, Any]]:
        """Get list of spreadsheets to extract from source config.

        Returns:
            List of spreadsheet configurations
        """
        if (
            hasattr(self.source_config, "spreadsheets")
            and self.source_config.spreadsheets
        ):
            return self.source_config.spreadsheets

        if (
            isinstance(self.source_config, dict)
            and "spreadsheets" in self.source_config
        ):
            return self.source_config["spreadsheets"]

        # Check for single spreadsheet_id
        spreadsheet_id = getattr(self.source_config, "spreadsheet_id", None)
        if spreadsheet_id:
            return [{"id": spreadsheet_id}]

        if (
            isinstance(self.source_config, dict)
            and "spreadsheet_id" in self.source_config
        ):
            return [{"id": self.source_config["spreadsheet_id"]}]

        raise ValueError(
            "Google Sheets source requires 'spreadsheets' or 'spreadsheet_id' configuration"
        )

    def _get_spreadsheet_modified_time(self, spreadsheet_id: str) -> Optional[datetime]:
        """Get spreadsheet modification time.

        Args:
            spreadsheet_id: Google Sheets spreadsheet ID

        Returns:
            Datetime object or None
        """
        try:
            # Use Drive API to get file metadata
            from google.oauth2 import service_account
            from googleapiclient.discovery import build

            credentials = service_account.Credentials.from_service_account_file(
                self.credentials_path,
                scopes=["https://www.googleapis.com/auth/drive.metadata.readonly"],
            )
            drive_service = build("drive", "v3", credentials=credentials)

            file_metadata = (
                drive_service.files()
                .get(fileId=spreadsheet_id, fields="modifiedTime")
                .execute()
            )
            modified_time_str = file_metadata.get("modifiedTime")

            if modified_time_str:
                return datetime.fromisoformat(modified_time_str.replace("Z", "+00:00"))
        except Exception:
            # If we can't get modification time, return None
            pass

        return None

    def _read_range(
        self, spreadsheet_id: str, range_name: str = "A1:Z1000"
    ) -> List[List[Any]]:
        """Read a range from a Google Sheet.

        Args:
            spreadsheet_id: Google Sheets spreadsheet ID
            range_name: A1 notation range (e.g., "Sheet1!A1:Z1000")

        Returns:
            List of rows, where each row is a list of values
        """
        value_render_option = self.engine_options.get(
            "value_render_option", "UNFORMATTED_VALUE"
        )
        date_time_render_option = self.engine_options.get(
            "date_time_render_option", "SERIAL_NUMBER"
        )

        try:
            result = (
                self.sheets_service.spreadsheets()
                .values()
                .get(
                    spreadsheetId=spreadsheet_id,
                    range=range_name,
                    valueRenderOption=value_render_option,
                    dateTimeRenderOption=date_time_render_option,
                )
                .execute()
            )

            return result.get("values", [])
        except Exception as e:
            raise RuntimeError(
                f"Failed to read range from spreadsheet {spreadsheet_id}: {str(e)}"
            ) from e

    def _rows_to_records(
        self, rows: List[List[Any]], has_header: bool = True
    ) -> List[Dict[str, Any]]:
        """Convert rows to records (dictionaries).

        Args:
            rows: List of rows from spreadsheet
            has_header: Whether first row contains headers

        Returns:
            List of record dictionaries
        """
        if not rows:
            return []

        if has_header:
            headers = [str(cell) for cell in rows[0]]
            data_rows = rows[1:]
        else:
            # Generate column names if no header
            max_cols = max(len(row) for row in rows) if rows else 0
            headers = [f"column_{i+1}" for i in range(max_cols)]
            data_rows = rows

        records = []
        for row in data_rows:
            record = {}
            for i, header in enumerate(headers):
                value = row[i] if i < len(row) else None
                record[header] = value
            records.append(record)

        return records

    def extract(
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from Google Sheets.

        Args:
            state_manager: Optional incremental state manager for tracking spreadsheet state

        Yields:
            Batches of records as dictionaries
        """
        # Delegate to engine extractor if using non-native engine
        if self._use_engine:
            yield from self._engine_extractor.extract(state_manager)
            return

        # Use native implementation
        spreadsheets = self._get_spreadsheets_to_extract()
        if not spreadsheets:
            raise ValueError(
                "Google Sheets source requires 'spreadsheets' or 'spreadsheet_id' configuration"
            )

        # Get incremental configuration
        incremental = self.source_config.incremental or {}
        strategy = incremental.get("strategy", "spreadsheet_modified_time")
        lookback_days = incremental.get("lookback_days", 0)
        state_path_str = incremental.get("state_path", "")
        state_path = Path(state_path_str) if state_path_str else None

        # Process each spreadsheet
        for spreadsheet_config in spreadsheets:
            spreadsheet_id = spreadsheet_config.get("id") or spreadsheet_config.get(
                "spreadsheet_id"
            )
            if not spreadsheet_id:
                continue

            range_name = spreadsheet_config.get("range", "A1:Z1000")
            sheet_name = spreadsheet_config.get("sheet", None)

            # Build full range notation
            if sheet_name:
                full_range = f"{sheet_name}!{range_name}"
            else:
                full_range = range_name

            # Check incremental state if enabled
            if strategy == "spreadsheet_modified_time" and state_path:
                modified_time = self._get_spreadsheet_modified_time(spreadsheet_id)

                if modified_time:
                    spreadsheet_id_str = str(spreadsheet_id)
                    modified_time_iso = modified_time.isoformat()

                    if IncrementalStateManager.should_skip_file(
                        file_id=spreadsheet_id_str,
                        current_modified_time=modified_time_iso,
                        state_path=state_path,
                        lookback_days=lookback_days,
                    ):
                        continue  # Skip this spreadsheet

            # Read data from spreadsheet
            rows = self._read_range(spreadsheet_id, full_range)

            if not rows:
                continue

            # Convert rows to records
            has_header = spreadsheet_config.get("has_header", True)
            records = self._rows_to_records(rows, has_header=has_header)

            if records:
                yield records

            # Update state after successful processing
            if state_path:
                modified_time = self._get_spreadsheet_modified_time(spreadsheet_id)
                if modified_time:
                    spreadsheet_id_str = str(spreadsheet_id)
                    modified_time_iso = modified_time.isoformat()
                    IncrementalStateManager.update_file_state(
                        file_id=spreadsheet_id_str,
                        modified_time=modified_time_iso,
                        state_path=state_path,
                    )

    def extract_metadata(self) -> Dict[str, Any]:
        """Extract naturally available metadata from Google Sheets.

        Extracts metadata that is naturally available:
        - Column names from first row (if has_header=True)
        - Spreadsheet metadata

        Returns:
            Dictionary with "tags" key containing field_name -> metadata mapping
        """
        source_tags = {}

        try:
            spreadsheets = self._get_spreadsheets_to_extract()

            # Process first spreadsheet to get column names
            for spreadsheet_config in spreadsheets[:1]:
                spreadsheet_id = spreadsheet_config.get("id") or spreadsheet_config.get(
                    "spreadsheet_id"
                )
                if not spreadsheet_id:
                    continue

                try:
                    range_name = spreadsheet_config.get(
                        "range", "A1:Z1"
                    )  # Just header row
                    sheet_name = spreadsheet_config.get("sheet", None)

                    if sheet_name:
                        full_range = f"{sheet_name}!{range_name}"
                    else:
                        full_range = range_name

                    # Read just the header row
                    rows = self._read_range(spreadsheet_id, full_range)

                    if rows:
                        has_header = spreadsheet_config.get("has_header", True)
                        if has_header:
                            headers = [str(cell) for cell in rows[0]]
                            for header in headers:
                                source_tags[header] = "column"
                        else:
                            # Generate column names
                            max_cols = len(rows[0]) if rows else 0
                            for i in range(max_cols):
                                source_tags[f"column_{i+1}"] = "column"

                except Exception:
                    # If reading fails, continue
                    continue

        except Exception:
            # If metadata extraction fails, return empty tags
            pass

        return {"tags": source_tags}
