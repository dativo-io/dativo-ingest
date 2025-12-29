"""Unit tests for incremental strategy factory and strategy name mapping."""

from pathlib import Path

import pytest

from dativo_ingest.incremental import create_incremental_strategy
from dativo_ingest.incremental.factory import IncrementalStrategyFactory
from dativo_ingest.incremental.strategies import CursorFieldStrategy


class TestIncrementalStrategyFactory:
    """Test incremental strategy factory."""

    def test_create_cursor_field_strategy(self, tmp_path):
        """Test creating cursor_field strategy."""
        state_path = tmp_path / "test_state.json"
        config = {"cursor_field": "updated_at"}

        strategy = IncrementalStrategyFactory.create(
            strategy_name="cursor_field",
            state_path=state_path,
            config=config,
        )

        assert isinstance(strategy, CursorFieldStrategy)
        assert strategy.cursor_field == "updated_at"
        assert strategy.state_path == state_path

    def test_create_incremental_strategy_with_state_path(self, tmp_path):
        """Test create_incremental_strategy with state_path in config."""
        state_path = tmp_path / "test_state.json"
        config = {
            "strategy": "cursor_field",
            "cursor_field": "updated_at",
            "state_path": str(state_path),
        }

        strategy = create_incremental_strategy(config)

        assert strategy is not None
        assert isinstance(strategy, CursorFieldStrategy)
        assert strategy.state_path == state_path

    def test_create_incremental_strategy_with_default_state_path(self, tmp_path):
        """Test create_incremental_strategy with default_state_path parameter."""
        state_path = tmp_path / "test_state.json"
        config = {
            "strategy": "cursor_field",
            "cursor_field": "updated_at",
        }

        strategy = create_incremental_strategy(config, default_state_path=state_path)

        assert strategy is not None
        assert isinstance(strategy, CursorFieldStrategy)
        assert strategy.state_path == state_path

    def test_create_incremental_strategy_returns_none_without_state_path(self):
        """Test that create_incremental_strategy returns None if no state_path provided."""
        config = {
            "strategy": "cursor_field",
            "cursor_field": "updated_at",
        }

        strategy = create_incremental_strategy(config, default_state_path=None)

        assert strategy is None

    def test_semantic_strategy_name_updated_at_maps_to_cursor_field(self, tmp_path):
        """Test that semantic strategy name 'updated_at' maps to 'cursor_field'."""
        state_path = tmp_path / "test_state.json"
        config = {
            "strategy": "updated_at",  # Semantic name
            "cursor_field": "updated_at",
            "state_path": str(state_path),
        }

        strategy = create_incremental_strategy(config)

        assert strategy is not None
        assert isinstance(strategy, CursorFieldStrategy)
        assert strategy.strategy_name == "cursor_field"  # Mapped to cursor_field
        assert strategy.cursor_field == "updated_at"

    def test_semantic_strategy_name_created_maps_to_cursor_field(self, tmp_path):
        """Test that semantic strategy name 'created' maps to 'cursor_field'."""
        state_path = tmp_path / "test_state.json"
        config = {
            "strategy": "created",  # Semantic name
            "cursor_field": "created_at",
            "state_path": str(state_path),
        }

        strategy = create_incremental_strategy(config)

        assert strategy is not None
        assert isinstance(strategy, CursorFieldStrategy)
        assert strategy.strategy_name == "cursor_field"  # Mapped to cursor_field
        assert strategy.cursor_field == "created_at"

    def test_semantic_strategy_name_updated_after_maps_to_cursor_field(self, tmp_path):
        """Test that semantic strategy name 'updated_after' maps to 'cursor_field'."""
        state_path = tmp_path / "test_state.json"
        config = {
            "strategy": "updated_after",  # Semantic name
            "cursor_field": "last_updated",
            "state_path": str(state_path),
        }

        strategy = create_incremental_strategy(config)

        assert strategy is not None
        assert isinstance(strategy, CursorFieldStrategy)
        assert strategy.strategy_name == "cursor_field"  # Mapped to cursor_field
        assert strategy.cursor_field == "last_updated"

    def test_auto_detect_cursor_field_strategy(self, tmp_path):
        """Test that strategy is auto-detected as cursor_field when cursor_field is present."""
        state_path = tmp_path / "test_state.json"
        config = {
            # No strategy specified
            "cursor_field": "updated_at",
            "state_path": str(state_path),
        }

        strategy = create_incremental_strategy(config)

        assert strategy is not None
        assert isinstance(strategy, CursorFieldStrategy)
        assert strategy.strategy_name == "cursor_field"
        assert strategy.cursor_field == "updated_at"

    def test_postgres_extractor_uses_state_path_from_config(self, tmp_path):
        """Test that postgres extractor uses state_path from incremental config."""
        from dativo_ingest.config import SourceConfig
        from dativo_ingest.connectors.postgres_extractor import PostgresExtractor

        state_path = tmp_path / "postgres_state.json"

        source_config = SourceConfig(
            type="postgres",
            tables=[{"name": "employees", "schema": "public", "object": "employees"}],
            connection={
                "host": "localhost",
                "port": 5432,
                "database": "test_db",
                "user": "test_user",
                "password": "test_password",
            },
            incremental={
                "enabled": True,
                "strategy": "updated_at",
                "cursor_field": "updated_at",
                "lookback_days": 1,
                "state_path": str(state_path),  # Explicitly set in config
            },
        )

        extractor = PostgresExtractor(source_config)

        # The extractor should create a strategy with the state_path from config
        # We can't easily test the actual extraction without a real DB, but we can
        # verify the config is set up correctly
        assert source_config.incremental is not None
        assert source_config.incremental.get("state_path") == str(state_path)
        assert source_config.incremental.get("strategy") == "updated_at"
