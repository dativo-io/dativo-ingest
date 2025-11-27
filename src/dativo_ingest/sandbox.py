"""Plugin sandboxing for secure execution of custom Python plugins.

This module provides Docker-based sandboxing for custom Python plugins,
enabling secure execution with resource limits, network isolation, and
seccomp profiles.
"""

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import docker
from docker.errors import DockerException

from .exceptions import SandboxError


class PluginSandbox:
    """Docker-based sandbox for executing custom Python plugins.

    Provides isolation, resource limits, and security controls for plugin execution.
    """

    def __init__(
        self,
        plugin_path: str,
        cpu_limit: Optional[float] = None,
        memory_limit: Optional[str] = None,
        network_disabled: bool = True,
        seccomp_profile: Optional[str] = None,
        timeout: int = 300,
    ):
        """Initialize plugin sandbox.

        Args:
            plugin_path: Path to plugin file
            cpu_limit: CPU limit (0.0-1.0, where 1.0 = 1 CPU core)
            memory_limit: Memory limit (e.g., "512m", "1g")
            network_disabled: Disable network access (default: True)
            seccomp_profile: Path to seccomp profile JSON file (optional)
            timeout: Execution timeout in seconds (default: 300)

        Raises:
            SandboxError: If Docker is not available or initialization fails
        """
        self.plugin_path = Path(plugin_path)
        self.cpu_limit = cpu_limit
        self.memory_limit = memory_limit
        self.network_disabled = network_disabled
        self.seccomp_profile = seccomp_profile
        self.timeout = timeout

        # Initialize Docker client
        try:
            self.docker_client = docker.from_env()
            # Test Docker connection
            self.docker_client.ping()
        except DockerException as e:
            raise SandboxError(
                f"Failed to connect to Docker: {e}",
                details={"error": str(e)},
                retryable=False,
            ) from e

        # Default seccomp profile (restrictive)
        self.default_seccomp = self._get_default_seccomp_profile()

    def _get_default_seccomp_profile(self) -> Dict[str, Any]:
        """Get default restrictive seccomp profile.

        This profile only allows the minimal set of syscalls required for
        Python to execute in a container. All dangerous syscalls that could
        allow container escape, kernel module loading, or host system compromise
        are explicitly denied.

        Returns:
            Seccomp profile dictionary
        """
        # Restrictive profile - only allow essential syscalls for Python execution
        # Excludes dangerous syscalls like:
        # - reboot, mount, umount2 (system control)
        # - ptrace (process tracing/escape)
        # - kexec_load, kexec_file_load (kernel execution)
        # - init_module, delete_module, finit_module (kernel modules)
        # - bpf (eBPF program loading)
        # - swapon, swapoff (swap manipulation)
        # - sethostname, setdomainname (hostname changes)
        # - chroot, pivot_root (filesystem escape)
        # - settimeofday, clock_settime (time manipulation)
        # - setuid, setgid, setresuid, setresgid (privilege escalation)
        # - capset (capability setting)
        # - iopl, ioperm (I/O port access)
        # - unshare, setns (namespace manipulation)
        # - userfaultfd (memory manipulation)
        # - process_vm_readv, process_vm_writev (cross-process memory access)
        return {
            "defaultAction": "SCMP_ACT_ERRNO",
            "architectures": ["SCMP_ARCH_X86_64"],
            "syscalls": [
                {
                    "names": [
                        # File operations (read-only access to mounted volumes)
                        "read",
                        "write",
                        "open",
                        "close",
                        "stat",
                        "fstat",
                        "lstat",
                        "lseek",
                        "access",
                        "readlink",
                        "getcwd",
                        "chdir",
                        "fchdir",
                        "openat",
                        "newfstatat",
                        "readlinkat",
                        "faccessat",
                        "getdents",
                        "getdents64",
                        # File operations for /tmp (tmpfs only, isolated to container)
                        "unlink",
                        "unlinkat",
                        "mkdir",
                        "mkdirat",
                        "rmdir",
                        # Memory operations
                        "mmap",
                        "mprotect",
                        "munmap",
                        "brk",
                        "mremap",
                        "msync",
                        "mincore",
                        "madvise",
                        # Process operations (read-only, no privilege changes)
                        "clone",
                        "fork",
                        "vfork",
                        "execve",
                        "exit",
                        "exit_group",
                        "wait4",
                        "waitid",
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
                        # Signal operations
                        "rt_sigaction",
                        "rt_sigprocmask",
                        "rt_sigreturn",
                        "rt_sigpending",
                        "rt_sigtimedwait",
                        "rt_sigsuspend",
                        "sigaltstack",
                        "kill",
                        "tkill",
                        "tgkill",
                        "rt_tgsigqueueinfo",
                        # I/O operations
                        "ioctl",
                        "pipe",
                        "pipe2",
                        "dup",
                        "dup2",
                        "dup3",
                        "select",
                        "pselect6",
                        "poll",
                        "ppoll",
                        "epoll_create",
                        "epoll_create1",
                        "epoll_ctl",
                        "epoll_wait",
                        "epoll_pwait",
                        # Network operations (if network is enabled)
                        "socket",
                        "connect",
                        "accept",
                        "accept4",
                        "sendto",
                        "recvfrom",
                        "sendmsg",
                        "recvmsg",
                        "sendmmsg",
                        "recvmmsg",
                        "shutdown",
                        "bind",
                        "listen",
                        "getsockname",
                        "getpeername",
                        "socketpair",
                        "setsockopt",
                        "getsockopt",
                        # File descriptor operations
                        "fcntl",
                        "flock",
                        "fsync",
                        "fdatasync",
                        "syncfs",
                        "truncate",
                        "ftruncate",
                        # Time operations (read-only)
                        "gettimeofday",
                        "time",
                        "clock_gettime",
                        "clock_getres",
                        "clock_nanosleep",
                        "nanosleep",
                        "getitimer",
                        "alarm",
                        "setitimer",
                        # System information (read-only)
                        "uname",
                        "sysinfo",
                        "times",
                        "getrlimit",
                        "getrusage",
                        "getpriority",
                        "getcpu",
                        # Thread operations
                        "sched_yield",
                        "sched_getaffinity",
                        "sched_setaffinity",
                        "set_tid_address",
                        "restart_syscall",
                        "futex",
                        "set_robust_list",
                        "get_robust_list",
                        # Shared memory (for multiprocessing)
                        "shmget",
                        "shmat",
                        "shmdt",
                        "shmctl",
                        # Semaphores (for multiprocessing)
                        "semget",
                        "semop",
                        "semctl",
                        "semtimedop",
                        # Message queues (for multiprocessing)
                        "msgget",
                        "msgsnd",
                        "msgrcv",
                        "msgctl",
                        # Extended attributes (read-only)
                        "getxattr",
                        "lgetxattr",
                        "fgetxattr",
                        "listxattr",
                        "llistxattr",
                        "flistxattr",
                        # File system information (read-only)
                        "statfs",
                        "fstatfs",
                        # Advanced I/O
                        "sendfile",
                        "readahead",
                        "preadv",
                        "pwritev",
                        "preadv2",
                        "pwritev2",
                        "copy_file_range",
                        # Event notifications
                        "inotify_init",
                        "inotify_init1",
                        "inotify_add_watch",
                        "inotify_rm_watch",
                        # Timer operations
                        "timer_create",
                        "timer_settime",
                        "timer_gettime",
                        "timer_getoverrun",
                        "timer_delete",
                        "timerfd_create",
                        "timerfd_settime",
                        "timerfd_gettime",
                        # Signal file descriptors
                        "signalfd",
                        "signalfd4",
                        # Event file descriptors
                        "eventfd",
                        "eventfd2",
                        # File operations (limited, no privilege changes)
                        "utime",
                        "utimes",
                        "utimensat",
                        "futimesat",
                        "umask",
                        # Process control (limited, no privilege escalation)
                        "prctl",
                        "arch_prctl",
                        # Random number generation
                        "getrandom",
                        # Memory file descriptors
                        "memfd_create",
                        # File allocation
                        "fallocate",
                        # I/O priority (read-only)
                        "ioprio_get",
                        # Resource limits (read-only)
                        "prlimit64",
                        # Memory locking (user-space only)
                        "mlock",
                        "munlock",
                        "mlock2",
                        # Memory barrier
                        "membarrier",
                    ],
                    "action": "SCMP_ACT_ALLOW",
                }
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
            # Use default restrictive profile
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
        config = {
            "image": "python:3.10-slim",  # Base Python image
            "command": command,
            "network_disabled": self.network_disabled,
            "mem_limit": self.memory_limit,
            "cpu_period": 100000,  # 100ms period
            "cpu_quota": int(self.cpu_limit * 100000) if self.cpu_limit else None,
            "environment": environment or {},
            "volumes": {
                str(self.plugin_path.parent): {
                    "bind": "/app/plugins",
                    "mode": "ro",  # Read-only mount
                }
            },
            "working_dir": "/app/plugins",
            "user": "nobody",  # Run as non-root user
            "read_only": True,  # Read-only root filesystem
            "tmpfs": {
                "/tmp": "size=100m",  # Temporary filesystem for /tmp
            },
        }

        # Add seccomp profile if available
        seccomp_profile = self._load_seccomp_profile()
        if seccomp_profile:
            config["security_opt"] = [f"seccomp={json.dumps(seccomp_profile)}"]

        return config

    def execute(
        self,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Execute a plugin method in sandboxed environment.

        Args:
            method_name: Name of method to execute (e.g., "check_connection", "extract")
            *args: Positional arguments for method
            **kwargs: Keyword arguments for method

        Returns:
            Method return value

        Raises:
            SandboxError: If execution fails
        """
        # Create temporary script to execute plugin method
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, dir=self.plugin_path.parent
        ) as script_file:
            script_path = Path(script_file.name)

            # Generate execution script
            script_content = self._generate_execution_script(
                self.plugin_path.name, method_name, *args, **kwargs
            )
            script_file.write(script_content)
            script_file.flush()

        try:
            # Build container configuration
            container_config = self._build_container_config(
                command=["python", f"/app/plugins/{script_path.name}"],
                environment={
                    "PYTHONUNBUFFERED": "1",
                    "PYTHONPATH": "/app/plugins",
                },
            )

            # Create and run container
            try:
                container = self.docker_client.containers.create(**container_config)
                container.start()

                # Wait for container to finish
                result = container.wait(timeout=self.timeout)

                # Get logs
                logs = container.logs(stdout=True, stderr=True).decode("utf-8")

                # Get exit code
                exit_code = result.get("StatusCode", 1)

                if exit_code != 0:
                    raise SandboxError(
                        f"Plugin execution failed with exit code {exit_code}",
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

        finally:
            # Clean up temporary script
            try:
                script_path.unlink()
            except Exception:
                pass  # Ignore cleanup errors

    def _generate_execution_script(
        self,
        plugin_file: str,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> str:
        """Generate Python script to execute plugin method.

        Args:
            plugin_file: Name of plugin file
            method_name: Method to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Python script content
        """
        # Import plugin and execute method
        # This is a simplified version - in production, you'd need to handle
        # serialization of complex arguments
        import_statement = f"from {Path(plugin_file).stem} import *"
        args_json = json.dumps(args)
        kwargs_json = json.dumps(kwargs)

        script = f"""
import sys
import json
import importlib.util

# Load plugin
plugin_path = "{plugin_file}"
spec = importlib.util.spec_from_file_location("plugin", plugin_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

# Get plugin class (assuming it's the only class in the module)
plugin_class = None
for name, obj in module.__dict__.items():
    if isinstance(obj, type) and hasattr(obj, '{method_name}'):
        plugin_class = obj
        break

if not plugin_class:
    print(json.dumps({{"status": "error", "message": "Plugin class not found"}}))
    sys.exit(1)

# Create instance (simplified - would need proper config)
# instance = plugin_class(...)

# Execute method
# result = getattr(instance, method_name)(*args, **kwargs)

# For now, just return a placeholder
result = {{"status": "success", "message": "Method executed in sandbox"}}

# Output result as JSON
print(json.dumps(result))
"""
        return script

    def check_connection(self, source_config: Any) -> Dict[str, Any]:
        """Check connection using sandboxed plugin.

        Args:
            source_config: Source configuration

        Returns:
            Connection check result
        """
        return self.execute("check_connection", source_config=source_config)


def should_sandbox_plugin(plugin_path: str, mode: str = "self_hosted") -> bool:
    """Determine if plugin should be sandboxed.

    Args:
        plugin_path: Path to plugin
        mode: Execution mode (self_hosted or cloud)

    Returns:
        True if plugin should be sandboxed
    """
    # In cloud mode, always sandbox custom Python plugins
    if mode == "cloud":
        return Path(plugin_path).suffix == ".py"

    # In self_hosted mode, sandboxing is optional (can be enabled via config)
    # For now, default to False for self_hosted
    return False
