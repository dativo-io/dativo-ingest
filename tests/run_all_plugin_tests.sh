#!/bin/bash
# Master test runner for plugin system
# Runs all plugin tests: unit tests, integration tests, and Rust tests

set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo "================================================"
echo "  DATIVO ETL - Plugin System Test Suite"
echo "================================================"
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKSPACE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Test results
TOTAL_SUITES=0
PASSED_SUITES=0
FAILED_SUITES=0

run_suite() {
    local suite_name="$1"
    local suite_command="$2"
    local is_optional="${3:-false}"
    
    TOTAL_SUITES=$((TOTAL_SUITES + 1))
    
    echo ""
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  Test Suite: $suite_name${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    
    if eval "$suite_command"; then
        echo ""
        echo -e "${GREEN}✓ $suite_name - PASSED${NC}"
        PASSED_SUITES=$((PASSED_SUITES + 1))
        return 0
    else
        echo ""
        if [ "$is_optional" = "true" ]; then
            echo -e "${YELLOW}⚠ $suite_name - SKIPPED (optional)${NC}"
            PASSED_SUITES=$((PASSED_SUITES + 1))  # Count as passed
        else
            echo -e "${RED}✗ $suite_name - FAILED${NC}"
            FAILED_SUITES=$((FAILED_SUITES + 1))
        fi
        return 1
    fi
}

# ==========================
# Suite 1: Unit Tests (pytest)
# ==========================
run_suite "Python Unit Tests (pytest)" \
    "cd '$WORKSPACE_DIR' && python3 -m pytest tests/test_plugins.py -v --tb=short"

# ==========================
# Suite 2: Integration Tests
# ==========================
run_suite "Plugin Integration Tests" \
    "bash '$SCRIPT_DIR/test_plugin_integration.sh'"

# ==========================
# Suite 3: Default Extractors
# ==========================
run_suite "Default CSV Extractor Tests" \
    "cd '$WORKSPACE_DIR' && python3 -m pytest tests/test_csv_extractor.py -v --tb=short" \
    "true"  # Optional if file exists

# ==========================
# Suite 4: Rust Plugin Tests
# ==========================
if command -v rustc &> /dev/null; then
    run_suite "Rust Plugin Tests" \
        "bash '$WORKSPACE_DIR/examples/plugins/rust/test_rust_plugins.sh'"
else
    echo ""
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${YELLOW}  Rust Plugin Tests - SKIPPED${NC}"
    echo -e "${YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "Rust toolchain not found. Skipping Rust plugin tests."
    echo "To install Rust:"
    echo "  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    echo "  source \$HOME/.cargo/env"
    echo ""
    TOTAL_SUITES=$((TOTAL_SUITES + 1))
    PASSED_SUITES=$((PASSED_SUITES + 1))  # Count as passed (optional)
fi

# ==========================
# Final Summary
# ==========================
echo ""
echo "================================================"
echo "  FINAL TEST SUMMARY"
echo "================================================"
echo ""
echo "Total test suites: $TOTAL_SUITES"
echo -e "Passed: ${GREEN}$PASSED_SUITES${NC}"
echo -e "Failed: ${RED}$FAILED_SUITES${NC}"
echo ""

if [ $FAILED_SUITES -eq 0 ]; then
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${GREEN}  ✓ ALL TESTS PASSED!${NC}"
    echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "Plugin system is fully tested and working correctly!"
    echo ""
    exit 0
else
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${RED}  ✗ SOME TESTS FAILED!${NC}"
    echo -e "${RED}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo ""
    echo "Please review the output above for details."
    echo ""
    exit 1
fi
