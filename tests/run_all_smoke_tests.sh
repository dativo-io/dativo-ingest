#!/bin/bash
# Master script to run all smoke tests (original + custom plugins)
# Usage: run_all_smoke_tests.sh [--skip-infrastructure-setup] [--skip-env-setup] [--skip-rust-build]

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Parse command line flags
SKIP_INFRASTRUCTURE_SETUP=false
SKIP_ENV_SETUP=false
SKIP_RUST_BUILD=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-infrastructure-setup)
            SKIP_INFRASTRUCTURE_SETUP=true
            shift
            ;;
        --skip-env-setup)
            SKIP_ENV_SETUP=true
            shift
            ;;
        --skip-rust-build)
            SKIP_RUST_BUILD=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-infrastructure-setup] [--skip-env-setup] [--skip-rust-build]"
            exit 1
            ;;
    esac
done

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

# Function to build Rust plugins
build_rust_plugins() {
    echo ""
    echo "🔨 Building Rust plugins..."
    
    # Check if Rust is available
    if ! command -v cargo &> /dev/null; then
        echo -e "${YELLOW}⚠️  Rust/Cargo not found. Skipping Rust plugin build.${NC}"
        echo "   Install Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
        return 1
    fi
    
    # Ensure cargo is in PATH
    export PATH="$HOME/.cargo/bin:$PATH"
    
    local rust_dir="$PROJECT_ROOT/examples/plugins/rust"
    if [ ! -d "$rust_dir" ]; then
        echo -e "${YELLOW}⚠️  Rust plugins directory not found: $rust_dir${NC}"
        return 1
    fi
    
    cd "$rust_dir"
    
    echo "   Building csv_reader_plugin..."
    if cargo build --release -p csv_reader_plugin 2>&1; then
        echo -e "${GREEN}   ✅ csv_reader_plugin built successfully${NC}"
    else
        echo -e "${RED}   ❌ Failed to build csv_reader_plugin${NC}"
        cd "$PROJECT_ROOT"
        return 1
    fi
    
    echo "   Building parquet_writer_plugin..."
    if cargo build --release -p parquet_writer_plugin 2>&1; then
        echo -e "${GREEN}   ✅ parquet_writer_plugin built successfully${NC}"
    else
        echo -e "${RED}   ❌ Failed to build parquet_writer_plugin${NC}"
        cd "$PROJECT_ROOT"
        return 1
    fi
    
    cd "$PROJECT_ROOT"
    echo -e "${GREEN}✅ All Rust plugins built successfully${NC}"
    return 0
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
        if [ "$SKIP_RUST_BUILD" = "true" ]; then
            echo -e "${YELLOW}⚠️  Rust plugins not found (build skipped via flag). Some custom plugin tests may be skipped.${NC}"
        else
            echo -e "${YELLOW}⚠️  Rust plugins not found. Attempting to build...${NC}"
            if build_rust_plugins; then
                echo -e "${GREEN}✅ Rust plugins built and ready${NC}"
            else
                echo -e "${YELLOW}⚠️  Rust plugin build failed. Some custom plugin tests may be skipped.${NC}"
            fi
        fi
        echo ""
    else
        echo -e "${GREEN}✅ Rust plugins found${NC}"
    fi
}

# Setup environment variables
setup_environment() {
    if [ "$SKIP_ENV_SETUP" = "true" ]; then
        echo "ℹ️  Skipping environment setup (--skip-env-setup flag)"
        return 0
    fi
    
    echo "🔧 Setting up environment..."
    
    # Check if variables are already set (user may have set them manually)
    local needs_setup=false
    
    # Check required environment variables - if any are missing, we need to source the setup script
    if [ -z "${PGHOST:-}" ] && [ -z "${PGDATABASE:-}" ]; then
        needs_setup=true
    fi
    
    if [ -z "${MYSQL_HOST:-}" ] && [ -z "${MYSQL_DATABASE:-}" ]; then
        needs_setup=true
    fi
    
    if [ -z "${MINIO_ENDPOINT:-}" ] && [ -z "${S3_ENDPOINT:-}" ]; then
        needs_setup=true
    fi
    
    if [ "$needs_setup" = "true" ]; then
        echo "   Sourcing environment setup script..."
        if [ -f "$SCRIPT_DIR/setup_smoke_test_env.sh" ]; then
            # Source the script - help text is automatically suppressed when sourced
            source "$SCRIPT_DIR/setup_smoke_test_env.sh"
            # Export all environment variables so they're available to child processes
            export PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD
            export MYSQL_HOST MYSQL_PORT MYSQL_DATABASE MYSQL_USER MYSQL_PASSWORD
            export MINIO_ENDPOINT MINIO_ACCESS_KEY MINIO_SECRET_KEY
            export S3_ENDPOINT AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_REGION
            echo -e "${GREEN}✅ Environment variables configured and exported${NC}"
        else
            echo -e "${YELLOW}⚠️  Setup script not found${NC}"
            echo "   Tests may fail if required services are not available."
        fi
    else
        # Even if variables are already set, export them to ensure child processes can access them
        export PGHOST PGPORT PGDATABASE PGUSER PGPASSWORD 2>/dev/null || true
        export MYSQL_HOST MYSQL_PORT MYSQL_DATABASE MYSQL_USER MYSQL_PASSWORD 2>/dev/null || true
        export MINIO_ENDPOINT MINIO_ACCESS_KEY MINIO_SECRET_KEY 2>/dev/null || true
        export S3_ENDPOINT AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_REGION 2>/dev/null || true
        echo -e "${GREEN}✅ Environment variables already configured${NC}"
    fi
}

# Check environment variables (for reporting)
# This is a summary check - variables should already be set by setup_environment()
check_environment() {
    echo "🔍 Final environment check..."
    
    # After setup_environment(), variables should be set (either from user or defaults)
    # Just verify and report what's configured
    local pg_configured=false
    local mysql_configured=false
    local s3_configured=false
    
    # Check PostgreSQL
    if [ -n "${PGHOST:-}" ] || [ -n "${PGDATABASE:-}" ]; then
        pg_configured=true
    fi
    
    # Check MySQL
    if [ -n "${MYSQL_HOST:-}" ] || [ -n "${MYSQL_DATABASE:-}" ]; then
        mysql_configured=true
    fi
    
    # Check MinIO/S3
    if [ -n "${MINIO_ENDPOINT:-}" ] || [ -n "${S3_ENDPOINT:-}" ]; then
        s3_configured=true
    fi
    
    if [ "$pg_configured" = true ] && [ "$mysql_configured" = true ] && [ "$s3_configured" = true ]; then
        echo -e "${GREEN}✅ All required environment variables are configured${NC}"
    else
        # This should not happen if setup_environment() worked correctly
        echo -e "${YELLOW}⚠️  Some environment variables may not be configured:${NC}"
        [ "$pg_configured" = false ] && echo "   - PostgreSQL variables"
        [ "$mysql_configured" = false ] && echo "   - MySQL variables"
        [ "$s3_configured" = false ] && echo "   - MinIO/S3 variables"
        echo ""
    fi
}

# Main execution
echo "🔍 Pre-flight checks..."

# Step 1: Check Docker configuration for sandbox tests
if [ -f "$SCRIPT_DIR/check_docker_config.sh" ]; then
    echo "🔍 Checking Docker configuration..."
    if ! bash "$SCRIPT_DIR/check_docker_config.sh"; then
        echo ""
        echo -e "${RED}❌ Docker configuration check failed.${NC}"
        echo "   Please fix Docker configuration issues before running smoke tests."
        exit 1
    fi
    echo ""
else
    echo -e "${YELLOW}⚠️  Docker configuration check script not found${NC}"
    echo "   Proceeding without Docker configuration validation..."
    echo ""
fi

# Step 2: Setup infrastructure services (Postgres, MySQL, MinIO, Nessie) - REQUIRED
# Note: These are infrastructure dependencies for testing, NOT the dativo-ingest service
# The dativo-ingest CLI runs locally and connects to these services
INFRASTRUCTURE_STARTED=0
if [ "$SKIP_INFRASTRUCTURE_SETUP" = "false" ]; then
    if [ -f "$SCRIPT_DIR/setup_smoke_test_infrastructure.sh" ]; then
        # Docker is REQUIRED for smoke tests (infrastructure services run in Docker)
        if ! bash "$SCRIPT_DIR/setup_smoke_test_infrastructure.sh" --no-teardown; then
            echo ""
            echo -e "${RED}❌ Infrastructure setup failed. Docker is required for smoke tests.${NC}"
            echo "   Use --skip-infrastructure-setup flag only if services are already running."
            exit 1
        fi
        INFRASTRUCTURE_STARTED=1
        echo ""
    else
        echo -e "${RED}❌ Infrastructure setup script not found${NC}"
        echo "   Infrastructure setup is required for smoke tests."
        exit 1
    fi
else
    echo "ℹ️  Skipping infrastructure setup (--skip-infrastructure-setup flag)"
    echo "   Assuming services are already running..."
    echo ""
    # Verify services are actually running
    if ! docker ps --format '{{.Names}}' | grep -q "dativo-postgres\|dativo-mysql\|dativo-minio\|dativo-nessie"; then
        echo -e "${YELLOW}⚠️  Warning: Infrastructure services don't appear to be running${NC}"
        echo "   Some tests may fail."
    fi
fi

# Step 2: Setup environment variables if needed
setup_environment

# Step 3: Check and build Rust plugins if needed
check_rust_plugins

# Step 4: Final environment check
check_environment

# Run test suite 1: Original smoke tests
run_test_suite \
    "Original Smoke Tests" \
    "$SCRIPT_DIR/smoke_tests.sh"

# Run test suite 2: Custom plugin smoke tests
run_test_suite \
    "Custom Plugin Smoke Tests" \
    "$SCRIPT_DIR/smoke_tests_custom_plugins.sh"

# Run test suite 3: Sandbox smoke tests (requires Docker)
run_test_suite \
    "Sandbox Smoke Tests" \
    "$SCRIPT_DIR/smoke_tests_sandbox.sh"

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

# Cleanup: Stop infrastructure services if we started them
if [ $INFRASTRUCTURE_STARTED -eq 1 ]; then
    echo ""
    echo -e "${BLUE}🧹 Cleaning up infrastructure services...${NC}"
    cd "$PROJECT_ROOT"
    DOCKER_COMPOSE="docker compose -f $PROJECT_ROOT/docker-compose.dev.yml"
    if $DOCKER_COMPOSE down >/dev/null 2>&1; then
        echo -e "${GREEN}✅ Infrastructure services stopped${NC}"
    else
        echo -e "${YELLOW}⚠️  Warning: Failed to stop some infrastructure services${NC}"
        echo "   You may need to stop them manually: docker compose -f docker-compose.dev.yml down"
    fi
    echo ""
fi

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

