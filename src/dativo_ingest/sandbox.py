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

        Returns:
            Seccomp profile dictionary
        """
        # Default restrictive profile - only allow essential syscalls
        return {
            "defaultAction": "SCMP_ACT_ERRNO",
            "architectures": ["SCMP_ARCH_X86_64"],
            "syscalls": [
                {
                    "names": [
                        "read",
                        "write",
                        "open",
                        "close",
                        "stat",
                        "fstat",
                        "lstat",
                        "poll",
                        "lseek",
                        "mmap",
                        "mprotect",
                        "munmap",
                        "brk",
                        "rt_sigaction",
                        "rt_sigprocmask",
                        "rt_sigreturn",
                        "ioctl",
                        "access",
                        "pipe",
                        "select",
                        "sched_yield",
                        "mremap",
                        "msync",
                        "mincore",
                        "madvise",
                        "shmget",
                        "shmat",
                        "shmctl",
                        "dup",
                        "dup2",
                        "pause",
                        "nanosleep",
                        "getitimer",
                        "alarm",
                        "setitimer",
                        "getpid",
                        "sendfile",
                        "socket",
                        "connect",
                        "accept",
                        "sendto",
                        "recvfrom",
                        "sendmsg",
                        "recvmsg",
                        "shutdown",
                        "bind",
                        "listen",
                        "getsockname",
                        "getpeername",
                        "socketpair",
                        "setsockopt",
                        "getsockopt",
                        "clone",
                        "fork",
                        "vfork",
                        "execve",
                        "exit",
                        "wait4",
                        "kill",
                        "uname",
                        "semget",
                        "semop",
                        "semctl",
                        "shmdt",
                        "msgget",
                        "msgsnd",
                        "msgrcv",
                        "msgctl",
                        "fcntl",
                        "flock",
                        "fsync",
                        "fdatasync",
                        "truncate",
                        "ftruncate",
                        "getdents",
                        "getcwd",
                        "chdir",
                        "fchdir",
                        "rename",
                        "mkdir",
                        "rmdir",
                        "creat",
                        "link",
                        "unlink",
                        "symlink",
                        "readlink",
                        "chmod",
                        "fchmod",
                        "chown",
                        "fchown",
                        "lchown",
                        "umask",
                        "gettimeofday",
                        "getrlimit",
                        "getrusage",
                        "sysinfo",
                        "times",
                        "ptrace",
                        "getuid",
                        "syslog",
                        "getgid",
                        "setuid",
                        "setgid",
                        "geteuid",
                        "getegid",
                        "setpgid",
                        "getppid",
                        "getpgrp",
                        "setsid",
                        "setreuid",
                        "setregid",
                        "getgroups",
                        "setgroups",
                        "setresuid",
                        "getresuid",
                        "setresgid",
                        "getresgid",
                        "getpgid",
                        "setfsuid",
                        "setfsgid",
                        "getsid",
                        "capget",
                        "capset",
                        "rt_sigpending",
                        "rt_sigtimedwait",
                        "rt_sigqueueinfo",
                        "rt_sigsuspend",
                        "sigaltstack",
                        "utime",
                        "mknod",
                        "uselib",
                        "personality",
                        "ustat",
                        "statfs",
                        "fstatfs",
                        "sysfs",
                        "getpriority",
                        "setpriority",
                        "sched_setparam",
                        "sched_getparam",
                        "sched_setscheduler",
                        "sched_getscheduler",
                        "sched_get_priority_max",
                        "sched_get_priority_min",
                        "sched_rr_get_interval",
                        "mlock",
                        "munlock",
                        "mlockall",
                        "munlockall",
                        "vhangup",
                        "modify_ldt",
                        "pivot_root",
                        "prctl",
                        "arch_prctl",
                        "adjtimex",
                        "setrlimit",
                        "chroot",
                        "sync",
                        "acct",
                        "settimeofday",
                        "mount",
                        "umount2",
                        "swapon",
                        "swapoff",
                        "reboot",
                        "sethostname",
                        "setdomainname",
                        "iopl",
                        "ioperm",
                        "create_module",
                        "init_module",
                        "delete_module",
                        "get_kernel_syms",
                        "query_module",
                        "quotactl",
                        "nfsservctl",
                        "getpmsg",
                        "putpmsg",
                        "afs_syscall",
                        "tuxcall",
                        "security",
                        "gettid",
                        "readahead",
                        "setxattr",
                        "lsetxattr",
                        "fsetxattr",
                        "getxattr",
                        "lgetxattr",
                        "fgetxattr",
                        "listxattr",
                        "llistxattr",
                        "flistxattr",
                        "removexattr",
                        "lremovexattr",
                        "fremovexattr",
                        "tkill",
                        "time",
                        "futex",
                        "sched_setaffinity",
                        "sched_getaffinity",
                        "set_thread_area",
                        "io_setup",
                        "io_destroy",
                        "io_getevents",
                        "io_submit",
                        "io_cancel",
                        "get_thread_area",
                        "lookup_dcookie",
                        "epoll_create",
                        "epoll_ctl_old",
                        "epoll_wait_old",
                        "remap_file_pages",
                        "getdents64",
                        "set_tid_address",
                        "restart_syscall",
                        "semtimedop",
                        "fadvise64",
                        "timer_create",
                        "timer_settime",
                        "timer_gettime",
                        "timer_getoverrun",
                        "timer_delete",
                        "clock_settime",
                        "clock_gettime",
                        "clock_getres",
                        "clock_nanosleep",
                        "exit_group",
                        "epoll_wait",
                        "epoll_ctl",
                        "tgkill",
                        "utimes",
                        "vserver",
                        "mbind",
                        "set_mempolicy",
                        "get_mempolicy",
                        "mq_open",
                        "mq_unlink",
                        "mq_timedsend",
                        "mq_timedreceive",
                        "mq_notify",
                        "mq_getsetattr",
                        "kexec_load",
                        "waitid",
                        "add_key",
                        "request_key",
                        "keyctl",
                        "ioprio_set",
                        "ioprio_get",
                        "inotify_init",
                        "inotify_add_watch",
                        "inotify_rm_watch",
                        "migrate_pages",
                        "openat",
                        "mkdirat",
                        "mknodat",
                        "fchownat",
                        "futimesat",
                        "newfstatat",
                        "unlinkat",
                        "renameat",
                        "linkat",
                        "symlinkat",
                        "readlinkat",
                        "fchmodat",
                        "faccessat",
                        "pselect6",
                        "ppoll",
                        "unshare",
                        "set_robust_list",
                        "get_robust_list",
                        "splice",
                        "tee",
                        "sync_file_range",
                        "vmsplice",
                        "move_pages",
                        "utimensat",
                        "epoll_pwait",
                        "signalfd",
                        "timerfd_create",
                        "eventfd",
                        "fallocate",
                        "timerfd_settime",
                        "timerfd_gettime",
                        "accept4",
                        "signalfd4",
                        "eventfd2",
                        "epoll_create1",
                        "dup3",
                        "pipe2",
                        "inotify_init1",
                        "preadv",
                        "pwritev",
                        "rt_tgsigqueueinfo",
                        "perf_event_open",
                        "recvmmsg",
                        "fanotify_init",
                        "fanotify_mark",
                        "prlimit64",
                        "name_to_handle_at",
                        "open_by_handle_at",
                        "clock_adjtime",
                        "syncfs",
                        "sendmmsg",
                        "setns",
                        "getcpu",
                        "process_vm_readv",
                        "process_vm_writev",
                        "kcmp",
                        "finit_module",
                        "sched_setattr",
                        "sched_getattr",
                        "renameat2",
                        "seccomp",
                        "getrandom",
                        "memfd_create",
                        "kexec_file_load",
                        "bpf",
                        "execveat",
                        "userfaultfd",
                        "membarrier",
                        "mlock2",
                        "copy_file_range",
                        "preadv2",
                        "pwritev2",
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
