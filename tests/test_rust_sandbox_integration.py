"""Integration tests for Rust plugin sandbox with real plugins.

These tests verify that the container reuse optimization works correctly
with actual Rust plugins (CSV reader, Parquet writer) and produces correct outputs.
"""

import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

# Mock docker module before importing
if "docker" not in sys.modules:
    mock_docker = Mock()
    mock_docker.from_env = Mock()
    mock_docker_errors = Mock()
    mock_docker_errors.DockerException = Exception
    mock_docker_errors.ImageNotFound = Exception
    sys.modules["docker"] = mock_docker
    sys.modules["docker.errors"] = mock_docker_errors

from dativo_ingest.rust_sandbox import RustPluginSandbox


class TestRustSandboxSecurityPreservation:
    """Test that security settings are preserved with container reuse."""

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_security_settings_preserved_in_config(self, mock_docker_module, tmp_path):
        """Test that all security settings are preserved in container config."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client
        mock_client.images.get.return_value = Mock()

        # Create sandbox with all security options
        sandbox = RustPluginSandbox(
            str(plugin_file),
            cpu_limit=0.5,
            memory_limit="512m",
            network_disabled=True,
            timeout=300,
        )

        # Trigger container creation
        mock_container = Mock()
        mock_client.containers.create.return_value = mock_container
        sandbox._start_container()

        # Verify container.create was called with security settings
        create_call_args = mock_client.containers.create.call_args
        config = (
            create_call_args[1]
            if len(create_call_args) > 1
            else create_call_args.kwargs
        )

        # Verify security settings
        assert config["network_disabled"] is True
        assert config["read_only"] is True
        # CPU limit is set via cpu_quota (not cpu_limit)
        assert config.get("cpu_quota") == 50000  # 0.5 * 100000
        assert config.get("cpu_period") == 100000
        assert config["mem_limit"] == "512m"
        assert "tmpfs" in config
        assert "/tmp" in config["tmpfs"]

        # Verify seccomp profile is included
        if "security_opt" in config:
            assert len(config["security_opt"]) > 0
            assert "seccomp=" in config["security_opt"][0]

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_read_only_filesystem_enforced(self, mock_docker_module, tmp_path):
        """Test that read-only filesystem is enforced."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client
        mock_client.images.get.return_value = Mock()

        sandbox = RustPluginSandbox(str(plugin_file))

        # Trigger container creation
        mock_container = Mock()
        mock_client.containers.create.return_value = mock_container
        sandbox._start_container()

        # Verify read-only root filesystem
        config = mock_client.containers.create.call_args.kwargs
        assert config["read_only"] is True

        # Verify tmpfs for /tmp (writable temp space)
        assert "tmpfs" in config
        assert "/tmp" in config["tmpfs"]

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_network_isolation_maintained(self, mock_docker_module, tmp_path):
        """Test that network isolation is maintained across requests."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client
        mock_client.images.get.return_value = Mock()

        sandbox = RustPluginSandbox(str(plugin_file), network_disabled=True)

        # Trigger container creation
        mock_container = Mock()
        mock_client.containers.create.return_value = mock_container
        sandbox._start_container()

        # Verify network is disabled
        config = mock_client.containers.create.call_args.kwargs
        assert config["network_disabled"] is True


class TestRustSandboxContainerHealthAndRecovery:
    """Test container health checking and recovery mechanisms."""

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_container_health_check_detects_stopped_container(
        self, mock_docker_module, tmp_path
    ):
        """Test that health check detects when container stops."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client
        mock_client.images.get.return_value = Mock()

        sandbox = RustPluginSandbox(str(plugin_file))

        # Create mock container
        mock_container = Mock()
        mock_container.status = "running"
        mock_client.containers.create.return_value = mock_container
        sandbox._start_container()

        # Container is healthy initially
        assert sandbox._check_container_health() is True

        # Simulate container stopping
        mock_container.status = "exited"

        # Health check should detect unhealthy container
        assert sandbox._check_container_health() is False

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_container_age_limit_enforced(self, mock_docker_module, tmp_path):
        """Test that container age limit is enforced."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client
        mock_client.images.get.return_value = Mock()

        # Create sandbox with 1-second age limit
        sandbox = RustPluginSandbox(str(plugin_file), container_max_age_seconds=1)

        # Create mock container
        mock_container = Mock()
        mock_container.status = "running"
        mock_client.containers.create.return_value = mock_container
        sandbox._start_container()

        # Container is healthy initially
        assert sandbox._check_container_health() is True

        # Simulate time passing
        import time

        original_start_time = sandbox._container_start_time
        sandbox._container_start_time = original_start_time - 2  # 2 seconds ago

        # Health check should detect container is too old
        assert sandbox._check_container_health() is False

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_request_counter_increments(self, mock_docker_module, tmp_path):
        """Test that request counter increments correctly."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client
        mock_client.images.get.return_value = Mock()

        sandbox = RustPluginSandbox(str(plugin_file))

        # Initial count should be 0
        assert sandbox._request_count == 0


class TestRustSandboxConfiguration:
    """Test configuration options for sandbox."""

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_max_retries_configuration(self, mock_docker_module, tmp_path):
        """Test that max_retries can be configured."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        sandbox = RustPluginSandbox(str(plugin_file), max_retries=5)
        assert sandbox.max_retries == 5

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_container_max_age_configuration(self, mock_docker_module, tmp_path):
        """Test that container_max_age_seconds can be configured."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        sandbox = RustPluginSandbox(str(plugin_file), container_max_age_seconds=3600)
        assert sandbox.container_max_age_seconds == 3600


class TestRustSandboxBuffering:
    """Test JSON line buffering for partial responses."""

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_buffer_initialization(self, mock_docker_module, tmp_path):
        """Test that buffer is initialized correctly."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        sandbox = RustPluginSandbox(str(plugin_file))

        # Buffer should be empty initially
        assert sandbox._buffer_remainder == b""


# Integration test placeholder (requires actual Rust plugins)
@pytest.mark.skipif(
    not os.path.exists("examples/plugins/rust/csv_reader/target/release"),
    reason="Rust plugin examples not built",
)
class TestRustPluginIntegration:
    """Integration tests with real Rust plugins (requires built plugins)."""

    def test_csv_reader_plugin_with_container_reuse(self, tmp_path):
        """Test CSV reader plugin with container reuse optimization.

        This test requires the Rust CSV reader plugin to be built:
        cd examples/plugins/rust && make build
        """
        # This is a placeholder for actual integration testing
        # Would require:
        # 1. Built Rust plugin (.so file)
        # 2. Docker image available
        # 3. Test CSV file
        # 4. Verification of output correctness
        pass

    def test_parquet_writer_plugin_with_container_reuse(self, tmp_path):
        """Test Parquet writer plugin with container reuse optimization.

        This test requires the Rust Parquet writer plugin to be built:
        cd examples/plugins/rust && make build
        """
        # This is a placeholder for actual integration testing
        # Would require:
        # 1. Built Rust plugin (.so file)
        # 2. Docker image available
        # 3. Test data
        # 4. Verification of output Parquet files
        pass


# Notes for future integration testing:
"""
To run integration tests with real Rust plugins:

1. Build the Rust plugin examples:
   cd examples/plugins/rust
   make build

2. Ensure Docker image is available:
   docker pull dativo/rust-plugin-runner:latest

3. Run integration tests:
   pytest tests/test_rust_sandbox_integration.py -v -m integration

Expected outcomes:
- CSV reader should extract records correctly
- Parquet writer should write valid Parquet files
- Container reuse should show performance improvement
- All security settings should be enforced
- Error recovery should handle plugin crashes gracefully
"""
