"""Google Sheets extractor supporting native, Airbyte, and Meltano engines."""

import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from ..config import ConnectorRecipe, SourceConfig
from ..incremental import create_incremental_strategy
from ..incremental.base import IncrementalStrategy
from ..incremental.strategies import SpreadsheetModifiedTimeStrategy
from ..logging import get_logger
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
        self.logger = get_logger()

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
        self,
        state_manager: Optional[IncrementalStateManager] = None,
        checkpoint_context: Optional[Dict[str, Any]] = None,
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from Google Sheets.

        Args:
            state_manager: Optional incremental state manager for tracking spreadsheet state
            checkpoint_context: Optional checkpoint context for WAL resume

        Yields:
            Batches of records as dictionaries
        """
        # Delegate to engine extractor if using non-native engine
        if self._use_engine:
            yield from self._engine_extractor.extract(
                state_manager, checkpoint_context=checkpoint_context
            )
            return

        # Use native implementation
        spreadsheets = self._get_spreadsheets_to_extract()
        if not spreadsheets:
            raise ValueError(
                "Google Sheets source requires 'spreadsheets' or 'spreadsheet_id' configuration"
            )

        # Create incremental strategy if configured
        incremental_strategy: Optional[IncrementalStrategy] = None
        if self.source_config.incremental:
            # Default to spreadsheet_modified_time for Google Sheets
            incremental_config = self.source_config.incremental.copy()
            if not incremental_config.get("strategy"):
                incremental_config["strategy"] = "spreadsheet_modified_time"
            incremental_strategy = create_incremental_strategy(
                incremental_config,
                default_state_path=None,
            )

        # Check for WAL checkpoint to resume from (before processing loop)
        wal_manager = None
        checkpointed_spreadsheet_id = None
        if checkpoint_context:
            wal_manager = checkpoint_context.get("wal_manager")
            checkpoint = checkpoint_context.get("checkpoint")
            if checkpoint and checkpoint.get("type") == "spreadsheet_based":
                checkpointed_spreadsheet_id = checkpoint.get("spreadsheet_id")
                if checkpointed_spreadsheet_id:
                    self.logger.info(
                        f"Resuming from WAL checkpoint at spreadsheet: {checkpointed_spreadsheet_id}",
                        extra={
                            "checkpointed_spreadsheet_id": checkpointed_spreadsheet_id,
                            "event_type": "wal_resume_detected",
                        },
                    )

        # Process each spreadsheet
        for spreadsheet_config in spreadsheets:
            spreadsheet_id = spreadsheet_config.get("id") or spreadsheet_config.get(
                "spreadsheet_id"
            )
            if not spreadsheet_id:
                continue

            # Check for WAL checkpoint resume: skip all spreadsheets up to and including
            # the checkpointed one (since checkpoint is updated after processing)
            if checkpointed_spreadsheet_id:
                if spreadsheet_id == checkpointed_spreadsheet_id:
                    # Found checkpointed spreadsheet - skip it and resume from next
                    self.logger.info(
                        f"Skipping checkpointed spreadsheet (already processed): {spreadsheet_id}",
                        extra={
                            "spreadsheet_id": str(spreadsheet_id),
                            "event_type": "spreadsheet_wal_skip",
                        },
                    )
                    # Clear checkpoint flag so we process remaining spreadsheets
                    checkpointed_spreadsheet_id = None
                    continue
                else:
                    # Haven't reached checkpoint yet - skip this spreadsheet
                    self.logger.info(
                        f"Skipping spreadsheet (before checkpoint): {spreadsheet_id}",
                        extra={
                            "spreadsheet_id": str(spreadsheet_id),
                            "checkpointed_spreadsheet_id": checkpointed_spreadsheet_id,
                            "event_type": "spreadsheet_wal_skip_before_checkpoint",
                        },
                    )
                    continue

            range_name = spreadsheet_config.get("range", "A1:Z1000")
            sheet_name = spreadsheet_config.get("sheet", None)

            # Build full range notation
            if sheet_name:
                full_range = f"{sheet_name}!{range_name}"
            else:
                full_range = range_name

            # Get spreadsheet modification time for incremental sync
            modified_time = self._get_spreadsheet_modified_time(spreadsheet_id)
            modified_time_iso = modified_time.isoformat() if modified_time else None

            # Create entity_metadata once for use throughout spreadsheet processing
            entity_metadata = {
                "spreadsheet_id": str(spreadsheet_id),
                "modified_time": modified_time_iso,
            }

            # Check incremental state if enabled
            if incremental_strategy:
                if not incremental_strategy.should_process_entity(entity_metadata):
                    self.logger.info(
                        f"Skipping spreadsheet (already processed): {spreadsheet_id}",
                        extra={
                            "spreadsheet_id": str(spreadsheet_id),
                            "event_type": "spreadsheet_skipped",
                        },
                    )
                    continue  # Skip this spreadsheet

            # Read data from spreadsheet
            rows = self._read_range(spreadsheet_id, full_range)

            if not rows:
                # Even if spreadsheet is empty, update state for file-based strategies
                # to prevent infinite reprocessing
                if incremental_strategy:
                    is_file_based_strategy = isinstance(
                        incremental_strategy, SpreadsheetModifiedTimeStrategy
                    )
                    if is_file_based_strategy:
                        incremental_strategy.update_state(entity_metadata, [])
                # Update WAL checkpoint even for empty spreadsheets
                if wal_manager and checkpoint_context:
                    stream_name = checkpoint_context.get(
                        "stream_name", str(spreadsheet_id)
                    )
                    checkpoint_data = {
                        "type": "spreadsheet_based",
                        "spreadsheet_id": str(spreadsheet_id),
                        "records_processed": 0,
                    }
                    wal_manager.update_checkpoint(stream_name, checkpoint_data)
                continue

            # Convert rows to records
            has_header = spreadsheet_config.get("has_header", True)
            records = self._rows_to_records(rows, has_header=has_header)

            # Filter records using incremental strategy (if needed)
            if incremental_strategy and records:
                records = incremental_strategy.filter_records(records, entity_metadata)

            if records:
                # Update WAL checkpoint after processing spreadsheet
                if wal_manager and checkpoint_context:
                    stream_name = checkpoint_context.get(
                        "stream_name", str(spreadsheet_id)
                    )
                    checkpoint_data = {
                        "type": "spreadsheet_based",
                        "spreadsheet_id": str(spreadsheet_id),
                        "records_processed": len(records),
                    }
                    wal_manager.update_checkpoint(stream_name, checkpoint_data)

                yield records

            # Update state after successful processing
            # For file-based strategies (SpreadsheetModifiedTimeStrategy), update state even if
            # there are no processed records, as they only need the modification time.
            # For cursor-based strategies, only update if there are processed records.
            if incremental_strategy:
                is_file_based_strategy = isinstance(
                    incremental_strategy, SpreadsheetModifiedTimeStrategy
                )
                # File-based strategies need state update even for empty spreadsheets to prevent infinite reprocessing
                # Cursor-based strategies only update when there are processed records
                should_update_state = is_file_based_strategy or len(records) > 0
                if should_update_state:
                    incremental_strategy.update_state(entity_metadata, records or [])

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
