"""Tests for plugin sandboxing functionality.

Tests cover:
1. Script generation for plugin execution
2. Container configuration
3. Argument serialization/deserialization
4. Error handling
5. Result parsing
"""

import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Mock docker module before importing sandbox
# This allows tests to run even if docker package is not installed
if "docker" not in sys.modules:
    mock_docker = Mock()
    mock_docker.from_env = Mock()
    mock_docker_errors = Mock()
    mock_docker_errors.DockerException = Exception
    sys.modules["docker"] = mock_docker
    sys.modules["docker.errors"] = mock_docker_errors

from dativo_ingest.exceptions import SandboxError
from dativo_ingest.sandbox import PluginSandbox, should_sandbox_plugin


class TestScriptGeneration:
    """Test script generation functionality."""

    def test_generate_execution_script_basic(self, tmp_path):
        """Test basic script generation."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseReader

class TestReader(BaseReader):
    def check_connection(self):
        return {"status": "ok"}
"""
        )

        sandbox = PluginSandbox(str(plugin_file))
        script = sandbox._generate_execution_script(
            plugin_file.name, "check_connection"
        )

        # Verify script contains key components
        assert "import sys" in script
        assert "import json" in script
        assert "importlib.util" in script
        assert plugin_file.name in script
        assert "check_connection" in script
        assert "json.dumps" in script

    def test_generate_execution_script_with_args(self, tmp_path):
        """Test script generation with arguments."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseReader

class TestReader(BaseReader):
    def check_connection(self):
        return {"status": "ok"}
"""
        )

        sandbox = PluginSandbox(str(plugin_file))
        script = sandbox._generate_execution_script(
            plugin_file.name, "check_connection", "arg1", kwarg1="value1"
        )

        # Verify arguments are deserialized (the JSON is embedded in the script)
        assert "json.loads" in script
        assert "args_data" in script
        assert "kwargs_data" in script
        # Verify the script uses the deserialized arguments
        assert "arg1" in script or '"arg1"' in script

    def test_generate_execution_script_instantiates_plugin(self, tmp_path):
        """Test that generated script actually instantiates the plugin."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseReader

class TestReader(BaseReader):
    def check_connection(self):
        return {"status": "ok"}
"""
        )

        sandbox = PluginSandbox(str(plugin_file))
        script = sandbox._generate_execution_script(
            plugin_file.name, "check_connection"
        )

        # Verify script instantiates the plugin (not commented out)
        assert "plugin_class(" in script or "instance = plugin_class" in script
        # Verify it's not just a placeholder
        assert (
            '"status": "success", "message": "Method executed in sandbox"' not in script
        )

    def test_generate_execution_script_calls_method(self, tmp_path):
        """Test that generated script calls the method."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseReader

class TestReader(BaseReader):
    def check_connection(self):
        return {"status": "ok"}
"""
        )

        sandbox = PluginSandbox(str(plugin_file))
        script = sandbox._generate_execution_script(
            plugin_file.name, "check_connection"
        )

        # Verify method is called (not commented out)
        assert "method()" in script or "result = method" in script
        # Verify it's not just a placeholder
        assert (
            '"status": "success", "message": "Method executed in sandbox"' not in script
        )

    def test_generate_execution_script_handles_result_serialization(self, tmp_path):
        """Test that script handles result serialization."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text(
            """
from dativo_ingest.plugins import BaseReader

class TestReader(BaseReader):
    def check_connection(self):
        return {"status": "ok"}
"""
        )

        sandbox = PluginSandbox(str(plugin_file))
        script = sandbox._generate_execution_script(
            plugin_file.name, "check_connection"
        )

        # Verify result is serialized
        assert '"result":' in script
        assert "to_dict()" in script or "result_dict" in script


class TestContainerConfiguration:
    """Test container configuration building."""

    def test_build_container_config_basic(self, tmp_path):
        """Test basic container configuration."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("")

        sandbox = PluginSandbox(str(plugin_file))
        config = sandbox._build_container_config(["python", "script.py"])

        assert config["image"] == "python:3.10-slim"
        assert config["network_disabled"] is True
        assert config["read_only"] is True
        # Note: user is not set by default for compatibility (colima, etc.)
        # Check that /app/plugins is in the volume bindings
        volumes = config["volumes"]
        assert any(v.get("bind") == "/app/plugins" for v in volumes.values())

    def test_build_container_config_mounts_source(self, tmp_path):
        """Test that container config mounts dativo_ingest source."""
        # Create a structure that mimics the project layout
        project_root = tmp_path / "project"
        src_dir = project_root / "src"
        dativo_dir = src_dir / "dativo_ingest"
        dativo_dir.mkdir(parents=True)
        (dativo_dir / "__init__.py").write_text("")

        plugin_file = project_root / "plugins" / "test_plugin.py"
        plugin_file.parent.mkdir(parents=True)
        plugin_file.write_text("")

        sandbox = PluginSandbox(str(plugin_file))
        config = sandbox._build_container_config(["python", "script.py"])

        # Verify source directory is mounted
        volumes = config["volumes"]
        assert any("/app/src" in str(v.get("bind", "")) for v in volumes.values())
        # Verify PYTHONPATH is set
        assert config["environment"].get("PYTHONPATH") == "/app/src"

    def test_build_container_config_sets_pythonpath(self, tmp_path):
        """Test that PYTHONPATH is set correctly."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("")

        sandbox = PluginSandbox(str(plugin_file))
        config = sandbox._build_container_config(["python", "script.py"])

        # PYTHONPATH should be set (either /app/src or /app/plugins)
        assert "PYTHONPATH" in config["environment"]
        assert config["environment"]["PYTHONPATH"] in ["/app/src", "/app/plugins"]

    def test_build_container_config_resource_limits(self, tmp_path):
        """Test resource limits in container config."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("")

        sandbox = PluginSandbox(str(plugin_file), cpu_limit=0.5, memory_limit="512m")
        config = sandbox._build_container_config(["python", "script.py"])

        assert config["cpu_period"] == 100000
        assert config["cpu_quota"] == 50000  # 0.5 * 100000
        assert config["mem_limit"] == "512m"


class TestArgumentHandling:
    """Test argument serialization and handling."""

    def test_args_serialization(self, tmp_path):
        """Test that arguments are properly serialized."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("")

        sandbox = PluginSandbox(str(plugin_file))
        script = sandbox._generate_execution_script(
            plugin_file.name, "method", "arg1", "arg2", kw1="val1", kw2="val2"
        )

        # Verify arguments are deserialized (JSON is embedded in script)
        assert "json.loads" in script
        assert "args_data" in script
        assert "kwargs_data" in script
        # Verify the arguments appear in the script (serialized)
        assert '"arg1"' in script or "arg1" in script

    def test_empty_args_handling(self, tmp_path):
        """Test handling of empty arguments."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("")

        sandbox = PluginSandbox(str(plugin_file))
        script = sandbox._generate_execution_script(plugin_file.name, "method")

        # Should handle no arguments
        assert "args_data" in script
        assert "kwargs_data" in script
        # Should handle empty args/kwargs (args used for instantiation, kwargs for method call)
        assert "args_data" in script and "kwargs_data" in script
        # Should handle empty kwargs for method call
        assert "has_kwargs" in script or "kwargs_data" in script


class TestResultParsing:
    """Test result parsing from container logs."""

    def test_parse_result_with_result_field(self):
        """Test parsing result that has 'result' field."""
        logs = 'Some log output\n{"status": "success", "result": {"key": "value"}}'
        result_lines = logs.strip().split("\n")
        result_json = json.loads(result_lines[-1])

        # Simulate the parsing logic from execute method
        if isinstance(result_json, dict) and "result" in result_json:
            parsed_result = result_json["result"]
        else:
            parsed_result = result_json

        assert parsed_result == {"key": "value"}

    def test_parse_result_without_result_field(self):
        """Test parsing result without 'result' field."""
        logs = 'Some log output\n{"status": "success", "data": "value"}'
        result_lines = logs.strip().split("\n")
        result_json = json.loads(result_lines[-1])

        # Simulate the parsing logic
        if isinstance(result_json, dict) and "result" in result_json:
            parsed_result = result_json["result"]
        else:
            parsed_result = result_json

        assert parsed_result == {"status": "success", "data": "value"}


class TestSandboxInitialization:
    """Test sandbox initialization and error handling."""

    @patch("dativo_ingest.sandbox.docker.from_env")
    def test_sandbox_init_success(self, mock_docker, tmp_path):
        """Test successful sandbox initialization."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("")

        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        sandbox = PluginSandbox(str(plugin_file))
        assert sandbox.plugin_path == plugin_file
        assert sandbox.network_disabled is True

    @patch("dativo_ingest.sandbox.docker.from_env")
    def test_sandbox_init_docker_error(self, mock_docker, tmp_path):
        """Test sandbox initialization with Docker error."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("")

        mock_docker.side_effect = Exception("Docker not available")

        with pytest.raises(SandboxError, match="Failed to connect to Docker"):
            PluginSandbox(str(plugin_file))

    @patch("dativo_ingest.sandbox.docker.from_env")
    def test_sandbox_init_docker_ping_fails(self, mock_docker, tmp_path):
        """Test sandbox initialization when Docker ping fails."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("")

        mock_client = Mock()
        mock_client.ping.side_effect = Exception("Connection failed")
        mock_docker.return_value = mock_client

        with pytest.raises(SandboxError, match="Failed to connect to Docker"):
            PluginSandbox(str(plugin_file))


class TestShouldSandboxPlugin:
    """Test should_sandbox_plugin function."""

    def test_should_sandbox_cloud_mode_python(self, tmp_path):
        """Test that Python plugins are sandboxed in cloud mode."""
        plugin_file = tmp_path / "test.py"
        plugin_file.write_text("")

        assert should_sandbox_plugin(str(plugin_file), mode="cloud") is True

    def test_should_sandbox_cloud_mode_rust(self, tmp_path):
        """Test that Rust plugins are not sandboxed in cloud mode."""
        plugin_file = tmp_path / "test.so"
        plugin_file.write_text("")

        assert should_sandbox_plugin(str(plugin_file), mode="cloud") is False

    def test_should_sandbox_self_hosted_mode(self, tmp_path):
        """Test that plugins are not sandboxed in self_hosted mode."""
        plugin_file = tmp_path / "test.py"
        plugin_file.write_text("")

        assert should_sandbox_plugin(str(plugin_file), mode="self_hosted") is False


class TestSandboxExecution:
    """Test sandbox execution (with mocked Docker)."""

    @patch("dativo_ingest.sandbox.docker.from_env")
    def test_execute_plugin_method_mocked(self, mock_docker, tmp_path):
        """Test executing a plugin method with mocked Docker."""
        # Create a test plugin
        plugin_file = tmp_path / "test_plugin.py"
        plugin_code = """
from dativo_ingest.plugins import BaseReader, ConnectionTestResult

class TestReader(BaseReader):
    def check_connection(self):
        return ConnectionTestResult(
            success=True,
            message="Test connection",
            details={"test": "data"}
        )
"""
        plugin_file.write_text(plugin_code)

        # Mock Docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        # Mock container
        mock_container = Mock()
        mock_container.wait.return_value = {"StatusCode": 0}
        mock_container.logs.return_value = b'{"status": "success", "result": {"success": true, "message": "Test connection", "details": {"test": "data"}}}'
        mock_client.containers.create.return_value = mock_container

        sandbox = PluginSandbox(str(plugin_file))
        result = sandbox.execute("check_connection")

        # Verify Docker was called
        mock_client.containers.create.assert_called_once()
        mock_container.start.assert_called_once()
        mock_container.wait.assert_called_once()

        # Verify result is parsed correctly
        assert isinstance(result, dict)
        assert "success" in result or result.get("status") == "success"

    @patch("dativo_ingest.sandbox.docker.from_env")
    def test_execute_plugin_method_error(self, mock_docker, tmp_path):
        """Test executing a plugin method that fails."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("")

        # Mock Docker client
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_docker.return_value = mock_client

        # Mock container with error
        mock_container = Mock()
        mock_container.wait.return_value = {"StatusCode": 1}
        mock_container.logs.return_value = b"Error occurred"
        mock_client.containers.create.return_value = mock_container

        sandbox = PluginSandbox(str(plugin_file))

        with pytest.raises(SandboxError, match="Plugin execution failed"):
            sandbox.execute("check_connection")


class TestScriptContentValidation:
    """Test that generated scripts have correct content."""

    def test_script_uses_prepared_variables(self, tmp_path):
        """Test that script uses serialized arguments."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("")

        sandbox = PluginSandbox(str(plugin_file))
        script = sandbox._generate_execution_script(
            plugin_file.name, "method", "arg1", kwarg1="value1"
        )

        # Verify the arguments are deserialized and used
        assert "json.loads" in script
        assert "args_data" in script
        assert "kwargs_data" in script
        # Verify the arguments are actually used in method calls
        assert "method(" in script or "result = method" in script

    def test_script_handles_plugin_instantiation(self, tmp_path):
        """Test that script properly handles plugin instantiation."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("")

        sandbox = PluginSandbox(str(plugin_file))
        script = sandbox._generate_execution_script(
            plugin_file.name, "method", "arg1", kwarg1="value1"
        )

        # Verify instantiation logic is present
        assert "plugin_class(" in script or "instance = plugin_class" in script
        # Verify it handles different argument combinations
        assert "args_data" in script and "kwargs_data" in script

    def test_script_handles_method_execution(self, tmp_path):
        """Test that script properly executes the method."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("")

        sandbox = PluginSandbox(str(plugin_file))
        script = sandbox._generate_execution_script(
            plugin_file.name, "method", "arg1", kwarg1="value1"
        )

        # Verify method execution logic
        assert "getattr(instance" in script
        assert "method(" in script or "result = method" in script
        # Verify it handles different argument combinations
        assert "args_data" in script and "kwargs_data" in script

    def test_script_returns_actual_result(self, tmp_path):
        """Test that script returns actual result, not placeholder."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("")

        sandbox = PluginSandbox(str(plugin_file))
        script = sandbox._generate_execution_script(plugin_file.name, "method")

        # Verify it's not the old placeholder
        assert (
            '"status": "success", "message": "Method executed in sandbox"' not in script
        )
        # Verify it actually executes and returns result
        assert '"result":' in script
        assert "result_dict" in script or "result" in script


class TestSeccompSecurity:
    """Test seccomp profile security - ensure dangerous syscalls are denied."""

    def test_dangerous_syscalls_explicitly_denied(self, tmp_path):
        """Test that dangerous syscalls are explicitly denied in seccomp profile."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("")

        sandbox = PluginSandbox(str(plugin_file))
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

    def test_seccomp_profile_structure(self, tmp_path):
        """Test that seccomp profile has correct structure."""
        plugin_file = tmp_path / "test_plugin.py"
        plugin_file.write_text("")

        sandbox = PluginSandbox(str(plugin_file))
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
