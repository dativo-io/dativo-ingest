"""Bridge for loading Rust plugins via ctypes/PyO3.

This module provides Python wrappers for Rust-based readers and writers,
enabling high-performance data processing while maintaining the same interface
as Python plugins.

Rust plugins must be compiled as shared libraries (.so, .dylib, .dll) and
expose C-compatible functions that can be called via ctypes or use PyO3
for native Python bindings.
"""

import ctypes
import json
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Type

from .plugins import BaseReader, BaseWriter


class RustReaderWrapper(BaseReader):
    """Wrapper class that bridges Python to Rust reader implementations.
    
    This wrapper handles:
    - Loading Rust shared library
    - Converting Python objects to JSON for Rust consumption
    - Converting JSON from Rust back to Python objects
    - Managing memory and lifecycle
    """
    
    def __init__(self, source_config, lib_path: str, func_name: str):
        """Initialize Rust reader wrapper.
        
        Args:
            source_config: Source configuration
            lib_path: Path to Rust shared library
            func_name: Name of reader creation function
        """
        super().__init__(source_config)
        self.lib_path = lib_path
        self.func_name = func_name
        
        # Load shared library
        self._lib = ctypes.CDLL(lib_path)
        
        # Set up function signatures
        self._setup_functions()
        
        # Initialize Rust reader
        config_json = self._serialize_config()
        self._reader_ptr = self._create_reader(config_json)
    
    def _setup_functions(self):
        """Set up ctypes function signatures for Rust library."""
        # create_reader(config_json: *const c_char) -> *mut Reader
        create_func = getattr(self._lib, self.func_name)
        create_func.argtypes = [ctypes.c_char_p]
        create_func.restype = ctypes.c_void_p
        self._create_reader = create_func
        
        # extract_batch(reader: *mut Reader) -> *const c_char (JSON)
        extract_func = getattr(self._lib, "extract_batch", None)
        if extract_func:
            extract_func.argtypes = [ctypes.c_void_p]
            extract_func.restype = ctypes.c_char_p
            self._extract_batch = extract_func
        
        # free_reader(reader: *mut Reader)
        free_func = getattr(self._lib, "free_reader", None)
        if free_func:
            free_func.argtypes = [ctypes.c_void_p]
            free_func.restype = None
            self._free_reader = free_func
        
        # free_string(s: *const c_char)
        free_str_func = getattr(self._lib, "free_string", None)
        if free_str_func:
            free_str_func.argtypes = [ctypes.c_char_p]
            free_str_func.restype = None
            self._free_string = free_str_func
    
    def _serialize_config(self) -> bytes:
        """Serialize source config to JSON for Rust.
        
        Returns:
            JSON bytes
        """
        config_dict = {
            "type": self.source_config.type,
            "connection": self.source_config.connection or {},
            "credentials": self.source_config.credentials or {},
            "objects": self.source_config.objects or [],
            "files": self.source_config.files or [],
            "incremental": self.source_config.incremental or {},
            "engine": self.source_config.engine or {},
        }
        return json.dumps(config_dict).encode("utf-8")
    
    def extract(
        self, state_manager: Optional[Any] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data using Rust reader.
        
        Args:
            state_manager: Optional state manager (not used in Rust plugins yet)
        
        Yields:
            Batches of records
        """
        while True:
            # Call Rust extract_batch function
            result_json = self._extract_batch(self._reader_ptr)
            
            if not result_json:
                break
            
            # Parse JSON result
            result_str = result_json.decode("utf-8")
            
            # Free the string in Rust
            if hasattr(self, "_free_string"):
                self._free_string(result_json)
            
            # Parse and yield batch
            batch = json.loads(result_str)
            
            if not batch:
                break
            
            yield batch
    
    def __del__(self):
        """Clean up Rust resources."""
        if hasattr(self, "_reader_ptr") and hasattr(self, "_free_reader"):
            self._free_reader(self._reader_ptr)


class RustWriterWrapper(BaseWriter):
    """Wrapper class that bridges Python to Rust writer implementations.
    
    This wrapper handles:
    - Loading Rust shared library
    - Converting Python objects to JSON for Rust consumption
    - Converting JSON from Rust back to Python objects
    - Managing memory and lifecycle
    """
    
    def __init__(self, asset_definition, target_config, output_base: str, 
                 lib_path: str, func_name: str):
        """Initialize Rust writer wrapper.
        
        Args:
            asset_definition: Asset definition
            target_config: Target configuration
            output_base: Base output path
            lib_path: Path to Rust shared library
            func_name: Name of writer creation function
        """
        super().__init__(asset_definition, target_config, output_base)
        self.lib_path = lib_path
        self.func_name = func_name
        
        # Load shared library
        self._lib = ctypes.CDLL(lib_path)
        
        # Set up function signatures
        self._setup_functions()
        
        # Initialize Rust writer
        config_json = self._serialize_config()
        self._writer_ptr = self._create_writer(config_json)
    
    def _setup_functions(self):
        """Set up ctypes function signatures for Rust library."""
        # create_writer(config_json: *const c_char) -> *mut Writer
        create_func = getattr(self._lib, self.func_name)
        create_func.argtypes = [ctypes.c_char_p]
        create_func.restype = ctypes.c_void_p
        self._create_writer = create_func
        
        # write_batch(writer: *mut Writer, records_json: *const c_char) -> *const c_char
        write_func = getattr(self._lib, "write_batch", None)
        if write_func:
            write_func.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
            write_func.restype = ctypes.c_char_p
            self._write_batch_rust = write_func
        
        # free_writer(writer: *mut Writer)
        free_func = getattr(self._lib, "free_writer", None)
        if free_func:
            free_func.argtypes = [ctypes.c_void_p]
            free_func.restype = None
            self._free_writer = free_func
        
        # free_string(s: *const c_char)
        free_str_func = getattr(self._lib, "free_string", None)
        if free_str_func:
            free_str_func.argtypes = [ctypes.c_char_p]
            free_str_func.restype = None
            self._free_string = free_str_func
    
    def _serialize_config(self) -> bytes:
        """Serialize config to JSON for Rust.
        
        Returns:
            JSON bytes
        """
        # Serialize schema
        schema = []
        if hasattr(self.asset_definition, "schema"):
            schema = self.asset_definition.schema
        
        config_dict = {
            "asset_name": self.asset_definition.name,
            "schema": schema,
            "output_base": self.output_base,
            "target_type": self.target_config.type,
            "connection": self.target_config.connection or {},
            "file_format": self.target_config.file_format,
            "engine": self.target_config.engine or {},
        }
        return json.dumps(config_dict).encode("utf-8")
    
    def write_batch(
        self, records: List[Dict[str, Any]], file_counter: int
    ) -> List[Dict[str, Any]]:
        """Write batch using Rust writer.
        
        Args:
            records: Records to write
            file_counter: File counter
        
        Returns:
            File metadata
        """
        # Serialize records and counter
        input_dict = {
            "records": records,
            "file_counter": file_counter,
        }
        input_json = json.dumps(input_dict).encode("utf-8")
        
        # Call Rust write_batch function
        result_json = self._write_batch_rust(self._writer_ptr, input_json)
        
        if not result_json:
            return []
        
        # Parse JSON result
        result_str = result_json.decode("utf-8")
        
        # Free the string in Rust
        if hasattr(self, "_free_string"):
            self._free_string(result_json)
        
        # Parse and return metadata
        metadata = json.loads(result_str)
        return metadata
    
    def __del__(self):
        """Clean up Rust resources."""
        if hasattr(self, "_writer_ptr") and hasattr(self, "_free_writer"):
            self._free_writer(self._writer_ptr)


def create_rust_reader_wrapper(lib_path: str, func_name: str) -> Type[BaseReader]:
    """Create a Rust reader wrapper class.
    
    Args:
        lib_path: Path to Rust shared library
        func_name: Name of reader creation function
    
    Returns:
        Reader wrapper class
    """
    class DynamicRustReader(RustReaderWrapper):
        def __init__(self, source_config):
            super().__init__(source_config, lib_path, func_name)
    
    return DynamicRustReader


def create_rust_writer_wrapper(lib_path: str, func_name: str) -> Type[BaseWriter]:
    """Create a Rust writer wrapper class.
    
    Args:
        lib_path: Path to Rust shared library
        func_name: Name of writer creation function
    
    Returns:
        Writer wrapper class
    """
    class DynamicRustWriter(RustWriterWrapper):
        def __init__(self, asset_definition, target_config, output_base):
            super().__init__(asset_definition, target_config, output_base, lib_path, func_name)
    
    return DynamicRustWriter
