"""Plugin system for custom readers and writers."""

import importlib.util
import inspect
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Type

from .config import SourceConfig, TargetConfig
from .validator import IncrementalStateManager


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
    
    def __init__(self, source_config: SourceConfig):
        """Initialize reader with source configuration.
        
        Args:
            source_config: Source configuration including connection details,
                          credentials, engine options, etc.
        """
        self.source_config = source_config
    
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
    
    def __init__(self, asset_definition: Any, target_config: TargetConfig, output_base: str):
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
    """Utility for loading custom reader and writer plugins."""
    
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
            raise ValueError(
                f"Class '{class_name}' not found in module: {module_path}"
            )
        
        plugin_class = getattr(module, class_name)
        
        # Validate class inheritance
        if not inspect.isclass(plugin_class):
            raise ValueError(
                f"{class_name} is not a class in {module_path}"
            )
        
        if not issubclass(plugin_class, base_class):
            raise ValueError(
                f"Plugin class {class_name} must inherit from {base_class.__name__}"
            )
        
        return plugin_class
    
    @staticmethod
    def load_reader(plugin_path: str) -> Type[BaseReader]:
        """Load a custom reader class.
        
        Args:
            plugin_path: Path to reader class (format: "path/to/module.py:ClassName")
        
        Returns:
            Reader class inheriting from BaseReader
        """
        return PluginLoader.load_class_from_path(plugin_path, BaseReader)
    
    @staticmethod
    def load_writer(plugin_path: str) -> Type[BaseWriter]:
        """Load a custom writer class.
        
        Args:
            plugin_path: Path to writer class (format: "path/to/module.py:ClassName")
        
        Returns:
            Writer class inheriting from BaseWriter
        """
        return PluginLoader.load_class_from_path(plugin_path, BaseWriter)
