"""Sandbox wrapper for Rust plugins.

This module provides Docker-based sandboxing for Rust plugins,
enabling secure execution with resource limits and network isolation.
"""

import json
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

        # Long-lived container + runner session state
        self._container = None
        self._exec_socket = None
        self._recv_buffer = b""
        self._runner_initialized = False

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

    def __del__(self) -> None:
        # Best-effort cleanup (avoid raising in GC)
        try:
            self.close()
        except Exception:
            pass

    def close(self) -> None:
        """Close any long-lived runner/container resources."""
        # Close exec socket first (stops stdin piping)
        sock = self._exec_socket
        self._exec_socket = None
        self._recv_buffer = b""
        self._runner_initialized = False
        try:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
        finally:
            container = self._container
            self._container = None
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    def _get_default_seccomp_profile(self) -> Dict[str, Any]:
        """Get minimal restrictive seccomp profile.

        This profile only allows the minimal set of syscalls required for
        Rust plugin execution in a container. All dangerous syscalls that could
        allow container escape, kernel module loading, or host system compromise
        are explicitly denied.

        The profile includes newer syscalls (openat2, close_range, clone3, etc.)
        required by modern runc versions for secure container startup, especially
        when using read-only filesystems and mount isolation. These syscalls are
        used by runc itself during container initialization, not by the container
        process, so they are safe to allow.

        The profile is minimal - only syscalls actually needed for Rust execution
        and secure container startup are included.

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
            "openat2",  # Newer secure version of openat (required by runc for /proc checks)
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
            "clone3",  # Newer version of clone (required by runc)
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
            "close_range",  # Required by runc for secure file descriptor closing
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
            # New mount API syscalls (required by runc for secure mount operations)
            # These are safe - they're used by runc itself, not by container processes
            "open_tree",  # Required by runc for mount namespace operations
            "move_mount",  # Required by runc for mount operations
            "fsopen",  # Required by runc for filesystem operations
            "fsmount",  # Required by runc for mounting
            "fspick",  # Required by runc for filesystem operations
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
            # Support both x86_64 and ARM64 (Apple Silicon)
            "architectures": ["SCMP_ARCH_X86_64", "SCMP_ARCH_AARCH64"],
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
            # Try to load shared seccomp.json file, fall back to default if not found
            shared_profile_path = Path(__file__).parent / "seccomp.json"
            if shared_profile_path.exists():
                try:
                    with open(shared_profile_path, "r") as f:
                        return json.load(f)
                except (json.JSONDecodeError, IOError):
                    # If file is corrupted or unreadable, fall back to default
                    pass
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
        # Use /usr/local/plugins as mount point (FHS-compliant, exists in base images)
        # This matches the Python sandbox for consistency
        plugin_dir = str(self.plugin_path.parent.absolute())
        volumes = {
            plugin_dir: {
                "bind": "/usr/local/plugins",
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
            "working_dir": "/usr/local/plugins",
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
        plugin_filename = self.plugin_path.name
        plugin_path_in_container = f"/usr/local/plugins/{plugin_filename}"

        request = {"method": method_name, **kwargs}

        try:
            self._ensure_started(plugin_path_in_container=plugin_path_in_container)
            response = self._send_and_receive_json(request)
            return self._extract_result(response)
        except SandboxError:
            raise
        except Exception as e:
            # Any unexpected error: reset the session so a retry can start fresh
            self.close()
            raise SandboxError(
                f"Rust plugin execution failed: {e}",
                details={"error": str(e), "method": method_name},
                retryable=True,
            ) from e

    def _ensure_started(self, plugin_path_in_container: str) -> None:
        """Ensure a long-lived container + rust-plugin-runner process is running."""
        if self._runner_initialized and self._container is not None and self._exec_socket:
            return

        # If we're partially initialized, reset before restarting
        self.close()

        container_config = self._build_container_config(
            command=["sleep", "infinity"],
            environment={"PLUGIN_PATH": plugin_path_in_container},
        )

        image_name = container_config.get("image", self.container_image)
        try:
            self.docker_client.images.get(image_name)
        except ImageNotFound:
            try:
                self.docker_client.images.pull(image_name)
            except Exception as pull_error:
                raise SandboxError(
                    f"Failed to pull Docker image {image_name}: {pull_error}. "
                    f"Please ensure the image is available or pull it manually with 'docker pull {image_name}'",
                    details={
                        "error": str(pull_error),
                        "image": image_name,
                        "error_type": "ImagePullError",
                    },
                    retryable=True,
                ) from pull_error

        try:
            try:
                container = self.docker_client.containers.create(**container_config)
            except ImageNotFound as image_error:
                explanation = getattr(image_error, "explanation", "")
                if explanation and "No such image:" in explanation:
                    missing_image_name = explanation.split("No such image:")[-1].strip()
                else:
                    missing_image_name = explanation if explanation else self.container_image
                raise SandboxError(
                    f"Docker image not found: {missing_image_name}. Please ensure the image is available or pull it with 'docker pull {missing_image_name}'",
                    details={
                        "error": str(image_error),
                        "image": missing_image_name,
                        "error_type": "ImageNotFound",
                    },
                    retryable=False,
                ) from image_error

            container.start()
            self._container = container

            # Start a single long-lived rust-plugin-runner process with an attached stdin/stdout.
            # The runner is explicitly designed to keep plugin state across multiple JSON lines.
            api = getattr(self.docker_client, "api", None)
            if api is None:
                raise SandboxError(
                    "Docker client does not expose low-level API needed for streaming exec",
                    details={"error_type": "DockerApiUnavailable"},
                    retryable=False,
                )

            exec_create_result = api.exec_create(
                container=self._container.id,
                cmd=["rust-plugin-runner"],
                stdin=True,
                tty=True,
            )
            exec_id = exec_create_result.get("Id")
            if not exec_id:
                raise SandboxError(
                    "Failed to create exec session for rust-plugin-runner",
                    details={"exec_create_result": exec_create_result},
                    retryable=True,
                )

            sock = api.exec_start(exec_id, socket=True, tty=True)
            # docker-py may wrap the socket; unwrap when possible
            self._exec_socket = getattr(sock, "_sock", sock)
            try:
                self._exec_socket.settimeout(self.timeout)
            except Exception:
                # Not all socket wrappers allow timeouts; ignore and rely on default behavior.
                pass

            # Initialize the runner with the plugin library path (once per container/session)
            init_response = self._send_and_receive_json({"init": plugin_path_in_container})
            if isinstance(init_response, dict) and init_response.get("status") == "error":
                raise SandboxError(
                    f"Rust plugin runner init failed: {init_response.get('error')}",
                    details={"response": init_response},
                    retryable=True,
                )
            if isinstance(init_response, dict) and init_response.get("error"):
                raise SandboxError(
                    f"Rust plugin runner init failed: {init_response.get('error')}",
                    details={"response": init_response},
                    retryable=True,
                )

            self._runner_initialized = True
        except SandboxError:
            self.close()
            raise
        except Exception as e:
            self.close()
            raise SandboxError(
                f"Failed to start Rust plugin sandbox session: {e}",
                details={"error": str(e)},
                retryable=True,
            ) from e

    def _send_and_receive_json(self, obj: Dict[str, Any]) -> Any:
        if not self._exec_socket:
            raise SandboxError(
                "Rust plugin runner is not started",
                details={"error_type": "RunnerNotStarted"},
                retryable=True,
            )

        line = json.dumps(obj, separators=(",", ":")).encode("utf-8") + b"\n"
        try:
            self._exec_socket.sendall(line)
        except Exception as e:
            raise SandboxError(
                f"Failed to send request to rust-plugin-runner: {e}",
                details={"error": str(e), "request": obj},
                retryable=True,
            ) from e

        raw_line = self._read_line()
        try:
            return json.loads(raw_line)
        except json.JSONDecodeError as e:
            raise SandboxError(
                f"Failed to parse Rust plugin response: {e}",
                details={"output": raw_line, "parse_error": str(e)},
                retryable=True,
            ) from e

    def _read_line(self) -> str:
        """Read a single '\n'-terminated line from the runner stdout."""
        if not self._exec_socket:
            raise SandboxError(
                "Rust plugin runner is not started",
                details={"error_type": "RunnerNotStarted"},
                retryable=True,
            )

        # Drain buffer if we already have a full line
        while b"\n" not in self._recv_buffer:
            chunk = self._exec_socket.recv(4096)
            if not chunk:
                raise SandboxError(
                    "Rust plugin runner closed the connection unexpectedly",
                    details={"error_type": "RunnerDisconnected"},
                    retryable=True,
                )
            self._recv_buffer += chunk

        line_bytes, _, remainder = self._recv_buffer.partition(b"\n")
        self._recv_buffer = remainder
        # With tty=True, output may contain '\r'; strip it.
        return line_bytes.decode("utf-8", errors="replace").strip("\r")

    def _extract_result(self, result_json: Any) -> Any:
        # Preserve backwards compatibility with previous parsing behavior.
        if isinstance(result_json, dict):
            # Runner convention: {"status":"error","error":"..."}
            if result_json.get("status") == "error":
                raise SandboxError(
                    f"Rust plugin execution returned error: {result_json.get('error')}",
                    details=result_json,
                    retryable=True,
                )
            if "error" in result_json and result_json.get("error"):
                raise SandboxError(
                    f"Rust plugin execution returned error: {result_json.get('error')}",
                    details=result_json,
                    retryable=True,
                )
            if "data" in result_json:
                return result_json["data"]
            if "result" in result_json:
                return result_json["result"]
        return result_json

    def check_connection(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Check connection using sandboxed Rust plugin.

        Args:
            config: Plugin configuration

        Returns:
            Connection check result
        """
        return self.execute("check_connection", config=json.dumps(config))
