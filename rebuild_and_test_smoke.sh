#!/bin/bash
# Convenience wrapper: Rebuild Rust plugins and run smoke tests
# This script is a convenience wrapper around `make test-smoke`
# The functionality is now integrated into the Makefile and test scripts

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║          Rebuild Rust Plugins and Run Smoke Tests (Convenience Wrapper)    ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"
echo ""
echo "This script is a convenience wrapper that calls 'make test-smoke'."
echo "The Makefile now handles:"
echo "  - Environment setup"
echo "  - Rust plugin building"
echo "  - Running all smoke tests"
echo ""
echo "For more control, use 'make test-smoke' directly or call the scripts individually:"
echo "  - tests/setup_smoke_test_env.sh"
echo "  - tests/build_rust_plugins.sh"
echo "  - tests/run_all_smoke_tests.sh"
echo ""

# Activate venv if it exists
if [ -f venv/bin/activate ]; then
    source venv/bin/activate
fi

# Run smoke tests via Makefile
make test-smoke

echo ""
echo "╔══════════════════════════════════════════════════════════════════════════════╗"
echo "║                              Done!                                          ║"
echo "╚══════════════════════════════════════════════════════════════════════════════╝"





