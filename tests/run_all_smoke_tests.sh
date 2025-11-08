#!/bin/bash
# Master script to run all smoke tests (original + custom plugins)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                    All Smoke Tests - Master Runner                          ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Track overall results
TOTAL_PASSED=0
TOTAL_FAILED=0
TOTAL_SKIPPED=0

# Function to run a test suite
run_test_suite() {
    local suite_name=$1
    local script_path=$2
    
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}📦 Running: $suite_name${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    
    if [ ! -f "$script_path" ]; then
        echo -e "${YELLOW}⚠️  SKIP: Test script not found: $script_path${NC}"
        TOTAL_SKIPPED=$((TOTAL_SKIPPED + 1))
        return 1
    fi
    
    # Make sure script is executable
    chmod +x "$script_path"
    
    # Run the test suite
    set +e
    "$script_path"
    EXIT_CODE=$?
    set -e
    
    if [ $EXIT_CODE -eq 0 ]; then
        echo -e "${GREEN}✅ PASS: $suite_name${NC}"
        TOTAL_PASSED=$((TOTAL_PASSED + 1))
        return 0
    else
        echo -e "${RED}❌ FAIL: $suite_name${NC}"
        TOTAL_FAILED=$((TOTAL_FAILED + 1))
        return 1
    fi
}

# Check if Rust plugins need to be built
check_rust_plugins() {
    local rust_reader="examples/plugins/rust/target/release/libcsv_reader_plugin.so"
    local rust_writer="examples/plugins/rust/target/release/libparquet_writer_plugin.so"
    
    # Check for .dylib on macOS
    if [[ "$OSTYPE" == "darwin"* ]]; then
        rust_reader="examples/plugins/rust/target/release/libcsv_reader_plugin.dylib"
        rust_writer="examples/plugins/rust/target/release/libparquet_writer_plugin.dylib"
    fi
    
    if [ ! -f "$rust_reader" ] || [ ! -f "$rust_writer" ]; then
        echo -e "${YELLOW}⚠️  Rust plugins not found. Some custom plugin tests may be skipped.${NC}"
        echo "   Build with: cd examples/plugins/rust && cargo build --release"
        echo ""
    else
        echo -e "${GREEN}✅ Rust plugins found${NC}"
    fi
}

# Check environment variables
check_environment() {
    echo "🔍 Checking environment setup..."
    
    local missing_vars=()
    
    # Check required environment variables
    if [ -z "$PGHOST" ] && [ -z "$PGDATABASE" ]; then
        missing_vars+=("PostgreSQL (PGHOST, PGDATABASE, etc.)")
    fi
    
    if [ -z "$MYSQL_HOST" ] && [ -z "$MYSQL_DATABASE" ]; then
        missing_vars+=("MySQL (MYSQL_HOST, MYSQL_DATABASE, etc.)")
    fi
    
    if [ -z "$MINIO_ENDPOINT" ] && [ -z "$S3_ENDPOINT" ]; then
        missing_vars+=("MinIO/S3 (MINIO_ENDPOINT or S3_ENDPOINT)")
    fi
    
    if [ ${#missing_vars[@]} -gt 0 ]; then
        echo -e "${YELLOW}⚠️  Some environment variables may be missing:${NC}"
        for var in "${missing_vars[@]}"; do
            echo "   - $var"
        done
        echo ""
        echo "   Tests may fail if required services are not available."
        echo ""
    else
        echo -e "${GREEN}✅ Environment variables look good${NC}"
    fi
}

# Main execution
echo "🔍 Pre-flight checks..."
check_rust_plugins
check_environment

# Run test suite 1: Original smoke tests
run_test_suite \
    "Original Smoke Tests" \
    "$SCRIPT_DIR/smoke_tests.sh"

# Run test suite 2: Custom plugin smoke tests
run_test_suite \
    "Custom Plugin Smoke Tests" \
    "$SCRIPT_DIR/smoke_tests_custom_plugins.sh"

# Print final summary
echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                         Final Test Summary                                  ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo -e "${GREEN}✅ Passed:  $TOTAL_PASSED${NC}"
echo -e "${RED}❌ Failed:  $TOTAL_FAILED${NC}"
echo -e "${YELLOW}⚠️  Skipped: $TOTAL_SKIPPED${NC}"
echo ""

# Exit with error if any tests failed
if [ $TOTAL_FAILED -gt 0 ]; then
    echo -e "${RED}❌ Some test suites failed!${NC}"
    exit 1
elif [ $TOTAL_PASSED -eq 0 ]; then
    echo -e "${YELLOW}⚠️  No test suites passed!${NC}"
    exit 1
else
    echo -e "${GREEN}✅ All test suites passed!${NC}"
    exit 0
fi

