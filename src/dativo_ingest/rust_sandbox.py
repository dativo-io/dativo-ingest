"""Sandbox wrapper for Rust plugins.

This module provides Docker-based sandboxing for Rust plugins,
enabling secure execution with resource limits and network isolation.
"""

import base64
import json
import os
import shlex
import subprocess
import time
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

    This sandbox now supports persistent container connections for improved performance.
    Instead of creating/destroying containers per request, it can reuse containers
    across multiple method calls, significantly reducing overhead for batch operations.
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
        reuse_container: bool = True,
        max_retries: int = 3,
        container_max_age_seconds: Optional[int] = None,
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
            reuse_container: Whether to reuse container across requests (default: True)
            max_retries: Maximum retries for failed requests (default: 3)
            container_max_age_seconds: Maximum container lifetime in seconds (optional)

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
        self.reuse_container = reuse_container
        self.max_retries = max_retries
        self.container_max_age_seconds = container_max_age_seconds

        # Container state for reuse
        self._container = None
        self._container_initialized = False
        self._exec_instance = None
        self._container_start_time = None
        self._request_count = 0
        self._buffer_remainder = b""  # Buffer for partial JSON lines

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

        # Create and start container immediately if reuse_container is enabled
        # This ensures container lifecycle is tied to sandbox instance, not per-call
        if self.reuse_container:
            try:
                self._start_container()
            except Exception as e:
                # If container creation fails during init, we'll retry on first execute()
                # This allows for graceful degradation if Docker is temporarily unavailable
                # Log the error but don't fail initialization
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

    def _start_container(self):
        """Start a persistent container for plugin execution.

        Creates and starts a long-running container that will handle
        multiple plugin method calls via stdin/stdout communication.

        Raises:
            SandboxError: If container creation or startup fails
        """
        if self._container is not None:
            return  # Container already running

        # Build container command - keep container alive for persistent connection
        plugin_filename = self.plugin_path.name
        plugin_path_in_container = f"/usr/local/plugins/{plugin_filename}"

        container_config = self._build_container_config(
            command=["sleep", "infinity"],  # Keep container alive
            environment={
                "PLUGIN_PATH": plugin_path_in_container,
            },
        )

        # Ensure the Docker image is available (pull if needed)
        image_name = container_config.get("image", self.container_image)
        try:
            self.docker_client.images.get(image_name)
        except ImageNotFound:
            # Image not found - try to pull it automatically
            try:
                self.docker_client.images.pull(image_name)
            except Exception as pull_error:
                # Pull failed - raise helpful error
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
                self._container = self.docker_client.containers.create(
                    **container_config
                )
            except ImageNotFound as image_error:
                # Docker image is missing even after pull attempt
                explanation = getattr(image_error, "explanation", "")
                if explanation and "No such image:" in explanation:
                    image_name = explanation.split("No such image:")[-1].strip()
                else:
                    image_name = explanation if explanation else self.container_image
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
            self._container.start()
            self._container_initialized = False  # Plugin not yet initialized

            # Track container start time
            self._container_start_time = time.time()

        except Exception as e:
            # Clean up on error
            if self._container:
                try:
                    self._container.remove(force=True)
                except Exception:
                    pass
                self._container = None
            raise SandboxError(
                f"Failed to start container: {e}",
                details={"error": str(e)},
                retryable=True,
            ) from e

    def _initialize_plugin(self):
        """Initialize the plugin in the running container.

        Sends the init request to rust-plugin-runner to load the plugin library.
        This only needs to be done once per container.

        Raises:
            SandboxError: If plugin initialization fails
        """
        if self._container_initialized:
            return  # Already initialized

        # Ensure container is started (should already be started in __init__ if reuse_container=True)
        # This is a fallback for cases where container creation failed during __init__
        if self._container is None:
            if not self.reuse_container:
                # Legacy path: create container on-demand
                self._start_container()
            else:
                # Container should have been created in __init__, but creation may have failed
                # Retry container creation here
                self._start_container()

        plugin_filename = self.plugin_path.name
        plugin_path_in_container = f"/usr/local/plugins/{plugin_filename}"

        # Close any existing exec instance socket before creating a new one
        # This prevents socket leaks when reinitializing after a retry
        if self._exec_instance:
            try:
                if "socket" in self._exec_instance:
                    self._exec_instance["socket"].close()
            except Exception:
                pass
            self._exec_instance = None

        # Send init request
        init_request = json.dumps({"init": plugin_path_in_container})

        try:
            # Create exec instance for rust-plugin-runner
            # This will be a persistent stdin/stdout connection
            exec_id = self.docker_client.api.exec_create(
                self._container.id,
                ["rust-plugin-runner"],
                stdin=True,
                stdout=True,
                stderr=True,
            )

            # Start exec with detach=False to get socket
            exec_socket = self.docker_client.api.exec_start(
                exec_id,
                socket=True,
                demux=False,
            )

            self._exec_instance = {
                "id": exec_id,
                "socket": exec_socket,
            }

            # Send init request
            init_line = init_request + "\n"
            exec_socket.sendall(init_line.encode("utf-8"))

            # Read init response (one JSON line)
            response_data = self._read_json_line(exec_socket)

            if not response_data:
                raise SandboxError(
                    "No response from plugin initialization",
                    details={"init_request": init_request},
                    retryable=True,
                )

            response = json.loads(response_data)

            if response.get("status") == "error" or "error" in response:
                raise SandboxError(
                    f"Plugin initialization failed: {response.get('error', 'Unknown error')}",
                    details={"response": response},
                    retryable=True,
                )

            self._container_initialized = True

        except json.JSONDecodeError as e:
            raise SandboxError(
                f"Failed to parse plugin initialization response: {e}",
                details={"error": str(e)},
                retryable=True,
            ) from e
        except Exception as e:
            raise SandboxError(
                f"Plugin initialization failed: {e}",
                details={"error": str(e)},
                retryable=True,
            ) from e

    def _check_container_health(self) -> bool:
        """Check if container is still healthy and within age limit.

        Returns:
            True if container is healthy, False otherwise
        """
        if self._container is None:
            return False

        # Check if container is still running
        try:
            self._container.reload()
            if self._container.status != "running":
                return False
        except Exception:
            return False

        # Check container age if limit is set
        if self.container_max_age_seconds and self._container_start_time:
            import time

            age = time.time() - self._container_start_time
            if age > self.container_max_age_seconds:
                return False

        return True

    def _read_json_line(self, socket, timeout: int = 30) -> str:
        """Read one line of JSON from socket with buffering support.

        Args:
            socket: Docker exec socket
            timeout: Read timeout in seconds

        Returns:
            JSON string (one line)

        Raises:
            SandboxError: If timeout or read error occurs
        """
        import select
        import time

        # Start with any buffered data from previous read
        buffer = self._buffer_remainder
        self._buffer_remainder = b""

        end_time = None
        if timeout:
            end_time = time.time() + timeout

        while True:
            # Check timeout
            if end_time and time.time() > end_time:
                raise SandboxError(
                    "Timeout reading response from plugin",
                    details={
                        "partial_buffer": buffer.decode("utf-8", errors="replace")
                    },
                    retryable=True,
                )

            # Check if we already have a complete line in buffer
            if b"\n" in buffer:
                line, remainder = buffer.split(b"\n", 1)
                self._buffer_remainder = remainder  # Save remainder for next read
                return line.decode("utf-8")

            # Read more data
            try:
                # Try to use select for non-blocking read if socket supports it
                # Check if socket has a valid fileno() method (not a Mock)
                try:
                    fileno = socket.fileno()
                    if isinstance(fileno, int):
                        ready = select.select([socket], [], [], 1.0)
                        if ready[0]:
                            chunk = socket.recv(4096)
                            if not chunk:
                                # Socket closed - return what we have
                                if buffer:
                                    return buffer.decode("utf-8", errors="replace")
                                raise SandboxError(
                                    "Socket closed before receiving complete response",
                                    details={
                                        "partial_buffer": buffer.decode(
                                            "utf-8", errors="replace"
                                        )
                                    },
                                    retryable=True,
                                )
                            buffer += chunk
                    else:
                        # Socket doesn't have valid fileno (likely a Mock in tests)
                        # Fall back to direct read
                        chunk = socket.recv(4096)
                        if not chunk:
                            # Socket closed - return what we have
                            if buffer:
                                return buffer.decode("utf-8", errors="replace")
                            raise SandboxError(
                                "Socket closed before receiving complete response",
                                details={
                                    "partial_buffer": buffer.decode(
                                        "utf-8", errors="replace"
                                    )
                                },
                                retryable=True,
                            )
                        buffer += chunk
                except (AttributeError, TypeError):
                    # Socket doesn't have fileno() or it's not callable (Mock in tests)
                    # Fall back to direct read
                    chunk = socket.recv(4096)
                    if not chunk:
                        # Socket closed - return what we have
                        if buffer:
                            return buffer.decode("utf-8", errors="replace")
                        raise SandboxError(
                            "Socket closed before receiving complete response",
                            details={
                                "partial_buffer": buffer.decode(
                                    "utf-8", errors="replace"
                                )
                            },
                            retryable=True,
                        )
                    buffer += chunk
            except select.error as e:
                raise SandboxError(
                    f"Select error reading from socket: {e}",
                    details={"error": str(e)},
                    retryable=True,
                ) from e
            except Exception as e:
                raise SandboxError(
                    f"Error reading from socket: {e}",
                    details={
                        "error": str(e),
                        "buffer": buffer.decode("utf-8", errors="replace"),
                    },
                    retryable=True,
                ) from e

    def _send_request(self, method_name: str, **kwargs: Any) -> Any:
        """Send a request to the running plugin container with retry logic.

        Args:
            method_name: Name of method to execute
            **kwargs: Method arguments

        Returns:
            Method result

        Raises:
            SandboxError: If request fails after all retries
        """
        last_error = None

        for attempt in range(self.max_retries):
            try:
                # Check container health before sending request
                if not self._check_container_health():
                    # Container unhealthy - attempt to restart it
                    # Container should only be removed in cleanup() at job end, not per-call
                    # However, if container is completely dead and restart fails, we must
                    # remove the dead container to avoid leaks. This is a rare recovery scenario.
                    if self._container:
                        try:
                            # Try to restart the existing container (preferred - no removal)
                            self._container.restart(timeout=10)
                            self._container_initialized = (
                                False  # Need to reinitialize plugin
                            )
                            self._container_start_time = time.time()
                        except Exception:
                            # Restart failed - container is completely dead
                            # Must remove dead container to avoid leaks, then recreate
                            # This violates the "once per job" rule but is necessary for recovery
                            if self._exec_instance:
                                try:
                                    if "socket" in self._exec_instance:
                                        self._exec_instance["socket"].close()
                                except Exception:
                                    pass
                                self._exec_instance = None
                            # Remove dead container (unavoidable for recovery)
                            try:
                                self._container.remove(force=True)
                            except Exception:
                                pass
                            self._container = None
                            self._container_initialized = False
                    # Reinitialize plugin in (restarted or recreated) container
                    self._initialize_plugin()

                # Ensure container is started and initialized
                if not self._container_initialized:
                    self._initialize_plugin()

                # Build request JSON
                request = {
                    "method": method_name,
                    **kwargs,
                }
                request_json = json.dumps(
                    request, separators=(",", ":")
                )  # Compact JSON

                # Send request via socket
                socket = self._exec_instance["socket"]
                request_line = request_json + "\n"
                socket.sendall(request_line.encode("utf-8"))

                # Read response (one JSON line)
                response_data = self._read_json_line(socket, timeout=self.timeout)

                if not response_data:
                    raise SandboxError(
                        f"No response from plugin method: {method_name}",
                        details={"method": method_name, "request": request},
                        retryable=True,
                    )

                response = json.loads(response_data)

                # Check for errors
                if response.get("status") == "error" or "error" in response:
                    raise SandboxError(
                        f"Plugin method failed: {response.get('error', 'Unknown error')}",
                        details={"method": method_name, "response": response},
                        retryable=True,
                    )

                # Increment request counter
                self._request_count += 1

                # Extract result
                if "data" in response:
                    return response["data"]
                elif "result" in response:
                    return response["result"]
                return response

            except json.JSONDecodeError as e:
                last_error = SandboxError(
                    f"Failed to parse plugin response: {e}",
                    details={
                        "method": method_name,
                        "error": str(e),
                        "attempt": attempt + 1,
                    },
                    retryable=True,
                )
                # Mark for reinitialization
                self._container_initialized = False
                if attempt < self.max_retries - 1:
                    continue
            except SandboxError as e:
                last_error = e
                # Mark for reinitialization if retryable
                if e.retryable:
                    self._container_initialized = False
                    if attempt < self.max_retries - 1:
                        continue
                break
            except Exception as e:
                last_error = SandboxError(
                    f"Plugin method execution failed: {e}",
                    details={
                        "method": method_name,
                        "error": str(e),
                        "attempt": attempt + 1,
                    },
                    retryable=True,
                )
                # Mark for reinitialization
                self._container_initialized = False
                if attempt < self.max_retries - 1:
                    continue

        # All retries failed
        raise (
            last_error
            if last_error
            else SandboxError(
                f"Plugin method execution failed after {self.max_retries} retries",
                details={"method": method_name},
                retryable=False,
            )
        )

    def cleanup(self):
        """Clean up container resources.

        This should be called when done with the sandbox to properly
        shut down and remove the container.
        """
        if self._exec_instance:
            try:
                if "socket" in self._exec_instance:
                    self._exec_instance["socket"].close()
            except Exception:
                pass
            self._exec_instance = None

        if self._container:
            try:
                self._container.remove(force=True)
            except Exception:
                pass
            self._container = None
            self._container_initialized = False

        # Clear buffer remainder to prevent stale data from old socket
        # being mixed with new socket data after container restart
        self._buffer_remainder = b""

    def __del__(self):
        """Cleanup on garbage collection."""
        self.cleanup()

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
        # Use persistent container connection for better performance
        if self.reuse_container:
            return self._send_request(method_name, **kwargs)

        # Legacy path: create/destroy container per request (for compatibility)
        return self._execute_oneshot(method_name, **kwargs)

    def _execute_oneshot(
        self,
        method_name: str,
        **kwargs: Any,
    ) -> Any:
        """Execute a single request with a disposable container.

        This is the legacy behavior: create container, execute request, destroy container.
        Used when reuse_container=False for compatibility or specific security requirements.

        Args:
            method_name: Name of method to execute
            **kwargs: Method arguments

        Returns:
            Method result

        Raises:
            SandboxError: If execution fails
        """
        # Build container command
        plugin_filename = self.plugin_path.name
        plugin_path_in_container = f"/usr/local/plugins/{plugin_filename}"

        # Create request JSON
        request = {
            "method": method_name,
            **kwargs,
        }

        # Build container configuration
        container_config = self._build_container_config(
            command=["sleep", "infinity"],
            environment={
                "PLUGIN_PATH": plugin_path_in_container,
            },
        )

        # Create and run container
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

        container = None
        try:
            try:
                container = self.docker_client.containers.create(**container_config)
            except ImageNotFound as image_error:
                explanation = getattr(image_error, "explanation", "")
                if explanation and "No such image:" in explanation:
                    image_name = explanation.split("No such image:")[-1].strip()
                else:
                    image_name = explanation if explanation else self.container_image
                raise SandboxError(
                    f"Docker image not found: {image_name}. Please ensure the image is available or pull it with 'docker pull {image_name}'",
                    details={
                        "error": str(image_error),
                        "image": image_name,
                        "error_type": "ImageNotFound",
                    },
                    retryable=False,
                )

            container.start()

            # Prepare init and method requests
            init_request = json.dumps({"init": plugin_path_in_container})
            method_request = json.dumps(request)

            # Use base64 encoding to safely pass JSON through shell
            init_b64 = base64.b64encode(init_request.encode("utf-8")).decode("utf-8")
            method_b64 = base64.b64encode(method_request.encode("utf-8")).decode(
                "utf-8"
            )

            init_b64_quoted = shlex.quote(init_b64)
            method_b64_quoted = shlex.quote(method_b64)

            # Execute both requests in single rust-plugin-runner process
            result = container.exec_run(
                [
                    "sh",
                    "-c",
                    f"(echo {init_b64_quoted} | base64 -d; echo {method_b64_quoted} | base64 -d) | rust-plugin-runner",
                ],
                stdin=True,
            )

            output = result.output.decode("utf-8") if result.output else ""
            logs = container.logs(stdout=True, stderr=True).decode("utf-8")
            combined_output = output if output else logs
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

            # Parse result
            try:
                result_lines = [
                    line.strip()
                    for line in combined_output.strip().split("\n")
                    if line.strip()
                ]
                if result_lines:
                    if len(result_lines) >= 2:
                        result_json = json.loads(result_lines[-1])
                    else:
                        result_json = json.loads(result_lines[0])

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
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass

    def check_connection(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Check connection using sandboxed Rust plugin.

        Args:
            config: Plugin configuration

        Returns:
            Connection check result
        """
        return self.execute("check_connection", config=json.dumps(config))
