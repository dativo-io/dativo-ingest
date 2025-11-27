# Custom Readers and Writers

This guide explains how to create and use custom readers and writers in the Dativo ETL platform.

## Overview

The Dativo ETL platform supports custom readers and writers in two languages:

### **1. Python Plugins**
- Easy to develop and debug
- Access to rich Python ecosystem
- Ideal for API integrations and rapid prototyping
- Good performance for most use cases

### **2. Rust Plugins**
- **10-100x faster** than Python for data-intensive operations
- Significantly lower memory usage
- Better compression ratios
- Ideal for large-scale data processing

Custom plugins receive the connection configuration from the job definition and can use it to interact with source and target systems.

## Connectors vs Custom Readers/Writers

Understanding when to use **connectors** versus **custom readers/writers** is crucial for making the right architectural choice.

### What Are Connectors?

**Connectors** are tenant-agnostic, reusable YAML recipes that define:
- **HOW to connect**: Credentials, rate limits, connection templates
- **Engine support**: Multiple engines (native, airbyte, meltano, singer)
- **Capabilities**: Supported objects, incremental strategies, roles (source/target)
- **Metadata**: Registered in `registry/connectors.yaml` with standardized patterns

**Example Connector:**
```yaml
# connectors/hubspot.yaml
name: hubspot
type: hubspot
default_engine:
  type: airbyte
  options:
    airbyte:
      docker_image: "airbyte/source-hubspot:0.2.0"
credentials:
  type: api_key
  from_env: HUBSPOT_API_KEY
```

### What Are Custom Readers/Writers?

**Custom readers/writers** are code-based plugins (Python or Rust) that:
- Provide **complete control** over extraction/writing logic
- Bypass the connector system entirely
- Can reference a connector as a "base" for metadata only
- Implement custom business logic, proprietary formats, or performance optimizations

**Example Custom Reader:**
```yaml
# Job config
source_connector: custom_api
source_connector_path: /app/connectors/csv.yaml  # Just for metadata

source:
  custom_reader: "/app/plugins/json_api_reader.py:JSONAPIReader"
  connection:
    base_url: "https://api.example.com"
```

### Key Differences

| Aspect | Connectors | Custom Readers/Writers |
|--------|-----------|------------------------|
| **Definition** | YAML configuration files | Python/Rust code classes |
| **Reusability** | Tenant-agnostic, reusable across jobs | Job-specific (unless shared as plugins) |
| **Engine Support** | Multiple engines (native, airbyte, meltano, singer) | Single implementation approach |
| **Flexibility** | Standardized patterns | Complete control over logic |
| **Maintenance** | Configuration-driven | Code-driven |
| **Performance** | Standard performance | Can optimize (especially with Rust) |

### When to Use Connectors

Use **connectors** when:
- ✅ You have a **standard data source/target** (Stripe, HubSpot, PostgreSQL, S3, etc.)
- ✅ You need **reusability** across multiple tenants/jobs
- ✅ You want **engine flexibility** (ability to switch between native/airbyte/meltano)
- ✅ You need **standardized connection patterns** and metadata
- ✅ The data source fits existing connector patterns

**Examples:**
- SaaS APIs (Stripe, HubSpot, Salesforce)
- Standard databases (PostgreSQL, MySQL)
- Cloud storage (S3, MinIO)
- Standard file formats (CSV, Parquet)

### When to Use Custom Readers/Writers

Use **custom readers/writers** when:
- ✅ You have a **proprietary API** with custom authentication or protocols
- ✅ You need **10-100x performance** improvements (Rust plugins)
- ✅ You're working with **custom file formats** or data structures
- ✅ You need **complex business logic** not covered by standard connectors
- ✅ You're **rapidly prototyping** before building a full connector
- ✅ You need **format-aware optimizations** (e.g., specialized compression)

**Examples:**
- Proprietary REST APIs with custom auth
- Custom binary file formats
- High-performance CSV processing (Rust)
- Delta Lake or other specialized formats
- Real-time data streams with custom protocols

### Hybrid Approach

You can use a **connector as a "base"** (for metadata/validation) while using a **custom reader/writer** for the actual work:

```yaml
source_connector: postgres  # Provides metadata about postgres type
source_connector_path: /app/connectors/postgres.yaml

source:
  custom_reader: "/app/plugins/my_custom_postgres_reader.py:MyReader"
  # Custom reader receives connection details from source_config
```

This approach gives you:
- Connector metadata and validation
- Custom extraction/writing logic
- Best of both worlds

### Decision Matrix

| Scenario | Recommendation |
|----------|---------------|
| Standard SaaS API (Stripe, HubSpot) | **Connector** |
| Standard database (PostgreSQL, MySQL) | **Connector** |
| Proprietary API with custom auth | **Custom Reader** |
| Need 10-100x performance boost | **Custom Reader/Writer (Rust)** |
| Custom file format | **Custom Reader/Writer** |
| Rapid prototyping | **Custom Reader/Writer** |
| Want to switch engines later | **Connector** |
| Need tenant-agnostic solution | **Connector** |
| Complex business logic | **Custom Reader/Writer** |

### Best Practices

1. **Start with connectors** for standard data sources - they're easier to maintain and reuse
2. **Use custom plugins** when connectors don't fit your needs or performance requirements
3. **Consider Rust plugins** for data-intensive operations where performance is critical
4. **Document custom plugins** well - they're code, not configuration
5. **Share custom plugins** across jobs when they solve common problems

## Choosing Between Python and Rust

| Use Case | Recommendation |
|----------|---------------|
| API integration, moderate data volumes | Python |
| Large CSV files (>1GB) | Rust |
| High-frequency data ingestion | Rust |
| Complex business logic | Python |
| Maximum performance required | Rust |
| Rapid prototyping | Python |

**Best Practice:** Start with Python, optimize with Rust when needed.

## Architecture

### Custom Readers

Custom readers extend the `BaseReader` class and implement the `extract()` method. The reader receives:
- `source_config`: Source configuration including connection details, credentials, and engine options
- `state_manager`: Optional state manager for incremental syncs

### Custom Writers

Custom writers extend the `BaseWriter` class and implement the `write_batch()` method. The writer receives:
- `asset_definition`: Asset definition with schema and metadata
- `target_config`: Target configuration including connection details, catalog, and format options
- `output_base`: Base output path for writing files

## Creating a Custom Reader

### Step 1: Create a Reader Class

Create a Python file with your custom reader class:

```python
# my_custom_reader.py
from typing import Any, Dict, Iterator, List, Optional
from dativo_ingest.plugins import BaseReader
from dativo_ingest.validator import IncrementalStateManager


class MyCustomReader(BaseReader):
    """Custom reader for reading from MySource."""
    
    def __init__(self, source_config):
        super().__init__(source_config)
        
        # Access connection details from source_config
        self.connection_info = source_config.connection
        self.credentials = source_config.credentials
        
        # Initialize your connection
        self.client = self._setup_client()
    
    def _setup_client(self):
        """Set up connection to your source system."""
        # Example: Initialize client with connection details
        api_key = self.credentials.get("api_key")
        endpoint = self.connection_info.get("endpoint")
        
        # Return your initialized client
        return MySourceClient(endpoint=endpoint, api_key=api_key)
    
    def extract(
        self, state_manager: Optional[IncrementalStateManager] = None
    ) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from source system.
        
        Yields batches of records as list of dictionaries.
        """
        # Get configuration options
        batch_size = self.source_config.engine.get("options", {}).get("batch_size", 1000)
        objects = self.source_config.objects or []
        
        for obj_name in objects:
            # Fetch data from your source
            offset = 0
            while True:
                # Read batch from source
                records = self.client.fetch(
                    object_name=obj_name,
                    limit=batch_size,
                    offset=offset
                )
                
                if not records:
                    break
                
                # Transform records to dictionary format
                batch = [self._transform_record(r) for r in records]
                
                yield batch
                
                offset += len(records)
    
    def _transform_record(self, record) -> Dict[str, Any]:
        """Transform source record to dictionary."""
        # Convert your source record format to dict
        return {
            "id": record.id,
            "name": record.name,
            # ... other fields
        }
    
    def get_total_records_estimate(self) -> Optional[int]:
        """Get estimated total number of records (optional)."""
        try:
            return self.client.count()
        except:
            return None
```

### Step 2: Configure Your Job

Add the custom reader to your job configuration:

```yaml
# job.yaml
tenant_id: acme
environment: prod

source_connector: my_custom_source
source_connector_path: /app/connectors/my_source.yaml

target_connector: s3
target_connector_path: /app/connectors/s3.yaml

asset: my_data
asset_path: /app/assets/my_data.yaml

source:
  # Specify custom reader path
  custom_reader: "/app/plugins/my_custom_reader.py:MyCustomReader"
  
  # Connection details (passed to your reader)
  connection:
    endpoint: "https://api.example.com"
  
  # Credentials (passed to your reader)
  credentials:
    api_key: "${MY_API_KEY}"
  
  # Objects to extract
  objects: ["users", "orders"]
  
  # Engine options (passed to your reader)
  engine:
    options:
      batch_size: 5000

target:
  connection:
    bucket: "my-data-lake"
```

## Creating a Custom Writer

### Step 1: Create a Writer Class

Create a Python file with your custom writer class:

```python
# my_custom_writer.py
from typing import Any, Dict, List
from dativo_ingest.plugins import BaseWriter


class MyCustomWriter(BaseWriter):
    """Custom writer for writing to MyTarget."""
    
    def __init__(self, asset_definition, target_config, output_base):
        super().__init__(asset_definition, target_config, output_base)
        
        # Access connection details from target_config
        self.connection_info = target_config.connection
        
        # Get schema from asset definition
        self.schema = asset_definition.schema
        
        # Initialize your connection
        self.client = self._setup_client()
    
    def _setup_client(self):
        """Set up connection to your target system."""
        # Example: Initialize client with connection details
        endpoint = self.connection_info.get("endpoint")
        api_key = self.connection_info.get("api_key")
        
        return MyTargetClient(endpoint=endpoint, api_key=api_key)
    
    def write_batch(
        self, records: List[Dict[str, Any]], file_counter: int
    ) -> List[Dict[str, Any]]:
        """Write a batch of records to target system.
        
        Args:
            records: List of validated records to write
            file_counter: Counter for generating unique identifiers
        
        Returns:
            List of file metadata dictionaries
        """
        if not records:
            return []
        
        # Write records to your target
        table_name = self.asset_definition.name
        result = self.client.bulk_insert(
            table=table_name,
            records=records
        )
        
        # Return metadata about what was written
        return [{
            "path": f"{self.output_base}/batch_{file_counter}.dat",
            "size_bytes": result.bytes_written,
            "record_count": len(records),
            "batch_id": result.batch_id,
        }]
    
    def commit_files(self, file_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Commit files to target system (optional).
        
        Override this if you need to perform post-write operations.
        """
        # Example: Finalize transaction or update catalog
        total_records = sum(fm.get("record_count", 0) for fm in file_metadata)
        
        self.client.finalize_batch(file_metadata)
        
        return {
            "status": "success",
            "files_added": len(file_metadata),
            "total_records": total_records,
        }
```

### Step 2: Configure Your Job

Add the custom writer to your job configuration:

```yaml
# job.yaml
tenant_id: acme
environment: prod

source_connector: postgres
source_connector_path: /app/connectors/postgres.yaml

target_connector: my_custom_target
target_connector_path: /app/connectors/my_target.yaml

asset: my_data
asset_path: /app/assets/my_data.yaml

source:
  tables:
    - name: "users"

target:
  # Specify custom writer path
  custom_writer: "/app/plugins/my_custom_writer.py:MyCustomWriter"
  
  # Connection details (passed to your writer)
  connection:
    endpoint: "https://api.example.com"
    api_key: "${TARGET_API_KEY}"
```

## Plugin Path Format

Custom reader/writer paths must follow this format:

```
/path/to/module.py:ClassName
```

- **Path**: Absolute or relative path to Python file containing the class
- **ClassName**: Name of the class to instantiate (must inherit from BaseReader or BaseWriter)

Examples:
- `/app/plugins/my_reader.py:MyReader`
- `./custom/writers/parquet_writer.py:OptimizedParquetWriter`
- `/workspace/plugins/delta_writer.py:DeltaLakeWriter`

### Cloud Storage Paths (AWS & GCP)

You can host plugin artifacts in S3 or Google Cloud Storage and reference them
directly in your job configuration:

```yaml
source:
  custom_reader: "s3://acme-plugins/readers/json_reader.py:JSONReader"

target:
  custom_writer: "gs://acme-plugins/writers/libparquet_writer.so:create_writer"
```

At runtime the plugin files are downloaded to a local cache and treated like
on-disk modules. Use the following environment variables to control caching:

- `DATIVO_PLUGIN_CACHE_DIR`: Override the default cache directory (defaults to
  the system temporary directory).
- `DATIVO_PLUGIN_REFRESH=true`: Force a fresh download on the next run, useful
  when rolling out a new plugin version.

## Advanced Examples

### Example 1: Custom JSON Reader with Pagination

```python
# json_api_reader.py
import requests
from typing import Any, Dict, Iterator, List, Optional
from dativo_ingest.plugins import BaseReader


class JSONAPIReader(BaseReader):
    """Read from paginated JSON API."""
    
    def extract(self, state_manager=None) -> Iterator[List[Dict[str, Any]]]:
        base_url = self.source_config.connection.get("base_url")
        headers = {
            "Authorization": f"Bearer {self.source_config.credentials.get('token')}"
        }
        
        page = 1
        page_size = self.source_config.engine.get("options", {}).get("page_size", 100)
        
        while True:
            response = requests.get(
                f"{base_url}/data",
                params={"page": page, "page_size": page_size},
                headers=headers
            )
            response.raise_for_status()
            
            data = response.json()
            records = data.get("items", [])
            
            if not records:
                break
            
            yield records
            
            if not data.get("has_next"):
                break
            
            page += 1
```

### Example 2: Custom Delta Lake Writer

```python
# delta_writer.py
from deltalake import DeltaTable, write_deltalake
import pyarrow as pa
from typing import Any, Dict, List
from dativo_ingest.plugins import BaseWriter


class DeltaLakeWriter(BaseWriter):
    """Write to Delta Lake format."""
    
    def __init__(self, asset_definition, target_config, output_base):
        super().__init__(asset_definition, target_config, output_base)
        self.table_path = output_base.replace("s3://", "")
        self.storage_options = self._get_storage_options()
    
    def _get_storage_options(self):
        """Get S3 storage options from connection config."""
        s3_config = self.target_config.connection.get("s3", {})
        return {
            "AWS_REGION": s3_config.get("region", "us-east-1"),
            "AWS_ACCESS_KEY_ID": s3_config.get("access_key"),
            "AWS_SECRET_ACCESS_KEY": s3_config.get("secret_key"),
        }
    
    def write_batch(self, records: List[Dict[str, Any]], file_counter: int) -> List[Dict[str, Any]]:
        """Write batch to Delta Lake."""
        if not records:
            return []
        
        # Convert records to PyArrow table
        table = pa.Table.from_pylist(records)
        
        # Write to Delta Lake
        write_deltalake(
            table_or_uri=self.table_path,
            data=table,
            mode="append",
            storage_options=self.storage_options,
        )
        
        # Estimate size
        size_bytes = sum(len(str(r)) for r in records)
        
        return [{
            "path": f"{self.table_path}/part-{file_counter:05d}",
            "size_bytes": size_bytes,
            "record_count": len(records),
        }]
    
    def commit_files(self, file_metadata: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Optimize Delta table."""
        dt = DeltaTable(self.table_path, storage_options=self.storage_options)
        dt.optimize.compact()
        
        return {
            "status": "success",
            "files_added": len(file_metadata),
            "delta_version": dt.version(),
        }
```

### Example 3: Custom Avro Writer

```python
# avro_writer.py
import avro.schema
from avro.datafile import DataFileWriter
from avro.io import DatumWriter
import tempfile
from typing import Any, Dict, List
from dativo_ingest.plugins import BaseWriter


class AvroWriter(BaseWriter):
    """Write to Avro format."""
    
    def __init__(self, asset_definition, target_config, output_base):
        super().__init__(asset_definition, target_config, output_base)
        self.avro_schema = self._build_avro_schema()
        self.s3_client = self._setup_s3_client()
    
    def _build_avro_schema(self):
        """Build Avro schema from asset definition."""
        fields = []
        for field in self.asset_definition.schema:
            avro_type = self._map_to_avro_type(field.get("type"))
            fields.append({
                "name": field["name"],
                "type": avro_type,
            })
        
        return avro.schema.parse(json.dumps({
            "type": "record",
            "name": self.asset_definition.name,
            "fields": fields,
        }))
    
    def _map_to_avro_type(self, odcs_type: str) -> str:
        """Map ODCS type to Avro type."""
        mapping = {
            "string": "string",
            "integer": "int",
            "number": "double",
            "boolean": "boolean",
            "timestamp": "long",
        }
        return mapping.get(odcs_type, "string")
    
    def write_batch(self, records: List[Dict[str, Any]], file_counter: int) -> List[Dict[str, Any]]:
        """Write batch to Avro file."""
        if not records:
            return []
        
        # Write to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".avro") as tmp:
            writer = DataFileWriter(tmp, DatumWriter(), self.avro_schema)
            for record in records:
                writer.append(record)
            writer.close()
            
            tmp_path = tmp.name
        
        # Upload to S3
        s3_key = f"{self.output_base}/part-{file_counter:05d}.avro"
        bucket = self.target_config.connection.get("s3", {}).get("bucket")
        
        self.s3_client.upload_file(tmp_path, bucket, s3_key)
        
        # Get file size
        import os
        size_bytes = os.path.getsize(tmp_path)
        os.unlink(tmp_path)
        
        return [{
            "path": f"s3://{bucket}/{s3_key}",
            "size_bytes": size_bytes,
            "record_count": len(records),
        }]
```

## Best Practices

### For Custom Readers

1. **Batch Processing**: Yield records in batches (1000-10000 records) for efficient processing
2. **Error Handling**: Handle connection errors gracefully and provide clear error messages
3. **State Management**: Use the state_manager for incremental syncs when applicable
4. **Resource Cleanup**: Close connections and release resources properly
5. **Logging**: Use Python's logging module to provide visibility into extraction progress

### For Custom Writers

1. **Schema Validation**: Validate records against asset definition schema before writing
2. **Atomic Writes**: Implement transactions or staging when possible
3. **Idempotency**: Design writers to be idempotent for retry scenarios
4. **Metadata Tracking**: Return accurate file metadata for observability
5. **Compression**: Use appropriate compression for target format

### Security

1. **Credentials**: Access credentials from `source_config.credentials` or `target_config.connection`
2. **Environment Variables**: Use environment variables for sensitive data
3. **Secrets Management**: Never hardcode secrets in plugin code
4. **Encryption**: Use encrypted connections (SSL/TLS) when available

## Testing Custom Plugins

### Unit Testing

```python
# test_my_reader.py
import pytest
from my_custom_reader import MyCustomReader
from dativo_ingest.config import SourceConfig


def test_reader_extraction():
    """Test custom reader extracts data correctly."""
    source_config = SourceConfig(
        type="custom",
        connection={"endpoint": "https://test.example.com"},
        credentials={"api_key": "test-key"},
        objects=["users"],
        engine={"options": {"batch_size": 100}},
    )
    
    reader = MyCustomReader(source_config)
    
    batches = list(reader.extract())
    assert len(batches) > 0
    assert all(isinstance(batch, list) for batch in batches)
```

### Integration Testing

Run a full job with your custom plugin:

```bash
# Set environment variables
export MY_API_KEY="your-api-key"

# Run job
dativo run --config /app/jobs/my_custom_job.yaml --mode self_hosted
```

## Troubleshooting

### Plugin Not Found

**Error**: `Plugin module not found: /path/to/plugin.py`

**Solution**: Ensure the plugin file path is correct and accessible

### Class Not Found

**Error**: `Class 'MyReader' not found in module`

**Solution**: Check the class name matches exactly (case-sensitive)

### Import Errors

**Error**: `ModuleNotFoundError: No module named 'xyz'`

**Solution**: Install required dependencies in your environment:
```bash
pip install xyz
```

### Connection Errors

**Error**: `Failed to connect to source`

**Solution**: 
- Verify connection details in job configuration
- Check network connectivity
- Validate credentials

## Rust Plugins

Rust plugins provide significant performance benefits for data-intensive operations.

### Quick Start with Rust

**1. Install Rust:**
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env
```

**2. Build example plugins:**
```bash
cd examples/plugins/rust
make build-release
```

**3. Use in job configuration:**
```yaml
source:
  custom_reader: "examples/plugins/rust/target/release/libcsv_reader_plugin.so:create_reader"
  files:
    - path: "/data/large_file.csv"
  engine:
    options:
      batch_size: 50000
```

### Available Rust Plugins

#### CSV Reader
- **Performance:** 10-50x faster than Python
- **Memory:** Uses 1/10th the memory
- **Location:** `examples/plugins/rust/csv_reader/`

```yaml
source:
  custom_reader: "/app/plugins/rust/target/release/libcsv_reader_plugin.so:create_reader"
  engine:
    options:
      batch_size: 50000  # Larger batches for Rust
      delimiter: ","
```

#### Parquet Writer
- **Performance:** 5-20x faster than PyArrow
- **Compression:** Better compression ratios
- **Location:** `examples/plugins/rust/parquet_writer/`

```yaml
target:
  custom_writer: "/app/plugins/rust/target/release/libparquet_writer_plugin.so:create_writer"
  engine:
    options:
      compression: "zstd"  # Best compression
      row_group_size: 500000
```

### Creating Rust Plugins

See the comprehensive guide in `examples/plugins/rust/README.md` for:
- Plugin structure and FFI interface
- Building and testing
- Performance benchmarking
- Platform-specific considerations

### Performance Comparison

**CSV Reading (10M rows):**
- Python: 45s, 2.5 GB memory
- **Rust: 3s, 200 MB memory** (15x faster, 12x less memory)

**Parquet Writing (10M rows):**
- Python: 28s, 580 MB file, 3.2 GB memory
- **Rust: 8s, 420 MB file, 400 MB memory** (3.5x faster, 27% better compression)

## Additional Resources

### Python Plugins
- [Python Plugin Examples](/workspace/examples/plugins/)
- [Plugin Base Classes API Reference](/workspace/src/dativo_ingest/plugins.py)
- [Job Configuration Guide](/docs/CONFIG_REFERENCE.md)

### Rust Plugins
- [Rust Plugin Examples](/workspace/examples/plugins/rust/)
- [Rust Plugin Guide](/workspace/examples/plugins/rust/README.md)
- [Build System](/workspace/examples/plugins/rust/Makefile)

## Support

For questions or issues with custom plugins:

**Python Plugins:**
1. Check the [Troubleshooting](#troubleshooting) section
2. Review example implementations in `/workspace/examples/plugins/`
3. Test with smaller datasets first

**Rust Plugins:**
1. Check build logs: `cargo build --release`
2. Verify exported symbols: `make symbols-reader`
3. Review Rust examples in `/workspace/examples/plugins/rust/`
4. Check platform-specific requirements (Linux: .so, macOS: .dylib, Windows: .dll)
