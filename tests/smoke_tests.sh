#!/bin/bash
# Smoke tests: Run actual CLI commands with test fixtures
# This is a simple wrapper that runs the CLI with test fixtures
# Users can also run this directly: dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/fixtures"
JOBS_DIR="$FIXTURES_DIR/jobs"
SECRETS_DIR="$FIXTURES_DIR/secrets"

# Cleanup function
cleanup() {
    echo ""
    echo "🧹 Cleaning up test artifacts..."
    
    # Clean up state files (if using default location)
    if [ -d .local/state ]; then
        echo "  - Removing state files..."
        rm -rf .local/state/test_tenant/*.state.json 2>/dev/null || true
    fi
    
    # Clean up temporary Parquet files
    echo "  - Removing temporary Parquet files..."
    rm -rf /tmp/dativo_ingest* 2>/dev/null || true
    rm -rf /tmp/*.parquet 2>/dev/null || true
    
    # Clean up log files
    echo "  - Removing log files..."
    rm -f *.log 2>/dev/null || true
    
    echo "✅ Cleanup complete"
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Run the CLI with test fixtures
python -m dativo_ingest.cli run \
    --job-dir "$JOBS_DIR" \
    --secrets-dir "$SECRETS_DIR" \
    --mode self_hosted

# Note: Cleanup will run automatically via trap on exit

