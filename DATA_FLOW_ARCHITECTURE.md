# Data Flow Architecture: Reader to Writer

This document explains how data is transmitted from readers (extractors) to writers in dativo-ingest, including how Airbyte readers work with Rust writers.

---

## Table of Contents

1. [Overview](#overview)
2. [The Python Iterator Pattern](#the-python-iterator-pattern)
3. [Data Flow Sequence](#data-flow-sequence)
4. [Reader Interface](#reader-interface)
5. [Writer Interface](#writer-interface)
6. [In-Memory Streaming](#in-memory-streaming)
7. [How Airbyte Readers Work](#how-airbyte-readers-work)
8. [How Rust Writers Work](#how-rust-writers-work)
9. [Airbyte Reader → Rust Writer Flow](#airbyte-reader--rust-writer-flow)
10. [Memory Management](#memory-management)
11. [Performance Characteristics](#performance-characteristics)

---

## Overview

Dativo-ingest uses a **Python iterator-based streaming architecture** to transmit data from readers to writers. This approach enables:

- ✅ **Low memory footprint** - Data is processed in batches, not all at once
- ✅ **Universal interface** - All readers/writers use the same protocol
- ✅ **Language interoperability** - Python, Airbyte, and Rust components work seamlessly
- ✅ **Backpressure handling** - Writers control processing speed

**Key Concept:** Data never sits in a large intermediate buffer. Instead, it flows through the pipeline in **batches** via Python iterators.

---

## The Python Iterator Pattern

At the core of the architecture is Python's iterator protocol:

```python
# Reader (extractor) yields batches
def extract(self) -> Iterator[List[Dict[str, Any]]]:
    for batch in data_source:
        yield batch  # Yields control back to caller
        
# Main loop consumes batches one at a time
for batch in extractor.extract():
    validated_batch = validator.validate(batch)
    writer.write_batch(validated_batch)
```

**Why iterators?**
- Memory efficient: Only one batch in memory at a time
- Natural backpressure: Reader pauses until writer is ready
- Composable: Easy to add validation, transformation, filtering

---

## Data Flow Sequence

Here's the complete flow from source to target:

```
┌──────────────┐
│   SOURCE     │ (CSV, Database, API, etc.)
└──────┬───────┘
       │
       │ Raw data
       ▼
┌──────────────────────────────────────────────────────┐
│  READER/EXTRACTOR                                    │
│  • Reads source data                                 │
│  • Converts to Python dictionaries                   │
│  • Yields batches (e.g., 10,000 records)            │
│  • Types: Native, Airbyte, Rust Plugin              │
└──────┬───────────────────────────────────────────────┘
       │
       │ Iterator[List[Dict[str, Any]]]
       │ ▲
       │ │ for batch in extractor.extract():
       │ │
┌──────▼───────────────────────────────────────────────┐
│  MAIN ORCHESTRATION LOOP (cli.py)                    │
│  • Iterates over batches from reader                 │
│  • Passes each batch through pipeline                │
└──────┬───────────────────────────────────────────────┘
       │
       │ Batch (List[Dict[str, Any]])
       ▼
┌──────────────────────────────────────────────────────┐
│  VALIDATOR                                           │
│  • Validates batch against schema                    │
│  • Returns valid records + error list                │
│  • Mode: strict (fail) or warn (log)                │
└──────┬───────────────────────────────────────────────┘
       │
       │ Valid records (List[Dict[str, Any]])
       ▼
┌──────────────────────────────────────────────────────┐
│  WRITER                                              │
│  • Writes batch to target format                     │
│  • Types: Parquet, Custom Python, Rust Plugin       │
│  • Returns file metadata                             │
└──────┬───────────────────────────────────────────────┘
       │
       │ File metadata
       ▼
┌──────────────────────────────────────────────────────┐
│  COMMITTER                                           │
│  • Uploads files to S3/MinIO                         │
│  • Commits to Iceberg catalog (optional)             │
│  • Updates state for incremental sync                │
└──────┬───────────────────────────────────────────────┘
       │
       ▼
┌──────────────┐
│   TARGET     │ (S3, MinIO, Iceberg)
└──────────────┘
```

---

## Reader Interface

All readers implement the `extract()` method that returns a Python iterator:

```python
from typing import Iterator, List, Dict, Any

class BaseReader:
    def extract(self, state_manager=None) -> Iterator[List[Dict[str, Any]]]:
        """Extract data from source.
        
        Yields:
            Batches of records (each batch is a list of dictionaries)
        """
        pass
```

**Example: CSV Reader**

```python
class CSVExtractor:
    def extract(self, state_manager=None) -> Iterator[List[Dict[str, Any]]]:
        # Read CSV in chunks
        for chunk in pd.read_csv(file_path, chunksize=10000):
            # Convert DataFrame chunk to list of dicts
            records = chunk.to_dict('records')
            yield records  # Yield batch to orchestrator
```

**Example: Airbyte Reader**

```python
class AirbyteExtractor:
    def extract(self, state_manager=None) -> Iterator[List[Dict[str, Any]]]:
        # Run Airbyte Docker container
        process = self._run_airbyte_docker()
        
        batch = []
        for line in process.stdout:
            record = json.loads(line)
            if record['type'] == 'RECORD':
                batch.append(record['record'])
                
                if len(batch) >= batch_size:
                    yield batch  # Yield when batch is full
                    batch = []
        
        if batch:
            yield batch  # Yield remaining records
```

---

## Writer Interface

All writers implement the `write_batch()` method:

```python
class BaseWriter:
    def write_batch(
        self, 
        records: List[Dict[str, Any]], 
        file_counter: int
    ) -> List[Dict[str, Any]]:
        """Write a batch of records.
        
        Args:
            records: Batch of validated records
            file_counter: Current file count (for naming)
            
        Returns:
            List of file metadata dictionaries
        """
        pass
```

**Example: Parquet Writer**

```python
class ParquetWriter:
    def write_batch(self, records, file_counter):
        # Convert records to PyArrow Table
        table = pa.Table.from_pylist(records, schema=self.schema)
        
        # Write to Parquet file
        file_path = f"{self.output_base}/file_{file_counter}.parquet"
        pq.write_table(table, file_path, compression='snappy')
        
        return [{
            "path": file_path,
            "size_bytes": os.path.getsize(file_path),
            "record_count": len(records)
        }]
```

---

## In-Memory Streaming

The critical connection happens in the main orchestration loop:

```python
# From cli.py:execute_job()
def execute_job(job_config: JobConfig) -> int:
    # 1. Initialize components
    extractor = create_extractor(job_config)  # Reader
    validator = SchemaValidator(asset_definition)
    writer = ParquetWriter(asset_definition, target_config)
    
    # 2. Process data in batches using iterator
    for batch_records in extractor.extract(state_manager):
        # batch_records is a List[Dict[str, Any]]
        
        # 3. Validate batch
        valid_records, errors = validator.validate_batch(batch_records)
        
        # 4. Write valid records
        if valid_records:
            file_metadata = writer.write_batch(valid_records, file_counter)
            all_files.extend(file_metadata)
            file_counter += len(file_metadata)
    
    # 5. Commit all files
    committer.commit_files(all_files)
```

**Key Points:**
- No intermediate storage between reader and writer
- Each batch lives in memory only during processing
- The `for` loop creates natural backpressure
- Writer controls when reader produces next batch

---

## How Airbyte Readers Work

Airbyte readers run as Docker containers and stream data via stdout:

### Architecture

```
┌─────────────────────────────────────────────────────┐
│  Dativo Python Process                              │
│                                                     │
│  ┌───────────────────────────────────────────┐    │
│  │  AirbyteExtractor                          │    │
│  │  1. Starts Docker container                │    │
│  │  2. Reads stdout line-by-line             │    │
│  │  3. Parses JSON (Airbyte protocol)        │    │
│  │  4. Batches records                        │    │
│  │  5. Yields batches via iterator            │    │
│  └───────────────┬───────────────────────────┘    │
│                  │                                  │
│                  │ stdout (newline-delimited JSON) │
│                  │                                  │
└──────────────────┼──────────────────────────────────┘
                   │
         ┌─────────▼──────────┐
         │  Docker Container  │
         │  ┌──────────────┐  │
         │  │   Airbyte    │  │
         │  │  Connector   │  │
         │  │ (e.g. Stripe)│  │
         │  └──────┬───────┘  │
         │         │          │
         │    API Calls       │
         │         │          │
         └─────────┼──────────┘
                   │
         ┌─────────▼──────────┐
         │   External API     │
         │  (Stripe, HubSpot) │
         └────────────────────┘
```

### Code Flow

```python
# connectors/engine_framework.py:AirbyteExtractor.extract()
def extract(self, state_manager=None) -> Iterator[List[Dict[str, Any]]]:
    # 1. Start Airbyte Docker container
    process = subprocess.Popen(
        ["docker", "run", "--rm", airbyte_image, "read", ...],
        stdout=subprocess.PIPE,
        text=True
    )
    
    # 2. Read stdout line-by-line
    batch = []
    for line in process.stdout:
        # 3. Parse Airbyte protocol JSON
        message = json.loads(line)
        
        # 4. Extract RECORD messages
        if message.get("type") == "RECORD":
            record = message.get("record", {})
            batch.append(record)
            
            # 5. Yield when batch reaches target size
            if len(batch) >= self.batch_size:
                yield batch  # Return control to main loop
                batch = []
    
    # 6. Yield remaining records
    if batch:
        yield batch
```

**Airbyte Protocol Format:**
```json
{"type": "RECORD", "record": {"id": 1, "name": "Customer 1"}}
{"type": "RECORD", "record": {"id": 2, "name": "Customer 2"}}
{"type": "STATE", "state": {"cursor": "2024-01-01"}}
```

---

## How Rust Writers Work

Rust writers are loaded as shared libraries (.so/.dll) and called via Python ctypes FFI:

### Architecture

```
┌──────────────────────────────────────────────────────┐
│  Dativo Python Process                               │
│                                                      │
│  ┌────────────────────────────────────────────┐    │
│  │  RustWriterBridge                           │    │
│  │  1. Loads Rust .so library via ctypes      │    │
│  │  2. Serializes records to JSON string      │    │
│  │  3. Calls Rust write_batch() via FFI       │    │
│  │  4. Receives JSON result string            │    │
│  │  5. Parses and returns file metadata       │    │
│  └────────┬───────────────────────────────────┘    │
│           │                                         │
│           │ FFI (ctypes)                            │
│           │ JSON string                             │
└───────────┼─────────────────────────────────────────┘
            │
┌───────────▼─────────────────────────────────────────┐
│  Rust Shared Library (.so)                          │
│                                                      │
│  ┌────────────────────────────────────────────┐    │
│  │  Rust Writer Implementation                 │    │
│  │  1. Receives JSON string via FFI           │    │
│  │  2. Deserializes to Rust structs           │    │
│  │  3. Writes Parquet using arrow/parquet libs│    │
│  │  4. Returns file metadata as JSON string   │    │
│  └────────────────────────────────────────────┘    │
│                                                      │
│  • 10-100x faster than Python                       │
│  • Lower memory usage                               │
│  • Better compression                               │
└──────────────────────────────────────────────────────┘
```

### Code Flow

**Python Side (rust_plugin_bridge.py):**

```python
class RustWriterBridge:
    def __init__(self, so_path, func_name, ...):
        # 1. Load Rust shared library
        self._lib = ctypes.CDLL(so_path)
        
        # 2. Define function signatures
        create_writer = getattr(self._lib, func_name)
        create_writer.argtypes = [ctypes.c_char_p]  # JSON config
        create_writer.restype = ctypes.c_void_p      # Opaque pointer
        
        write_batch = getattr(self._lib, "write_batch")
        write_batch.argtypes = [
            ctypes.c_void_p,     # Writer pointer
            ctypes.c_char_p      # JSON records
        ]
        write_batch.restype = ctypes.c_void_p  # JSON result string
        
        # 3. Create Rust writer instance
        config_json = json.dumps(config).encode('utf-8')
        self._writer_ptr = create_writer(config_json)
    
    def write_batch(self, records: List[Dict], file_counter: int):
        # 4. Serialize records to JSON
        records_json = json.dumps(records).encode('utf-8')
        
        # 5. Call Rust write_batch via FFI
        result_ptr = self._write_batch(self._writer_ptr, records_json)
        
        # 6. Convert C string to Python string
        result_str = ctypes.string_at(result_ptr).decode('utf-8')
        
        # 7. Free Rust-allocated string
        self._free_string(result_ptr)
        
        # 8. Parse result
        file_metadata = json.loads(result_str)
        return file_metadata
```

**Rust Side (example):**

```rust
// Rust writer implementation
#[no_mangle]
pub extern "C" fn create_writer(config_json: *const c_char) -> *mut Writer {
    // Parse JSON config
    let config_str = unsafe { CStr::from_ptr(config_json).to_str().unwrap() };
    let config: WriterConfig = serde_json::from_str(config_str).unwrap();
    
    // Create writer instance
    let writer = Writer::new(config);
    Box::into_raw(Box::new(writer))
}

#[no_mangle]
pub extern "C" fn write_batch(
    writer_ptr: *mut Writer,
    records_json: *const c_char
) -> *const c_char {
    let writer = unsafe { &mut *writer_ptr };
    
    // Parse records
    let records_str = unsafe { CStr::from_ptr(records_json).to_str().unwrap() };
    let records: Vec<Record> = serde_json::from_str(records_str).unwrap();
    
    // Write to Parquet (using arrow/parquet crates)
    let file_metadata = writer.write_parquet(&records);
    
    // Return metadata as JSON
    let result_json = serde_json::to_string(&file_metadata).unwrap();
    CString::new(result_json).unwrap().into_raw()
}
```

---

## Airbyte Reader → Rust Writer Flow

Here's the complete flow when using an Airbyte reader with a Rust writer:

```
Step 1: Setup
┌─────────────────────────┐      ┌─────────────────────────┐
│  AirbyteExtractor       │      │  RustWriterBridge       │
│  • Starts Docker        │      │  • Loads .so library    │
│  • Configures connector │      │  • Creates Rust writer  │
└───────────┬─────────────┘      └───────────┬─────────────┘
            │                                 │
            │                                 │
            
Step 2: Main Loop Iteration
            │                                 │
            │ 1. extract() called             │
            │    Returns iterator             │
            ▼                                 │
┌─────────────────────────┐                  │
│  Docker Container       │                  │
│  ├─ Airbyte Stripe      │                  │
│  ├─ Reads Stripe API    │                  │
│  └─ Outputs JSON lines  │                  │
└───────────┬─────────────┘                  │
            │                                 │
            │ 2. Stream JSON to stdout        │
            │    {"type":"RECORD",...}        │
            │    {"type":"RECORD",...}        │
            ▼                                 │
┌─────────────────────────┐                  │
│  Python Iterator        │                  │
│  • Buffers records      │                  │
│  • Batches to 10K       │                  │
│  • Yields batch         │                  │
└───────────┬─────────────┘                  │
            │                                 │
            │ 3. Batch (List[Dict])           │
            │    [{"id":1,...}, {"id":2,...}] │
            ▼                                 │
┌─────────────────────────────────────────────┐
│  Main Loop (cli.py)                         │
│  for batch in extractor.extract():          │
│      valid = validator.validate(batch)      │
│      writer.write_batch(valid)              │
└───────────┬─────────────────────────────────┘
            │                                 │
            │ 4. write_batch(valid_records)   │
            │                                 ▼
            │                 ┌─────────────────────────┐
            │                 │  RustWriterBridge       │
            │                 │  • JSON.dumps(records)  │
            │                 │  • Calls Rust FFI       │
            │                 └───────────┬─────────────┘
            │                             │
            │                             │ 5. FFI call
            │                             │    JSON string
            │                             ▼
            │                 ┌─────────────────────────┐
            │                 │  Rust Writer (.so)      │
            │                 │  • Parse JSON           │
            │                 │  • Write Parquet        │
            │                 │  • Return metadata JSON │
            │                 └───────────┬─────────────┘
            │                             │
            │                             │ 6. File metadata
            │                             │    (JSON string)
            │                 ┌───────────▼─────────────┐
            │                 │  Python                 │
            │                 │  • Parse JSON result    │
            │                 │  • Return metadata list │
            │                 └───────────┬─────────────┘
            │                             │
            │◄────────────────────────────┘
            │ 7. file_metadata
            ▼
    [Continue loop with next batch...]
```

**Key Points:**

1. **No intermediate files**: Data flows through memory only
2. **Batch-by-batch**: One batch processed at a time
3. **Language boundaries**: 
   - Airbyte (Docker) → Python: stdout/JSON
   - Python → Rust: ctypes FFI/JSON
4. **Format conversions**:
   - Airbyte JSON → Python dict
   - Python dict → JSON string
   - JSON string → Rust struct
   - Rust struct → Parquet bytes
5. **Performance**: Rust handles intensive I/O, Python handles orchestration

---

## Memory Management

### Batch Sizing

Default batch sizes are optimized for memory efficiency:

```python
# CSV Reader
CHUNK_SIZE = 10000  # pandas read_csv chunksize

# Airbyte Reader  
BATCH_SIZE = 10000  # Buffer size before yielding

# Rust Reader
BATCH_SIZE = 50000  # Larger batches (Rust handles more efficiently)

# Parquet Writer
TARGET_SIZE_MB = 128  # Target Parquet file size
```

### Memory Flow

For a typical job with 1M records:

```
Total Records: 1,000,000
Batch Size: 10,000
Batches: 100

Memory per batch: ~10 MB (1000 records × ~10 KB each)
Peak memory: ~30-50 MB
  - Current batch: 10 MB
  - Validation: 10 MB
  - Writing: 10-30 MB (Parquet encoding)

Total memory: < 100 MB for entire 1M record job
```

**With Rust Writer:**
- Python memory: ~20 MB (batch + metadata)
- Rust memory: ~30 MB (parsing + Parquet encoding)
- Total: ~50 MB peak

**Comparison (loading entire dataset):**
- All-in-memory: 1000 MB (1 GB)
- Streaming: 50 MB (20x less)

---

## Performance Characteristics

### Python Reader → Python Writer

```
CSV (10K records/sec) → Parquet (8K records/sec)
Bottleneck: Parquet encoding
Memory: ~30 MB per batch
```

### Airbyte Reader → Python Writer

```
Airbyte/Stripe (5K records/sec) → Parquet (8K records/sec)
Bottleneck: API rate limits, Docker overhead
Memory: ~50 MB (Docker + Python)
```

### Python Reader → Rust Writer

```
CSV (10K records/sec) → Rust Parquet (100K records/sec)
Bottleneck: CSV parsing (Python)
Memory: ~40 MB per batch
Speedup: 10-15x faster writes
```

### Airbyte Reader → Rust Writer

```
Airbyte/Stripe (5K records/sec) → Rust Parquet (100K records/sec)
Bottleneck: API rate limits
Memory: ~60 MB (Docker + Python + Rust)
Speedup: Writer doesn't bottleneck on API data
```

**Key Insight:** With Rust writers, the writer never becomes the bottleneck. API rate limits or source extraction speed limit throughput, not the writer.

---

## Summary

### Architecture Pattern

✅ **Iterator-based streaming**: Memory-efficient, natural backpressure
✅ **Universal interface**: All readers yield `Iterator[List[Dict]]`, all writers accept `List[Dict]`
✅ **Language interop**: Python orchestrates, components can be Python/Airbyte/Rust
✅ **No intermediate storage**: Data flows through memory only

### Data Format

- **Between components**: Python dictionaries (`Dict[str, Any]`)
- **Over FFI boundaries**: JSON strings
- **On disk**: Parquet files

### Performance

- **Python → Python**: Good (10K records/sec)
- **Airbyte → Python**: Moderate (5K records/sec, limited by API)
- **Any → Rust**: Excellent (50-100K records/sec writes)

### Memory Efficiency

- **Batch size**: 10K-50K records
- **Peak memory**: 30-100 MB regardless of dataset size
- **Scalability**: Can process billions of records with constant memory

---

## Code Examples

### Full Example: Airbyte Stripe → Rust Parquet Writer

**Job Configuration:**
```yaml
tenant_id: mycompany
source_connector: stripe
source_connector_path: connectors/stripe.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: stripe_customers
asset_path: assets/stripe/v1.0/customers.yaml

source:
  objects: [customers]
  engine:
    type: airbyte
    options:
      docker_image: "airbyte/source-stripe:2.1.5"
      batch_size: 10000

target:
  custom_writer: "/app/plugins/rust/target/release/libparquet_writer_plugin.so:create_writer"
  connection:
    s3:
      bucket: "${S3_BUCKET}"
      prefix: "customers"
  engine:
    options:
      batch_size: 50000  # Larger batches for Rust
```

**Execution Flow:**

1. **Reader Setup**: AirbyteExtractor starts Stripe Docker container
2. **Writer Setup**: RustWriterBridge loads .so, creates Rust writer
3. **Main Loop**:
   ```python
   for batch in airbyte_extractor.extract():
       # batch: List[Dict] from Stripe API via Docker stdout
       
       valid_batch, errors = validator.validate_batch(batch)
       # valid_batch: List[Dict] of valid Stripe customer records
       
       file_metadata = rust_writer.write_batch(valid_batch, file_counter)
       # Rust writes Parquet, returns metadata
       
       all_files.extend(file_metadata)
   ```
4. **Commit**: Upload Parquet files to S3, commit to Iceberg catalog

**Result**: Stripe data → Parquet files in S3, with optimal performance from Rust writer

---

## Related Documentation

- [CUSTOM_PLUGINS.md](docs/CUSTOM_PLUGINS.md) - Creating custom readers/writers
- [INGESTION_EXECUTION.md](docs/INGESTION_EXECUTION.md) - Execution flow details
- [TESTING_PLAYBOOK.md](TESTING_PLAYBOOK.md) - Test Case 11: Rust plugin performance testing

---

**Questions?** This architecture enables mixing and matching any reader with any writer while maintaining performance and memory efficiency.
