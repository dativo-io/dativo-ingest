#!/bin/bash
# Integration tests for plugin system
# Tests actual CLI execution with Python and Rust plugins

set -e

echo "=================================="
echo "Plugin System Integration Tests"
echo "=================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Function to run a test
run_test() {
    local test_name="$1"
    local test_command="$2"
    
    TESTS_RUN=$((TESTS_RUN + 1))
    echo -n "Test $TESTS_RUN: $test_name... "
    
    if eval "$test_command" > /dev/null 2>&1; then
        echo -e "${GREEN}PASSED${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        return 0
    else
        echo -e "${RED}FAILED${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        return 1
    fi
}

# Setup test environment
export PYTHONPATH="/workspace/src:$PYTHONPATH"
TEST_DIR=$(mktemp -d)
trap "rm -rf $TEST_DIR" EXIT

echo "Test directory: $TEST_DIR"
echo ""

# ==========================
# Test 1: Default CSV Reader
# ==========================
echo "--- Default Readers and Writers ---"
echo ""

# Create test CSV
cat > "$TEST_DIR/test.csv" <<EOF
id,name,value
1,Alice,100
2,Bob,200
3,Charlie,300
EOF

# Create asset definition
cat > "$TEST_DIR/asset.yaml" <<EOF
name: test_data
version: "1.0"
source_type: csv
object: test
team:
  owner: test@example.com
schema:
  - name: id
    type: integer
  - name: name
    type: string
  - name: value
    type: integer
EOF

run_test "CSV extractor can read file" \
    "python3 -c \"
from dativo_ingest.connectors.csv_extractor import CSVExtractor
from dativo_ingest.config import SourceConfig
config = SourceConfig(type='csv', files=[{'path': '$TEST_DIR/test.csv'}])
extractor = CSVExtractor(config)
batches = list(extractor.extract())
assert len(batches) == 1
assert len(batches[0]) == 3
\""

# ==========================
# Test 2: Custom Python Reader
# ==========================
echo ""
echo "--- Custom Python Plugins ---"
echo ""

# Create custom Python reader
cat > "$TEST_DIR/custom_reader.py" <<'EOF'
from dativo_ingest.plugins import BaseReader

class TestReader(BaseReader):
    def extract(self, state_manager=None):
        # Generate test data
        records = [{"id": i, "value": i * 10} for i in range(1, 6)]
        yield records
        
    def get_total_records_estimate(self):
        return 5
EOF

run_test "Can load custom Python reader" \
    "python3 -c \"
from dativo_ingest.plugins import PluginLoader
reader_class = PluginLoader.load_reader('$TEST_DIR/custom_reader.py:TestReader')
assert reader_class.__name__ == 'TestReader'
\""

run_test "Custom Python reader extracts data" \
    "python3 -c \"
from dativo_ingest.plugins import PluginLoader
from dativo_ingest.config import SourceConfig
reader_class = PluginLoader.load_reader('$TEST_DIR/custom_reader.py:TestReader')
config = SourceConfig(type='test')
reader = reader_class(config)
batches = list(reader.extract())
assert len(batches) == 1
assert len(batches[0]) == 5
assert reader.get_total_records_estimate() == 5
\""

# Create custom Python writer
cat > "$TEST_DIR/custom_writer.py" <<'EOF'
import json
import os
from dativo_ingest.plugins import BaseWriter

class TestWriter(BaseWriter):
    def write_batch(self, records, file_counter):
        os.makedirs(self.output_base, exist_ok=True)
        output_file = f"{self.output_base}/part-{file_counter:05d}.json"
        with open(output_file, "w") as f:
            json.dump(records, f)
        return [{"path": output_file, "size_bytes": len(json.dumps(records)), "record_count": len(records)}]
EOF

run_test "Can load custom Python writer" \
    "python3 -c \"
from dativo_ingest.plugins import PluginLoader
writer_class = PluginLoader.load_writer('$TEST_DIR/custom_writer.py:TestWriter')
assert writer_class.__name__ == 'TestWriter'
\""

run_test "Custom Python writer writes data" \
    "python3 -c \"
from dativo_ingest.plugins import PluginLoader
from dativo_ingest.config import TargetConfig

class MockAsset:
    name = 'test'
    schema = []

writer_class = PluginLoader.load_writer('$TEST_DIR/custom_writer.py:TestWriter')
config = TargetConfig(type='test')
writer = writer_class(MockAsset(), config, '$TEST_DIR/output')
records = [{'id': 1}, {'id': 2}]
metadata = writer.write_batch(records, 0)
assert len(metadata) == 1
assert metadata[0]['record_count'] == 2

# Verify file exists
import os
assert os.path.exists(metadata[0]['path'])
\""

# ==========================
# Test 3: End-to-End Pipeline
# ==========================
echo ""
echo "--- End-to-End Pipeline ---"
echo ""

run_test "Python reader + writer pipeline" \
    "python3 -c \"
from dativo_ingest.plugins import PluginLoader
from dativo_ingest.config import SourceConfig, TargetConfig

class MockAsset:
    name = 'test'
    schema = []

# Load reader and writer
reader_class = PluginLoader.load_reader('$TEST_DIR/custom_reader.py:TestReader')
writer_class = PluginLoader.load_writer('$TEST_DIR/custom_writer.py:TestWriter')

# Create instances
reader = reader_class(SourceConfig(type='test'))
writer = writer_class(MockAsset(), TargetConfig(type='test'), '$TEST_DIR/pipeline_output')

# Run pipeline
total_records = 0
for batch_idx, batch in enumerate(reader.extract()):
    metadata = writer.write_batch(batch, batch_idx)
    total_records += metadata[0]['record_count']

assert total_records == 5
\""

# ==========================
# Test 4: Plugin Type Detection
# ==========================
echo ""
echo "--- Plugin Type Detection ---"
echo ""

run_test "Detects Python plugin from .py extension" \
    "python3 -c \"
from dativo_ingest.plugins import PluginLoader
plugin_type = PluginLoader._detect_plugin_type('/path/to/plugin.py:Class')
assert plugin_type == 'python'
\""

run_test "Detects Rust plugin from .so extension" \
    "python3 -c \"
from dativo_ingest.plugins import PluginLoader
plugin_type = PluginLoader._detect_plugin_type('/path/to/libplugin.so:create_reader')
assert plugin_type == 'rust'
\""

run_test "Detects Rust plugin from .dylib extension" \
    "python3 -c \"
from dativo_ingest.plugins import PluginLoader
plugin_type = PluginLoader._detect_plugin_type('/path/to/libplugin.dylib:create_reader')
assert plugin_type == 'rust'
\""

run_test "Detects Rust plugin from .dll extension" \
    "python3 -c \"
from dativo_ingest.plugins import PluginLoader
plugin_type = PluginLoader._detect_plugin_type('/path/to/plugin.dll:create_reader')
assert plugin_type == 'rust'
\""

# ==========================
# Test 5: Error Handling
# ==========================
echo ""
echo "--- Error Handling ---"
echo ""

# Create reader that throws error
cat > "$TEST_DIR/error_reader.py" <<'EOF'
from dativo_ingest.plugins import BaseReader

class ErrorReader(BaseReader):
    def extract(self, state_manager=None):
        raise ValueError("Intentional test error")
EOF

run_test "Reader errors are propagated" \
    "python3 -c \"
from dativo_ingest.plugins import PluginLoader
from dativo_ingest.config import SourceConfig
reader_class = PluginLoader.load_reader('$TEST_DIR/error_reader.py:ErrorReader')
reader = reader_class(SourceConfig(type='test'))
try:
    list(reader.extract())
    assert False, 'Should have raised error'
except ValueError as e:
    assert 'Intentional test error' in str(e)
\""

run_test "Missing plugin file raises error" \
    "python3 -c \"
from dativo_ingest.plugins import PluginLoader
try:
    PluginLoader.load_reader('/nonexistent/plugin.py:Class')
    assert False, 'Should have raised error'
except ValueError as e:
    assert 'not found' in str(e)
\""

run_test "Invalid plugin format raises error" \
    "python3 -c \"
from dativo_ingest.plugins import PluginLoader
try:
    PluginLoader.load_reader('invalid_format_without_colon')
    assert False, 'Should have raised error'
except ValueError as e:
    assert 'must be in format' in str(e)
\""

# ==========================
# Test 6: Rust Plugin Bridge
# ==========================
echo ""
echo "--- Rust Plugin Bridge ---"
echo ""

run_test "Rust bridge module can be imported" \
    "python3 -c \"
from dativo_ingest.rust_plugin_bridge import RustReaderWrapper, RustWriterWrapper
assert RustReaderWrapper is not None
assert RustWriterWrapper is not None
\""

run_test "Rust wrapper serializes config to JSON" \
    "python3 -c \"
import json
from dativo_ingest.rust_plugin_bridge import RustReaderWrapper
from dativo_ingest.config import SourceConfig

config = SourceConfig(
    type='test',
    connection={'url': 'http://test'},
    credentials={'token': 'secret'},
    objects=['table1']
)

# Create wrapper without library (just for testing serialization)
wrapper = object.__new__(RustReaderWrapper)
wrapper.source_config = config
config_json = wrapper._serialize_config()
config_dict = json.loads(config_json)

assert config_dict['type'] == 'test'
assert config_dict['connection']['url'] == 'http://test'
assert 'table1' in config_dict['objects']
\""

# ==========================
# Summary
# ==========================
echo ""
echo "=================================="
echo "Test Summary"
echo "=================================="
echo "Total tests run: $TESTS_RUN"
echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Failed: ${RED}$TESTS_FAILED${NC}"
echo ""

if [ $TESTS_FAILED -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed!${NC}"
    exit 1
fi
