#!/usr/bin/env bash
# Performance tests for dativo-ingest
# Requires bash 4.0+ for associative arrays
# 
# Tests 4 scenarios:
# 1. CSV reader (Python) -> Iceberg table on S3 (MinIO)
# 2. CSV reader (Rust) -> Iceberg table on S3 (MinIO)
# 3. Iceberg table on S3 (MinIO) -> CSV writer (Python)
# 4. Iceberg table on S3 (MinIO) -> CSV writer (Rust)
#
# This follows the same pattern as smoke tests - runs actual CLI commands
# with job configurations from tests/fixtures/jobs/
#
# Requirements:
# - Docker (for MinIO and Nessie)
# - Rust (optional, for Rust plugin tests)
# - Python dependencies installed
#
# Usage: ./run_performance_tests.sh [--skip-infrastructure-setup] [--skip-data-generation]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Parse command line flags
SKIP_INFRASTRUCTURE_SETUP=false
SKIP_DATA_GENERATION=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-infrastructure-setup)
            SKIP_INFRASTRUCTURE_SETUP=true
            shift
            ;;
        --skip-data-generation)
            SKIP_DATA_GENERATION=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-infrastructure-setup] [--skip-data-generation]"
            exit 1
            ;;
    esac
done

# Configuration
PERF_TEST_CSV_FILE="${PERF_TEST_CSV_FILE:-tests/fixtures/seeds/perf_test_data_1gb.csv}"
TENANT_ID="perf_test_tenant"
RESULTS_DIR="/tmp/dativo_perf_test_results"
mkdir -p "$RESULTS_DIR"

# Performance metrics (using simple variables instead of associative arrays for bash 3.2 compatibility)
TEST1_STATUS=""
TEST1_DURATION=""
TEST2_STATUS=""
TEST2_DURATION=""
TEST3_STATUS=""
TEST3_DURATION=""
TEST4_STATUS=""
TEST4_DURATION=""

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                    Performance Test Suite                                   ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""

# Function to print section header
print_section() {
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
}

# Function to check prerequisites
check_prerequisites() {
    print_section "Checking Prerequisites"
    
    local errors=0
    
    # Check Docker
    if ! command -v docker >/dev/null 2>&1; then
        echo -e "${RED}❌ Docker not found${NC}"
        errors=$((errors + 1))
    elif ! docker info >/dev/null 2>&1; then
        echo -e "${RED}❌ Docker daemon not running${NC}"
        errors=$((errors + 1))
    else
        echo -e "${GREEN}✅ Docker is available${NC}"
    fi
    
    # Check Python
    if ! command -v python3 >/dev/null 2>&1; then
        echo -e "${RED}❌ Python3 not found${NC}"
        errors=$((errors + 1))
    else
        echo -e "${GREEN}✅ Python3 is available${NC}"
    fi
    
    # Check Rust (optional)
    if ! command -v cargo >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Rust/Cargo not found - Rust plugin tests will be skipped${NC}"
    else
        echo -e "${GREEN}✅ Rust/Cargo is available${NC}"
    fi
    
    if [ $errors -gt 0 ]; then
        echo ""
        echo -e "${RED}❌ Prerequisites check failed. Please install missing dependencies.${NC}"
        exit 1
    fi
}

# Function to setup infrastructure (reuse existing script)
setup_infrastructure() {
    print_section "Setting Up Infrastructure"
    
    if [ "$SKIP_INFRASTRUCTURE_SETUP" = "true" ]; then
        echo "ℹ️  Skipping infrastructure setup (--skip-infrastructure-setup flag)"
        echo "   Assuming services are already running..."
        return
    fi
    
    if [ -f "$SCRIPT_DIR/setup_smoke_test_infrastructure.sh" ]; then
        echo "Using existing infrastructure setup script..."
        bash "$SCRIPT_DIR/setup_smoke_test_infrastructure.sh" --no-teardown || {
            echo -e "${YELLOW}⚠️  Infrastructure setup had issues, but continuing...${NC}"
        }
    else
        echo -e "${RED}❌ Infrastructure setup script not found${NC}"
        exit 1
    fi
    
    # Set environment variables
    export S3_ENDPOINT="${S3_ENDPOINT:-http://localhost:9000}"
    export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-minioadmin}"
    export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-minioadmin}"
    export AWS_REGION="${AWS_REGION:-us-east-1}"
    export S3_BUCKET="${S3_BUCKET:-test-bucket}"
    export NESSIE_URI="${NESSIE_URI:-http://localhost:19120/api/v1}"
    export STATE_DIR="${STATE_DIR:-/tmp/dativo-state}"
    mkdir -p "$STATE_DIR/$TENANT_ID"
    
    echo -e "${GREEN}✅ Infrastructure ready${NC}"
}

# Function to generate test data
generate_test_data() {
    print_section "Generating Test Data"
    
    if [ "$SKIP_DATA_GENERATION" = "true" ]; then
        echo "ℹ️  Skipping data generation (--skip-data-generation flag)"
        if [ ! -f "$PERF_TEST_CSV_FILE" ]; then
            echo -e "${RED}❌ Test data file not found: $PERF_TEST_CSV_FILE${NC}"
            echo "   Generate it with: python tests/scripts/generate_perf_test_data.py"
            exit 1
        fi
        echo -e "${GREEN}✅ Using existing test data: $PERF_TEST_CSV_FILE${NC}"
        return
    fi
    
    if [ -f "$PERF_TEST_CSV_FILE" ]; then
        local file_size=$(du -h "$PERF_TEST_CSV_FILE" | cut -f1)
        echo -e "${YELLOW}⚠️  Test data file already exists: $PERF_TEST_CSV_FILE ($file_size)${NC}"
        # In non-interactive mode (like CI), use existing file
        if [ -t 0 ]; then
            # Interactive mode - ask user
            read -p "Regenerate? (y/N): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                echo "Using existing file..."
                return
            fi
        else
            # Non-interactive mode - use existing file
            echo "Using existing file (non-interactive mode)..."
            return
        fi
    fi
    
    echo "Generating 1GB CSV file..."
    if [ -f "$SCRIPT_DIR/scripts/generate_perf_test_data.py" ]; then
        python3 "$SCRIPT_DIR/scripts/generate_perf_test_data.py" --output "$PERF_TEST_CSV_FILE"
    else
        echo -e "${RED}❌ Data generation script not found${NC}"
        exit 1
    fi
    
    if [ ! -f "$PERF_TEST_CSV_FILE" ]; then
        echo -e "${RED}❌ Failed to generate test data${NC}"
        exit 1
    fi
    
    local file_size=$(du -h "$PERF_TEST_CSV_FILE" | cut -f1)
    echo -e "${GREEN}✅ Test data generated: $PERF_TEST_CSV_FILE ($file_size)${NC}"
}

# Function to build Rust plugins
build_rust_plugins() {
    print_section "Building Rust Plugins"
    
    if ! command -v cargo >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  Rust not available, skipping Rust plugin build${NC}"
        return 1
    fi
    
    local rust_dir="$PROJECT_ROOT/examples/plugins/rust"
    if [ ! -d "$rust_dir" ]; then
        echo -e "${YELLOW}⚠️  Rust plugins directory not found: $rust_dir${NC}"
        return 1
    fi
    
    echo "Building Rust plugins..."
    cd "$rust_dir"
    
    if cargo build --release >/tmp/rust_build.log 2>&1; then
        echo -e "${GREEN}✅ Rust plugins built successfully${NC}"
        cd "$PROJECT_ROOT"
        return 0
    else
        echo -e "${YELLOW}⚠️  Rust plugin build failed (check /tmp/rust_build.log)${NC}"
        cd "$PROJECT_ROOT"
        return 1
    fi
}

# Function to run a performance test (follows smoke test pattern)
run_performance_test() {
    local test_name=$1
    local test_desc=$2
    local job_config=$3
    
    print_section "Test: $test_name"
    echo "Description: $test_desc"
    
    if [ ! -f "$job_config" ]; then
        echo -e "${RED}❌ Job config not found: $job_config${NC}"
        set_test_result "$test_name" "SKIPPED" "" "Config file not found"
        return 1
    fi
    
    # Set CSV file path for job configs
    export PERF_TEST_CSV_FILE
    
    local start_time=$(date +%s.%N)
    local result_file="$RESULTS_DIR/${test_name}_result.json"
    
    echo "Running job..."
    # Use venv Python if available, otherwise use system python3
    if [ -f "$PROJECT_ROOT/venv/bin/python" ]; then
        PYTHON_CMD="$PROJECT_ROOT/venv/bin/python"
    else
        PYTHON_CMD="python3"
    fi
    
    PYTHONPATH=src "$PYTHON_CMD" -m dativo_ingest.cli run \
        --config "$job_config" \
        --secrets-dir "$SCRIPT_DIR/fixtures/secrets" \
        --mode self_hosted \
        > "$RESULTS_DIR/${test_name}_output.log" 2>&1
    
    local exit_code=$?
    local end_time=$(date +%s.%N)
    local duration=$(echo "$end_time - $start_time" | bc)
    
    if [ $exit_code -eq 0 ]; then
        echo -e "${GREEN}✅ Test completed successfully${NC}"
        echo "Duration: ${duration}s"
        set_test_result "$test_name" "PASSED" "$duration" ""
    else
        echo -e "${RED}❌ Test failed${NC}"
        echo "Duration: ${duration}s"
        echo "Check logs: $RESULTS_DIR/${test_name}_output.log"
        set_test_result "$test_name" "FAILED" "$duration" "See output log"
    fi
    
    return $exit_code
}

# Function to cleanup
cleanup() {
    print_section "Cleaning Up Test Data"
    
    echo "Cleaning up MinIO bucket (performance test data)..."
    if command -v mc >/dev/null 2>&1; then
        mc alias set local http://localhost:9000 minioadmin minioadmin 2>/dev/null || true
        mc rm --recursive --force "local/test-bucket/perf_test_db" 2>/dev/null || true
        echo "✅ MinIO bucket cleaned"
    else
        echo -e "${YELLOW}⚠️  MinIO client (mc) not found. Manual cleanup may be needed.${NC}"
    fi
    
    echo -e "${GREEN}✅ Cleanup complete${NC}"
    echo ""
    echo "Test results and logs available in: $RESULTS_DIR"
    echo "CSV test data preserved at: $PERF_TEST_CSV_FILE"
}

# Function to set test result (bash 3.2 compatible)
set_test_result() {
    local test_name=$1
    local status=$2
    local duration=$3
    local error=$4
    
    case "$test_name" in
        performance_test_1_csv_python_to_iceberg)
            TEST1_STATUS="$status"
            TEST1_DURATION="${duration:-N/A}"
            ;;
        performance_test_2_csv_rust_to_iceberg)
            TEST2_STATUS="$status"
            TEST2_DURATION="${duration:-N/A}"
            ;;
        performance_test_3_iceberg_to_csv_python)
            TEST3_STATUS="$status"
            TEST3_DURATION="${duration:-N/A}"
            ;;
        performance_test_4_iceberg_to_csv_rust)
            TEST4_STATUS="$status"
            TEST4_DURATION="${duration:-N/A}"
            ;;
    esac
}

# Function to get test result
get_test_result() {
    local test_name=$1
    case "$test_name" in
        performance_test_1_csv_python_to_iceberg)
            echo "${TEST1_STATUS:-SKIPPED}|${TEST1_DURATION:-N/A}"
            ;;
        performance_test_2_csv_rust_to_iceberg)
            echo "${TEST2_STATUS:-SKIPPED}|${TEST2_DURATION:-N/A}"
            ;;
        performance_test_3_iceberg_to_csv_python)
            echo "${TEST3_STATUS:-SKIPPED}|${TEST3_DURATION:-N/A}"
            ;;
        performance_test_4_iceberg_to_csv_rust)
            echo "${TEST4_STATUS:-SKIPPED}|${TEST4_DURATION:-N/A}"
            ;;
        *)
            echo "SKIPPED|N/A"
            ;;
    esac
}

# Function to print results summary
print_results() {
    print_section "Performance Test Results Summary"
    
    echo ""
    echo "Test Results:"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    printf "%-50s %-15s %-15s\n" "Test" "Status" "Duration (s)"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    local test_names=(
        "performance_test_1_csv_python_to_iceberg"
        "performance_test_2_csv_rust_to_iceberg"
        "performance_test_3_iceberg_to_csv_python"
        "performance_test_4_iceberg_to_csv_rust"
    )
    
    for test_name in "${test_names[@]}"; do
        local result=$(get_test_result "$test_name")
        local status=$(echo "$result" | cut -d'|' -f1)
        local duration=$(echo "$result" | cut -d'|' -f2)
        
        if [ "$status" = "PASSED" ]; then
            printf "%-50s ${GREEN}%-15s${NC} %-15s\n" "$test_name" "$status" "$duration"
        elif [ "$status" = "FAILED" ]; then
            printf "%-50s ${RED}%-15s${NC} %-15s\n" "$test_name" "$status" "$duration"
        else
            printf "%-50s ${YELLOW}%-15s${NC} %-15s\n" "$test_name" "$status" "$duration"
        fi
    done
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    echo "Detailed logs available in: $RESULTS_DIR"
}

# Main execution
main() {
    # Trap cleanup on exit
    trap cleanup EXIT
    
    check_prerequisites
    setup_infrastructure
    generate_test_data
    
    # Build Rust plugins if available
    if command -v cargo >/dev/null 2>&1; then
        build_rust_plugins || echo -e "${YELLOW}⚠️  Continuing without Rust plugins...${NC}"
    fi
    
    # Run tests (following smoke test pattern - just run CLI commands)
    echo ""
    echo "╔══════════════════════════════════════════════════════════════════════════════╗"
    echo "║                    Running Performance Tests                                 ║"
    echo "╚══════════════════════════════════════════════════════════════════════════════╝"
    
    # Test 1: CSV (Python) -> Iceberg
    run_performance_test \
        "performance_test_1_csv_python_to_iceberg" \
        "CSV reader (Python) -> Iceberg table on S3 (MinIO)" \
        "$SCRIPT_DIR/fixtures/jobs/performance_test_1_csv_python_to_iceberg.yaml"
    
    # Test 2: CSV (Rust) -> Iceberg
    if [ -f "$PROJECT_ROOT/examples/plugins/rust/target/release/libcsv_reader_plugin.so" ] || \
       [ -f "$PROJECT_ROOT/examples/plugins/rust/target/release/libcsv_reader_plugin.dylib" ]; then
        run_performance_test \
            "performance_test_2_csv_rust_to_iceberg" \
            "CSV reader (Rust) -> Iceberg table on S3 (MinIO)" \
            "$SCRIPT_DIR/fixtures/jobs/performance_test_2_csv_rust_to_iceberg.yaml"
    else
        echo -e "${YELLOW}⚠️  Skipping Test 2: Rust CSV reader plugin not found${NC}"
        set_test_result "performance_test_2_csv_rust_to_iceberg" "SKIPPED" "" "Rust plugin not found"
    fi
    
    # Test 3: Iceberg -> CSV (Python)
    # Wait a bit for Iceberg writes to complete
    sleep 2
    run_performance_test \
        "performance_test_3_iceberg_to_csv_python" \
        "Iceberg table on S3 (MinIO) -> CSV writer (Python)" \
        "$SCRIPT_DIR/fixtures/jobs/performance_test_3_iceberg_to_csv_python.yaml"
    
    # Test 4: Iceberg -> CSV (Rust)
    run_performance_test \
        "performance_test_4_iceberg_to_csv_rust" \
        "Iceberg table on S3 (MinIO) -> CSV writer (Rust)" \
        "$SCRIPT_DIR/fixtures/jobs/performance_test_4_iceberg_to_csv_rust.yaml"
    
    print_results
}

# Run main
main
