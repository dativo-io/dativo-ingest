"""Wrapper classes for sandboxed plugin execution.

These wrappers intercept plugin method calls and route them through Docker sandbox
for secure execution in cloud mode.
"""

from typing import Any, Dict, Iterator, List, Optional

from .config import SourceConfig, TargetConfig
from .plugins import BaseReader, BaseWriter, ConnectionTestResult, DiscoveryResult
from .sandbox import PluginSandbox
from .validator import IncrementalStateManager


def _serialize_config(obj: Any) -> Dict[str, Any]:
    """Serialize config object to dictionary for JSON serialization.

    Args:
        obj: Config object (SourceConfig, TargetConfig, AssetDefinition, etc.)

    Returns:
        Dictionary representation
    """
    if hasattr(obj, "model_dump"):
        # Pydantic v2
        return obj.model_dump()
    elif hasattr(obj, "dict"):
        # Pydantic v1
        return obj.dict()
    elif hasattr(obj, "__dict__"):
        return obj.__dict__
    else:
        return obj


class SandboxedReaderWrapper(BaseReader):
    """Wrapper that routes reader calls through Docker sandbox.

    This wrapper maintains the same interface as BaseReader but executes
    all method calls in a Docker container for security isolation.
    """

    def __init__(
        self,
        plugin_path: str,
        source_config: SourceConfig,
        mode: str,
        sandbox_config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize sandboxed reader wrapper.

        Args:
            plugin_path: Path to plugin file
            source_config: Source configuration
            mode: Execution mode (self_hosted or cloud)
            sandbox_config: Optional sandbox configuration
        """
        # Initialize base class with source_config
        super().__init__(source_config)
        self.plugin_path = plugin_path
        self.mode = mode
        self.sandbox_config = sandbox_config or {}
        # Filter out 'enabled' field - it's used to determine whether to sandbox,
        # but not passed to PluginSandbox constructor
        sandbox_kwargs = {
            k: v for k, v in self.sandbox_config.items() if k != "enabled"
        }
        self.sandbox = PluginSandbox(plugin_path, **sandbox_kwargs)

    def check_connection(self) -> ConnectionTestResult:
        """Check connection via sandbox.

        Returns:
            ConnectionTestResult indicating success or failure
        """
        source_config_dict = _serialize_config(self.source_config)
        result = self.sandbox.execute(
            "check_connection", source_config=source_config_dict
        )

        # Convert result to ConnectionTestResult if needed
        if isinstance(result, dict):
            return ConnectionTestResult(
                success=result.get("success", False),
                message=result.get("message", ""),
                error_code=result.get("error_code"),
                details=result.get("details", {}),
            )
        elif isinstance(result, ConnectionTestResult):
            return result
        else:
            # Fallback
            return ConnectionTestResult(
                success=True,
                message=str(result),
                details={"raw_result": result},
            )

    def discover(self) -> DiscoveryResult:
        """Discover streams via sandbox.

        Returns:
            DiscoveryResult with available objects
        """
        source_config_dict = _serialize_config(self.source_config)
        result = self.sandbox.execute("discover", source_config=source_config_dict)

        # Convert result to DiscoveryResult if needed
        if isinstance(result, dict):
            return DiscoveryResult(
                objects=result.get("objects", []),
                metadata=result.get("metadata", {}),
            )
        elif isinstance(result, DiscoveryResult):
            return result
        else:
            # Fallback
            return DiscoveryResult(
                objects=[],
                metadata={"raw_result": result},
            )

    def extract(
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data via sandbox.

        For now, we use a batch approach where all batches are returned at once.
        Future enhancement: streaming via named pipes or sockets.

        Args:
            state_manager: Optional state manager for incremental syncs

        Yields:
            Batches of records
        """
        source_config_dict = _serialize_config(self.source_config)
        # Serialize state_manager if provided
        state_manager_dict = None
        if state_manager:
            # State manager might have state data we need to serialize
            if hasattr(state_manager, "state"):
                state_manager_dict = {"state": state_manager.state}
            else:
                state_manager_dict = {}

        result = self.sandbox.execute(
            "extract",
            source_config=source_config_dict,
            state_manager=state_manager_dict,
        )

        # Result should be a list of batches
        if isinstance(result, list):
            for batch in result:
                yield batch
        elif isinstance(result, dict) and "batches" in result:
            for batch in result["batches"]:
                yield batch
        else:
            # Single batch or unexpected format
            if result:
                yield result if isinstance(result, list) else [result]

    def get_total_records_estimate(self) -> Optional[int]:
        """Get estimated total number of records via sandbox.

        Returns:
            Estimated record count or None
        """
        source_config_dict = _serialize_config(self.source_config)
        result = self.sandbox.execute(
            "get_total_records_estimate", source_config=source_config_dict
        )

        if isinstance(result, int):
            return result
        elif isinstance(result, dict):
            return result.get("estimate")
        else:
            return None


class SandboxedWriterWrapper(BaseWriter):
    """Wrapper that routes writer calls through Docker sandbox.

    This wrapper maintains the same interface as BaseWriter but executes
    all method calls in a Docker container for security isolation.
    """

    def __init__(
        self,
        plugin_path: str,
        asset_definition: Any,
        target_config: TargetConfig,
        output_base: str,
        mode: str,
        sandbox_config: Optional[Dict[str, Any]] = None,
    ):
        """Initialize sandboxed writer wrapper.

        Args:
            plugin_path: Path to plugin file
            asset_definition: Asset definition
            target_config: Target configuration
            output_base: Base output path
            mode: Execution mode (self_hosted or cloud)
            sandbox_config: Optional sandbox configuration
        """
        # Initialize base class
        super().__init__(asset_definition, target_config, output_base)
        self.plugin_path = plugin_path
        self.mode = mode
        self.sandbox_config = sandbox_config or {}
        # Filter out 'enabled' field - it's used to determine whether to sandbox,
        # but not passed to PluginSandbox constructor
        sandbox_kwargs = {
            k: v for k, v in self.sandbox_config.items() if k != "enabled"
        }
        self.sandbox = PluginSandbox(plugin_path, **sandbox_kwargs)

    def check_connection(self) -> ConnectionTestResult:
        """Check connection via sandbox.

        Returns:
            ConnectionTestResult indicating success or failure
        """
        asset_dict = _serialize_config(self.asset_definition)
        target_config_dict = _serialize_config(self.target_config)
        result = self.sandbox.execute(
            "check_connection",
            asset_definition=asset_dict,
            target_config=target_config_dict,
            output_base=self.output_base,
        )

        # Convert result to ConnectionTestResult if needed
        if isinstance(result, dict):
            return ConnectionTestResult(
                success=result.get("success", False),
                message=result.get("message", ""),
                error_code=result.get("error_code"),
                details=result.get("details", {}),
            )
        elif isinstance(result, ConnectionTestResult):
            return result
        else:
            # Fallback
            return ConnectionTestResult(
                success=True,
                message=str(result),
                details={"raw_result": result},
            )

    def write_batch(
        self, records: List[Dict[str, Any]], file_counter: int
    ) -> List[Dict[str, Any]]:
        """Write batch via sandbox.

        Args:
            records: Records to write
            file_counter: File counter

        Returns:
            File metadata
        """
        asset_dict = _serialize_config(self.asset_definition)
        target_config_dict = _serialize_config(self.target_config)

        # Serialize records (handle datetime objects)
        import datetime

        serializable_records = []
        for record in records:
            serializable_record = {}
            for key, value in record.items():
                if isinstance(value, datetime.datetime):
                    serializable_record[key] = value.isoformat()
                elif isinstance(value, datetime.date):
                    serializable_record[key] = datetime.datetime.combine(
                        value, datetime.time.min
                    ).isoformat()
                else:
                    serializable_record[key] = value
            serializable_records.append(serializable_record)

        result = self.sandbox.execute(
            "write_batch",
            asset_definition=asset_dict,
            target_config=target_config_dict,
            output_base=self.output_base,
            records=serializable_records,
            file_counter=file_counter,
        )

        # Result should be a list of file metadata
        if isinstance(result, list):
            return result
        elif isinstance(result, dict) and "files" in result:
            return result["files"]
        else:
            # Single file or unexpected format
            return [result] if result else []

    def commit_files(self, file_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Commit files via sandbox.

        Args:
            file_metadata: List of file metadata from write_batch calls

        Returns:
            Dictionary with commit result information
        """
        asset_dict = _serialize_config(self.asset_definition)
        target_config_dict = _serialize_config(self.target_config)

        result = self.sandbox.execute(
            "commit_files",
            asset_definition=asset_dict,
            target_config=target_config_dict,
            output_base=self.output_base,
            file_metadata=file_metadata,
        )

        # Result should be a dictionary
        if isinstance(result, dict):
            return result
        else:
            # Fallback
            return {"status": "success", "result": result}
