"""Tests for state directory initialization."""

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dativo_ingest.config import JobConfig, SourceConfig
from dativo_ingest.validator import initialize_state_directory


class TestInitializeStateDirectory:
    """Test state directory initialization."""

    def test_creates_parent_directories(self, tmp_path):
        """Test that parent directories are created."""
        state_path = tmp_path / "nested" / "deep" / "state.json"

        # Create mock job config with incremental config
        source_config = Mock(spec=SourceConfig)
        source_config.incremental = {"state_path": str(state_path)}

        job_config = Mock(spec=JobConfig)
        job_config.get_source.return_value = source_config

        initialize_state_directory(job_config)

        assert state_path.parent.exists()
        assert state_path.parent.is_dir()

    def test_validates_writable_directory(self, tmp_path):
        """Test that directory writability is validated."""
        state_path = tmp_path / "state.json"

        source_config = Mock(spec=SourceConfig)
        source_config.incremental = {"state_path": str(state_path)}

        job_config = Mock(spec=JobConfig)
        job_config.get_source.return_value = source_config

        # Should not raise if directory is writable
        initialize_state_directory(job_config)

    def test_handles_no_incremental_config(self):
        """Test that function handles missing incremental config."""
        source_config = Mock(spec=SourceConfig)
        source_config.incremental = None

        job_config = Mock(spec=JobConfig)
        job_config.get_source.return_value = source_config

        # Should not raise
        initialize_state_directory(job_config)

    def test_handles_empty_state_path(self):
        """Test that function handles empty state_path."""
        source_config = Mock(spec=SourceConfig)
        source_config.incremental = {"state_path": ""}

        job_config = Mock(spec=JobConfig)
        job_config.get_source.return_value = source_config

        # Should not raise
        initialize_state_directory(job_config)

    def test_handles_missing_state_path_key(self):
        """Test that function handles missing state_path key."""
        source_config = Mock(spec=SourceConfig)
        source_config.incremental = {}

        job_config = Mock(spec=JobConfig)
        job_config.get_source.return_value = source_config

        # Should not raise
        initialize_state_directory(job_config)

    def test_raises_on_non_writable_directory(self, tmp_path):
        """Test that PermissionError is raised for non-writable directory."""
        # Create a read-only directory (if possible on this system)
        read_only_dir = tmp_path / "readonly"
        read_only_dir.mkdir()

        state_path = read_only_dir / "state.json"

        source_config = Mock(spec=SourceConfig)
        source_config.incremental = {"state_path": str(state_path)}

        job_config = Mock(spec=JobConfig)
        job_config.get_source.return_value = source_config

        # Try to make directory read-only (may not work on all systems)
        try:
            os.chmod(read_only_dir, 0o555)
            with pytest.raises(PermissionError, match="not writable"):
                initialize_state_directory(job_config)
        except (OSError, PermissionError):
            # On some systems (e.g., macOS), we can't make directories truly read-only
            # Just verify the function doesn't crash
            initialize_state_directory(job_config)
        finally:
            # Restore permissions for cleanup
            try:
                os.chmod(read_only_dir, 0o755)
            except OSError:
                pass
