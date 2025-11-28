"""Wrapper classes for sandboxed Rust plugin execution.

These wrappers intercept Rust plugin method calls and route them through Docker sandbox
for secure execution in cloud mode.
"""

from typing import Any, Dict, Iterator, List, Optional

from .config import SourceConfig, TargetConfig
from .plugins import BaseReader, BaseWriter, ConnectionTestResult, DiscoveryResult
from .rust_sandbox import RustPluginSandbox
from .validator import IncrementalStateManager


class SandboxedRustReaderWrapper(BaseReader):
    """Wrapper that routes Rust reader calls through Docker sandbox."""

    def __init__(
        self,
        plugin_path: str,
        source_config: SourceConfig,
        mode: str,
        sandbox_config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize sandboxed Rust reader wrapper."""
        super().__init__(source_config)
        self.plugin_path = plugin_path
        self.mode = mode
        self.sandbox_config = sandbox_config or {}
        # Filter out 'enabled' field - it's used to determine whether to sandbox,
        # but not passed to RustPluginSandbox constructor
        sandbox_kwargs = {
            k: v for k, v in self.sandbox_config.items() if k != "enabled"
        }
        self.sandbox = RustPluginSandbox(plugin_path, **sandbox_kwargs)

    def check_connection(self) -> ConnectionTestResult:
        """Check connection via sandbox."""
        source_config_dict = {
            "type": self.source_config.type,
            "connection": self.source_config.connection or {},
            "credentials": self.source_config.credentials or {},
        }
        result = self.sandbox.check_connection(source_config_dict)

        if isinstance(result, dict):
            return ConnectionTestResult(
                success=result.get("success", False),
                message=result.get("message", ""),
                error_code=result.get("error_code"),
                details=result.get("details", {}),
            )
        return ConnectionTestResult(success=True, message=str(result))

    def discover(self) -> DiscoveryResult:
        """Discover streams via sandbox."""
        # TODO: Implement discover for Rust plugins
        return DiscoveryResult(objects=[], metadata={})

    def extract(
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data via sandbox."""
        # TODO: Implement extract for Rust plugins
        yield []


class SandboxedRustWriterWrapper(BaseWriter):
    """Wrapper that routes Rust writer calls through Docker sandbox."""

    def __init__(
        self,
        plugin_path: str,
        asset_definition: Any,
        target_config: TargetConfig,
        output_base: str,
        mode: str,
        sandbox_config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize sandboxed Rust writer wrapper."""
        super().__init__(asset_definition, target_config, output_base)
        self.plugin_path = plugin_path
        self.mode = mode
        self.sandbox_config = sandbox_config or {}
        # Filter out 'enabled' field - it's used to determine whether to sandbox,
        # but not passed to RustPluginSandbox constructor
        sandbox_kwargs = {
            k: v for k, v in self.sandbox_config.items() if k != "enabled"
        }
        self.sandbox = RustPluginSandbox(plugin_path, **sandbox_kwargs)

    def check_connection(self) -> ConnectionTestResult:
        """Check connection via sandbox."""
        # TODO: Implement check_connection for Rust writers
        return ConnectionTestResult(success=True, message="OK")

    def write_batch(
        self, records: List[Dict[str, Any]], file_counter: int
    ) -> List[Dict[str, Any]]:
        """Write batch via sandbox."""
        # TODO: Implement write_batch for Rust plugins
        return []

    def commit_files(self, file_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Commit files via sandbox."""
        # TODO: Implement commit_files for Rust plugins
        return {"status": "success"}
