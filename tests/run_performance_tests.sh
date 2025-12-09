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
CYAN='\033[0;36m'
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

# Track whether we generated the test data file (so we only delete files we created)
DATA_FILE_GENERATED=false

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
    
    # Check bc (for calculations)
    if ! command -v bc >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️  bc not found - performance comparisons will be limited${NC}"
        echo "   Install with: brew install bc (macOS) or apt-get install bc (Linux)"
    else
        echo -e "${GREEN}✅ bc is available (for calculations)${NC}"
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
    
    # Set environment variables (always needed, even when skipping infrastructure setup)
    # These use default values if not already set, assuming services are running with default config
    export S3_ENDPOINT="${S3_ENDPOINT:-http://localhost:9000}"
    export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-minioadmin}"
    export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-minioadmin}"
    export AWS_REGION="${AWS_REGION:-us-east-1}"
    export S3_BUCKET="${S3_BUCKET:-test-bucket}"
    export NESSIE_URI="${NESSIE_URI:-http://localhost:19120/api/v1}"
    export STATE_DIR="${STATE_DIR:-/tmp/dativo-state}"
    mkdir -p "$STATE_DIR/$TENANT_ID"
    
    if [ "$SKIP_INFRASTRUCTURE_SETUP" = "true" ]; then
        echo "ℹ️  Skipping infrastructure setup (--skip-infrastructure-setup flag)"
        echo "   Assuming services are already running..."
        echo "   Using environment variables:"
        echo "     S3_ENDPOINT=$S3_ENDPOINT"
        echo "     NESSIE_URI=$NESSIE_URI"
        echo "     STATE_DIR=$STATE_DIR"
        echo -e "${GREEN}✅ Environment variables set${NC}"
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
    
    echo -e "${GREEN}✅ Infrastructure ready${NC}"
}

# Function to generate test data
generate_test_data() {
    print_section "Generating Test Data"
    
    if [ "$SKIP_DATA_GENERATION" = "true" ]; then
        echo "ℹ️  Skipping data generation (--skip-data-generation flag)"
        if [ ! -f "$PERF_TEST_CSV_FILE" ]; then
            echo -e "${RED}❌ Test data file not found: $PERF_TEST_CSV_FILE${NC}"
            echo "   Generate it with: dativo_ingest run --config configs/jobs/mimesis_perf_test.yaml"
            echo "   (Legacy script: python tests/scripts/legacy/generate_perf_test_data.py - deprecated)"
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
    
    echo "Generating test data using Mimesis connector..."
    
    # Use mimesis connector job to generate data
    # Note: Mimesis connector is the canonical way to generate synthetic data
    MIAMESIS_JOB_CONFIG="$PROJECT_ROOT/configs/jobs/mimesis_perf_test.yaml"
    
    if [ ! -f "$MIAMESIS_JOB_CONFIG" ]; then
        echo -e "${RED}❌ Mimesis job config not found: $MIAMESIS_JOB_CONFIG${NC}"
        echo "   Please ensure the mimesis connector is properly configured."
        exit 1
    fi
    
    # Run mimesis job (generates Parquet)
    echo "Running mimesis connector job to generate performance test data..."
    PYTHONPATH=src python3 -m dativo_ingest.cli run \
        --config "$MIAMESIS_JOB_CONFIG" \
        --secrets-dir "$SCRIPT_DIR/fixtures/secrets" \
        --mode self_hosted || {
        echo -e "${RED}❌ Failed to generate test data using mimesis connector${NC}"
        exit 1
    }
    
    # Note: Mimesis generates Parquet files, not CSV
    # Future work: Migrate tests to read Parquet directly, removing CSV fallback
    # If CSV is specifically needed for tests, consider:
    # 1. Updating tests to read Parquet instead (preferred)
    # 2. Adding a Parquet-to-CSV conversion step
    # 3. Using a custom CSV writer plugin
    
    # For now, check if we need to generate CSV for backward compatibility
    # This is a temporary measure until tests are updated to use Parquet
    LEGACY_SCRIPT="$SCRIPT_DIR/scripts/legacy/generate_perf_test_data.py"
    if [ ! -f "$PERF_TEST_CSV_FILE" ] && [ -f "$LEGACY_SCRIPT" ]; then
        echo -e "${YELLOW}⚠️  Tests expect CSV format. Generating CSV using legacy script as fallback.${NC}"
        echo "   Consider updating tests to use Parquet format generated by mimesis connector."
        python3 "$LEGACY_SCRIPT" --output "$PERF_TEST_CSV_FILE" || {
            echo -e "${RED}❌ Failed to generate CSV fallback${NC}"
            exit 1
        }
    fi
    
    if [ ! -f "$PERF_TEST_CSV_FILE" ]; then
        echo -e "${YELLOW}⚠️  CSV file not generated. Tests may need to be updated to use Parquet.${NC}"
        # Don't fail here - let tests handle missing file
        return
    fi
    
    # Only mark as generated and report success if file actually exists
    if [ -f "$PERF_TEST_CSV_FILE" ]; then
        # Mark that we generated this file (so cleanup knows it's safe to delete)
        DATA_FILE_GENERATED=true
        
        local file_size=$(du -h "$PERF_TEST_CSV_FILE" | cut -f1)
        echo -e "${GREEN}✅ Test data generated: $PERF_TEST_CSV_FILE ($file_size)${NC}"
    fi
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
    # Calculate duration (use awk if bc not available)
    local duration
    if command -v bc >/dev/null 2>&1; then
        duration=$(echo "$end_time - $start_time" | bc)
    else
        duration=$(awk "BEGIN {printf \"%.2f\", $end_time - $start_time}")
    fi
    
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
        # Clean up Nessie catalog database
        mc rm --recursive --force "local/test-bucket/perf_test_db" 2>/dev/null || true
        # Clean up performance test data (Parquet and CSV files)
        # Path structure: dativo/performance_test/perf_test_data/
        mc rm --recursive --force "local/test-bucket/dativo/performance_test/perf_test_data" 2>/dev/null || true
        echo "✅ MinIO bucket cleaned"
    else
        echo -e "${YELLOW}⚠️  MinIO client (mc) not found. Manual cleanup may be needed.${NC}"
    fi
    
    # Clean up generated performance test data files (only if we generated them)
    if [ "$DATA_FILE_GENERATED" = "true" ]; then
        echo "Cleaning up generated performance test data files..."
        if [ -f "$PERF_TEST_CSV_FILE" ]; then
            rm -f "$PERF_TEST_CSV_FILE"
            echo "✅ Removed: $PERF_TEST_CSV_FILE"
        fi
    else
        echo "ℹ️  Skipping test data cleanup (file was not generated by this script)"
    fi
    
    echo -e "${GREEN}✅ Cleanup complete${NC}"
    echo ""
    echo "Test results and logs available in: $RESULTS_DIR"
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

# Function to get numeric duration (for calculations)
get_numeric_duration() {
    local duration=$1
    if [ "$duration" = "N/A" ] || [ -z "$duration" ]; then
        echo "0"
    else
        echo "$duration"
    fi
}

# Function to format duration
format_duration() {
    local duration=$1
    if [ "$duration" = "N/A" ] || [ -z "$duration" ]; then
        echo "N/A"
    else
        # Convert to readable format (seconds with 2 decimal places)
        printf "%.2f" "$duration" 2>/dev/null || echo "$duration"
    fi
}

# Function to calculate speedup
calculate_speedup() {
    local baseline=$1
    local comparison=$2
    if [ "$baseline" = "0" ] || [ "$baseline" = "N/A" ] || [ "$comparison" = "0" ] || [ "$comparison" = "N/A" ]; then
        echo "N/A"
    else
        if command -v bc >/dev/null 2>&1; then
            local speedup=$(echo "scale=2; $baseline / $comparison" | bc 2>/dev/null || echo "N/A")
            echo "$speedup"
        else
            # Fallback using awk
            local speedup=$(awk "BEGIN {printf \"%.2f\", $baseline / $comparison}" 2>/dev/null || echo "N/A")
            echo "$speedup"
        fi
    fi
}

# Function to write statistics to file
write_statistics_file() {
    local stats_file="$RESULTS_DIR/performance_statistics.txt"
    
    {
        echo "╔══════════════════════════════════════════════════════════════════════════════╗"
        echo "║              Performance Test Statistics & Comparison                       ║"
        echo "╚══════════════════════════════════════════════════════════════════════════════╝"
        echo ""
        echo "Generated: $(date)"
        echo "Test Data: $PERF_TEST_CSV_FILE ($(du -h "$PERF_TEST_CSV_FILE" 2>/dev/null | cut -f1 || echo 'N/A'))"
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "INDIVIDUAL TEST RESULTS"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        
        # Test 1: CSV Python -> Iceberg
        local test1_result=$(get_test_result "performance_test_1_csv_python_to_iceberg")
        local test1_status=$(echo "$test1_result" | cut -d'|' -f1)
        local test1_duration=$(echo "$test1_result" | cut -d'|' -f2)
        echo "Test 1: CSV Reader (Python) -> Iceberg"
        echo "  Status: $test1_status"
        echo "  Duration: $(format_duration "$test1_duration") seconds"
        echo ""
        
        # Test 2: CSV Rust -> Iceberg
        local test2_result=$(get_test_result "performance_test_2_csv_rust_to_iceberg")
        local test2_status=$(echo "$test2_result" | cut -d'|' -f1)
        local test2_duration=$(echo "$test2_result" | cut -d'|' -f2)
        echo "Test 2: CSV Reader (Rust) -> Iceberg"
        echo "  Status: $test2_status"
        echo "  Duration: $(format_duration "$test2_duration") seconds"
        echo ""
        
        # Test 3: Iceberg -> CSV Python
        local test3_result=$(get_test_result "performance_test_3_iceberg_to_csv_python")
        local test3_status=$(echo "$test3_result" | cut -d'|' -f1)
        local test3_duration=$(echo "$test3_result" | cut -d'|' -f2)
        echo "Test 3: Iceberg -> CSV Writer (Python)"
        echo "  Status: $test3_status"
        echo "  Duration: $(format_duration "$test3_duration") seconds"
        echo ""
        
        # Test 4: Iceberg -> CSV Rust
        local test4_result=$(get_test_result "performance_test_4_iceberg_to_csv_rust")
        local test4_status=$(echo "$test4_result" | cut -d'|' -f1)
        local test4_duration=$(echo "$test4_result" | cut -d'|' -f2)
        echo "Test 4: Iceberg -> CSV Writer (Rust)"
        echo "  Status: $test4_status"
        echo "  Duration: $(format_duration "$test4_duration") seconds"
        echo ""
        
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "PERFORMANCE COMPARISONS"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        
        # Comparison 1: CSV Reading (Python vs Rust)
        local test1_num=$(get_numeric_duration "$test1_duration")
        local test2_num=$(get_numeric_duration "$test2_duration")
        if [ "$test1_status" = "PASSED" ] && [ "$test2_status" = "PASSED" ] && [ "$test1_num" != "0" ] && [ "$test2_num" != "0" ]; then
            local csv_speedup=$(calculate_speedup "$test1_num" "$test2_num")
            echo "CSV Reading Performance:"
            echo "  Python: $(format_duration "$test1_duration")s"
            echo "  Rust:   $(format_duration "$test2_duration")s"
            if [ "$csv_speedup" != "N/A" ]; then
                echo "  Speedup: ${csv_speedup}x (Rust is $(format_duration "$csv_speedup")x faster)"
                local improvement
                if command -v bc >/dev/null 2>&1; then
                    improvement=$(echo "scale=1; ($test1_num - $test2_num) * 100 / $test1_num" | bc 2>/dev/null || echo "N/A")
                else
                    improvement=$(awk "BEGIN {printf \"%.1f\", ($test1_num - $test2_num) * 100 / $test1_num}" 2>/dev/null || echo "N/A")
                fi
                if [ "$improvement" != "N/A" ]; then
                    echo "  Improvement: ${improvement}% faster with Rust"
                fi
            fi
            echo ""
        fi
        
        # Comparison 2: CSV Writing (Python vs Rust)
        local test3_num=$(get_numeric_duration "$test3_duration")
        local test4_num=$(get_numeric_duration "$test4_duration")
        if [ "$test3_status" = "PASSED" ] && [ "$test4_status" = "PASSED" ] && [ "$test3_num" != "0" ] && [ "$test4_num" != "0" ]; then
            local write_speedup=$(calculate_speedup "$test3_num" "$test4_num")
            echo "CSV Writing Performance:"
            echo "  Python: $(format_duration "$test3_duration")s"
            echo "  Rust:   $(format_duration "$test4_duration")s"
            if [ "$write_speedup" != "N/A" ]; then
                echo "  Speedup: ${write_speedup}x (Rust is $(format_duration "$write_speedup")x faster)"
                local improvement
                if command -v bc >/dev/null 2>&1; then
                    improvement=$(echo "scale=1; ($test3_num - $test4_num) * 100 / $test3_num" | bc 2>/dev/null || echo "N/A")
                else
                    improvement=$(awk "BEGIN {printf \"%.1f\", ($test3_num - $test4_num) * 100 / $test3_num}" 2>/dev/null || echo "N/A")
                fi
                if [ "$improvement" != "N/A" ]; then
                    echo "  Improvement: ${improvement}% faster with Rust"
                fi
            fi
            echo ""
        fi
        
        # Comparison 3: End-to-end pipeline comparison
        if [ "$test1_status" = "PASSED" ] && [ "$test3_status" = "PASSED" ] && [ "$test1_num" != "0" ] && [ "$test3_num" != "0" ]; then
            local total_python
            if command -v bc >/dev/null 2>&1; then
                total_python=$(echo "scale=2; $test1_num + $test3_num" | bc 2>/dev/null || echo "N/A")
            else
                total_python=$(awk "BEGIN {printf \"%.2f\", $test1_num + $test3_num}" 2>/dev/null || echo "N/A")
            fi
            echo "End-to-End Pipeline (CSV -> Iceberg -> CSV):"
            echo "  Read (Python):  $(format_duration "$test1_duration")s"
            echo "  Write (Python): $(format_duration "$test3_duration")s"
            if [ "$total_python" != "N/A" ]; then
                echo "  Total (Python): $(format_duration "$total_python")s"
            fi
            echo ""
        fi
        
        if [ "$test2_status" = "PASSED" ] && [ "$test4_status" = "PASSED" ] && [ "$test2_num" != "0" ] && [ "$test4_num" != "0" ]; then
            local total_rust
            if command -v bc >/dev/null 2>&1; then
                total_rust=$(echo "scale=2; $test2_num + $test4_num" | bc 2>/dev/null || echo "N/A")
            else
                total_rust=$(awk "BEGIN {printf \"%.2f\", $test2_num + $test4_num}" 2>/dev/null || echo "N/A")
            fi
            echo "End-to-End Pipeline (CSV -> Iceberg -> CSV) with Rust:"
            echo "  Read (Rust):  $(format_duration "$test2_duration")s"
            echo "  Write (Rust): $(format_duration "$test4_duration")s"
            if [ "$total_rust" != "N/A" ]; then
                echo "  Total (Rust): $(format_duration "$total_rust")s"
            fi
            echo ""
            
            # Compare total pipelines
            local total_python
            if command -v bc >/dev/null 2>&1; then
                total_python=$(echo "scale=2; $test1_num + $test3_num" | bc 2>/dev/null || echo "0")
            else
                total_python=$(awk "BEGIN {printf \"%.2f\", $test1_num + $test3_num}" 2>/dev/null || echo "0")
            fi
            if [ "$total_python" != "0" ] && [ "$total_python" != "N/A" ] && [ "$total_rust" != "N/A" ]; then
                local pipeline_speedup=$(calculate_speedup "$total_python" "$total_rust")
                if [ "$pipeline_speedup" != "N/A" ]; then
                    echo "Pipeline Speedup: ${pipeline_speedup}x faster with Rust plugins"
                fi
            fi
        fi
        
        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "SUMMARY"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo ""
        
        local passed_count=0
        local failed_count=0
        local skipped_count=0
        
        for test_name in "performance_test_1_csv_python_to_iceberg" "performance_test_2_csv_rust_to_iceberg" "performance_test_3_iceberg_to_csv_python" "performance_test_4_iceberg_to_csv_rust"; do
            local result=$(get_test_result "$test_name")
            local status=$(echo "$result" | cut -d'|' -f1)
            case "$status" in
                PASSED) passed_count=$((passed_count + 1)) ;;
                FAILED) failed_count=$((failed_count + 1)) ;;
                *) skipped_count=$((skipped_count + 1)) ;;
            esac
        done
        
        echo "Tests Passed: $passed_count"
        echo "Tests Failed: $failed_count"
        echo "Tests Skipped: $skipped_count"
        echo ""
        echo "Detailed logs available in: $RESULTS_DIR"
        
    } > "$stats_file"
    
    echo -e "${GREEN}✅ Statistics written to: $stats_file${NC}"
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
            printf "%-50s ${GREEN}%-15s${NC} %-15s\n" "$test_name" "$status" "$(format_duration "$duration")"
        elif [ "$status" = "FAILED" ]; then
            printf "%-50s ${RED}%-15s${NC} %-15s\n" "$test_name" "$status" "$(format_duration "$duration")"
        else
            printf "%-50s ${YELLOW}%-15s${NC} %-15s\n" "$test_name" "$status" "$(format_duration "$duration")"
        fi
    done
    
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # Performance Comparisons
    print_section "Performance Comparisons"
    
    local test1_result=$(get_test_result "performance_test_1_csv_python_to_iceberg")
    local test1_status=$(echo "$test1_result" | cut -d'|' -f1)
    local test1_duration=$(echo "$test1_result" | cut -d'|' -f2)
    local test1_num=$(get_numeric_duration "$test1_duration")
    
    local test2_result=$(get_test_result "performance_test_2_csv_rust_to_iceberg")
    local test2_status=$(echo "$test2_result" | cut -d'|' -f1)
    local test2_duration=$(echo "$test2_result" | cut -d'|' -f2)
    local test2_num=$(get_numeric_duration "$test2_duration")
    
    local test3_result=$(get_test_result "performance_test_3_iceberg_to_csv_python")
    local test3_status=$(echo "$test3_result" | cut -d'|' -f1)
    local test3_duration=$(echo "$test3_result" | cut -d'|' -f2)
    local test3_num=$(get_numeric_duration "$test3_duration")
    
    local test4_result=$(get_test_result "performance_test_4_iceberg_to_csv_rust")
    local test4_status=$(echo "$test4_result" | cut -d'|' -f1)
    local test4_duration=$(echo "$test4_result" | cut -d'|' -f2)
    local test4_num=$(get_numeric_duration "$test4_duration")
    
    # CSV Reading Comparison
    if [ "$test1_status" = "PASSED" ] && [ "$test2_status" = "PASSED" ] && [ "$test1_num" != "0" ] && [ "$test2_num" != "0" ]; then
        local csv_speedup=$(calculate_speedup "$test1_num" "$test2_num")
        echo ""
        echo -e "${CYAN}CSV Reading Performance Comparison:${NC}"
        echo "  Python CSV Reader: $(format_duration "$test1_duration")s"
        echo "  Rust CSV Reader:   $(format_duration "$test2_duration")s"
        if [ "$csv_speedup" != "N/A" ]; then
            echo -e "  ${GREEN}Speedup: ${csv_speedup}x${NC} (Rust is $(format_duration "$csv_speedup")x faster)"
            local improvement
            if command -v bc >/dev/null 2>&1; then
                improvement=$(echo "scale=1; ($test1_num - $test2_num) * 100 / $test1_num" | bc 2>/dev/null || echo "N/A")
            else
                improvement=$(awk "BEGIN {printf \"%.1f\", ($test1_num - $test2_num) * 100 / $test1_num}" 2>/dev/null || echo "N/A")
            fi
            if [ "$improvement" != "N/A" ]; then
                echo -e "  ${GREEN}Improvement: ${improvement}% faster with Rust${NC}"
            fi
        fi
    fi
    
    # CSV Writing Comparison
    if [ "$test3_status" = "PASSED" ] && [ "$test4_status" = "PASSED" ] && [ "$test3_num" != "0" ] && [ "$test4_num" != "0" ]; then
        local write_speedup=$(calculate_speedup "$test3_num" "$test4_num")
        echo ""
        echo -e "${CYAN}CSV Writing Performance Comparison:${NC}"
        echo "  Python CSV Writer: $(format_duration "$test3_duration")s"
        echo "  Rust CSV Writer:   $(format_duration "$test4_duration")s"
        if [ "$write_speedup" != "N/A" ]; then
            echo -e "  ${GREEN}Speedup: ${write_speedup}x${NC} (Rust is $(format_duration "$write_speedup")x faster)"
            local improvement
            if command -v bc >/dev/null 2>&1; then
                improvement=$(echo "scale=1; ($test3_num - $test4_num) * 100 / $test3_num" | bc 2>/dev/null || echo "N/A")
            else
                improvement=$(awk "BEGIN {printf \"%.1f\", ($test3_num - $test4_num) * 100 / $test3_num}" 2>/dev/null || echo "N/A")
            fi
            if [ "$improvement" != "N/A" ]; then
                echo -e "  ${GREEN}Improvement: ${improvement}% faster with Rust${NC}"
            fi
        fi
    fi
    
    # End-to-end pipeline comparison
    if [ "$test1_status" = "PASSED" ] && [ "$test3_status" = "PASSED" ] && [ "$test2_status" = "PASSED" ] && [ "$test4_status" = "PASSED" ] && \
       [ "$test1_num" != "0" ] && [ "$test2_num" != "0" ] && [ "$test3_num" != "0" ] && [ "$test4_num" != "0" ]; then
        local total_python
        local total_rust
        if command -v bc >/dev/null 2>&1; then
            total_python=$(echo "scale=2; $test1_num + $test3_num" | bc 2>/dev/null || echo "0")
            total_rust=$(echo "scale=2; $test2_num + $test4_num" | bc 2>/dev/null || echo "0")
        else
            total_python=$(awk "BEGIN {printf \"%.2f\", $test1_num + $test3_num}" 2>/dev/null || echo "0")
            total_rust=$(awk "BEGIN {printf \"%.2f\", $test2_num + $test4_num}" 2>/dev/null || echo "0")
        fi
        if [ "$total_python" != "0" ] && [ "$total_rust" != "0" ] && [ "$total_python" != "N/A" ] && [ "$total_rust" != "N/A" ]; then
            local pipeline_speedup=$(calculate_speedup "$total_python" "$total_rust")
            echo ""
            echo -e "${CYAN}End-to-End Pipeline Comparison (CSV -> Iceberg -> CSV):${NC}"
            echo "  Python (Read + Write): $(format_duration "$total_python")s"
            echo "  Rust (Read + Write):   $(format_duration "$total_rust")s"
            if [ "$pipeline_speedup" != "N/A" ]; then
                echo -e "  ${GREEN}Pipeline Speedup: ${pipeline_speedup}x${NC} faster with Rust plugins"
            fi
        fi
    fi
    
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""
    
    # Write detailed statistics to file
    write_statistics_file
    
    echo ""
    echo "Detailed logs available in: $RESULTS_DIR"
    echo "Statistics file: $RESULTS_DIR/performance_statistics.txt"
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
        "$SCRIPT_DIR/fixtures/jobs/performance_test_1_csv_python_to_iceberg.yaml" || true
    
    # Test 2: CSV (Rust) -> Iceberg
    if [ -f "$PROJECT_ROOT/examples/plugins/rust/target/release/libcsv_reader_plugin.so" ] || \
       [ -f "$PROJECT_ROOT/examples/plugins/rust/target/release/libcsv_reader_plugin.dylib" ]; then
        run_performance_test \
            "performance_test_2_csv_rust_to_iceberg" \
            "CSV reader (Rust) -> Iceberg table on S3 (MinIO)" \
            "$SCRIPT_DIR/fixtures/jobs/performance_test_2_csv_rust_to_iceberg.yaml" || true
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
        "$SCRIPT_DIR/fixtures/jobs/performance_test_3_iceberg_to_csv_python.yaml" || true
    
    # Test 4: Iceberg -> CSV (Rust)
    # This test depends on Test 2's output, so skip if Rust plugins are not available
    # Verify that the config actually uses Rust CSV writer
    local test4_config="$SCRIPT_DIR/fixtures/jobs/performance_test_4_iceberg_to_csv_rust.yaml"
    local uses_rust_writer=false
    if grep -q "libcsv_writer_plugin" "$test4_config" 2>/dev/null; then
        uses_rust_writer=true
    fi
    
    if [ "$uses_rust_writer" = "true" ]; then
        # Check for Rust CSV writer plugin
        if [ -f "$PROJECT_ROOT/examples/plugins/rust/target/release/libcsv_writer_plugin.so" ] || \
           [ -f "$PROJECT_ROOT/examples/plugins/rust/target/release/libcsv_writer_plugin.dylib" ]; then
            run_performance_test \
                "performance_test_4_iceberg_to_csv_rust" \
                "Iceberg table on S3 (MinIO) -> CSV writer (Rust)" \
                "$test4_config" || true
        else
            echo -e "${RED}❌ Test 4 config requires Rust CSV writer plugin, but plugin not found${NC}"
            echo -e "${YELLOW}   Expected: libcsv_writer_plugin.so or libcsv_writer_plugin.dylib${NC}"
            echo -e "${YELLOW}   Location: examples/plugins/rust/target/release/${NC}"
            echo -e "${YELLOW}   Run: cd examples/plugins/rust && cargo build --release${NC}"
            set_test_result "performance_test_4_iceberg_to_csv_rust" "SKIPPED" "" "Rust CSV writer plugin not found"
        fi
    else
        echo -e "${RED}❌ Test 4 config does not use Rust CSV writer plugin${NC}"
        echo -e "${YELLOW}   Config should specify: custom_writer: \"...libcsv_writer_plugin.so:create_writer\"${NC}"
        set_test_result "performance_test_4_iceberg_to_csv_rust" "SKIPPED" "" "Config does not use Rust writer"
    fi
    
    print_results
}

# Run main
main
