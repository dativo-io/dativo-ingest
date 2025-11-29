"""Integration tests for sandboxed plugins.

These tests require Docker to be running and will execute plugins in actual containers.
"""

# Check if Docker is available - use real Docker for integration tests
# Import docker properly (avoid local directory shadowing)
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

original_path = sys.path[:]
if "." in sys.path:
    sys.path.remove(".")
if "" in sys.path:
    sys.path.remove("")

try:
    import os

    import docker

    # Try to connect to Docker
    # First, check if DOCKER_HOST is set
    docker_host = os.environ.get("DOCKER_HOST")

    # If not set and standard socket doesn't exist, try Colima socket
    if not docker_host:
        colima_socket = Path.home() / ".colima" / "default" / "docker.sock"
        if colima_socket.exists():
            os.environ["DOCKER_HOST"] = f"unix://{colima_socket}"

    docker_client = docker.from_env()
    docker_client.ping()
    DOCKER_AVAILABLE = True
except Exception as e:
    # Docker not available - skip integration tests
    DOCKER_AVAILABLE = False
    # Print to stderr so it's visible even if stdout is captured
    import sys as sys_module

    print(
        f"Docker check failed: {type(e).__name__}: {e}",
        file=sys_module.stderr,
    )
    # Also try to provide helpful message about Colima
    colima_socket = Path.home() / ".colima" / "default" / "docker.sock"
    if colima_socket.exists() and "DOCKER_HOST" not in os.environ:
        print(
            f"Note: Colima socket found at {colima_socket}, but connection still failed.",
            file=sys_module.stderr,
        )
finally:
    # Restore path
    sys.path = original_path

from dativo_ingest.config import SourceConfig, TargetConfig
from dativo_ingest.plugins import ConnectionTestResult, DiscoveryResult, PluginLoader
from dativo_ingest.sandboxed_plugin_wrapper import (
    SandboxedReaderWrapper,
    SandboxedWriterWrapper,
)


@pytest.mark.integration
@pytest.mark.requires_docker
@pytest.mark.skipif(not DOCKER_AVAILABLE, reason="Docker not available")
class TestSandboxIntegration:
    """Integration tests requiring Docker."""

    def test_python_plugin_sandboxed_execution(self, tmp_path):
        """Test that Python plugin executes in Docker container."""
        # Create plugin
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseReader, ConnectionTestResult

class TestReader(BaseReader):
    def check_connection(self):
        return ConnectionTestResult(
            success=True,
            message="Sandboxed execution successful",
            details={"sandboxed": True}
        )
    
    def discover(self):
        from dativo_ingest.plugins import DiscoveryResult
        return DiscoveryResult(
            objects=[{"name": "test_table", "type": "table"}],
            metadata={"sandboxed": True}
        )
    
    def extract(self, state_manager=None):
        yield [{"id": 1, "data": "test"}]
"""
        )

        # Load with sandboxing
        reader_class = PluginLoader.load_reader(
            f"{plugin_file}:TestReader", mode="cloud"
        )

        source_config = SourceConfig(type="test", connection={})
        reader = reader_class(source_config)

        # Verify it's sandboxed
        assert isinstance(reader, SandboxedReaderWrapper)

        # Execute check_connection
        result = reader.check_connection()

        # Verify result
        assert result.success is True
        assert (
            "sandbox" in result.message.lower()
            or "sandboxed" in str(result.details).lower()
        )

    def test_python_plugin_extract_in_sandbox(self, tmp_path):
        """Test that extract() method works in sandbox."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseReader

class TestReader(BaseReader):
    def extract(self, state_manager=None):
        yield [{"id": 1, "name": "test1"}]
        yield [{"id": 2, "name": "test2"}]
"""
        )

        reader_class = PluginLoader.load_reader(
            f"{plugin_file}:TestReader", mode="cloud"
        )

        source_config = SourceConfig(type="test", connection={})
        reader = reader_class(source_config)

        # Extract should return batches
        batches = list(reader.extract())

        assert len(batches) == 2
        assert batches[0] == [{"id": 1, "name": "test1"}]
        assert batches[1] == [{"id": 2, "name": "test2"}]

    def test_python_writer_sandboxed_execution(self, tmp_path):
        """Test that Python writer executes in Docker container."""
        plugin_file = tmp_path / "test_writer.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseWriter, ConnectionTestResult

class TestWriter(BaseWriter):
    def check_connection(self):
        return ConnectionTestResult(
            success=True,
            message="Writer sandboxed execution successful"
        )
    
    def write_batch(self, records, file_counter):
        return [{"path": f"test_{file_counter}.parquet", "size_bytes": 1024}]
"""
        )

        writer_class = PluginLoader.load_writer(
            f"{plugin_file}:TestWriter", mode="cloud"
        )

        asset_definition = Mock()
        asset_definition.name = "test_asset"
        target_config = TargetConfig(type="s3", connection={})
        writer = writer_class(asset_definition, target_config, "s3://test")

        # Verify it's sandboxed
        assert isinstance(writer, SandboxedWriterWrapper)

        # Execute check_connection
        result = writer.check_connection()

        assert result.success is True

        # Execute write_batch
        file_metadata = writer.write_batch([{"id": 1}], file_counter=1)
        assert len(file_metadata) == 1
        assert "test_1.parquet" in file_metadata[0]["path"]

    def test_sandbox_resource_limits(self, tmp_path):
        """Test that sandbox respects resource limits."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseReader, ConnectionTestResult

class TestReader(BaseReader):
    def check_connection(self):
        return ConnectionTestResult(success=True, message="OK")
"""
        )

        sandbox_config = {"cpu_limit": 0.5, "memory_limit": "256m"}

        reader_class = PluginLoader.load_reader(
            f"{plugin_file}:TestReader",
            mode="cloud",
            sandbox_config=sandbox_config,
        )

        source_config = SourceConfig(type="test", connection={})
        reader = reader_class(source_config)

        # Verify sandbox was created with correct config
        assert reader.sandbox.cpu_limit == 0.5
        assert reader.sandbox.memory_limit == "256m"

    def test_sandbox_network_isolation(self, tmp_path):
        """Test that sandbox has network disabled by default."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseReader, ConnectionTestResult

class TestReader(BaseReader):
    def check_connection(self):
        return ConnectionTestResult(success=True, message="OK")
"""
        )

        reader_class = PluginLoader.load_reader(
            f"{plugin_file}:TestReader", mode="cloud"
        )

        source_config = SourceConfig(type="test", connection={})
        reader = reader_class(source_config)

        # Network should be disabled by default
        assert reader.sandbox.network_disabled is True

    def test_sandbox_timeout(self, tmp_path):
        """Test that sandbox respects timeout."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseReader, ConnectionTestResult

class TestReader(BaseReader):
    def check_connection(self):
        return ConnectionTestResult(success=True, message="OK")
"""
        )

        sandbox_config = {"timeout": 60}

        reader_class = PluginLoader.load_reader(
            f"{plugin_file}:TestReader",
            mode="cloud",
            sandbox_config=sandbox_config,
        )

        source_config = SourceConfig(type="test", connection={})
        reader = reader_class(source_config)

        # Verify timeout was set
        assert reader.sandbox.timeout == 60

    def test_sandbox_config_from_job_config(self, tmp_path):
        """Test that sandbox config is extracted from job config."""
        from dativo_ingest.config import JobConfig, PluginConfig, PluginSandboxConfig

        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseReader

class TestReader(BaseReader):
    def extract(self, state_manager=None):
        yield [{"id": 1}]
"""
        )

        # Create job config with plugin config
        plugin_config = PluginConfig(
            sandbox=PluginSandboxConfig(
                enabled=True, cpu_limit=0.75, memory_limit="512m", timeout=120
            )
        )

        # Test that config is respected
        reader_class = PluginLoader.load_reader(
            f"{plugin_file}:TestReader",
            mode="self_hosted",  # Would normally not sandbox
            plugin_config=plugin_config.model_dump(),
        )

        source_config = SourceConfig(type="test", connection={})
        reader = reader_class(source_config)

        # Should be sandboxed because config says enabled=True
        assert isinstance(reader, SandboxedReaderWrapper)
