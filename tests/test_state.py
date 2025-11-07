"""Unit tests for incremental state management."""

import sys
import tempfile
from pathlib import Path

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.validator import IncrementalStateManager


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


class TestIncrementalStateManager:
    """Test incremental state management operations."""

    def test_read_state_nonexistent(self, temp_dir):
        """Test reading state from non-existent file returns empty dict."""
        state_path = temp_dir / "state.json"
        state = IncrementalStateManager.read_state(state_path)
        assert state == {}

    def test_read_write_state(self, temp_dir):
        """Test reading and writing state."""
        state_path = temp_dir / "state.json"
        test_state = {"file_123": {"last_modified": "2024-01-01T00:00:00Z"}}
        IncrementalStateManager.write_state(state_path, test_state)
        read_state = IncrementalStateManager.read_state(state_path)
        assert read_state == test_state

    def test_should_skip_file_no_state(self, temp_dir):
        """Test file should not be skipped if no state exists."""
        state_path = temp_dir / "state.json"
        result = IncrementalStateManager.should_skip_file(
            "file_123", "2024-01-01T00:00:00Z", state_path
        )
        assert result is False

    def test_should_skip_file_not_modified(self, temp_dir):
        """Test file should be skipped if not modified."""
        state_path = temp_dir / "state.json"
        # Write initial state
        IncrementalStateManager.write_state(
            state_path, {"file_123": {"last_modified": "2024-01-02T00:00:00Z"}}
        )
        # Check with older timestamp
        result = IncrementalStateManager.should_skip_file(
            "file_123", "2024-01-01T00:00:00Z", state_path, lookback_days=0
        )
        assert result is True

    def test_update_file_state(self, temp_dir):
        """Test updating file state."""
        state_path = temp_dir / "state.json"
        IncrementalStateManager.update_file_state(
            "file_123", "2024-01-01T00:00:00Z", state_path
        )
        state = IncrementalStateManager.read_state(state_path)
        assert "file_file_123" in state
        assert state["file_file_123"]["last_modified"] == "2024-01-01T00:00:00Z"

