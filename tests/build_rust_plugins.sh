#!/bin/bash
# Build Rust plugins for smoke tests
# This script can be called standalone or sourced by other scripts

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if Rust is available
if ! command -v cargo &> /dev/null; then
    echo -e "${YELLOW}⚠️  Rust/Cargo not found.${NC}"
    echo "   Install Rust: curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh"
    exit 1
fi

# Ensure cargo is in PATH
export PATH="$HOME/.cargo/bin:$PATH"

# Check if Rust plugins directory exists
RUST_DIR="$PROJECT_ROOT/examples/plugins/rust"
if [ ! -d "$RUST_DIR" ]; then
    echo -e "${RED}❌ Rust plugins directory not found: $RUST_DIR${NC}"
    exit 1
fi

echo "🔨 Building Rust plugins..."
echo "   Directory: $RUST_DIR"
echo ""

cd "$RUST_DIR"

# Build csv_reader_plugin
echo "   Building csv_reader_plugin..."
if cargo build --release -p csv_reader_plugin; then
    echo -e "${GREEN}   ✅ csv_reader_plugin built successfully${NC}"
else
    echo -e "${RED}   ❌ Failed to build csv_reader_plugin${NC}"
    cd "$PROJECT_ROOT"
    exit 1
fi

echo ""

# Build parquet_writer_plugin
echo "   Building parquet_writer_plugin..."
if cargo build --release -p parquet_writer_plugin; then
    echo -e "${GREEN}   ✅ parquet_writer_plugin built successfully${NC}"
else
    echo -e "${RED}   ❌ Failed to build parquet_writer_plugin${NC}"
    cd "$PROJECT_ROOT"
    exit 1
fi

cd "$PROJECT_ROOT"

echo ""
echo -e "${GREEN}✅ All Rust plugins built successfully${NC}"

