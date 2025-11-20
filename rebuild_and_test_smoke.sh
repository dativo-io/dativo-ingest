#!/bin/bash
# Rebuild Rust plugins and run smoke tests

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Step 1: Rebuilding Rust CSV Reader Plugin"
echo "=========================================="

export PATH="$HOME/.cargo/bin:$PATH"
cd examples/plugins/rust
cargo build --release -p csv_reader_plugin

echo ""
echo "✅ Rust CSV reader plugin rebuilt successfully"
echo ""

cd "$SCRIPT_DIR"

echo "=========================================="
echo "Step 2: Running All Smoke Tests"
echo "=========================================="

source venv/bin/activate
source tests/setup_smoke_test_env.sh
export PATH="$HOME/.cargo/bin:$PATH"

./tests/run_all_smoke_tests.sh

echo ""
echo "=========================================="
echo "Done!"
echo "=========================================="





