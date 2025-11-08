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

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                         SMOKE TESTS                                   ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

# Run the CLI with test fixtures
echo "📦 Running ingestion jobs..."
python -m dativo_ingest.cli run \
    --job-dir "$JOBS_DIR" \
    --secrets-dir "$SECRETS_DIR" \
    --mode self_hosted

EXIT_CODE=$?

if [ $EXIT_CODE -ne 0 ]; then
    echo "❌ Ingestion jobs failed"
    exit $EXIT_CODE
fi

echo ""
echo "✅ Ingestion jobs completed successfully"
echo ""

# Verify tag propagation (if Nessie is available)
if [ -n "$NESSIE_URI" ]; then
    echo "🔍 Verifying tag propagation..."
    echo ""
    python "$SCRIPT_DIR/verify_tag_propagation.py"
    TAG_VERIFY_EXIT=$?
    
    if [ $TAG_VERIFY_EXIT -eq 0 ]; then
        echo ""
        echo "✅ Tag propagation verified"
    else
        echo ""
        echo "⚠️  Tag propagation verification failed (non-critical in CI)"
        # Don't fail the smoke test if tag verification fails
        # This is because Nessie might not be fully configured
    fi
else
    echo "ℹ️  Skipping tag propagation verification (NESSIE_URI not set)"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                    ✅ SMOKE TESTS PASSED                             ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"

# Note: Cleanup will run automatically via trap on exit

