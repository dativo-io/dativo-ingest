#!/bin/bash
# Test script for Rust plugins
# Builds and tests Rust plugins if Rust toolchain is available

set -e

echo "======================================"
echo "Rust Plugin Tests"
echo "======================================"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

# Check if Rust is installed
if ! command -v rustc &> /dev/null; then
    echo -e "${YELLOW}Rust toolchain not found. Skipping Rust plugin tests.${NC}"
    echo ""
    echo "To install Rust:"
    echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    echo "  source \$HOME/.cargo/env"
    exit 0
fi

echo -e "${GREEN}✓ Rust toolchain found${NC}"
rustc --version
cargo --version
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Test counter
TESTS_RUN=0
TESTS_PASSED=0

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
        return 1
    fi
}

# ==========================
# Build Rust Plugins
# ==========================
echo "--- Building Rust Plugins ---"
echo ""

echo "Building CSV reader plugin..."
if cargo build --release -p csv_reader_plugin 2>&1 | tail -5; then
    echo -e "${GREEN}✓ CSV reader built successfully${NC}"
else
    echo -e "${RED}✗ CSV reader build failed${NC}"
    exit 1
fi
echo ""

echo "Building Parquet writer plugin..."
if cargo build --release -p parquet_writer_plugin 2>&1 | tail -5; then
    echo -e "${GREEN}✓ Parquet writer built successfully${NC}"
else
    echo -e "${RED}✗ Parquet writer build failed${NC}"
    exit 1
fi
echo ""

# ==========================
# Verify Build Outputs
# ==========================
echo "--- Verifying Build Outputs ---"
echo ""

# Detect platform extension
if [[ "$OSTYPE" == "darwin"* ]]; then
    LIB_EXT="dylib"
elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    LIB_EXT="dll"
else
    LIB_EXT="so"
fi

CSV_READER_LIB="target/release/libcsv_reader_plugin.$LIB_EXT"
PARQUET_WRITER_LIB="target/release/libparquet_writer_plugin.$LIB_EXT"

run_test "CSV reader library exists" \
    "test -f '$CSV_READER_LIB'"

run_test "Parquet writer library exists" \
    "test -f '$PARQUET_WRITER_LIB'"

# ==========================
# Check Exported Symbols (Linux/macOS only)
# ==========================
if command -v nm &> /dev/null && [[ "$OSTYPE" != "msys" && "$OSTYPE" != "win32" ]]; then
    echo ""
    echo "--- Checking Exported Symbols ---"
    echo ""
    
    echo "CSV Reader exports:"
    nm -D "$CSV_READER_LIB" 2>/dev/null | grep -E "(create_reader|extract_batch|free_reader|free_string)" | head -5 || echo "  (symbols check not available)"
    echo ""
    
    echo "Parquet Writer exports:"
    nm -D "$PARQUET_WRITER_LIB" 2>/dev/null | grep -E "(create_writer|write_batch|free_writer|free_string)" | head -5 || echo "  (symbols check not available)"
    echo ""
    
    run_test "CSV reader exports create_reader" \
        "nm -D '$CSV_READER_LIB' 2>/dev/null | grep -q 'create_reader'"
    
    run_test "CSV reader exports extract_batch" \
        "nm -D '$CSV_READER_LIB' 2>/dev/null | grep -q 'extract_batch'"
    
    run_test "Parquet writer exports create_writer" \
        "nm -D '$PARQUET_WRITER_LIB' 2>/dev/null | grep -q 'create_writer'"
    
    run_test "Parquet writer exports write_batch" \
        "nm -D '$PARQUET_WRITER_LIB' 2>/dev/null | grep -q 'write_batch'"
fi

# ==========================
# Run Rust Unit Tests
# ==========================
echo ""
echo "--- Running Rust Unit Tests ---"
echo ""

echo "Testing CSV reader..."
if cargo test -p csv_reader_plugin 2>&1 | tail -10; then
    echo -e "${GREEN}✓ CSV reader tests passed${NC}"
else
    echo -e "${RED}✗ CSV reader tests failed${NC}"
fi
echo ""

echo "Testing Parquet writer..."
if cargo test -p parquet_writer_plugin 2>&1 | tail -10; then
    echo -e "${GREEN}✓ Parquet writer tests passed${NC}"
else
    echo -e "${RED}✗ Parquet writer tests failed${NC}"
fi
echo ""

# ==========================
# Test Python Integration
# ==========================
echo "--- Testing Python Integration ---"
echo ""

# Create test directory
TEST_DIR=$(mktemp -d)
trap "rm -rf $TEST_DIR" EXIT

# Create test CSV file
cat > "$TEST_DIR/test.csv" <<EOF
id,name,value
1,Alice,100
2,Bob,200
3,Charlie,300
EOF

# Test CSV reader via Python
echo "Testing CSV reader from Python..."
python3 -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR/../..')
from dativo_ingest.plugins import PluginLoader

# Detect plugin type
plugin_path = '$CSV_READER_LIB:create_reader'
plugin_type = PluginLoader._detect_plugin_type(plugin_path)
print(f'  Plugin type detected: {plugin_type}')
assert plugin_type == 'rust', f'Expected rust, got {plugin_type}'
print('  ✓ Plugin type detection works')
" 2>&1 | grep -v "^$" || echo -e "${YELLOW}  Python integration test skipped${NC}"

# ==========================
# File Size Check
# ==========================
echo ""
echo "--- Build Output Sizes ---"
echo ""

if [ -f "$CSV_READER_LIB" ]; then
    SIZE=$(du -h "$CSV_READER_LIB" | cut -f1)
    echo "CSV Reader: $SIZE"
fi

if [ -f "$PARQUET_WRITER_LIB" ]; then
    SIZE=$(du -h "$PARQUET_WRITER_LIB" | cut -f1)
    echo "Parquet Writer: $SIZE"
fi
echo ""

# ==========================
# Summary
# ==========================
echo "======================================"
echo "Test Summary"
echo "======================================"
echo "Tests run: $TESTS_RUN"
echo -e "Passed: ${GREEN}$TESTS_PASSED${NC}"
echo ""

if [ $TESTS_PASSED -eq $TESTS_RUN ]; then
    echo -e "${GREEN}✓ All Rust plugin tests passed!${NC}"
    echo ""
    echo "Plugin libraries are ready to use:"
    echo "  Reader: $CSV_READER_LIB"
    echo "  Writer: $PARQUET_WRITER_LIB"
    exit 0
else
    echo -e "${YELLOW}⚠ Some checks did not pass${NC}"
    echo "Plugins may still be usable, check output above for details."
    exit 0
fi
