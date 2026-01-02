"""Performance tests for Rust plugin sandbox container reuse.

This test demonstrates the performance improvement from reusing containers
across multiple method calls instead of creating/destroying containers per request.
"""

import sys
from unittest.mock import Mock, patch

import pytest

# Mock docker module before importing rust_sandbox
if "docker" not in sys.modules:
    mock_docker = Mock()
    mock_docker.from_env = Mock()
    mock_docker_errors = Mock()
    mock_docker_errors.DockerException = Exception
    mock_docker_errors.ImageNotFound = Exception
    sys.modules["docker"] = mock_docker
    sys.modules["docker.errors"] = mock_docker_errors

from dativo_ingest.rust_sandbox import RustPluginSandbox


class TestRustSandboxContainerReuse:
    """Test container reuse optimization for Rust sandbox."""

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_reuse_container_enabled_by_default(self, mock_docker_module, tmp_path):
        """Test that container reuse is enabled by default."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        sandbox = RustPluginSandbox(str(plugin_file))
        assert sandbox.reuse_container is True

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_reuse_container_can_be_disabled(self, mock_docker_module, tmp_path):
        """Test that container reuse can be disabled for compatibility."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        sandbox = RustPluginSandbox(str(plugin_file), reuse_container=False)
        assert sandbox.reuse_container is False

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_container_not_reused_legacy_mode(self, mock_docker_module, tmp_path):
        """Test that legacy mode (reuse_container=False) creates/destroys per request."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        # Mock container
        mock_container = Mock()
        mock_exec_result = Mock()
        mock_exec_result.exit_code = 0
        mock_exec_result.output = b'{"status": "success"}\n{"status": "success", "data": {"result": "ok"}}'
        mock_container.exec_run.return_value = mock_exec_result
        mock_container.logs.return_value = b""
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        sandbox = RustPluginSandbox(str(plugin_file), reuse_container=False)

        # Execute multiple requests
        sandbox.execute("method1", param="value1")
        sandbox.execute("method2", param="value2")
        sandbox.execute("method3", param="value3")

        # In legacy mode, container is created/destroyed per request
        # So we should have 3 creates and 3 removes
        assert mock_client.containers.create.call_count == 3
        assert mock_container.remove.call_count == 3

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_cleanup_removes_container(self, mock_docker_module, tmp_path):
        """Test that cleanup() properly removes the container."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        mock_container = Mock()
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        sandbox = RustPluginSandbox(str(plugin_file))
        
        # Trigger container creation
        sandbox._start_container()
        
        # Cleanup should remove container
        sandbox.cleanup()
        
        assert mock_container.remove.called

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_cleanup_ignores_errors(self, mock_docker_module, tmp_path):
        """Test that cleanup() ignores errors during container removal."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        mock_container = Mock()
        mock_container.remove.side_effect = Exception("Removal error")
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        sandbox = RustPluginSandbox(str(plugin_file))
        sandbox._start_container()
        
        # Should not raise error
        sandbox.cleanup()

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_del_calls_cleanup(self, mock_docker_module, tmp_path):
        """Test that __del__ calls cleanup()."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        mock_container = Mock()
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        sandbox = RustPluginSandbox(str(plugin_file))
        sandbox._start_container()
        
        # Delete sandbox
        del sandbox
        
        # Container should be removed
        assert mock_container.remove.called


class TestRustSandboxPerformanceComparison:
    """Performance comparison tests (conceptual - actual timings would need real containers)."""

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_legacy_mode_overhead_documentation(self, mock_docker_module, tmp_path):
        """Document the overhead difference between legacy and reuse modes.
        
        This test documents the conceptual performance difference:
        
        Legacy Mode (reuse_container=False):
        - 100 batches = 100 container creates + 100 container destroys
        - Overhead: ~100-500ms per container create/destroy
        - Total overhead: 10-50 seconds for 100 batches
        
        Reuse Mode (reuse_container=True):
        - 100 batches = 1 container create + 1 container destroy
        - Overhead: ~100-500ms for initial setup, minimal per-batch overhead
        - Total overhead: <1 second for 100 batches
        
        Expected improvement: 10-50x faster for batch operations
        """
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        # This test is for documentation purposes
        # Actual performance measurements would require real Docker containers
        
        # Legacy mode: Multiple container creates/destroys
        sandbox_legacy = RustPluginSandbox(str(plugin_file), reuse_container=False)
        assert sandbox_legacy.reuse_container is False
        
        # Reuse mode: Single container for multiple operations
        sandbox_reuse = RustPluginSandbox(str(plugin_file), reuse_container=True)
        assert sandbox_reuse.reuse_container is True
        
        # The performance difference is significant:
        # - Legacy: O(n) container operations for n batches
        # - Reuse: O(1) container operations for n batches
