"""Wrapper classes for sandboxed Rust plugin execution.

These wrappers intercept Rust plugin method calls and route them through Docker sandbox
for secure execution in cloud mode.
"""

import json
from typing import Any, Dict, Iterator, List, Optional

from .config import SourceConfig, TargetConfig
from .exceptions import SandboxError
from .plugins import BaseReader, BaseWriter, ConnectionTestResult, DiscoveryResult
from .rust_sandbox import RustPluginSandbox
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
        """Discover streams via sandbox.

        Returns:
            DiscoveryResult with available objects

        Raises:
            SandboxError: If execution fails
        """
        source_config_dict = _serialize_config(self.source_config)
        result = self.sandbox.execute("discover", config=json.dumps(source_config_dict))

        # Check for errors
        if isinstance(result, dict) and "error" in result:
            raise SandboxError(
                f"Discover failed: {result.get('error', 'Unknown error')}",
                details=result,
                retryable=True,
            )

        # Convert result to DiscoveryResult if needed
        if isinstance(result, dict):
            # Handle response wrapped in "data" field (from plugin runner)
            if "data" in result:
                data = result["data"]
                if isinstance(data, dict):
                    return DiscoveryResult(
                        objects=data.get("objects", []),
                        metadata=data.get("metadata", {}),
                    )
                else:
                    return DiscoveryResult(
                        objects=[],
                        metadata={"raw_result": data},
                    )
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

        The extract method uses the stateful API internally:
        - Creates a reader with the source config
        - Loops calling extract_batch until all data is extracted
        - Returns all batches as a list

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

        # Call extract - the plugin should handle initialization internally
        # or return all batches in a single response
        config_json = json.dumps(source_config_dict)
        request_kwargs = {"config": config_json}
        if state_manager_dict:
            request_kwargs["state_manager"] = state_manager_dict

        result = self.sandbox.execute("extract", **request_kwargs)

        # Check for errors
        if isinstance(result, dict) and "error" in result:
            raise SandboxError(
                f"Extract failed: {result.get('error', 'Unknown error')}",
                details=result,
                retryable=True,
            )

        # Result should be a list of batches
        if isinstance(result, list):
            for batch in result:
                yield batch
        elif isinstance(result, dict):
            if "batches" in result:
                for batch in result["batches"]:
                    yield batch
            elif "data" in result:
                # Rust plugin runner wraps result in {"data": ...}
                data = result["data"]
                if isinstance(data, list):
                    for batch in data:
                        yield batch
                else:
                    yield data if isinstance(data, list) else [data]
            else:
                # Single batch or unexpected format
                if result:
                    yield result if isinstance(result, list) else [result]
        else:
            # Single batch or unexpected format
            if result:
                yield result if isinstance(result, list) else [result]


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
        """Check connection via sandbox.

        Returns:
            ConnectionTestResult indicating success or failure
        """
        asset_dict = _serialize_config(self.asset_definition)
        target_config_dict = _serialize_config(self.target_config)
        config_dict = {
            "asset_definition": asset_dict,
            "target_config": target_config_dict,
            "output_base": self.output_base,
        }
        result = self.sandbox.execute(
            "check_connection", config=json.dumps(config_dict)
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

        # Prepare config for writer creation (if needed)
        config_dict = {
            "asset_definition": asset_dict,
            "target_config": target_config_dict,
            "output_base": self.output_base,
        }
        config_json = json.dumps(config_dict)

        # Write batch - the plugin runner will create writer if needed
        result = self.sandbox.execute(
            "write_batch",
            config=config_json,  # Pass config so writer can be created if needed
            records=serializable_records,
            file_counter=file_counter,
        )

        # Check for errors
        if isinstance(result, dict) and "error" in result:
            raise SandboxError(
                f"Write batch failed: {result.get('error', 'Unknown error')}",
                details=result,
                retryable=True,
            )

        # Result should be a list of file metadata
        if isinstance(result, list):
            return result
        elif isinstance(result, dict):
            if "data" in result:
                # Rust plugin runner wraps result in {"data": ...}
                data = result["data"]
                return data if isinstance(data, list) else [data]
            elif "files" in result:
                return result["files"]
            else:
                # Single file or unexpected format
                return [result] if result else []
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

        # Check for errors
        if isinstance(result, dict) and "error" in result:
            raise SandboxError(
                f"Commit files failed: {result.get('error', 'Unknown error')}",
                details=result,
                retryable=True,
            )

        # Result should be a dictionary
        if isinstance(result, dict):
            # Handle response wrapped in "data" field (from plugin runner)
            if "data" in result:
                return result["data"]
            return result
        else:
            # Fallback
            return {"status": "success", "result": result}
