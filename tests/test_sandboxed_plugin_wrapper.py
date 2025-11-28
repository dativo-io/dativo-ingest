"""Tests for sandboxed plugin wrappers."""

from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from dativo_ingest.config import SourceConfig, TargetConfig
from dativo_ingest.plugins import ConnectionTestResult, DiscoveryResult, PluginLoader
from dativo_ingest.sandboxed_plugin_wrapper import (
    SandboxedReaderWrapper,
    SandboxedWriterWrapper,
)


class TestSandboxedReaderWrapper:
    """Test sandboxed reader wrapper."""

    @patch("dativo_ingest.sandbox.docker")
    def test_check_connection_via_sandbox(self, mock_docker, tmp_path):
        """Test that check_connection routes through sandbox."""
        # Create test plugin
        plugin_file = tmp_path / "test_reader.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseReader, ConnectionTestResult

class TestReader(BaseReader):
    def check_connection(self):
        return ConnectionTestResult(True, "OK")
"""
        )

        # Mock docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        # Mock container
        mock_container = Mock()
        mock_container.wait.return_value = {"StatusCode": 0}
        # The logs should return bytes with JSON result
        # The execute method looks for the last line that's valid JSON
        mock_container.logs.return_value = b'Some log output\n{"status": "success", "result": {"success": true, "message": "OK"}}'
        mock_container.start.return_value = None  # start() returns None
        mock_client.containers.create.return_value = mock_container

        # Create wrapper
        source_config = SourceConfig(type="test", connection={})
        wrapper = SandboxedReaderWrapper(str(plugin_file), source_config, mode="cloud")

        # Call check_connection
        result = wrapper.check_connection()

        # Verify sandbox was called (diagnostic container + actual container)
        assert mock_client.containers.create.call_count == 2
        assert result.success is True
        assert result.message == "OK"

    @patch("dativo_ingest.sandbox.docker")
    def test_discover_via_sandbox(self, mock_docker, tmp_path):
        """Test that discover routes through sandbox."""
        plugin_file = tmp_path / "test_reader.py"
        plugin_file.write_text("")

        # Mock docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        # Mock container
        mock_container = Mock()
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.return_value = b'{"status": "success", "result": {"objects": [{"name": "table1", "type": "table"}], "metadata": {}}}'
        mock_client.containers.create.return_value = mock_container

        source_config = SourceConfig(type="test", connection={})
        wrapper = SandboxedReaderWrapper(str(plugin_file), source_config, mode="cloud")

        result = wrapper.discover()

        # Verify sandbox was called (diagnostic container + actual container)
        assert mock_client.containers.create.call_count == 2
        assert isinstance(result, DiscoveryResult)
        assert len(result.objects) == 1
        assert result.objects[0]["name"] == "table1"

    @patch("dativo_ingest.sandbox.docker")
    def test_extract_via_sandbox(self, mock_docker, tmp_path):
        """Test that extract routes through sandbox and returns batches."""
        plugin_file = tmp_path / "test_reader.py"
        plugin_file.write_text("")

        # Mock docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        # Mock container
        mock_container = Mock()
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.return_value = b'{"status": "success", "result": [[{"id": 1, "name": "test1"}], [{"id": 2, "name": "test2"}]]}'
        mock_client.containers.create.return_value = mock_container

        source_config = SourceConfig(type="test", connection={})
        wrapper = SandboxedReaderWrapper(str(plugin_file), source_config, mode="cloud")

        # Extract should yield batches
        batches = list(wrapper.extract())

        # Verify sandbox was called (diagnostic container + actual container)
        assert mock_client.containers.create.call_count == 2
        assert len(batches) == 2
        assert batches[0] == [{"id": 1, "name": "test1"}]
        assert batches[1] == [{"id": 2, "name": "test2"}]

    def test_no_sandboxing_in_self_hosted_mode(self, tmp_path):
        """Test that sandboxing is disabled in self_hosted mode."""
        plugin_file = tmp_path / "test_reader.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseReader

class TestReader(BaseReader):
    def extract(self, state_manager=None):
        yield [{"id": 1}]
"""
        )

        reader_class = PluginLoader.load_reader(
            f"{plugin_file}:TestReader", mode="self_hosted"
        )

        # Should be direct class, not wrapper
        assert reader_class.__name__ == "TestReader"
        # Verify it's not a wrapper by checking it doesn't have sandbox attribute
        source_config = SourceConfig(type="test", connection={})
        reader = reader_class(source_config)
        assert not hasattr(reader, "sandbox")

    @patch("dativo_ingest.sandbox.docker")
    def test_sandboxing_in_cloud_mode(self, mock_docker, tmp_path):
        """Test that sandboxing is enabled in cloud mode."""
        plugin_file = tmp_path / "test_reader.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseReader

class TestReader(BaseReader):
    def extract(self, state_manager=None):
        yield [{"id": 1}]
"""
        )

        # Mock docker client to avoid actual Docker calls in unit test
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        # Load reader - in cloud mode, should return factory that creates sandboxed wrapper
        reader_class = PluginLoader.load_reader(
            f"{plugin_file}:TestReader", mode="cloud"
        )

        # Should be a factory function (not the actual class)
        # The factory function name should match the plugin class name
        assert callable(reader_class)

        # Should be a factory function that creates wrapper
        source_config = SourceConfig(type="test", connection={})
        # This will try to create PluginSandbox which will use the mocked docker
        reader = reader_class(source_config)

        # Should be a SandboxedReaderWrapper
        assert isinstance(reader, SandboxedReaderWrapper)
        assert hasattr(reader, "sandbox")

    @patch("dativo_ingest.sandbox.docker")
    def test_sandbox_config_respected(self, mock_docker, tmp_path):
        """Test that sandbox config is respected."""
        plugin_file = tmp_path / "test_reader.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseReader

class TestReader(BaseReader):
    def extract(self, state_manager=None):
        yield [{"id": 1}]
"""
        )

        # Mock docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        sandbox_config = {"cpu_limit": 0.5, "memory_limit": "256m"}
        plugin_config = {"sandbox": {"enabled": True}}

        reader_class = PluginLoader.load_reader(
            f"{plugin_file}:TestReader",
            mode="self_hosted",
            sandbox_config=sandbox_config,
            plugin_config=plugin_config,
        )

        source_config = SourceConfig(type="test", connection={})
        reader = reader_class(source_config)

        # Should be sandboxed because config says enabled=True
        assert isinstance(reader, SandboxedReaderWrapper)
        assert reader.sandbox_config == sandbox_config


class TestSandboxedWriterWrapper:
    """Test sandboxed writer wrapper."""

    @patch("dativo_ingest.sandbox.docker")
    def test_check_connection_via_sandbox(self, mock_docker, tmp_path):
        """Test that check_connection routes through sandbox."""
        plugin_file = tmp_path / "test_writer.py"
        plugin_file.write_text("")

        # Mock docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        # Mock container
        mock_container = Mock()
        mock_container.wait.return_value = {"StatusCode": 0}
        # The logs should return bytes with JSON result
        # The execute method looks for the last line that's valid JSON
        mock_container.logs.return_value = b'Some log output\n{"status": "success", "result": {"success": true, "message": "OK"}}'
        mock_container.start.return_value = None  # start() returns None
        mock_client.containers.create.return_value = mock_container

        # Create minimal asset and target config
        asset_definition = Mock()
        asset_definition.name = "test_asset"
        target_config = TargetConfig(type="s3", connection={})
        output_base = "s3://test-bucket"

        wrapper = SandboxedWriterWrapper(
            str(plugin_file),
            asset_definition,
            target_config,
            output_base,
            mode="cloud",
        )

        result = wrapper.check_connection()

        # Verify sandbox was called (diagnostic container + actual container)
        assert mock_client.containers.create.call_count == 2
        # start() and wait() are called for both diagnostic and actual containers
        assert mock_container.start.call_count == 2
        assert mock_container.wait.call_count == 2
        # The result should be parsed from the JSON logs
        assert result.success is True
        assert result.message == "OK"

    @patch("dativo_ingest.sandbox.docker")
    def test_write_batch_via_sandbox(self, mock_docker, tmp_path):
        """Test that write_batch routes through sandbox."""
        plugin_file = tmp_path / "test_writer.py"
        plugin_file.write_text("")

        # Mock docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        # Mock container
        mock_container = Mock()
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.return_value = b'{"status": "success", "result": [{"path": "s3://bucket/file1.parquet", "size_bytes": 1024}]}'
        mock_client.containers.create.return_value = mock_container

        asset_definition = Mock()
        target_config = TargetConfig(type="s3", connection={})
        output_base = "s3://test-bucket"

        wrapper = SandboxedWriterWrapper(
            str(plugin_file),
            asset_definition,
            target_config,
            output_base,
            mode="cloud",
        )

        records = [{"id": 1, "name": "test"}]
        result = wrapper.write_batch(records, file_counter=1)

        # Verify sandbox was called (diagnostic container + actual container)
        assert mock_client.containers.create.call_count == 2
        assert len(result) == 1
        assert result[0]["path"] == "s3://bucket/file1.parquet"

    @patch("dativo_ingest.sandbox.docker")
    def test_commit_files_via_sandbox(self, mock_docker, tmp_path):
        """Test that commit_files routes through sandbox."""
        plugin_file = tmp_path / "test_writer.py"
        plugin_file.write_text("")

        # Mock docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        # Mock container
        mock_container = Mock()
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.return_value = b'{"status": "success", "result": null}'
        mock_client.containers.create.return_value = mock_container

        asset_definition = Mock()
        target_config = TargetConfig(type="s3", connection={})
        output_base = "s3://test-bucket"

        wrapper = SandboxedWriterWrapper(
            str(plugin_file),
            asset_definition,
            target_config,
            output_base,
            mode="cloud",
        )

        file_metadata = [
            {"path": "s3://bucket/file1.parquet"},
            {"path": "s3://bucket/file2.parquet"},
        ]
        # commit_files returns None, so we just verify it was called
        wrapper.commit_files(file_metadata)

        # Verify sandbox was called (diagnostic container + actual container)
        assert mock_client.containers.create.call_count == 2

    def test_no_sandboxing_in_self_hosted_mode(self, tmp_path):
        """Test that sandboxing is disabled in self_hosted mode for writers."""
        plugin_file = tmp_path / "test_writer.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseWriter

class TestWriter(BaseWriter):
    def write_batch(self, records, file_counter):
        return [{"path": "test.parquet"}]
"""
        )

        writer_class = PluginLoader.load_writer(
            f"{plugin_file}:TestWriter", mode="self_hosted"
        )

        # Should be direct class, not wrapper
        assert writer_class.__name__ == "TestWriter"

        # Verify it's not a wrapper
        asset_definition = Mock()
        target_config = TargetConfig(type="s3", connection={})
        writer = writer_class(asset_definition, target_config, "s3://test")
        assert not hasattr(writer, "sandbox")

    @patch("dativo_ingest.sandbox.docker")
    def test_sandboxing_in_cloud_mode(self, mock_docker, tmp_path):
        """Test that sandboxing is enabled in cloud mode for writers."""
        plugin_file = tmp_path / "test_writer.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseWriter

class TestWriter(BaseWriter):
    def write_batch(self, records, file_counter):
        return [{"path": "test.parquet"}]
"""
        )

        # Mock docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.from_env.return_value = mock_client

        writer_class = PluginLoader.load_writer(
            f"{plugin_file}:TestWriter", mode="cloud"
        )

        # Should be a factory function that creates wrapper
        asset_definition = Mock()
        target_config = TargetConfig(type="s3", connection={})
        writer = writer_class(asset_definition, target_config, "s3://test")

        # Should be a SandboxedWriterWrapper
        assert isinstance(writer, SandboxedWriterWrapper)
        assert hasattr(writer, "sandbox")
