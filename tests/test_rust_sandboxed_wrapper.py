"""Tests for Rust sandboxed plugin wrappers.

Tests verify that:
1. All wrapper methods (discover, extract, write_batch, commit_files) call sandbox.execute()
2. Methods properly handle responses from the sandbox
3. Errors are properly raised when sandbox returns errors
4. Methods handle different response formats correctly
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from dativo_ingest.config import SourceConfig, TargetConfig
from dativo_ingest.exceptions import SandboxError
from dativo_ingest.plugins import ConnectionTestResult, DiscoveryResult
from dativo_ingest.rust_sandboxed_wrapper import (
    SandboxedRustReaderWrapper,
    SandboxedRustWriterWrapper,
)


class TestSandboxedRustReaderWrapper:
    """Test Rust sandboxed reader wrapper."""

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_discover_calls_sandbox_execute(self, mock_docker, tmp_path):
        """Test that discover() calls sandbox.execute() with correct parameters."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        # Mock docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        # Mock container and exec_run
        mock_container = Mock()
        mock_container.start.return_value = None
        mock_container.exec_run.return_value = Mock(
            exit_code=0,
            output=b'{"status": "success", "message": "Initialized"}\n{"status": "success", "data": {"objects": [{"name": "table1"}], "metadata": {}}}',
        )
        mock_container.logs.return_value = b""
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()  # Image exists

        source_config = SourceConfig(type="test", connection={"host": "localhost"})
        wrapper = SandboxedRustReaderWrapper(
            str(plugin_file), source_config, mode="cloud"
        )

        result = wrapper.discover()

        # Verify sandbox.execute was called (via exec_run)
        assert mock_container.exec_run.called
        # Verify result
        assert isinstance(result, DiscoveryResult)
        assert len(result.objects) == 1
        assert result.objects[0]["name"] == "table1"

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_discover_handles_error_response(self, mock_docker, tmp_path):
        """Test that discover() raises SandboxError when sandbox returns error."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        mock_container = Mock()
        mock_container.start.return_value = None
        mock_container.exec_run.return_value = Mock(
            exit_code=0,
            output=b'{"status": "success", "message": "Initialized"}\n{"error": "Plugin error"}',
        )
        mock_container.logs.return_value = b""
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        source_config = SourceConfig(type="test", connection={})
        wrapper = SandboxedRustReaderWrapper(
            str(plugin_file), source_config, mode="cloud"
        )

        with pytest.raises(SandboxError, match="Discover failed"):
            wrapper.discover()

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_extract_calls_sandbox_execute(self, mock_docker, tmp_path):
        """Test that extract() calls sandbox.execute() and yields batches."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        # Mock response with batches in data field
        mock_container = Mock()
        mock_container.start.return_value = None
        mock_container.exec_run.return_value = Mock(
            exit_code=0,
            output=b'{"status": "success", "message": "Initialized"}\n{"status": "success", "data": [[{"id": 1}], [{"id": 2}]]}',
        )
        mock_container.logs.return_value = b""
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        source_config = SourceConfig(type="test", connection={})
        wrapper = SandboxedRustReaderWrapper(
            str(plugin_file), source_config, mode="cloud"
        )

        batches = list(wrapper.extract())

        # Verify sandbox.execute was called
        assert mock_container.exec_run.called
        # Verify batches were yielded
        assert len(batches) == 2
        assert batches[0] == [{"id": 1}]
        assert batches[1] == [{"id": 2}]

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_extract_handles_error_response(self, mock_docker, tmp_path):
        """Test that extract() raises SandboxError when sandbox returns error."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        mock_container = Mock()
        mock_container.start.return_value = None
        mock_container.exec_run.return_value = Mock(
            exit_code=0,
            output=b'{"status": "success", "message": "Initialized"}\n{"error": "Extraction failed"}',
        )
        mock_container.logs.return_value = b""
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        source_config = SourceConfig(type="test", connection={})
        wrapper = SandboxedRustReaderWrapper(
            str(plugin_file), source_config, mode="cloud"
        )

        with pytest.raises(SandboxError, match="Extract failed"):
            list(wrapper.extract())

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_extract_handles_stateful_api_response(self, mock_docker, tmp_path):
        """Test that extract() properly handles stateful API response (create_reader + extract_batch loop).

        The extract method in the plugin runner internally:
        1. Creates a reader if not already created
        2. Loops calling extract_batch until done
        3. Returns all batches in a single response
        """
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        # Mock response showing extract internally handled stateful API
        mock_container = Mock()
        mock_container.start.return_value = None
        mock_container.exec_run.return_value = Mock(
            exit_code=0,
            output=b'{"status": "success", "message": "Initialized"}\n{"status": "success", "data": [[{"id": 1, "name": "batch1"}], [{"id": 2, "name": "batch2"}], [{"id": 3, "name": "batch3"}]]}',
        )
        mock_container.logs.return_value = b""
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        source_config = SourceConfig(type="test", connection={"host": "localhost"})
        wrapper = SandboxedRustReaderWrapper(
            str(plugin_file), source_config, mode="cloud"
        )

        batches = list(wrapper.extract())

        # Verify sandbox.execute was called with extract method
        assert mock_container.exec_run.called
        # Verify all batches were yielded
        assert len(batches) == 3
        assert batches[0] == [{"id": 1, "name": "batch1"}]
        assert batches[1] == [{"id": 2, "name": "batch2"}]
        assert batches[2] == [{"id": 3, "name": "batch3"}]

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_extract_with_state_manager(self, mock_docker, tmp_path):
        """Test that extract() properly serializes state_manager if provided."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        mock_container = Mock()
        mock_container.start.return_value = None
        mock_container.exec_run.return_value = Mock(
            exit_code=0,
            output=b'{"status": "success", "message": "Initialized"}\n{"status": "success", "data": [[{"id": 1}]]}',
        )
        mock_container.logs.return_value = b""
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        source_config = SourceConfig(type="test", connection={})
        wrapper = SandboxedRustReaderWrapper(
            str(plugin_file), source_config, mode="cloud"
        )

        # Create a mock state manager
        state_manager = Mock()
        state_manager.state = {"last_id": 100}

        batches = list(wrapper.extract(state_manager=state_manager))

        # Verify sandbox.execute was called
        assert mock_container.exec_run.called
        # Verify batches were yielded
        assert len(batches) == 1

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_check_connection_calls_sandbox(self, mock_docker, tmp_path):
        """Test that check_connection() calls sandbox.check_connection()."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        mock_container = Mock()
        mock_container.start.return_value = None
        mock_container.exec_run.return_value = Mock(
            exit_code=0,
            output=b'{"status": "success", "message": "Initialized"}\n{"status": "success", "success": true, "message": "Connection OK"}',
        )
        mock_container.logs.return_value = b""
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        source_config = SourceConfig(type="test", connection={})
        wrapper = SandboxedRustReaderWrapper(
            str(plugin_file), source_config, mode="cloud"
        )

        result = wrapper.check_connection()

        # Verify sandbox was called
        assert mock_container.exec_run.called
        # Verify result
        assert isinstance(result, ConnectionTestResult)
        assert result.success is True


class TestSandboxedRustWriterWrapper:
    """Test Rust sandboxed writer wrapper."""

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_write_batch_calls_sandbox_execute(self, mock_docker, tmp_path):
        """Test that write_batch() calls sandbox.execute() with correct parameters."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        # Mock response with file metadata in data field
        mock_container = Mock()
        mock_container.start.return_value = None
        mock_container.exec_run.return_value = Mock(
            exit_code=0,
            output=b'{"status": "success", "message": "Initialized"}\n{"status": "success", "data": [{"path": "s3://bucket/file.parquet", "size_bytes": 1024}]}',
        )
        mock_container.logs.return_value = b""
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        # Create a proper AssetDefinition with required fields
        from dativo_ingest.config import AssetDefinition, TeamModel

        asset_definition = AssetDefinition(
            name="test_asset",
            version="1.0.0",
            source_type="test",
            object="test_table",
            schema=[{"name": "id", "type": "integer"}],
            team=TeamModel(owner="test_owner"),
        )
        target_config = TargetConfig(type="s3", connection={})
        output_base = "s3://test-bucket"

        wrapper = SandboxedRustWriterWrapper(
            str(plugin_file), asset_definition, target_config, output_base, mode="cloud"
        )

        records = [{"id": 1, "name": "test"}]
        result = wrapper.write_batch(records, file_counter=1)

        # Verify sandbox.execute was called
        assert mock_container.exec_run.called
        # Verify result
        assert len(result) == 1
        assert result[0]["path"] == "s3://bucket/file.parquet"
        assert result[0]["size_bytes"] == 1024

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_write_batch_handles_error_response(self, mock_docker, tmp_path):
        """Test that write_batch() raises SandboxError when sandbox returns error."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        mock_container = Mock()
        mock_container.start.return_value = None
        mock_container.exec_run.return_value = Mock(
            exit_code=0,
            output=b'{"status": "success", "message": "Initialized"}\n{"error": "Write failed"}',
        )
        mock_container.logs.return_value = b""
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        from dativo_ingest.config import AssetDefinition, TeamModel

        asset_definition = AssetDefinition(
            name="test_asset",
            version="1.0.0",
            source_type="test",
            object="test_table",
            schema=[],
            team=TeamModel(owner="test_owner"),
        )
        target_config = TargetConfig(type="s3", connection={})
        wrapper = SandboxedRustWriterWrapper(
            str(plugin_file), asset_definition, target_config, "s3://test", mode="cloud"
        )

        with pytest.raises(SandboxError, match="Write batch failed"):
            wrapper.write_batch([{"id": 1}], file_counter=1)

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_commit_files_calls_sandbox_execute(self, mock_docker, tmp_path):
        """Test that commit_files() calls sandbox.execute() with correct parameters."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        mock_container = Mock()
        mock_container.start.return_value = None
        mock_container.exec_run.return_value = Mock(
            exit_code=0,
            output=b'{"status": "success", "message": "Initialized"}\n{"status": "success", "data": {"status": "success", "files_committed": 2}}',
        )
        mock_container.logs.return_value = b""
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        from dativo_ingest.config import AssetDefinition, TeamModel

        asset_definition = AssetDefinition(
            name="test_asset",
            version="1.0.0",
            source_type="test",
            object="test_table",
            schema=[],
            team=TeamModel(owner="test_owner"),
        )
        target_config = TargetConfig(type="s3", connection={})
        wrapper = SandboxedRustWriterWrapper(
            str(plugin_file), asset_definition, target_config, "s3://test", mode="cloud"
        )

        file_metadata = [
            {"path": "s3://bucket/file1.parquet"},
            {"path": "s3://bucket/file2.parquet"},
        ]
        result = wrapper.commit_files(file_metadata)

        # Verify sandbox.execute was called
        assert mock_container.exec_run.called
        # Verify result
        assert isinstance(result, dict)
        assert result["status"] == "success"
        assert result["files_committed"] == 2

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_commit_files_handles_error_response(self, mock_docker, tmp_path):
        """Test that commit_files() raises SandboxError when sandbox returns error."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        mock_container = Mock()
        mock_container.start.return_value = None
        mock_container.exec_run.return_value = Mock(
            exit_code=0,
            output=b'{"status": "success", "message": "Initialized"}\n{"error": "Commit failed"}',
        )
        mock_container.logs.return_value = b""
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        from dativo_ingest.config import AssetDefinition, TeamModel

        asset_definition = AssetDefinition(
            name="test_asset",
            version="1.0.0",
            source_type="test",
            object="test_table",
            schema=[],
            team=TeamModel(owner="test_owner"),
        )
        target_config = TargetConfig(type="s3", connection={})
        wrapper = SandboxedRustWriterWrapper(
            str(plugin_file), asset_definition, target_config, "s3://test", mode="cloud"
        )

        with pytest.raises(SandboxError, match="Commit files failed"):
            wrapper.commit_files([{"path": "s3://bucket/file.parquet"}])

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_check_connection_calls_sandbox(self, mock_docker, tmp_path):
        """Test that check_connection() calls sandbox.execute()."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        mock_container = Mock()
        mock_container.start.return_value = None
        mock_container.exec_run.return_value = Mock(
            exit_code=0,
            output=b'{"status": "success", "message": "Initialized"}\n{"status": "success", "success": true, "message": "Connection OK"}',
        )
        mock_container.logs.return_value = b""
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        from dativo_ingest.config import AssetDefinition, TeamModel

        asset_definition = AssetDefinition(
            name="test_asset",
            version="1.0.0",
            source_type="test",
            object="test_table",
            schema=[],
            team=TeamModel(owner="test_owner"),
        )
        target_config = TargetConfig(type="s3", connection={})
        wrapper = SandboxedRustWriterWrapper(
            str(plugin_file), asset_definition, target_config, "s3://test", mode="cloud"
        )

        result = wrapper.check_connection()

        # Verify sandbox was called
        assert mock_container.exec_run.called
        # Verify result
        assert isinstance(result, ConnectionTestResult)
        assert result.success is True

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_write_batch_creates_writer_if_needed(self, mock_docker, tmp_path):
        """Test that write_batch() passes config to allow writer creation."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        mock_container = Mock()
        mock_container.start.return_value = None
        # First call creates writer, second call writes batch
        mock_container.exec_run.return_value = Mock(
            exit_code=0,
            output=b'{"status": "success", "message": "Initialized"}\n{"status": "success", "data": [{"path": "file.parquet"}]}',
        )
        mock_container.logs.return_value = b""
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        from dativo_ingest.config import AssetDefinition, TeamModel

        asset_definition = AssetDefinition(
            name="test_asset",
            version="1.0.0",
            source_type="test",
            object="test_table",
            schema=[],
            team=TeamModel(owner="test_owner"),
        )
        target_config = TargetConfig(type="s3", connection={})
        wrapper = SandboxedRustWriterWrapper(
            str(plugin_file), asset_definition, target_config, "s3://test", mode="cloud"
        )

        # Verify that exec_run was called with config parameter
        # The exec_run call should include the config in the request
        wrapper.write_batch([{"id": 1}], file_counter=1)

        # Verify exec_run was called
        assert mock_container.exec_run.called
        # Get the command that was passed to exec_run
        call_args = mock_container.exec_run.call_args
        # The command should include base64 encoded JSON that contains config
        assert call_args is not None
