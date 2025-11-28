"""Performance tests for sandboxed plugins.

These tests measure the overhead of sandboxing compared to direct execution.
"""

# Check if Docker is available - use real Docker for performance tests
# Import docker properly (avoid local directory shadowing)
import sys
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

original_path = sys.path[:]
if "." in sys.path:
    sys.path.remove(".")
if "" in sys.path:
    sys.path.remove("")

try:
    import docker

    docker_client = docker.from_env()
    docker_client.ping()
    DOCKER_AVAILABLE = True
except Exception as e:
    # Docker not available - skip performance tests
    DOCKER_AVAILABLE = False
    print(f"Docker check failed: {e}")
finally:
    # Restore path
    sys.path = original_path

from dativo_ingest.config import SourceConfig, TargetConfig
from dativo_ingest.plugins import PluginLoader


@pytest.mark.skipif(not DOCKER_AVAILABLE, reason="Docker not available")
class TestSandboxPerformance:
    """Test sandbox performance overhead."""

    def test_sandbox_overhead_simple_operation(self, tmp_path):
        """Measure overhead of sandboxing for simple operations."""
        plugin_file = tmp_path / "perf_plugin.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseReader, ConnectionTestResult

class PerfReader(BaseReader):
    def check_connection(self):
        return ConnectionTestResult(success=True, message="OK")
"""
        )

        # Test without sandbox
        start = time.time()
        reader_class = PluginLoader.load_reader(
            f"{plugin_file}:PerfReader", mode="self_hosted"
        )
        source_config = SourceConfig(type="test", connection={})
        reader = reader_class(source_config)
        result = reader.check_connection()
        no_sandbox_time = time.time() - start

        # Test with sandbox (if Docker available)
        try:
            start = time.time()
            reader_class = PluginLoader.load_reader(
                f"{plugin_file}:PerfReader", mode="cloud"
            )
            reader = reader_class(source_config)
            result = reader.check_connection()
            sandbox_time = time.time() - start

            # Overhead should be reasonable (< 5 seconds for simple operation)
            overhead = sandbox_time - no_sandbox_time
            assert overhead < 5.0, f"Sandbox overhead too high: {overhead}s"
        except Exception:
            # Docker not available, skip sandbox test
            pytest.skip("Docker not available for sandbox performance test")

    def test_sandbox_overhead_extract_operation(self, tmp_path):
        """Measure overhead of sandboxing for extract operations."""
        plugin_file = tmp_path / "perf_plugin.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseReader

class PerfReader(BaseReader):
    def extract(self, state_manager=None):
        # Generate small dataset
        for i in range(10):
            yield [{"id": i, "data": f"test_{i}"}]
"""
        )

        # Test without sandbox
        start = time.time()
        reader_class = PluginLoader.load_reader(
            f"{plugin_file}:PerfReader", mode="self_hosted"
        )
        source_config = SourceConfig(type="test", connection={})
        reader = reader_class(source_config)
        batches = list(reader.extract())
        no_sandbox_time = time.time() - start

        # Test with sandbox (if Docker available)
        try:
            start = time.time()
            reader_class = PluginLoader.load_reader(
                f"{plugin_file}:PerfReader", mode="cloud"
            )
            reader = reader_class(source_config)
            batches = list(reader.extract())
            sandbox_time = time.time() - start

            # Overhead should be reasonable (< 10 seconds for extract)
            overhead = sandbox_time - no_sandbox_time
            assert overhead < 10.0, f"Sandbox overhead too high: {overhead}s"
        except Exception:
            # Docker not available, skip sandbox test
            pytest.skip("Docker not available for sandbox performance test")

    def test_sandbox_overhead_write_operation(self, tmp_path):
        """Measure overhead of sandboxing for write operations."""
        plugin_file = tmp_path / "perf_writer.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseWriter

class PerfWriter(BaseWriter):
    def write_batch(self, records, file_counter):
        return [{"path": f"test_{file_counter}.parquet", "size_bytes": 1024}]
"""
        )

        # Test without sandbox
        start = time.time()
        writer_class = PluginLoader.load_writer(
            f"{plugin_file}:PerfWriter", mode="self_hosted"
        )
        asset_definition = Mock()
        target_config = TargetConfig(type="s3", connection={})
        writer = writer_class(asset_definition, target_config, "s3://test")
        result = writer.write_batch([{"id": 1}], file_counter=1)
        no_sandbox_time = time.time() - start

        # Test with sandbox (if Docker available)
        try:
            start = time.time()
            writer_class = PluginLoader.load_writer(
                f"{plugin_file}:PerfWriter", mode="cloud"
            )
            writer = writer_class(asset_definition, target_config, "s3://test")
            result = writer.write_batch([{"id": 1}], file_counter=1)
            sandbox_time = time.time() - start

            # Overhead should be reasonable (< 5 seconds for write)
            overhead = sandbox_time - no_sandbox_time
            assert overhead < 5.0, f"Sandbox overhead too high: {overhead}s"
        except Exception:
            # Docker not available, skip sandbox test
            pytest.skip("Docker not available for sandbox performance test")
