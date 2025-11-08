# Plugin System Testing Guide

Comprehensive testing documentation for the Dativo ETL plugin system.

## Overview

The plugin system is tested at multiple levels:

1. **Unit Tests** - Test individual components (base classes, loaders, validators)
2. **Integration Tests** - Test plugin loading and execution
3. **End-to-End Tests** - Test complete ETL pipelines with plugins
4. **Performance Tests** - Test plugin performance characteristics
5. **Rust Plugin Tests** - Test Rust plugin builds and integration

## Quick Start

### Run All Tests

```bash
# Run complete test suite
./tests/run_all_plugin_tests.sh
```

### Run Specific Test Suites

```bash
# Unit tests only (pytest)
pytest tests/test_plugins.py -v

# Integration tests only
./tests/test_plugin_integration.sh

# Rust plugin tests only
./examples/plugins/rust/test_rust_plugins.sh
```

## Test Coverage

### 1. Unit Tests (`test_plugins.py`)

**Coverage:**
- ✅ Plugin loading (Python and Rust)
- ✅ Base class functionality
- ✅ Error handling
- ✅ Configuration access
- ✅ Type detection
- ✅ Default readers (CSV extractor)
- ✅ Default writers (Parquet writer)
- ✅ Custom Python readers
- ✅ Custom Python writers
- ✅ Rust plugin bridge

**Run:**
```bash
pytest tests/test_plugins.py -v
```

**Classes tested:**
- `TestPluginLoader` - Plugin loading functionality
- `TestBaseReader` - Base reader class
- `TestBaseWriter` - Base writer class
- `TestDefaultReaders` - Built-in CSV extractor
- `TestDefaultWriters` - Built-in Parquet writer
- `TestPythonPluginEndToEnd` - Complete Python plugin pipeline
- `TestRustPluginDetection` - Rust plugin type detection
- `TestRustPluginBridge` - Rust FFI bridge
- `TestPluginErrorHandling` - Error propagation
- `TestPluginConfiguration` - Configuration handling
- `TestPluginPerformance` - Performance characteristics

### 2. Integration Tests (`test_plugin_integration.sh`)

**Coverage:**
- ✅ Default CSV reader with real files
- ✅ Custom Python reader loading and execution
- ✅ Custom Python writer loading and execution
- ✅ End-to-end reader → writer pipeline
- ✅ Plugin type detection (all formats)
- ✅ Error handling and propagation
- ✅ Rust bridge import and serialization
- ✅ Configuration passing to plugins

**Run:**
```bash
./tests/test_plugin_integration.sh
```

**Tests:**
- Default readers and writers with real data
- Custom Python plugins with file I/O
- Complete ETL pipeline (reader → writer)
- Plugin type detection for all extensions
- Error handling scenarios
- Rust bridge functionality

### 3. Rust Plugin Tests (`test_rust_plugins.sh`)

**Coverage:**
- ✅ Rust plugin compilation
- ✅ Build output verification
- ✅ Exported symbol verification
- ✅ Rust unit tests
- ✅ Python integration
- ✅ File size checks

**Run:**
```bash
cd examples/plugins/rust
./test_rust_plugins.sh
```

**Tests:**
- Build CSV reader plugin
- Build Parquet writer plugin
- Verify shared library outputs
- Check exported FFI functions
- Run Rust unit tests
- Test Python can detect plugin type

## Test Environment Setup

### Python Environment

```bash
# Install test dependencies
pip install pytest pytest-mock

# Set Python path
export PYTHONPATH="/workspace/src:$PYTHONPATH"
```

### Rust Environment (Optional)

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# Build Rust plugins
cd examples/plugins/rust
make build-release
```

## Writing Plugin Tests

### Testing a Custom Python Reader

```python
def test_my_custom_reader(tmp_path):
    """Test custom reader implementation."""
    # Create reader plugin
    reader_code = '''
from dativo_ingest.plugins import BaseReader

class MyReader(BaseReader):
    def extract(self, state_manager=None):
        # Your test logic
        yield [{"id": 1, "data": "test"}]
'''
    
    reader_file = tmp_path / "my_reader.py"
    reader_file.write_text(reader_code)
    
    # Load and test
    reader_class = PluginLoader.load_reader(f"{reader_file}:MyReader")
    source_config = SourceConfig(type="test")
    reader = reader_class(source_config)
    
    # Verify
    batches = list(reader.extract())
    assert len(batches) == 1
    assert batches[0][0]["id"] == 1
```

### Testing a Custom Python Writer

```python
def test_my_custom_writer(tmp_path):
    """Test custom writer implementation."""
    # Create writer plugin
    writer_code = '''
from dativo_ingest.plugins import BaseWriter

class MyWriter(BaseWriter):
    def write_batch(self, records, file_counter):
        # Your test logic
        return [{"path": "test.dat", "size_bytes": 100}]
'''
    
    writer_file = tmp_path / "my_writer.py"
    writer_file.write_text(writer_code)
    
    # Load and test
    writer_class = PluginLoader.load_writer(f"{writer_file}:MyWriter")
    
    class MockAsset:
        name = "test"
        schema = []
    
    target_config = TargetConfig(type="test")
    writer = writer_class(MockAsset(), target_config, "/tmp")
    
    # Verify
    metadata = writer.write_batch([{"id": 1}], 0)
    assert len(metadata) == 1
```

### Testing End-to-End Pipeline

```python
def test_complete_pipeline(tmp_path):
    """Test complete ETL pipeline with plugins."""
    # Create reader and writer
    # ... (see test_plugins.py for complete example)
    
    # Run pipeline
    for batch_idx, batch in enumerate(reader.extract()):
        metadata = writer.write_batch(batch, batch_idx)
        # Verify each batch
    
    # Verify final results
    assert all output files exist
    assert data is correct
```

## Continuous Integration

### GitHub Actions (Example)

```yaml
name: Plugin Tests

on: [push, pull_request]

jobs:
  test-python-plugins:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pytest pytest-mock
      - name: Run plugin tests
        run: |
          export PYTHONPATH="$PWD/src:$PYTHONPATH"
          pytest tests/test_plugins.py -v
          ./tests/test_plugin_integration.sh
  
  test-rust-plugins:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Install Rust
        uses: actions-rs/toolchain@v1
        with:
          toolchain: stable
      - name: Build and test Rust plugins
        run: |
          cd examples/plugins/rust
          ./test_rust_plugins.sh
```

## Test Fixtures

### CSV Test Data

```python
@pytest.fixture
def sample_csv_file(tmp_path):
    """Create sample CSV file for testing."""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text("id,name,value\n1,Alice,100\n2,Bob,200\n")
    return csv_file
```

### Mock Asset Definition

```python
@pytest.fixture
def mock_asset():
    """Create mock asset definition."""
    class MockAsset:
        name = "test_table"
        domain = "test"
        dataProduct = "test_product"
        schema = [
            {"name": "id", "type": "integer"},
            {"name": "name", "type": "string"},
        ]
    return MockAsset()
```

## Performance Testing

### Benchmarking Plugins

```python
def test_reader_performance(benchmark):
    """Benchmark reader performance."""
    reader_class = PluginLoader.load_reader("path/to/reader.py:Reader")
    source_config = SourceConfig(type="test")
    reader = reader_class(source_config)
    
    # Benchmark extraction
    result = benchmark(lambda: list(reader.extract()))
    
    # Assert performance characteristics
    assert result.stats.median < 1.0  # < 1 second
```

### Memory Usage Testing

```python
def test_reader_memory_usage():
    """Test reader memory usage."""
    import tracemalloc
    
    tracemalloc.start()
    
    # Extract large dataset
    reader = create_reader()
    for batch in reader.extract():
        process_batch(batch)
    
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    # Assert memory stays under limit
    assert peak / 1024 / 1024 < 500  # < 500 MB
```

## Debugging Failed Tests

### Verbose Output

```bash
# Run tests with verbose output
pytest tests/test_plugins.py -v -s

# Run integration tests with detailed output
bash -x ./tests/test_plugin_integration.sh
```

### Debugging Plugin Loading

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Load plugin with detailed logging
reader_class = PluginLoader.load_reader("path/to/reader.py:Reader")
```

### Debugging Rust Plugins

```bash
# Check exported symbols
nm -D target/release/libplugin.so | grep create_reader

# Run with debug symbols
cargo build --profile dev
```

## Test Maintenance

### Adding New Tests

1. Add test to appropriate class in `test_plugins.py`
2. Add integration test to `test_plugin_integration.sh`
3. Update documentation in this file
4. Run full test suite to verify

### Updating Tests

1. Update test code
2. Verify all affected tests pass
3. Update documentation if behavior changed
4. Run full regression suite

## Test Metrics

### Current Coverage

- **Unit Tests**: 50+ test cases
- **Integration Tests**: 15+ scenarios
- **Rust Tests**: 10+ checks
- **Code Coverage**: Aiming for 80%+

### Test Execution Time

- Unit tests: ~5 seconds
- Integration tests: ~10 seconds
- Rust tests: ~30 seconds (including build)
- Total: ~45 seconds

## Troubleshooting

### pytest Not Found

```bash
pip install pytest pytest-mock
```

### Rust Tests Failing

```bash
# Ensure Rust is installed
rustc --version

# Clean and rebuild
cd examples/plugins/rust
cargo clean
cargo build --release
```

### Import Errors

```bash
# Set PYTHONPATH
export PYTHONPATH="/workspace/src:$PYTHONPATH"
```

### Permission Errors

```bash
# Make scripts executable
chmod +x tests/*.sh
chmod +x examples/plugins/rust/*.sh
```

## Best Practices

1. **Test Isolation** - Each test should be independent
2. **Use Fixtures** - Reuse common test setup
3. **Test Edge Cases** - Test error conditions
4. **Performance Tests** - Include performance benchmarks
5. **Documentation** - Document test purpose and expected behavior
6. **CI Integration** - Run tests on every commit
7. **Coverage Tracking** - Monitor code coverage trends

## Additional Resources

- [pytest Documentation](https://docs.pytest.org/)
- [Python Testing Best Practices](https://docs.python-guide.org/writing/tests/)
- [Rust Testing Guide](https://doc.rust-lang.org/book/ch11-00-testing.html)
- [Plugin Development Guide](../docs/CUSTOM_PLUGINS.md)
