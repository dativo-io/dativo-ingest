"""Tests for Rust plugin sandboxing functionality.

Tests cover:
1. Container configuration
2. Seccomp profile generation
3. Error handling
4. Result parsing
5. Method execution
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Mock docker module before importing rust_sandbox
# This allows tests to run even if docker package is not installed
if "docker" not in sys.modules:
    mock_docker = Mock()
    mock_docker.from_env = Mock()
    mock_docker_errors = Mock()
    mock_docker_errors.DockerException = Exception
    mock_docker_errors.ImageNotFound = Exception
    sys.modules["docker"] = mock_docker
    sys.modules["docker.errors"] = mock_docker_errors

from dativo_ingest.exceptions import SandboxError
from dativo_ingest.rust_sandbox import RustPluginSandbox


class _FakeExecSocket:
    """Minimal socket-like object for exec_start(socket=True) tests.

    RustPluginSandbox runs rust-plugin-runner with tty=True, so stdout is raw bytes.
    """

    def __init__(self, responses: list[str]):
        self._outgoing: list[bytes] = []
        self._buffer = "".join(responses).encode("utf-8")
        self.closed = False
        self.timeout = None

    def sendall(self, data: bytes) -> None:
        self._outgoing.append(data)

    def recv(self, n: int) -> bytes:
        if not self._buffer:
            return b""
        chunk = self._buffer[:n]
        self._buffer = self._buffer[n:]
        return chunk

    def settimeout(self, timeout: float) -> None:
        self.timeout = timeout

    def close(self) -> None:
        self.closed = True


class TestRustSandboxInitialization:
    """Test Rust sandbox initialization and error handling."""

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_rust_sandbox_init_success(self, mock_docker_module, tmp_path):
        """Test successful Rust sandbox initialization."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        sandbox = RustPluginSandbox(str(plugin_file))
        assert sandbox.plugin_path == plugin_file
        assert sandbox.network_disabled is True
        assert sandbox.container_image == "dativo/rust-plugin-runner:latest"

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_rust_sandbox_init_docker_error(self, mock_docker_module, tmp_path):
        """Test Rust sandbox initialization with Docker error."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_docker_module.from_env.side_effect = Exception("Docker not available")

        with pytest.raises(SandboxError, match="Failed to connect to Docker"):
            RustPluginSandbox(str(plugin_file))

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_rust_sandbox_init_docker_ping_fails(self, mock_docker_module, tmp_path):
        """Test Rust sandbox initialization when Docker ping fails."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.side_effect = Exception("Connection failed")
        mock_docker_module.from_env.return_value = mock_client

        with pytest.raises(SandboxError, match="Failed to connect to Docker"):
            RustPluginSandbox(str(plugin_file))

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_rust_sandbox_custom_image(self, mock_docker_module, tmp_path):
        """Test Rust sandbox with custom container image."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        sandbox = RustPluginSandbox(
            str(plugin_file), container_image="custom/rust-runner:v1.0"
        )
        assert sandbox.container_image == "custom/rust-runner:v1.0"

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_rust_sandbox_resource_limits(self, mock_docker_module, tmp_path):
        """Test Rust sandbox with resource limits."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        sandbox = RustPluginSandbox(
            str(plugin_file), cpu_limit=0.5, memory_limit="512m", timeout=120
        )
        assert sandbox.cpu_limit == 0.5
        assert sandbox.memory_limit == "512m"
        assert sandbox.timeout == 120


class TestRustSandboxContainerConfiguration:
    """Test container configuration building for Rust sandbox."""

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_build_container_config_basic(self, mock_docker_module, tmp_path):
        """Test basic container configuration."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        sandbox = RustPluginSandbox(str(plugin_file))
        config = sandbox._build_container_config(["sleep", "infinity"])

        assert config["image"] == "dativo/rust-plugin-runner:latest"
        assert config["network_disabled"] is True
        assert config["read_only"] is True
        assert config["working_dir"] == "/usr/local/plugins"
        # Check that /usr/local/plugins is in the volume bindings (FHS-compliant)
        volumes = config["volumes"]
        assert any(v.get("bind") == "/usr/local/plugins" for v in volumes.values())

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_build_container_config_resource_limits(self, mock_docker_module, tmp_path):
        """Test resource limits in container config."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        sandbox = RustPluginSandbox(
            str(plugin_file), cpu_limit=0.5, memory_limit="512m"
        )
        config = sandbox._build_container_config(["sleep", "infinity"])

        assert config.get("cpu_period") == 100000
        assert config.get("cpu_quota") == 50000  # 0.5 * 100000
        assert config.get("mem_limit") == "512m"

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_build_container_config_seccomp_profile(self, mock_docker_module, tmp_path):
        """Test that seccomp profile is included in config."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        sandbox = RustPluginSandbox(str(plugin_file))
        config = sandbox._build_container_config(["sleep", "infinity"])

        # Seccomp profile should be included
        assert "security_opt" in config
        assert len(config["security_opt"]) > 0
        assert "seccomp=" in config["security_opt"][0]

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_build_container_config_custom_seccomp_profile(
        self, mock_docker_module, tmp_path
    ):
        """Test container config with custom seccomp profile."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        # Create custom seccomp profile
        seccomp_file = tmp_path / "custom_seccomp.json"
        custom_profile = {
            "defaultAction": "SCMP_ACT_ERRNO",
            "architectures": ["SCMP_ARCH_X86_64"],
            "syscalls": [{"names": ["read", "write"], "action": "SCMP_ACT_ALLOW"}],
        }
        seccomp_file.write_text(json.dumps(custom_profile))

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        sandbox = RustPluginSandbox(str(plugin_file), seccomp_profile=str(seccomp_file))
        config = sandbox._build_container_config(["sleep", "infinity"])

        # Should use custom profile
        assert "security_opt" in config
        profile_json = json.loads(config["security_opt"][0].replace("seccomp=", ""))
        assert profile_json == custom_profile

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_build_container_config_seccomp_profile_not_found(
        self, mock_docker_module, tmp_path
    ):
        """Test error when seccomp profile file doesn't exist."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        sandbox = RustPluginSandbox(
            str(plugin_file), seccomp_profile="/nonexistent/seccomp.json"
        )

        with pytest.raises(SandboxError, match="Seccomp profile not found"):
            sandbox._load_seccomp_profile()


class TestRustSandboxSeccompSecurity:
    """Test seccomp profile security - ensure dangerous syscalls are denied."""

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_dangerous_syscalls_explicitly_denied(self, mock_docker_module, tmp_path):
        """Test that dangerous syscalls are explicitly denied in seccomp profile."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        sandbox = RustPluginSandbox(str(plugin_file))
        profile = sandbox._get_default_seccomp_profile()

        # Dangerous syscalls that must be explicitly denied
        dangerous_syscalls = [
            "reboot",
            "mount",
            "umount",
            "umount2",
            "ptrace",
            "kexec_load",
            "kexec_file_load",
            "init_module",
            "delete_module",
            "finit_module",
            "bpf",
            "swapon",
            "swapoff",
            "sethostname",
            "setdomainname",
            "chroot",
            "pivot_root",
            "settimeofday",
            "clock_settime",
            "setuid",
            "setgid",
            "setresuid",
            "setresgid",
            "capset",
            "iopl",
            "ioperm",
            "unshare",
            "setns",
            "userfaultfd",
            "process_vm_readv",
            "process_vm_writev",
        ]

        # Check that dangerous syscalls are in the deny list
        deny_syscalls = []
        allow_syscalls = []

        for syscall_entry in profile["syscalls"]:
            if syscall_entry["action"] == "SCMP_ACT_ERRNO":
                deny_syscalls.extend(syscall_entry["names"])
            elif syscall_entry["action"] == "SCMP_ACT_ALLOW":
                allow_syscalls.extend(syscall_entry["names"])

        # Verify all dangerous syscalls are explicitly denied
        for dangerous_syscall in dangerous_syscalls:
            assert (
                dangerous_syscall in deny_syscalls
            ), f"Dangerous syscall {dangerous_syscall} is not explicitly denied"

        # Verify dangerous syscalls are NOT in the allowed list
        for dangerous_syscall in dangerous_syscalls:
            assert (
                dangerous_syscall not in allow_syscalls
            ), f"Dangerous syscall {dangerous_syscall} is in the allowed list!"

        # Verify default action is ERRNO (deny by default)
        assert profile["defaultAction"] == "SCMP_ACT_ERRNO"

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_seccomp_profile_structure(self, mock_docker_module, tmp_path):
        """Test that seccomp profile has correct structure."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        sandbox = RustPluginSandbox(str(plugin_file))
        profile = sandbox._get_default_seccomp_profile()

        # Verify profile structure
        assert "defaultAction" in profile
        assert "architectures" in profile
        assert "syscalls" in profile
        assert isinstance(profile["syscalls"], list)
        assert len(profile["syscalls"]) >= 2  # At least deny list and allow list

        # Verify there's a deny list (dangerous syscalls)
        has_deny_list = any(
            entry.get("action") == "SCMP_ACT_ERRNO" for entry in profile["syscalls"]
        )
        assert (
            has_deny_list
        ), "Seccomp profile should have explicit deny list for dangerous syscalls"


class TestRustSandboxExecution:
    """Test Rust sandbox execution (with mocked Docker)."""

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_execute_plugin_method_mocked(self, mock_docker_module, tmp_path):
        """Test executing a Rust plugin method with mocked Docker."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        # Mock Docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        # Mock container + streaming exec session
        mock_container = Mock()
        mock_container.id = "container-id"
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()  # Image exists

        mock_client.api = Mock()
        mock_client.api.exec_create.return_value = {"Id": "exec-id"}
        mock_client.api.exec_start.return_value = _FakeExecSocket(
            [
                '{"status":"success","message":"Initialized"}\n',
                '{"status":"success","data":{"result":"ok"}}\n',
            ]
        )

        sandbox = RustPluginSandbox(str(plugin_file))
        result = sandbox.execute("check_connection", config='{"test": "config"}')

        # Verify Docker was called (container + long-lived runner)
        assert mock_client.containers.create.call_count == 1
        assert mock_container.start.call_count == 1
        assert mock_client.api.exec_create.call_count == 1
        assert mock_client.api.exec_start.call_count == 1

        # Verify result is parsed correctly
        assert isinstance(result, dict)
        assert result.get("result") == "ok"

        # Cleanup is explicit (not per execute call)
        sandbox.close()
        assert mock_container.remove.call_count == 1

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_execute_plugin_method_error(self, mock_docker_module, tmp_path):
        """Test executing a Rust plugin method that fails."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        # Mock Docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        # Mock container + error response from runner
        mock_container = Mock()
        mock_container.id = "container-id"
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        mock_client.api = Mock()
        mock_client.api.exec_create.return_value = {"Id": "exec-id"}
        mock_client.api.exec_start.return_value = _FakeExecSocket(
            [
                '{"status":"success","message":"Initialized"}\n',
                '{"status":"error","error":"Error occurred"}\n',
            ]
        )

        sandbox = RustPluginSandbox(str(plugin_file))

        with pytest.raises(SandboxError, match="returned error"):
            sandbox.execute("check_connection", config='{"test": "config"}')

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_execute_plugin_method_parse_error(self, mock_docker_module, tmp_path):
        """Test executing a Rust plugin method with invalid JSON response."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        # Mock Docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        # Mock container + invalid JSON output
        mock_container = Mock()
        mock_container.id = "container-id"
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        mock_client.api = Mock()
        mock_client.api.exec_create.return_value = {"Id": "exec-id"}
        mock_client.api.exec_start.return_value = _FakeExecSocket(
            [
                '{"status":"success","message":"Initialized"}\n',
                "Invalid JSON response\n",
            ]
        )

        sandbox = RustPluginSandbox(str(plugin_file))

        with pytest.raises(SandboxError, match="Failed to parse Rust plugin response"):
            sandbox.execute("check_connection", config='{"test": "config"}')

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_execute_plugin_method_with_result_field(
        self, mock_docker_module, tmp_path
    ):
        """Test executing a Rust plugin method that returns result in 'result' field."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        # Mock Docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        # Mock container + method response using 'result' field
        mock_container = Mock()
        mock_container.id = "container-id"
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        mock_client.api = Mock()
        mock_client.api.exec_create.return_value = {"Id": "exec-id"}
        mock_client.api.exec_start.return_value = _FakeExecSocket(
            [
                '{"status":"success","message":"Initialized"}\n',
                '{"status":"success","result":{"key":"value"}}\n',
            ]
        )

        sandbox = RustPluginSandbox(str(plugin_file))
        result = sandbox.execute("extract_batch", batch=[])

        # Verify result is extracted from 'result' field
        assert isinstance(result, dict)
        assert result.get("key") == "value"

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_execute_plugin_method_with_data_field(self, mock_docker_module, tmp_path):
        """Test executing a Rust plugin method that returns result in 'data' field."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        # Mock Docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        # Mock container + method response using 'data' field
        mock_container = Mock()
        mock_container.id = "container-id"
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        mock_client.api = Mock()
        mock_client.api.exec_create.return_value = {"Id": "exec-id"}
        mock_client.api.exec_start.return_value = _FakeExecSocket(
            [
                '{"status":"success","message":"Initialized"}\n',
                '{"status":"success","data":{"key":"value"}}\n',
            ]
        )

        sandbox = RustPluginSandbox(str(plugin_file))
        result = sandbox.execute("extract_batch", batch=[])

        # Verify result is extracted from 'data' field
        assert isinstance(result, dict)
        assert result.get("key") == "value"

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_execute_plugin_method_multiline_response(self, mock_docker_module, tmp_path):
        """Test a normal init+method response (runner is line-delimited)."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        # Mock Docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        # Mock container with two line-delimited responses (init + method response)
        mock_container = Mock()
        mock_container.id = "container-id"
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        mock_client.api = Mock()
        mock_client.api.exec_create.return_value = {"Id": "exec-id"}
        mock_client.api.exec_start.return_value = _FakeExecSocket(
            [
                '{"status":"success","message":"Initialized"}\n',
                '{"status":"success","data":{"result":"ok"}}\n',
            ]
        )

        sandbox = RustPluginSandbox(str(plugin_file))
        result = sandbox.execute("check_connection", config='{"test": "config"}')

        # Verify result is parsed from last line
        assert isinstance(result, dict)
        assert result.get("result") == "ok"

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_check_connection_method(self, mock_docker_module, tmp_path):
        """Test check_connection convenience method."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        # Mock Docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        # Mock container + method response
        mock_container = Mock()
        mock_container.id = "container-id"
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        mock_client.api = Mock()
        mock_client.api.exec_create.return_value = {"Id": "exec-id"}
        mock_client.api.exec_start.return_value = _FakeExecSocket(
            [
                '{"status":"success","message":"Initialized"}\n',
                '{"status":"success","data":{"success":true}}\n',
            ]
        )

        sandbox = RustPluginSandbox(str(plugin_file))
        config = {"type": "test", "connection": {}}
        result = sandbox.check_connection(config)

        assert isinstance(result, dict)

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_execute_container_cleanup_on_error(self, mock_docker_module, tmp_path):
        """Test that container is cleaned up even when execution fails."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        # Mock Docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        # Mock container + socket that fails on request send
        mock_container = Mock()
        mock_container.id = "container-id"
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        mock_client.api = Mock()
        mock_client.api.exec_create.return_value = {"Id": "exec-id"}
        fake_socket = _FakeExecSocket(['{"status":"success","message":"Initialized"}\n'])

        def _sendall_raises(_data: bytes) -> None:
            raise Exception("Execution error")

        fake_socket.sendall = _sendall_raises  # type: ignore[method-assign]
        mock_client.api.exec_start.return_value = fake_socket

        sandbox = RustPluginSandbox(str(plugin_file))

        with pytest.raises(SandboxError):
            sandbox.execute("check_connection", config='{"test": "config"}')

        # Verify container cleanup was attempted
        assert mock_container.remove.call_count == 1

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_execute_container_cleanup_ignores_errors(
        self, mock_docker_module, tmp_path
    ):
        """Test that container cleanup errors are ignored."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        # Mock Docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        # Mock container + method response
        mock_container = Mock()
        mock_container.id = "container-id"
        # Make remove raise an error
        mock_container.remove.side_effect = Exception("Cleanup error")
        mock_client.containers.create.return_value = mock_container
        mock_client.images.get.return_value = Mock()

        mock_client.api = Mock()
        mock_client.api.exec_create.return_value = {"Id": "exec-id"}
        mock_client.api.exec_start.return_value = _FakeExecSocket(
            [
                '{"status":"success","message":"Initialized"}\n',
                '{"status":"success","data":{}}\n',
            ]
        )

        sandbox = RustPluginSandbox(str(plugin_file))

        result = sandbox.execute("check_connection", config='{"test": "config"}')
        assert result is not None
        # Should not raise error even if cleanup fails
        sandbox.close()


class TestRustSandboxImageNotFoundErrorHandling:
    """Test ImageNotFound error handling for Rust sandbox."""

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_execute_image_not_found(self, mock_docker_module, tmp_path):
        """Test that ImageNotFound is properly handled."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        # Mock Docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        # Mock ImageNotFound exception - need to create a proper exception class
        class MockImageNotFound(Exception):
            def __init__(self, msg):
                super().__init__(msg)
                self.explanation = msg

        mock_image_error = MockImageNotFound(
            "No such image: dativo/rust-plugin-runner:latest"
        )
        mock_client.containers.create.side_effect = mock_image_error

        # Patch ImageNotFound to be our mock exception
        with patch("dativo_ingest.rust_sandbox.ImageNotFound", MockImageNotFound):
            sandbox = RustPluginSandbox(str(plugin_file))

            with pytest.raises(SandboxError) as exc_info:
                sandbox.execute("check_connection", config='{"test": "config"}')

            # Verify error details
            assert "Docker image not found" in str(exc_info.value)
            assert "dativo/rust-plugin-runner:latest" in str(exc_info.value)
            assert "docker pull" in str(exc_info.value)
            assert exc_info.value.details.get("error_type") == "ImageNotFound"

    @patch("dativo_ingest.rust_sandbox.docker")
    def test_execute_image_not_found_custom_image(self, mock_docker_module, tmp_path):
        """Test that ImageNotFound includes custom image name."""
        plugin_file = tmp_path / "test_plugin.so"
        plugin_file.write_bytes(b"fake plugin binary")

        # Mock Docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker_module.from_env.return_value = mock_client

        # Mock ImageNotFound exception
        class MockImageNotFound(Exception):
            def __init__(self, msg):
                super().__init__(msg)
                self.explanation = msg

        mock_image_error = MockImageNotFound("No such image: custom/rust-runner:v1.0")
        mock_client.containers.create.side_effect = mock_image_error

        # Patch ImageNotFound to be our mock exception
        with patch("dativo_ingest.rust_sandbox.ImageNotFound", MockImageNotFound):
            sandbox = RustPluginSandbox(
                str(plugin_file), container_image="custom/rust-runner:v1.0"
            )

            with pytest.raises(SandboxError) as exc_info:
                sandbox.execute("check_connection", config='{"test": "config"}')

            # Verify error includes custom image name
            assert "Docker image not found" in str(exc_info.value)
            assert "custom/rust-runner:v1.0" in str(exc_info.value)
