"""Factory for creating incremental strategy instances."""

from pathlib import Path
from typing import Any, Dict, Optional

from .base import IncrementalStrategy
from .strategies import (
    CursorFieldStrategy,
    FileModifiedTimeStrategy,
    SpreadsheetModifiedTimeStrategy,
)


class IncrementalStrategyFactory:
    """Factory for creating incremental strategy instances."""

    # Registry of available strategies
    _strategies = {
        "file_modified_time": FileModifiedTimeStrategy,
        "spreadsheet_modified_time": SpreadsheetModifiedTimeStrategy,
        "cursor_field": CursorFieldStrategy,
    }

    @classmethod
    def create(
        cls,
        strategy_name: str,
        state_path: Path,
        config: Dict[str, Any],
    ) -> IncrementalStrategy:
        """Create an incremental strategy instance.

        Args:
            strategy_name: Name of the strategy
            state_path: Path to state file
            config: Strategy configuration dictionary

        Returns:
            IncrementalStrategy instance

        Raises:
            ValueError: If strategy name is not supported
        """
        strategy_class = cls._strategies.get(strategy_name)
        if not strategy_class:
            supported = ", ".join(cls._strategies.keys())
            raise ValueError(
                f"Unsupported incremental strategy: {strategy_name}. "
                f"Supported strategies: {supported}"
            )

        return strategy_class(strategy_name, state_path, config)

    @classmethod
    def register_strategy(
        cls, name: str, strategy_class: type[IncrementalStrategy]
    ) -> None:
        """Register a custom strategy class.

        Args:
            name: Strategy name
            strategy_class: Strategy class (must inherit from IncrementalStrategy)
        """
        if not issubclass(strategy_class, IncrementalStrategy):
            raise TypeError(
                f"Strategy class must inherit from IncrementalStrategy, got {strategy_class}"
            )
        cls._strategies[name] = strategy_class

    @classmethod
    def get_supported_strategies(cls) -> list[str]:
        """Get list of supported strategy names.

        Returns:
            List of strategy names
        """
        return list(cls._strategies.keys())


def create_incremental_strategy(
    incremental_config: Optional[Dict[str, Any]],
    default_state_path: Optional[Path] = None,
) -> Optional[IncrementalStrategy]:
    """Convenience function to create an incremental strategy from config.

    Args:
        incremental_config: Incremental configuration dictionary (from source_config.incremental)
        default_state_path: Default state path if not specified in config

    Returns:
        IncrementalStrategy instance or None if incremental is disabled or invalid
    """
    if not incremental_config or not isinstance(incremental_config, dict):
        return None

    # Get strategy name
    strategy_name = incremental_config.get("strategy")
    if not strategy_name:
        # Auto-detect strategy based on config
        if incremental_config.get("cursor_field"):
            strategy_name = "cursor_field"
        else:
            # Default to file_modified_time for file-based sources
            strategy_name = "file_modified_time"

    # Get state path
    state_path_str = incremental_config.get("state_path")
    if state_path_str:
        state_path = Path(state_path_str)
    elif default_state_path:
        state_path = default_state_path
    else:
        # Can't create strategy without state path
        return None

    # Create strategy
    try:
        return IncrementalStrategyFactory.create(
            strategy_name=strategy_name,
            state_path=state_path,
            config=incremental_config,
        )
    except (ValueError, TypeError) as e:
        # Strategy not supported or invalid config, return None
        # Logging can be added here if needed
        return None
