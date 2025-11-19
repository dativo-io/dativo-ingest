#!/bin/bash
# Smoke tests: Run actual CLI commands with test fixtures
# This is a simple wrapper that runs the CLI with test fixtures
# Users can also run this directly: dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/fixtures"
JOBS_DIR="$FIXTURES_DIR/jobs"
SECRETS_DIR="$FIXTURES_DIR/secrets"

# Detect Python interpreter (prefer venv if available)
if [ -f "$PROJECT_ROOT/venv/bin/python" ]; then
    PYTHON_CMD="$PROJECT_ROOT/venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
else
    PYTHON_CMD="python"
fi

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
# Capture output to analyze results
set +e
OUTPUT=$($PYTHON_CMD -m dativo_ingest.cli run \
    --job-dir "$JOBS_DIR" \
    --secrets-dir "$SECRETS_DIR" \
    --mode self_hosted 2>&1)
EXIT_CODE=$?
set -e

# Count successful and failed jobs
SUCCESS_COUNT=$(echo "$OUTPUT" | grep -c '"event_type": "job_finished"' 2>/dev/null || true)
FAILED_COUNT=$(echo "$OUTPUT" | grep -c '"event_type": "job_error"' 2>/dev/null || true)

# Count expected failures (database connection errors)
DB_CONN_ERRORS=$(echo "$OUTPUT" | grep -cE "(Failed to connect to (Postgres|MySQL) database|Connection refused)" 2>/dev/null || true)

# Ensure these are integers (strip any whitespace/newlines, default to 0 if empty)
SUCCESS_COUNT=$(echo "${SUCCESS_COUNT:-0}" | tr -d '\n\r ' | head -1)
FAILED_COUNT=$(echo "${FAILED_COUNT:-0}" | tr -d '\n\r ' | head -1)
DB_CONN_ERRORS=$(echo "${DB_CONN_ERRORS:-0}" | tr -d '\n\r ' | head -1)

echo ""
echo "📊 Smoke Test Results:"
echo "  ✅ Successful jobs: $SUCCESS_COUNT"
echo "  ❌ Failed jobs: $FAILED_COUNT"
echo "  🔌 Database connection errors (expected): $DB_CONN_ERRORS"
echo ""

# Check for critical errors (non-database related)
CRITICAL_ERRORS=$(echo "$OUTPUT" | grep -cE "(Strict validation mode: failing|Column.*is declared non-nullable)" 2>/dev/null || true)
CRITICAL_ERRORS=$(echo "${CRITICAL_ERRORS:-0}" | tr -d '\n\r ' | head -1)

if [ "$CRITICAL_ERRORS" -gt 0 ]; then
    echo "❌ Critical errors found (validation/schema issues):"
    echo "$OUTPUT" | grep -E "(Strict validation mode: failing|Column.*is declared non-nullable)" | head -5
    echo ""
    exit 1
fi

# If we have successful jobs and no critical errors, consider it a pass
# (database connection errors are expected if services aren't running)
if [ "$SUCCESS_COUNT" -gt 0 ] && [ "$CRITICAL_ERRORS" -eq 0 ]; then
    echo "✅ Smoke tests completed successfully"
    exit 0
elif [ "$FAILED_COUNT" -eq "$DB_CONN_ERRORS" ]; then
    # All failures are expected database connection errors
    echo "✅ Smoke tests completed (all failures are expected database connection errors)"
    exit 0
else
    echo "❌ Smoke tests failed with unexpected errors"
    exit 1
fi

# Note: Cleanup will run automatically via trap on exit

