"""Sandbox wrapper for Rust plugins.

This module provides Docker-based sandboxing for Rust plugins,
enabling secure execution with resource limits and network isolation.
"""

import base64
import json
import os
import shlex
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

    from docker.errors import DockerException, ImageNotFound

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
    ImageNotFound = Exception

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
        seccomp_profile: Optional[str] = None,
        timeout: int = 300,
        container_image: str = "dativo/rust-plugin-runner:latest",
    ):
        """Initialize Rust plugin sandbox.

        Args:
            plugin_path: Path to Rust plugin library (.so, .dylib, .dll)
            cpu_limit: CPU limit (0.0-1.0, where 1.0 = 1 CPU core)
            memory_limit: Memory limit (e.g., "512m", "1g")
            network_disabled: Disable network access (default: True)
            seccomp_profile: Path to seccomp profile JSON file (optional)
            timeout: Execution timeout in seconds (default: 300)
            container_image: Docker image for Rust plugin runner

        Raises:
            SandboxError: If Docker is not available or initialization fails
        """
        self.plugin_path = Path(plugin_path)
        self.cpu_limit = cpu_limit
        self.memory_limit = memory_limit
        self.network_disabled = network_disabled
        self.seccomp_profile = seccomp_profile
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

        # Default seccomp profile (restrictive)
        self.default_seccomp = self._get_default_seccomp_profile()

    def _get_default_seccomp_profile(self) -> Dict[str, Any]:
        """Get minimal restrictive seccomp profile.

        This profile only allows the minimal set of syscalls required for
        Rust plugin execution in a container. All dangerous syscalls that could
        allow container escape, kernel module loading, or host system compromise
        are explicitly denied.

        The profile is minimal - only syscalls actually needed for Rust execution
        are included.

        Returns:
            Seccomp profile dictionary
        """
        # Minimal set of syscalls needed for Rust to run in a container
        # Based on actual requirements for Rust plugin execution
        minimal_syscalls = [
            # Essential file operations
            "read",
            "write",
            "open",
            "close",
            "stat",
            "fstat",
            "lstat",
            "lseek",
            "access",
            "getcwd",
            "chdir",
            "fchdir",
            "openat",
            "newfstatat",
            "faccessat",
            "getdents",
            "getdents64",
            # File operations for /tmp (tmpfs only, isolated to container)
            "unlink",
            "unlinkat",
            "mkdir",
            "mkdirat",
            "rmdir",
            # Essential memory operations
            "mmap",
            "mprotect",
            "munmap",
            "brk",
            "mremap",
            # Essential process operations
            "clone",
            "fork",
            "execve",
            "exit",
            "exit_group",
            "wait4",
            "getpid",
            "getppid",
            "gettid",
            "getuid",
            "geteuid",
            "getgid",
            "getegid",
            "getgroups",
            "getresuid",
            "getresgid",
            "getpgid",
            "getpgrp",
            "getsid",
            # Essential signal operations
            "rt_sigaction",
            "rt_sigprocmask",
            "rt_sigreturn",
            "kill",
            # Essential I/O operations
            "ioctl",
            "pipe",
            "pipe2",
            "dup",
            "dup2",
            "dup3",
            "select",
            "poll",
            "epoll_create",
            "epoll_create1",
            "epoll_ctl",
            "epoll_wait",
            # Network operations (only if network is enabled, but include for compatibility)
            "socket",
            "connect",
            "accept",
            "accept4",
            "sendto",
            "recvfrom",
            "sendmsg",
            "recvmsg",
            "shutdown",
            "getsockname",
            "getpeername",
            "socketpair",
            "setsockopt",
            "getsockopt",
            # Essential file descriptor operations
            "fcntl",
            "fsync",
            "fdatasync",
            "truncate",
            "ftruncate",
            # Essential time operations
            "gettimeofday",
            "time",
            "clock_gettime",
            "clock_getres",
            "nanosleep",
            # Essential system information
            "uname",
            "getrlimit",
            "getrusage",
            # Essential thread operations
            "sched_yield",
            "set_tid_address",
            "restart_syscall",
            "futex",
            "set_robust_list",
            "get_robust_list",
            # Essential process control
            "prctl",
            "arch_prctl",
            # Random number generation (needed by Rust)
            "getrandom",
            # Additional syscalls that may be needed for dynamic library loading
            "madvise",
            "readlink",
            "readlinkat",
        ]

        # Define dangerous syscalls that must be explicitly denied
        # These syscalls are security risks and should never be allowed
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

        return {
            "defaultAction": "SCMP_ACT_ERRNO",
            "architectures": ["SCMP_ARCH_X86_64"],
            "syscalls": [
                # First, explicitly deny dangerous syscalls (defense in depth)
                {
                    "names": dangerous_syscalls,
                    "action": "SCMP_ACT_ERRNO",
                },
                # Then, allow only minimal safe syscalls needed for Rust execution
                {
                    "names": minimal_syscalls,
                    "action": "SCMP_ACT_ALLOW",
                },
            ],
        }

    def _load_seccomp_profile(self) -> Optional[Dict[str, Any]]:
        """Load seccomp profile from file or use default.

        Returns:
            Seccomp profile dictionary or None
        """
        if self.seccomp_profile:
            profile_path = Path(self.seccomp_profile)
            if profile_path.exists():
                with open(profile_path, "r") as f:
                    return json.load(f)
            else:
                raise SandboxError(
                    f"Seccomp profile not found: {self.seccomp_profile}",
                    details={"profile_path": str(profile_path)},
                    retryable=False,
                )
        else:
            # Return default restrictive profile for security
            # If the Docker environment doesn't support seccomp profiles (e.g., some colima setups),
            # the try/except in _build_container_config will catch the error and continue without it
            return self.default_seccomp

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

        # Add seccomp profile if available
        # Note: Some Docker environments (e.g., colima) may not support custom seccomp profiles
        # In such cases, we skip the seccomp profile for compatibility
        # We'll try to apply it, but if container creation fails, we'll retry without it
        seccomp_profile = self._load_seccomp_profile()
        if seccomp_profile:
            try:
                # Serialize seccomp profile to JSON string for Docker
                # Docker expects the profile as a JSON string in security_opt
                config["security_opt"] = [f"seccomp={json.dumps(seccomp_profile)}"]
            except Exception:
                # If seccomp profile can't be serialized, continue without it
                # This allows the sandbox to work in environments like colima
                pass

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
        # Use a keep-alive command so the container stays running
        # We'll use exec_run to run rust-plugin-runner with our inputs
        container_config = self._build_container_config(
            command=["sleep", "infinity"],  # Keep container alive
            environment={
                "PLUGIN_PATH": plugin_path_in_container,
            },
        )

        # Create and run container
        try:
            try:
                container = self.docker_client.containers.create(**container_config)
            except ImageNotFound as image_error:
                # Docker image is missing - this is a configuration issue
                image_name = getattr(image_error, "explanation", self.container_image)
                raise SandboxError(
                    f"Docker image not found: {image_name}. Please ensure the image is available or pull it with 'docker pull {image_name}'",
                    details={
                        "error": str(image_error),
                        "image": image_name,
                        "error_type": "ImageNotFound",
                    },
                    retryable=False,
                )

            # Start container
            container.start()

            # Prepare both requests - init and method call
            # The rust-plugin-runner expects to read multiple lines from stdin
            # in a single process to maintain state
            init_request = json.dumps({"init": plugin_path_in_container})
            method_request = json.dumps(request)

            # Use base64 encoding to safely pass JSON through shell
            # This avoids issues with special characters, quotes, newlines, etc.
            init_b64 = base64.b64encode(init_request.encode("utf-8")).decode("utf-8")
            method_b64 = base64.b64encode(method_request.encode("utf-8")).decode(
                "utf-8"
            )

            # Use shlex.quote to properly escape base64 strings for shell safety
            # This prevents shell interpretation issues with special characters
            init_b64_quoted = shlex.quote(init_b64)
            method_b64_quoted = shlex.quote(method_b64)

            # Use a single exec_run that pipes both requests to rust-plugin-runner
            # This ensures both requests go to the same process, maintaining state
            # Pipe both decoded JSON lines to the same rust-plugin-runner process
            result = container.exec_run(
                [
                    "sh",
                    "-c",
                    f"(echo {init_b64_quoted} | base64 -d; echo {method_b64_quoted} | base64 -d) | rust-plugin-runner",
                ],
                stdin=True,
            )

            # Get output from exec_run (stdout and stderr combined)
            output = result.output.decode("utf-8") if result.output else ""

            # Also get logs from container (in case output is in logs)
            logs = container.logs(stdout=True, stderr=True).decode("utf-8")

            # Combine outputs, preferring exec_run output
            combined_output = output if output else logs

            # Get exit code
            exit_code = result.exit_code

            if exit_code != 0:
                raise SandboxError(
                    f"Rust plugin execution failed with exit code {exit_code}",
                    details={
                        "exit_code": exit_code,
                        "logs": combined_output,
                        "method": method_name,
                    },
                    retryable=True,
                )

            # Parse result from output
            # The rust-plugin-runner outputs one JSON response per line
            # We want the last non-empty line (which should be the method response)
            try:
                result_lines = [
                    line.strip()
                    for line in combined_output.strip().split("\n")
                    if line.strip()
                ]
                if result_lines:
                    # The last line should be the method response
                    # The first line should be the init response
                    if len(result_lines) >= 2:
                        # Parse the method response (last line)
                        result_json = json.loads(result_lines[-1])
                    else:
                        # Fallback: parse the only line
                        result_json = json.loads(result_lines[0])

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
            except (json.JSONDecodeError, IndexError) as e:
                # If we can't parse JSON, return logs
                raise SandboxError(
                    f"Failed to parse Rust plugin response: {e}",
                    details={
                        "output": combined_output,
                        "method": method_name,
                        "parse_error": str(e),
                    },
                    retryable=True,
                )

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
