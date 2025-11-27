# Plugin Development Guide

This guide explains how to develop custom plugins for the Dativo ingestion platform, including both local and cloud execution.

## Table of Contents

1. [Overview](#overview)
2. [Plugin Types](#plugin-types)
3. [Python Plugins](#python-plugins)
4. [Rust Plugins](#rust-plugins)
5. [Cloud Execution](#cloud-execution)
6. [Testing Plugins](#testing-plugins)
7. [Best Practices](#best-practices)

## Overview

Dativo supports custom plugins for both data readers (sources) and writers (targets). Plugins can be written in:
- **Python**: Easy development, great for API integrations
- **Rust**: High performance, compiled to shared libraries

Plugins can run:
- **Locally**: In the same process as the main application
- **In the Cloud**: AWS Lambda or GCP Cloud Functions for isolation and scalability

## Plugin Types

### Reader Plugins (BaseReader)

Reader plugins extract data from sources:
- API endpoints
- Custom file formats
- Proprietary systems
- Legacy databases

**Required Methods:**
- `extract()`: Yield batches of records

**Optional Methods:**
- `check_connection()`: Test connectivity
- `discover()`: List available objects
- `get_total_records_estimate()`: Provide record count

### Writer Plugins (BaseWriter)

Writer plugins write data to targets:
- Custom file formats
- Proprietary systems
- Specialized databases
- Custom APIs

**Required Methods:**
- `write_batch()`: Write a batch of records

**Optional Methods:**
- `check_connection()`: Test connectivity
- `commit_files()`: Finalize write operations

## Python Plugins

### Basic Reader Example

```python
"""Custom reader plugin for JSON APIs."""

from typing import Any, Dict, Iterator, List, Optional
from dativo_ingest.plugins import BaseReader, ConnectionTestResult, DiscoveryResult
from dativo_ingest.validator import IncrementalStateManager

class MyCustomReader(BaseReader):
    """Custom reader for my data source."""
    
    __version__ = "1.0.0"
    
    def __init__(self, source_config):
        """Initialize reader with source configuration."""
        super().__init__(source_config)
        
        # Extract configuration
        self.base_url = source_config.connection.get("base_url")
        self.api_key = source_config.credentials.get("api_key")
        
        # Initialize your client
        self.client = self._setup_client()
    
    def _setup_client(self):
        """Set up API client."""
        # Your client setup code
        return MyAPIClient(self.base_url, self.api_key)
    
    def check_connection(self) -> ConnectionTestResult:
        """Test connection to data source."""
        try:
            # Test connection
            self.client.ping()
            return ConnectionTestResult(
                success=True,
                message="Connection successful"
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                message=f"Connection failed: {str(e)}",
                error_code="CONNECTION_ERROR"
            )
    
    def discover(self) -> DiscoveryResult:
        """Discover available objects."""
        try:
            # List available objects
            objects = self.client.list_objects()
            
            discovered = [
                {
                    "name": obj.name,
                    "type": "table",
                    "description": obj.description
                }
                for obj in objects
            ]
            
            return DiscoveryResult(
                objects=discovered,
                metadata={"api_version": "v1"}
            )
        except Exception as e:
            return DiscoveryResult(objects=[], metadata={"error": str(e)})
    
    def extract(
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from source."""
        # Get objects to extract
        objects = self.source_config.objects or []
        
        for obj_name in objects:
            # Extract data for each object
            for page in self._extract_pages(obj_name):
                yield page
    
    def _extract_pages(self, object_name: str) -> Iterator[List[Dict[str, Any]]]:
        """Extract pages for an object."""
        page = 1
        while True:
            # Fetch page
            records = self.client.get_page(object_name, page)
            
            if not records:
                break
            
            yield records
            page += 1
    
    def get_total_records_estimate(self) -> Optional[int]:
        """Get estimated total records."""
        try:
            return self.client.get_count()
        except:
            return None
```

### Basic Writer Example

```python
"""Custom writer plugin for JSON files."""

from typing import Any, Dict, List
from dativo_ingest.plugins import BaseWriter, ConnectionTestResult
import json
from pathlib import Path

class MyCustomWriter(BaseWriter):
    """Custom writer for my data target."""
    
    __version__ = "1.0.0"
    
    def __init__(self, asset_definition, target_config, output_base: str):
        """Initialize writer with target configuration."""
        super().__init__(asset_definition, target_config, output_base)
        
        # Extract configuration
        self.format = target_config.engine.get("options", {}).get("format", "jsonl")
        self.output_dir = Path(output_base)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def check_connection(self) -> ConnectionTestResult:
        """Test connection to target."""
        try:
            # Test write access
            test_file = self.output_dir / ".test"
            test_file.write_text("test")
            test_file.unlink()
            
            return ConnectionTestResult(
                success=True,
                message="Target accessible"
            )
        except Exception as e:
            return ConnectionTestResult(
                success=False,
                message=f"Target not accessible: {str(e)}",
                error_code="ACCESS_ERROR"
            )
    
    def write_batch(
        self, records: List[Dict[str, Any]], file_counter: int
    ) -> List[Dict[str, Any]]:
        """Write batch of records."""
        # Generate filename
        filename = f"{self.asset_definition.name}_{file_counter:06d}.json"
        filepath = self.output_dir / filename
        
        # Write records
        with open(filepath, "w") as f:
            if self.format == "jsonl":
                for record in records:
                    f.write(json.dumps(record) + "\n")
            else:
                json.dump(records, f, indent=2)
        
        # Return file metadata
        return [{
            "path": str(filepath),
            "size_bytes": filepath.stat().st_size,
            "record_count": len(records)
        }]
    
    def commit_files(self, file_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Commit written files."""
        return {
            "status": "success",
            "files_added": len(file_metadata),
            "total_records": sum(m.get("record_count", 0) for m in file_metadata)
        }
```

### Using the Plugin

Create a job configuration:

```yaml
source:
  custom_reader: "plugins/my_reader.py:MyCustomReader"
  connection:
    base_url: "https://api.example.com"
  credentials:
    api_key: "${API_KEY}"
  objects: ["users", "orders"]

target:
  custom_writer: "plugins/my_writer.py:MyCustomWriter"
  engine:
    options:
      format: "jsonl"
```

## Rust Plugins

### Setting Up Rust Environment

```bash
# Create new library project
cargo new --lib my_plugin

# Edit Cargo.toml
```

**Cargo.toml:**
```toml
[package]
name = "my_plugin"
version = "0.1.0"
edition = "2021"

[lib]
crate-type = ["cdylib"]

[dependencies]
serde = { version = "1.0", features = ["derive"] }
serde_json = "1.0"
libc = "0.2"
```

### Basic Reader Example

```rust
use libc::{c_char, c_void};
use serde::{Deserialize, Serialize};
use std::ffi::{CStr, CString};

#[derive(Deserialize)]
struct Config {
    connection: serde_json::Value,
    credentials: serde_json::Value,
    objects: Vec<String>,
}

pub struct Reader {
    config: Config,
    current_batch: usize,
}

#[no_mangle]
pub extern "C" fn create_reader(config_json: *const c_char) -> *mut Reader {
    let config_str = unsafe {
        CStr::from_ptr(config_json).to_str().unwrap()
    };
    
    let config: Config = serde_json::from_str(config_str).unwrap();
    
    let reader = Reader {
        config,
        current_batch: 0,
    };
    
    Box::into_raw(Box::new(reader))
}

#[no_mangle]
pub extern "C" fn extract_batch(reader: *mut Reader) -> *const c_char {
    let reader = unsafe { &mut *reader };
    
    // Extract data
    let records = vec![
        serde_json::json!({"id": 1, "name": "Record 1"}),
        serde_json::json!({"id": 2, "name": "Record 2"}),
    ];
    
    let result = serde_json::to_string(&records).unwrap();
    CString::new(result).unwrap().into_raw()
}

#[no_mangle]
pub extern "C" fn free_reader(reader: *mut Reader) {
    if !reader.is_null() {
        unsafe {
            drop(Box::from_raw(reader));
        }
    }
}

#[no_mangle]
pub extern "C" fn free_string(s: *mut c_char) {
    if !s.is_null() {
        unsafe {
            drop(CString::from_raw(s));
        }
    }
}
```

### Building Rust Plugin

```bash
# Build release version
cargo build --release

# Library will be at target/release/libmy_plugin.so (Linux)
# or target/release/libmy_plugin.dylib (macOS)
```

### Using Rust Plugin

```yaml
source:
  custom_reader: "rust/target/release/libmy_plugin.so:create_reader"
  connection:
    path: "/data/input"
  objects: ["data"]
```

## Cloud Execution

### When to Use Cloud Execution

Use cloud execution when you need:
- **Isolation**: Separate plugin execution from main process
- **Scalability**: Handle variable workloads
- **Resource Control**: Limit memory and timeout per plugin
- **Cost Optimization**: Pay only for execution time

### AWS Lambda Configuration

```yaml
source:
  custom_reader: "plugins/my_reader.py:MyCustomReader"
  engine:
    cloud_execution:
      enabled: true
      provider: "aws"
      runtime: "python3.11"
      memory_mb: 512
      timeout_seconds: 300
      aws:
        role_arn: "arn:aws:iam::account:role/lambda-role"
        security_groups: ["sg-xxx"]
        subnets: ["subnet-xxx"]
      environment_variables:
        LOG_LEVEL: "INFO"
```

### GCP Cloud Functions Configuration

```yaml
source:
  custom_reader: "plugins/my_reader.py:MyCustomReader"
  engine:
    cloud_execution:
      enabled: true
      provider: "gcp"
      runtime: "python311"
      memory_mb: 512
      timeout_seconds: 300
      gcp:
        project_id: "my-project"
        region: "us-central1"
        service_account: "plugin@my-project.iam.gserviceaccount.com"
      environment_variables:
        LOG_LEVEL: "INFO"
```

**Note**: Cloud execution works for both Python and Rust plugins. See [cloud_plugin_execution.md](cloud_plugin_execution.md) for detailed documentation.

## Testing Plugins

### Local Testing

Create a test script:

```python
"""Test script for custom plugin."""

from dativo_ingest.config import SourceConfig
from plugins.my_reader import MyCustomReader

# Create test configuration
source_config = SourceConfig(
    type="custom",
    connection={"base_url": "https://api.example.com"},
    credentials={"api_key": "test_key"},
    objects=["users"]
)

# Initialize reader
reader = MyCustomReader(source_config)

# Test connection
result = reader.check_connection()
print(f"Connection test: {result.to_dict()}")

# Test discovery
discovery = reader.discover()
print(f"Discovered objects: {discovery.to_dict()}")

# Test extraction
for batch_idx, batch in enumerate(reader.extract()):
    print(f"Batch {batch_idx}: {len(batch)} records")
    if batch:
        print(f"Sample: {batch[0]}")
```

### Unit Testing

```python
"""Unit tests for custom plugin."""

import pytest
from plugins.my_reader import MyCustomReader
from dativo_ingest.config import SourceConfig

@pytest.fixture
def source_config():
    return SourceConfig(
        type="custom",
        connection={"base_url": "https://api.example.com"},
        credentials={"api_key": "test_key"},
        objects=["users"]
    )

@pytest.fixture
def reader(source_config):
    return MyCustomReader(source_config)

def test_check_connection(reader):
    """Test connection check."""
    result = reader.check_connection()
    assert result.success

def test_discover(reader):
    """Test discovery."""
    result = reader.discover()
    assert len(result.objects) > 0

def test_extract(reader):
    """Test data extraction."""
    batches = list(reader.extract())
    assert len(batches) > 0
    assert len(batches[0]) > 0
```

## Best Practices

### 1. Error Handling

```python
def extract(self, state_manager=None):
    """Extract with proper error handling."""
    try:
        # Your extraction logic
        yield records
    except ConnectionError as e:
        # Handle retryable errors
        raise RuntimeError(f"Connection failed: {e}")
    except Exception as e:
        # Handle non-retryable errors
        raise ValueError(f"Extraction failed: {e}")
```

### 2. Logging

```python
import logging

logger = logging.getLogger(__name__)

def extract(self, state_manager=None):
    """Extract with logging."""
    logger.info("Starting extraction")
    
    for page in self._extract_pages():
        logger.debug(f"Extracted page with {len(page)} records")
        yield page
    
    logger.info("Extraction complete")
```

### 3. Configuration Validation

```python
def __init__(self, source_config):
    """Initialize with validation."""
    super().__init__(source_config)
    
    # Validate required configuration
    if not source_config.connection.get("base_url"):
        raise ValueError("base_url is required in connection config")
    
    if not source_config.credentials.get("api_key"):
        raise ValueError("api_key is required in credentials")
```

### 4. Batch Size

```python
def extract(self, state_manager=None):
    """Extract with optimal batch size."""
    BATCH_SIZE = 1000  # Adjust based on your data
    
    batch = []
    for record in self._fetch_records():
        batch.append(record)
        
        if len(batch) >= BATCH_SIZE:
            yield batch
            batch = []
    
    # Yield remaining records
    if batch:
        yield batch
```

### 5. Memory Management

```python
def extract(self, state_manager=None):
    """Extract with memory management."""
    # Process in chunks to avoid memory issues
    for chunk in self._fetch_chunks():
        # Process chunk
        records = self._process_chunk(chunk)
        yield records
        
        # Clear references
        del chunk
        del records
```

### 6. Testing Connection

```python
def check_connection(self):
    """Comprehensive connection test."""
    try:
        # Test basic connectivity
        response = self.client.ping()
        
        # Test authentication
        self.client.list_objects()
        
        return ConnectionTestResult(
            success=True,
            message="Connection successful",
            details={
                "server_version": response.version,
                "authenticated": True
            }
        )
    except AuthenticationError as e:
        return ConnectionTestResult(
            success=False,
            message=f"Authentication failed: {e}",
            error_code="AUTH_FAILED"
        )
    except Exception as e:
        return ConnectionTestResult(
            success=False,
            message=f"Connection failed: {e}",
            error_code="CONNECTION_ERROR"
        )
```

## Next Steps

- Review [example plugins](../examples/plugins/)
- Learn about [cloud execution](cloud_plugin_execution.md)
- See [custom plugin job examples](../examples/jobs/)
- Test your plugin locally before deploying

## Support

For questions or issues:
1. Check example plugins
2. Review this documentation
3. Open an issue on GitHub
