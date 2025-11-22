# Testing Strategy

Dativo uses a two-tier testing approach:

## 1. Unit Tests (`test_m1_1_cli.py`)

**Purpose**: Test internal functions and modules in isolation

**What they test**:
- Config loading and parsing
- Schema validation logic
- Connector validation
- Incremental state management
- Error handling

**Why we need them**:
- Fast execution
- Isolated testing of individual components
- Easy to debug failures
- Code coverage tracking

**Run with**:
```bash
# Run all unit tests
pytest tests/test_*.py -v

# Run specific test file
pytest tests/test_config.py -v
pytest tests/test_validator.py -v
pytest tests/test_state.py -v

# Or using Makefile
make test-unit
```

## 2. Smoke Tests

**Purpose**: Test the actual CLI execution with real fixtures

**What they test**:
- Full CLI command execution
- Startup sequence (config loading, secrets, infrastructure)
- End-to-end job execution
- Integration with actual connectors

**Why we need them**:
- Verify the CLI works as users would use it
- Test real-world scenarios
- Catch integration issues
- Validate the full pipeline

**Run with**:
```bash
# Direct CLI command (recommended)
dativo run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted

# Or using Python module (if dativo command not available)
python -m dativo_ingest.cli run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted

# Or using Makefile
make test-smoke
```

**Note**: Smoke tests are just running the CLI directly with test fixtures. No special test code needed!

## Why Not Pytest for Smoke Tests?

For a config-driven system, smoke tests should simply run the CLI directly with test fixtures:

1. **Run the actual CLI commands** that users would run
2. **Check exit codes** to verify success/failure
3. **No special test code needed** - just use the CLI

This approach:
- ✅ Tests what users actually do
- ✅ Simpler and more maintainable
- ✅ No need for pytest fixtures for CLI execution
- ✅ Easy to add new test cases

## Adding New Smoke Tests

Simply add new job configurations to `tests/fixtures/jobs/` and run the CLI:

```bash
# Add new job config: tests/fixtures/jobs/new_job.yaml
# Then run:
dativo run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted
```

## Test Fixtures

All test fixtures are in `tests/fixtures/`:
- `jobs/` - Job configurations
- `assets/` - Asset definitions
- `seeds/` - Test data files
- `secrets/` - Test secrets (placeholders)

## Running All Tests

```bash
make test  # Runs both unit and smoke tests
```

---

## Plugin Testing

The plugin system is tested at multiple levels:

1. **Unit Tests** - Test individual components (base classes, loaders, validators)
2. **Integration Tests** - Test plugin loading and execution
3. **End-to-End Tests** - Test complete ETL pipelines with plugins
4. **Performance Tests** - Test plugin performance characteristics
5. **Rust Plugin Tests** - Test Rust plugin builds and integration

### Quick Start

```bash
# Run complete plugin test suite
./tests/run_all_plugin_tests.sh

# Unit tests only (pytest)
pytest tests/test_plugins.py -v

# Integration tests only
./tests/test_plugin_integration.sh

# Rust plugin tests only
./examples/plugins/rust/test_rust_plugins.sh
```

### Test Coverage

#### Unit Tests (`test_plugins.py`)

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

#### Integration Tests (`test_plugin_integration.sh`)

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

#### Rust Plugin Tests (`test_rust_plugins.sh`)

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

### Test Environment Setup

#### Python Environment

```bash
# Install test dependencies
pip install pytest pytest-mock

# Set Python path
export PYTHONPATH="src:$PYTHONPATH"
```

#### Rust Environment (Optional)

```bash
# Install Rust
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env

# Build Rust plugins
cd examples/plugins/rust
make build-release
```

### Writing Plugin Tests

#### Testing a Custom Python Reader

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

#### Testing a Custom Python Writer

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
    writer = writer_class(MockAsset(), target_config, str(tmp_path))
    
    # Verify
    result = writer.write_batch([{"id": 1}], 1)
    assert len(result) == 1
    assert result[0]["path"] == "test.dat"
```

### CI Integration

Plugin tests are automatically run in GitHub Actions CI/CD:

- **Main CI Pipeline** (`ci.yml`): Runs plugin tests on every PR
- **Plugin-Specific Tests** (`plugin-tests.yml`): Comprehensive plugin test suite
- **Matrix Testing**: Tests on Python 3.10, 3.11, Ubuntu, and macOS

See [.github/workflows/README.md](../.github/workflows/README.md) for more details.

### Test Statistics

**Total Tests:**
- **47** Python plugin unit tests
- **19** Python plugin integration tests
- **10** Rust plugin tests
- **Total: 76+ tests** for the plugin system

### See Also

- [docs/CUSTOM_PLUGINS.md](../docs/CUSTOM_PLUGINS.md) - Custom plugins guide
- [examples/plugins/README.md](../examples/plugins/README.md) - Plugin examples
- [examples/plugins/rust/README.md](../examples/plugins/rust/README.md) - Rust plugin guide

