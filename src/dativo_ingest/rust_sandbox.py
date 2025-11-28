"""Sandbox wrapper for Rust plugins.

This module provides Docker-based sandboxing for Rust plugins,
enabling secure execution with resource limits and network isolation.
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    # Import docker - handle case where local 'docker' directory shadows package
    # Remove current directory from path temporarily to avoid shadowing
    import sys

    original_path = sys.path[:]
    if "." in sys.path:
        sys.path.remove(".")
    if "" in sys.path:
        sys.path.remove("")

    from docker.errors import DockerException

    import docker

    # Restore path
    sys.path = original_path
except (ImportError, AttributeError):
    # Docker not available or local directory shadows it - define a placeholder exception
    # Restore path if it was modified
    if "original_path" in locals():
        sys.path = original_path
    docker = None
    DockerException = Exception

from .exceptions import SandboxError


class RustPluginSandbox:
    """Docker-based sandbox for executing Rust plugins.

    Provides isolation, resource limits, and security controls for Rust plugin execution.
    Uses a Rust plugin runner container that loads and executes plugins dynamically.
    """

    def __init__(
        self,
        plugin_path: str,
        cpu_limit: Optional[float] = None,
        memory_limit: Optional[str] = None,
        network_disabled: bool = True,
        timeout: int = 300,
        container_image: str = "dativo/rust-plugin-runner:latest",
    ):
        """Initialize Rust plugin sandbox.

        Args:
            plugin_path: Path to Rust plugin library (.so, .dylib, .dll)
            cpu_limit: CPU limit (0.0-1.0, where 1.0 = 1 CPU core)
            memory_limit: Memory limit (e.g., "512m", "1g")
            network_disabled: Disable network access (default: True)
            timeout: Execution timeout in seconds (default: 300)
            container_image: Docker image for Rust plugin runner

        Raises:
            SandboxError: If Docker is not available or initialization fails
        """
        self.plugin_path = Path(plugin_path)
        self.cpu_limit = cpu_limit
        self.memory_limit = memory_limit
        self.network_disabled = network_disabled
        self.timeout = timeout
        self.container_image = container_image

        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
            # Test Docker connection
            self.docker_client.ping()
        except (DockerException, Exception) as e:
            raise SandboxError(
                f"Failed to connect to Docker: {e}",
                details={"error": str(e)},
                retryable=False,
            ) from e

    def _build_container_config(
        self, command: List[str], environment: Optional[Dict[str, str]] = None
    ) -> Dict[str, Any]:
        """Build Docker container configuration.

        Args:
            command: Command to execute in container
            environment: Environment variables

        Returns:
            Container configuration dictionary
        """
        # Build volumes dictionary
        plugin_dir = str(self.plugin_path.parent.absolute())
        volumes = {
            plugin_dir: {
                "bind": "/app/plugins",
                "mode": "ro",  # Read-only mount
            }
        }

        env = environment.copy() if environment else {}

        config = {
            "image": self.container_image,
            "command": command,
            "network_disabled": self.network_disabled,
            "mem_limit": self.memory_limit,
            "cpu_period": 100000,  # 100ms period
            "cpu_quota": int(self.cpu_limit * 100000) if self.cpu_limit else None,
            "environment": env,
            "volumes": volumes,
            "working_dir": "/app/plugins",
            "read_only": True,  # Read-only root filesystem
            "tmpfs": {
                "/tmp": "size=100m",  # Temporary filesystem for /tmp
            },
        }

        return config

    def execute(
        self,
        method_name: str,
        **kwargs: Any,
    ) -> Any:
        """Execute a Rust plugin method in sandboxed environment.

        Args:
            method_name: Name of method to execute (e.g., "extract_batch", "write_batch")
            **kwargs: Keyword arguments for method

        Returns:
            Method return value

        Raises:
            SandboxError: If execution fails
        """
        # Build container command
        plugin_filename = self.plugin_path.name
        plugin_path_in_container = f"/app/plugins/{plugin_filename}"

        # Create request JSON
        request = {
            "method": method_name,
            **kwargs,
        }

        # Build container configuration
        container_config = self._build_container_config(
            command=["rust-plugin-runner"],
            environment={
                "PLUGIN_PATH": plugin_path_in_container,
            },
        )

        # Create and run container
        try:
            container = self.docker_client.containers.create(**container_config)

            # Start container
            container.start()

            # Send initialization request
            init_request = json.dumps({"init": plugin_path_in_container})
            init_result = container.exec_run(
                ["sh", "-c", f'echo "{init_request}" | rust-plugin-runner'],
                stdin=True,
            )

            # Send method request
            method_request = json.dumps(request)
            result = container.exec_run(
                ["sh", "-c", f'echo "{method_request}" | rust-plugin-runner'],
                stdin=True,
            )

            # Wait for container to finish
            container.wait(timeout=self.timeout)

            # Get logs
            logs = container.logs(stdout=True, stderr=True).decode("utf-8")

            # Get exit code
            exit_code = result.exit_code

            if exit_code != 0:
                raise SandboxError(
                    f"Rust plugin execution failed with exit code {exit_code}",
                    details={
                        "exit_code": exit_code,
                        "logs": logs,
                        "method": method_name,
                    },
                    retryable=True,
                )

            # Parse result from logs (last line should be JSON)
            try:
                result_lines = logs.strip().split("\n")
                if result_lines:
                    result_json = json.loads(result_lines[-1])
                    # Extract the "data" or "result" field if present
                    if isinstance(result_json, dict):
                        if "data" in result_json:
                            return result_json["data"]
                        elif "result" in result_json:
                            return result_json["result"]
                        return result_json
                    return result_json
                else:
                    return None
            except (json.JSONDecodeError, IndexError):
                # If we can't parse JSON, return logs
                return {"status": "success", "output": logs}

        finally:
            # Clean up container
            try:
                container.remove(force=True)
            except Exception:
                pass  # Ignore cleanup errors

    def check_connection(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Check connection using sandboxed Rust plugin.

        Args:
            config: Plugin configuration

        Returns:
            Connection check result
        """
        return self.execute("check_connection", config=json.dumps(config))
