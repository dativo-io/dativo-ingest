"""Concrete implementations of incremental sync strategies."""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from .base import IncrementalStrategy


class FileModifiedTimeStrategy(IncrementalStrategy):
    """Strategy for tracking file modification times.

    Used for: CSV files, Google Drive files, Markdown KV files
    State format: file_{file_id} -> {last_modified: "...", file_id: "..."}
    """

    def should_process_entity(self, entity: Dict[str, Any]) -> bool:
        """Check if file should be processed based on modification time.

        Args:
            entity: Must contain 'file_id' and 'modified_time' (ISO format string)

        Returns:
            True if file should be processed, False to skip
        """
        file_id = (
            entity.get("file_id")
            or entity.get("path")
            or str(entity.get("file_path", ""))
        )
        current_modified_time = entity.get("modified_time")

        if not current_modified_time:
            # No modification time available, process file
            return True

        state = self.read_state()
        file_key = f"file_{file_id}"

        if file_key not in state:
            return True  # No state, process file

        last_modified = state[file_key].get("last_modified")
        if not last_modified:
            return True  # Invalid state, process file

        # Compare timestamps (string comparison works for ISO timestamps)
        if current_modified_time <= last_modified:
            # File hasn't been modified since last run
            if self.lookback_days == 0:
                return False  # Skip if no lookback
            # If lookback_days > 0, we still process files within the lookback window
            # This is handled by the caller, so we return True here
            return True

        return True  # File has been modified, process it

    def filter_records(
        self, records: List[Dict[str, Any]], entity: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """No filtering needed - all records are processed if file changed.

        Args:
            records: List of records
            entity: Entity metadata

        Returns:
            All records (no filtering)
        """
        return records

    def update_state(
        self, entity: Dict[str, Any], processed_records: List[Dict[str, Any]]
    ) -> None:
        """Update state with file modification time.

        Args:
            entity: Must contain 'file_id' and 'modified_time'
            processed_records: Processed records (not used for this strategy)
        """
        file_id = (
            entity.get("file_id")
            or entity.get("path")
            or str(entity.get("file_path", ""))
        )
        modified_time = entity.get("modified_time")

        if not modified_time:
            return  # Can't update state without modification time

        state = self.read_state()
        file_key = f"file_{file_id}"
        state[file_key] = {
            "last_modified": modified_time,
            "file_id": file_id,
        }
        self.write_state(state)

    def get_state_key(self, entity: Dict[str, Any]) -> str:
        """Get state key for file.

        Args:
            entity: Entity metadata

        Returns:
            State key string
        """
        file_id = (
            entity.get("file_id")
            or entity.get("path")
            or str(entity.get("file_path", ""))
        )
        return f"file_{file_id}"


class SpreadsheetModifiedTimeStrategy(IncrementalStrategy):
    """Strategy for tracking spreadsheet modification times.

    Used for: Google Sheets
    State format: spreadsheet_{spreadsheet_id} -> {last_modified: "...", spreadsheet_id: "..."}
    """

    def should_process_entity(self, entity: Dict[str, Any]) -> bool:
        """Check if spreadsheet should be processed based on modification time.

        Args:
            entity: Must contain 'spreadsheet_id' and 'modified_time' (ISO format string)

        Returns:
            True if spreadsheet should be processed, False to skip
        """
        spreadsheet_id = entity.get("spreadsheet_id")
        current_modified_time = entity.get("modified_time")

        if not spreadsheet_id or not current_modified_time:
            return True  # No ID or time, process it

        state = self.read_state()
        sheet_key = f"spreadsheet_{spreadsheet_id}"

        if sheet_key not in state:
            return True  # No state, process spreadsheet

        last_modified = state[sheet_key].get("last_modified")
        if not last_modified:
            return True  # Invalid state, process spreadsheet

        # Compare timestamps
        if current_modified_time <= last_modified:
            # Spreadsheet hasn't been modified since last run
            if self.lookback_days == 0:
                return False  # Skip if no lookback
            return True  # Process if within lookback window

        return True  # Spreadsheet has been modified, process it

    def filter_records(
        self, records: List[Dict[str, Any]], entity: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """No filtering needed - all records are processed if spreadsheet changed.

        Args:
            records: List of records
            entity: Entity metadata

        Returns:
            All records (no filtering)
        """
        return records

    def update_state(
        self, entity: Dict[str, Any], processed_records: List[Dict[str, Any]]
    ) -> None:
        """Update state with spreadsheet modification time.

        Args:
            entity: Must contain 'spreadsheet_id' and 'modified_time'
            processed_records: Processed records (not used for this strategy)
        """
        spreadsheet_id = entity.get("spreadsheet_id")
        modified_time = entity.get("modified_time")

        if not spreadsheet_id or not modified_time:
            return  # Can't update state without required fields

        state = self.read_state()
        sheet_key = f"spreadsheet_{spreadsheet_id}"
        state[sheet_key] = {
            "last_modified": modified_time,
            "spreadsheet_id": spreadsheet_id,
        }
        self.write_state(state)

    def get_state_key(self, entity: Dict[str, Any]) -> str:
        """Get state key for spreadsheet.

        Args:
            entity: Entity metadata

        Returns:
            State key string
        """
        spreadsheet_id = entity.get("spreadsheet_id")
        return f"spreadsheet_{spreadsheet_id}"


class CursorFieldStrategy(IncrementalStrategy):
    """Strategy for tracking cursor field values.

    Used for: Databases (Postgres, MySQL), CSV files with cursor fields
    State format: {object_name}.{cursor_field} -> {last_value: "...", updated_at: "..."}
    """

    def __init__(
        self,
        strategy_name: str,
        state_path: Path,
        config: Dict[str, Any],
    ):
        """Initialize cursor field strategy.

        Args:
            strategy_name: Strategy name
            state_path: Path to state file
            config: Must contain 'cursor_field' key
        """
        super().__init__(strategy_name, state_path, config)
        self.cursor_field = config.get("cursor_field")
        if not self.cursor_field:
            raise ValueError(
                "cursor_field strategy requires 'cursor_field' in incremental config"
            )

    def should_process_entity(self, entity: Dict[str, Any]) -> bool:
        """Always process entity - filtering happens at record level.

        Args:
            entity: Entity metadata

        Returns:
            Always True
        """
        return True

    def get_last_cursor_value(self, object_name: str) -> Optional[str]:
        """Get last cursor value from state.

        Args:
            object_name: Object/table name

        Returns:
            Last cursor value or None if not found
        """
        state = self.read_state()
        state_key = f"{object_name}.{self.cursor_field}"
        if state_key in state:
            return state[state_key].get("last_value")
        return None

    def filter_records(
        self, records: List[Dict[str, Any]], entity: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Filter records where cursor_field >= last_value.

        Args:
            records: List of records to filter
            entity: Must contain 'object_name' or 'name'

        Returns:
            Filtered list of records
        """
        object_name = entity.get("object_name") or entity.get("name") or "default"
        last_value = self.get_last_cursor_value(object_name)

        if last_value is None:
            # No previous state, return all records
            return records

        # Filter records where cursor_field >= last_value
        filtered = []
        for record in records:
            record_cursor = record.get(self.cursor_field)
            if record_cursor is None:
                # Skip records without cursor field value
                continue
            # String comparison works for ISO timestamps and sortable values
            if record_cursor >= last_value:
                filtered.append(record)

        return filtered

    def update_state(
        self, entity: Dict[str, Any], processed_records: List[Dict[str, Any]]
    ) -> None:
        """Update state with max cursor value from processed records.

        Args:
            entity: Must contain 'object_name' or 'name'
            processed_records: Records that were successfully processed
        """
        if not processed_records:
            return  # No records to update state from

        object_name = entity.get("object_name") or entity.get("name") or "default"
        state_key = f"{object_name}.{self.cursor_field}"

        # Find max cursor value in processed records
        max_cursor_value = None
        for record in processed_records:
            record_cursor = record.get(self.cursor_field)
            if record_cursor is not None:
                if max_cursor_value is None or record_cursor > max_cursor_value:
                    max_cursor_value = record_cursor

        if max_cursor_value is None:
            return  # No valid cursor values found

        # Update state
        state = self.read_state()
        if state_key not in state:
            state[state_key] = {}
        state[state_key]["last_value"] = max_cursor_value
        state[state_key]["updated_at"] = datetime.now().isoformat()
        self.write_state(state)

    def get_state_key(self, entity: Dict[str, Any]) -> str:
        """Get state key for object and cursor field.

        Args:
            entity: Entity metadata

        Returns:
            State key string
        """
        object_name = entity.get("object_name") or entity.get("name") or "default"
        return f"{object_name}.{self.cursor_field}"
