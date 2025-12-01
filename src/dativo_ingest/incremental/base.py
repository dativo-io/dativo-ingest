"""Base classes for incremental sync strategies."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..validator import IncrementalStateManager


class IncrementalStrategy(ABC):
    """Base class for incremental sync strategies.

    All incremental strategies must implement this interface to provide
    consistent behavior across all extractors.
    """

    def __init__(
        self,
        strategy_name: str,
        state_path: Path,
        config: Dict[str, Any],
    ):
        """Initialize incremental strategy.

        Args:
            strategy_name: Name of the strategy (e.g., "cursor_field", "file_modified_time")
            state_path: Path to state file for persistence
            config: Strategy-specific configuration dictionary
        """
        self.strategy_name = strategy_name
        self.state_path = state_path
        self.config = config
        self.lookback_days = config.get("lookback_days", 0)

    @abstractmethod
    def should_process_entity(self, entity: Dict[str, Any]) -> bool:
        """Determine if an entity (file, table, spreadsheet) should be processed.

        This is called before reading any data from the entity.
        For file-based strategies, this checks if the file was modified.
        For cursor-based strategies, this typically returns True (filtering happens at record level).

        Args:
            entity: Entity metadata dictionary (file path, table name, spreadsheet ID, etc.)

        Returns:
            True if entity should be processed, False to skip
        """
        pass

    @abstractmethod
    def filter_records(
        self, records: List[Dict[str, Any]], entity: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Filter records based on incremental state.

        This is called after reading records from the entity.
        For cursor-based strategies, this filters records where cursor_field >= last_value.
        For file-based strategies, this typically returns all records (filtering happened at entity level).

        Args:
            records: List of records to filter
            entity: Entity metadata dictionary

        Returns:
            Filtered list of records
        """
        pass

    @abstractmethod
    def update_state(
        self, entity: Dict[str, Any], processed_records: List[Dict[str, Any]]
    ) -> None:
        """Update incremental state after processing records.

        Args:
            entity: Entity metadata dictionary
            processed_records: Records that were successfully processed
        """
        pass

    def get_state_key(self, entity: Dict[str, Any]) -> str:
        """Get state key for this entity.

        Args:
            entity: Entity metadata dictionary

        Returns:
            State key string
        """
        raise NotImplementedError("Subclasses must implement get_state_key")

    def read_state(self) -> Dict[str, Any]:
        """Read current state from state file.

        Returns:
            State dictionary
        """
        return IncrementalStateManager.read_state(self.state_path)

    def write_state(self, state: Dict[str, Any]) -> None:
        """Write state to state file.

        Args:
            state: State dictionary to write
        """
        IncrementalStateManager.write_state(self.state_path, state)
