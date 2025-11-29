"""Plugin system for custom readers and writers."""

import importlib.util
import inspect
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Type

from .config import SourceConfig, TargetConfig
from .exceptions import PluginError, PluginVersionError
from .validator import IncrementalStateManager

# Plugin SDK version - increment when making breaking changes
PLUGIN_SDK_VERSION = "1.0.0"


class ConnectionTestResult:
    """Result of connection testing."""

    def __init__(
        self,
        success: bool,
        message: str,
        error_code: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ):
        """Initialize connection test result.

        Args:
            success: Whether connection test succeeded
            message: Human-readable message
            error_code: Optional error code (e.g., "AUTH_FAILED", "NETWORK_ERROR")
            details: Optional additional details
        """
        self.success = success
        self.message = message
        self.error_code = error_code
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        result = {
            "success": self.success,
            "message": self.message,
        }
        if self.error_code:
            result["error_code"] = self.error_code
        if self.details:
            result["details"] = self.details
        return result


class DiscoveryResult:
    """Result of discovery operation."""

    def __init__(
        self,
        objects: List[Dict[str, Any]],
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize discovery result.

        Args:
            objects: List of available objects/tables/streams
                    Each object should have at minimum: name, type
            metadata: Optional metadata about the source
        """
        self.objects = objects
        self.metadata = metadata or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            "objects": self.objects,
            "metadata": self.metadata,
        }


class BaseReader(ABC):
    """Base class for custom data readers.

    Custom readers must inherit from this class and implement the extract method.
    The reader receives the source configuration including connection details
    and can use it to extract data from the source system.

    Example:
        class MyCustomReader(BaseReader):
            def __init__(self, source_config: SourceConfig):
                super().__init__(source_config)
                # Initialize your reader with connection details
                self.connection = self._setup_connection()

            def extract(self, state_manager: Optional[IncrementalStateManager] = None) -> Iterator[List[Dict[str, Any]]]:
                # Your custom extraction logic
                # Read from source using self.source_config.connection
                # Yield batches of records
                yield batch_records
    """

    # Plugin SDK version - should match PLUGIN_SDK_VERSION
    __version__ = "1.0.0"

    def __init__(self, source_config: SourceConfig):
        """Initialize reader with source configuration.

        Args:
            source_config: Source configuration including connection details,
                          credentials, engine options, etc.
        """
        self.source_config = source_config
        # Validate plugin version compatibility
        self._validate_version()

    def _validate_version(self) -> None:
        """Validate plugin version compatibility.

        Raises:
            PluginVersionError: If plugin version is incompatible
        """
        plugin_version = getattr(self.__class__, "__version__", None)
        if plugin_version:
            # Simple version check - can be enhanced with semantic versioning
            # For now, just check if version attribute exists
            # Future: implement proper semantic version comparison
            pass

    def check_connection(self) -> ConnectionTestResult:
        """Check connection to source system.

        This method should validate that the reader can connect to the source
        system using the provided configuration. It should NOT extract data,
        only verify connectivity and credentials.

        Returns:
            ConnectionTestResult indicating success or failure

        Example:
            def check_connection(self) -> ConnectionTestResult:
                try:
                    # Test connection
                    response = self.client.ping()
                    return ConnectionTestResult(
                        success=True,
                        message="Connection successful",
                        details={"server_version": response.version}
                    )
                except AuthenticationError as e:
                    return ConnectionTestResult(
                        success=False,
                        message=f"Authentication failed: {e}",
                        error_code="AUTH_FAILED"
                    )
                except NetworkError as e:
                    return ConnectionTestResult(
                        success=False,
                        message=f"Network error: {e}",
                        error_code="NETWORK_ERROR"
                    )
        """
        # Default implementation - plugins should override
        return ConnectionTestResult(
            success=True,
            message="Connection test not implemented",
            details={"note": "Plugin does not implement check_connection"},
        )

    def discover(self) -> DiscoveryResult:
        """Discover available objects/tables/streams.

        Override this method to implement discovery for your reader.
        This method should return a list of available objects that can be
        extracted from the source system.

        Returns:
            DiscoveryResult with list of available objects

        Example:
            def discover(self) -> DiscoveryResult:
                tables = self.client.list_tables()
                objects = []
                for table in tables:
                    objects.append({
                        "name": table.name,
                        "type": "table",
                        "description": table.description,
                        "columns": [{"name": col.name, "type": col.type} for col in table.columns]
                    })
                return DiscoveryResult(
                    objects=objects,
                    metadata={"database": "production", "schema": "public"}
                )
        """
        # Default implementation - plugins should override
        return DiscoveryResult(
            objects=[],
            metadata={"note": "Plugin does not implement discover"},
        )

    @abstractmethod
    def extract(
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from source system.

        Args:
            state_manager: Optional state manager for incremental syncs

        Yields:
            Batches of records as list of dictionaries
        """
        pass

    def get_total_records_estimate(self) -> Optional[int]:
        """Get estimated total number of records.

        Returns:
            Estimated record count or None if cannot estimate
        """
        return None


class BaseWriter(ABC):
    """Base class for custom data writers.

    Custom writers must inherit from this class and implement the write_batch method.
    The writer receives the target configuration including connection details
    and can use it to write data to the target system.

    Example:
        class MyCustomWriter(BaseWriter):
            def __init__(self, asset_definition: AssetDefinition, target_config: TargetConfig, output_base: str):
                super().__init__(asset_definition, target_config, output_base)
                # Initialize your writer with connection details
                self.connection = self._setup_connection()

            def write_batch(self, records: List[Dict[str, Any]], file_counter: int) -> List[Dict[str, Any]]:
                # Your custom writing logic
                # Write to target using self.target_config.connection
                # Return file metadata for tracking
                return [{"path": "...", "size_bytes": 1234}]

            def commit_files(self, file_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
                # Optional: Implement commit logic
                return {"status": "success", "files_added": len(file_metadata)}
    """

    # Plugin SDK version - should match PLUGIN_SDK_VERSION
    __version__ = "1.0.0"

    def __init__(
        self, asset_definition: Any, target_config: TargetConfig, output_base: str
    ):
        """Initialize writer with target configuration.

        Args:
            asset_definition: Asset definition with schema and metadata
            target_config: Target configuration including connection details,
                          catalog, file format, etc.
            output_base: Base output path for writing files
        """
        self.asset_definition = asset_definition
        self.target_config = target_config
        self.output_base = output_base
        # Validate plugin version compatibility
        self._validate_version()

    def _validate_version(self) -> None:
        """Validate plugin version compatibility.

        Raises:
            PluginVersionError: If plugin version is incompatible
        """
        plugin_version = getattr(self.__class__, "__version__", None)
        if plugin_version:
            # Simple version check - can be enhanced with semantic versioning
            # For now, just check if version attribute exists
            # Future: implement proper semantic version comparison
            pass

    def check_connection(self) -> ConnectionTestResult:
        """Check connection to target system.

        This method should validate that the writer can connect to the target
        system using the provided configuration. It should NOT write data,
        only verify connectivity and credentials.

        Returns:
            ConnectionTestResult indicating success or failure

        Example:
            def check_connection(self) -> ConnectionTestResult:
                try:
                    # Test connection (e.g., S3 bucket access)
                    self.s3_client.head_bucket(Bucket=self.bucket)
                    return ConnectionTestResult(
                        success=True,
                        message="Connection successful",
                        details={"bucket": self.bucket}
                    )
                except ClientError as e:
                    error_code = e.response['Error']['Code']
                    if error_code == '403':
                        return ConnectionTestResult(
                            success=False,
                            message="Access denied",
                            error_code="AUTH_FAILED"
                        )
                    else:
                        return ConnectionTestResult(
                            success=False,
                            message=f"Connection failed: {e}",
                            error_code="CONNECTION_FAILED"
                        )
        """
        # Default implementation - plugins should override
        return ConnectionTestResult(
            success=True,
            message="Connection test not implemented",
            details={"note": "Plugin does not implement check_connection"},
        )

    @abstractmethod
    def write_batch(
        self, records: List[Dict[str, Any]], file_counter: int
    ) -> List[Dict[str, Any]]:
        """Write a batch of records to target system.

        Args:
            records: List of validated records to write
            file_counter: Counter for generating unique file names

        Returns:
            List of file metadata dictionaries with at minimum:
                - path: File path or identifier
                - size_bytes: File size in bytes (optional)
        """
        pass

    def commit_files(self, file_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Commit files to target system (optional).

        Override this method if your writer needs to perform post-write operations
        like registering files in a catalog or finalizing transactions.

        Args:
            file_metadata: List of file metadata from write_batch calls

        Returns:
            Dictionary with commit result information
        """
        return {
            "status": "success",
            "files_added": len(file_metadata),
        }


class PluginLoader:
    """Utility for loading custom reader and writer plugins.

    Supports both Python and Rust plugins:
    - Python: "path/to/module.py:ClassName"
    - Rust: "path/to/libplugin.so:function_name" (or .dylib, .dll)
    """

    @staticmethod
    def _detect_plugin_type(plugin_path: str) -> str:
        """Detect plugin type from file extension.

        Args:
            plugin_path: Plugin path

        Returns:
            Plugin type: "python" or "rust"
        """
        module_path_str = plugin_path.split(":")[0]
        path = Path(module_path_str)

        if path.suffix == ".py":
            return "python"
        elif path.suffix in [".so", ".dylib", ".dll"]:
            return "rust"
        else:
            # Default to Python for backward compatibility
            return "python"

    @staticmethod
    def load_class_from_path(plugin_path: str, base_class: Type) -> Type:
        """Load a Python class from a file path.

        Args:
            plugin_path: Path to Python file containing the class
                        Format: "path/to/module.py:ClassName"
            base_class: Expected base class (BaseReader or BaseWriter)

        Returns:
            The loaded class

        Raises:
            ValueError: If plugin cannot be loaded or doesn't inherit from base_class
        """
        # Parse path and class name
        if ":" not in plugin_path:
            raise ValueError(
                f"Plugin path must be in format 'path/to/module.py:ClassName', got: {plugin_path}"
            )

        module_path_str, class_name = plugin_path.rsplit(":", 1)
        module_path = Path(module_path_str)

        if not module_path.exists():
            raise ValueError(f"Plugin module not found: {module_path}")

        if not module_path.is_file():
            raise ValueError(f"Plugin path is not a file: {module_path}")

        # Load module dynamically
        module_name = module_path.stem
        spec = importlib.util.spec_from_file_location(module_name, module_path)

        if spec is None or spec.loader is None:
            raise ValueError(f"Failed to load module spec from: {module_path}")

        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        # Get class from module
        if not hasattr(module, class_name):
            raise ValueError(f"Class '{class_name}' not found in module: {module_path}")

        plugin_class = getattr(module, class_name)

        # Validate class inheritance
        if not inspect.isclass(plugin_class):
            raise PluginError(
                f"{class_name} is not a class in {module_path}",
                details={"module_path": str(module_path), "class_name": class_name},
            )

        if not issubclass(plugin_class, base_class):
            raise PluginError(
                f"Plugin class {class_name} must inherit from {base_class.__name__}",
                details={
                    "module_path": str(module_path),
                    "class_name": class_name,
                    "expected_base": base_class.__name__,
                },
            )

        # Check version compatibility
        plugin_version = getattr(plugin_class, "__version__", None)
        if plugin_version:
            # Future: implement semantic version comparison
            # For now, just log version info
            pass

        return plugin_class

    @staticmethod
    def load_rust_plugin(
        plugin_path: str,
        base_class: Type,
        mode: str = "self_hosted",
        sandbox_config: Optional[Dict[str, Any]] = None,
        plugin_config: Optional[Dict[str, Any]] = None,
    ) -> Type:
        """Load a Rust plugin as a wrapper class.

        Args:
            plugin_path: Path to Rust shared library
                        Format: "path/to/libplugin.so:create_reader" or "create_writer"
            base_class: Expected base class (BaseReader or BaseWriter)
            mode: Execution mode (self_hosted or cloud)
            sandbox_config: Optional sandbox configuration dict
            plugin_config: Optional plugin configuration dict (for checking sandbox enabled)

        Returns:
            Wrapper class that uses Rust plugin (may be sandboxed wrapper)

        Raises:
            ValueError: If plugin cannot be loaded
        """
        if ":" not in plugin_path:
            raise ValueError(
                f"Rust plugin path must be in format 'path/to/libplugin.so:function_name', got: {plugin_path}"
            )

        lib_path_str, func_name = plugin_path.rsplit(":", 1)
        lib_path = Path(lib_path_str)

        # If the specified file doesn't exist, try alternative extensions
        if not lib_path.exists():
            # Try .dylib (macOS), .so (Linux), .dll (Windows)
            alternatives = []
            if lib_path.suffix == ".so":
                alternatives = [
                    lib_path.with_suffix(".dylib"),
                    lib_path.with_suffix(".dll"),
                ]
            elif lib_path.suffix == ".dylib":
                alternatives = [
                    lib_path.with_suffix(".so"),
                    lib_path.with_suffix(".dll"),
                ]
            elif lib_path.suffix == ".dll":
                alternatives = [
                    lib_path.with_suffix(".so"),
                    lib_path.with_suffix(".dylib"),
                ]
            else:
                # No extension or unknown extension, try all
                alternatives = [
                    lib_path.with_suffix(".so"),
                    lib_path.with_suffix(".dylib"),
                    lib_path.with_suffix(".dll"),
                ]

            # Try alternatives
            found = False
            for alt_path in alternatives:
                if alt_path.exists():
                    lib_path = alt_path
                    found = True
                    break

            if not found:
                raise ValueError(
                    f"Rust plugin library not found: {lib_path_str}\n"
                    f"Tried: {lib_path} and alternatives: {[str(a) for a in alternatives]}"
                )

        if not lib_path.is_file():
            raise ValueError(f"Rust plugin path is not a file: {lib_path}")

        # Check if sandboxing is needed (after resolving lib_path)
        from .sandbox import should_sandbox_plugin

        should_sandbox = should_sandbox_plugin(str(lib_path), mode, plugin_config)

        if should_sandbox:
            # Use sandboxed wrapper for Rust plugins
            # Create sandbox instance
            sandbox_kwargs = {}
            if sandbox_config:
                sandbox_kwargs.update(sandbox_config)

            if base_class == BaseReader:
                # Create sandboxed reader wrapper
                def create_sandboxed_rust_reader(source_config):
                    from .rust_sandboxed_wrapper import SandboxedRustReaderWrapper

                    return SandboxedRustReaderWrapper(
                        str(lib_path),
                        source_config,
                        mode,
                        sandbox_kwargs,
                    )

                create_sandboxed_rust_reader.__name__ = (
                    f"SandboxedRustReader_{lib_path.stem}"
                )
                return create_sandboxed_rust_reader
            elif base_class == BaseWriter:
                # Create sandboxed writer wrapper
                def create_sandboxed_rust_writer(
                    asset_definition, target_config, output_base
                ):
                    from .rust_sandboxed_wrapper import SandboxedRustWriterWrapper

                    return SandboxedRustWriterWrapper(
                        str(lib_path),
                        asset_definition,
                        target_config,
                        output_base,
                        mode,
                        sandbox_kwargs,
                    )

                create_sandboxed_rust_writer.__name__ = (
                    f"SandboxedRustWriter_{lib_path.stem}"
                )
                return create_sandboxed_rust_writer
            else:
                raise ValueError(
                    f"Unsupported base class for Rust plugin: {base_class}"
                )

        # No sandboxing - use existing direct loading
        # Import Rust plugin loader (optional dependency)
        try:
            from .rust_plugin_bridge import (
                create_rust_reader_wrapper,
                create_rust_writer_wrapper,
            )
        except ImportError:
            raise ImportError(
                "Rust plugin support requires additional dependencies. "
                "Install with: pip install dativo-ingest[rust]"
            )

        # Create appropriate wrapper based on base class
        if base_class == BaseReader:
            return create_rust_reader_wrapper(str(lib_path), func_name)
        elif base_class == BaseWriter:
            return create_rust_writer_wrapper(str(lib_path), func_name)
        else:
            raise ValueError(f"Unsupported base class for Rust plugin: {base_class}")

    @staticmethod
    def load_reader(
        plugin_path: str,
        mode: str = "self_hosted",
        sandbox_config: Optional[Dict[str, Any]] = None,
        plugin_config: Optional[Dict[str, Any]] = None,
    ) -> Type[BaseReader]:
        """Load a custom reader class (Python or Rust).

        Args:
            plugin_path: Path to reader plugin
                        Python: "path/to/module.py:ClassName"
                        Rust: "path/to/libplugin.so:create_reader"
            mode: Execution mode (self_hosted or cloud)
            sandbox_config: Optional sandbox configuration dict
            plugin_config: Optional plugin configuration dict (for checking sandbox enabled)

        Returns:
            Reader class inheriting from BaseReader (may be sandboxed wrapper)
        """
        from .sandbox import should_sandbox_plugin

        plugin_type = PluginLoader._detect_plugin_type(plugin_path)

        if plugin_type == "python":
            plugin_class = PluginLoader.load_class_from_path(plugin_path, BaseReader)

            # Check if sandboxing is needed
            if should_sandbox_plugin(plugin_path, mode, plugin_config):
                from .sandboxed_plugin_wrapper import SandboxedReaderWrapper

                # Return a factory function that creates sandboxed wrapper
                def create_sandboxed_reader(source_config):
                    return SandboxedReaderWrapper(
                        plugin_path, source_config, mode, sandbox_config
                    )

                # Make it look like a class for compatibility
                create_sandboxed_reader.__name__ = plugin_class.__name__
                create_sandboxed_reader.__module__ = plugin_class.__module__
                return create_sandboxed_reader
            else:
                return plugin_class
        elif plugin_type == "rust":
            # Rust sandboxing will be handled in load_rust_plugin
            return PluginLoader.load_rust_plugin(
                plugin_path, BaseReader, mode, sandbox_config, plugin_config
            )
        else:
            raise ValueError(f"Unsupported plugin type: {plugin_type}")

    @staticmethod
    def load_writer(
        plugin_path: str,
        mode: str = "self_hosted",
        sandbox_config: Optional[Dict[str, Any]] = None,
        plugin_config: Optional[Dict[str, Any]] = None,
    ) -> Type[BaseWriter]:
        """Load a custom writer class (Python or Rust).

        Args:
            plugin_path: Path to writer plugin
                        Python: "path/to/module.py:ClassName"
                        Rust: "path/to/libplugin.so:create_writer"
            mode: Execution mode (self_hosted or cloud)
            sandbox_config: Optional sandbox configuration dict
            plugin_config: Optional plugin configuration dict (for checking sandbox enabled)

        Returns:
            Writer class inheriting from BaseWriter (may be sandboxed wrapper)
        """
        from .sandbox import should_sandbox_plugin

        plugin_type = PluginLoader._detect_plugin_type(plugin_path)

        if plugin_type == "python":
            plugin_class = PluginLoader.load_class_from_path(plugin_path, BaseWriter)

            # Check if sandboxing is needed
            if should_sandbox_plugin(plugin_path, mode, plugin_config):
                from .sandboxed_plugin_wrapper import SandboxedWriterWrapper

                # Return a factory function that creates sandboxed wrapper
                def create_sandboxed_writer(
                    asset_definition, target_config, output_base
                ):
                    return SandboxedWriterWrapper(
                        plugin_path,
                        asset_definition,
                        target_config,
                        output_base,
                        mode,
                        sandbox_config,
                    )

                # Make it look like a class for compatibility
                create_sandboxed_writer.__name__ = plugin_class.__name__
                create_sandboxed_writer.__module__ = plugin_class.__module__
                return create_sandboxed_writer
            else:
                return plugin_class
        elif plugin_type == "rust":
            # Rust sandboxing will be handled in load_rust_plugin
            return PluginLoader.load_rust_plugin(
                plugin_path, BaseWriter, mode, sandbox_config, plugin_config
            )
        else:
            raise ValueError(f"Unsupported plugin type: {plugin_type}")
