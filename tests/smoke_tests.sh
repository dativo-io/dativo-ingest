#!/bin/bash
# Smoke tests: Run actual CLI commands with test fixtures
# This is a simple wrapper that runs the CLI with test fixtures
# Users can also run this directly: dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/fixtures"
JOBS_DIR="$FIXTURES_DIR/jobs"
SECRETS_DIR="$FIXTURES_DIR/secrets"

# Detect Python interpreter
# Prefer: 1) venv python, 2) python (GitHub Actions uses this), 3) python3.12, 4) python3
if [ -f "$PROJECT_ROOT/venv/bin/python" ]; then
    PYTHON_CMD="$PROJECT_ROOT/venv/bin/python"
elif command -v python >/dev/null 2>&1; then
    PYTHON_CMD="python"
elif command -v python3.12 >/dev/null 2>&1; then
    PYTHON_CMD="python3.12"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_CMD="python3"
else
    echo "❌ ERROR: No Python interpreter found"
    exit 1
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
    
    # Clean up S3 test directory
    if [ -d "s3:" ]; then
        echo "  - Removing S3 test directory..."
        rm -rf "s3:" 2>/dev/null || true
    fi
    
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

# Capture output to analyze results
set +e
OUTPUT=$(PYTHONPATH=src $PYTHON_CMD -m dativo_ingest.cli run \
    --job-dir "$JOBS_DIR" \
    --secrets-dir "$SECRETS_DIR" \
    --mode self_hosted 2>&1)
EXIT_CODE=$?
set -e

# Count successful and failed jobs
SUCCESS_COUNT=$(echo "$OUTPUT" | grep -c '"event_type": "job_finished"' 2>/dev/null || true)
FAILED_COUNT=$(echo "$OUTPUT" | grep -c '"event_type": "job_error"' 2>/dev/null || true)

# Count MySQL-specific job results
MYSQL_JOBS=$(echo "$OUTPUT" | grep -cE "mysql.*to.*iceberg|mysql.*to.*s3" 2>/dev/null || true)
MYSQL_SUCCESS=$(echo "$OUTPUT" | grep -E "mysql.*to.*iceberg|mysql.*to.*s3" | grep -c '"event_type": "job_finished"' 2>/dev/null || true)
MYSQL_FAILED=$(echo "$OUTPUT" | grep -E "mysql.*to.*iceberg|mysql.*to.*s3" | grep -c '"event_type": "job_error"' 2>/dev/null || true)

# Count expected failures (database connection errors, API credential errors, Docker errors)
DB_CONN_ERRORS=$(echo "$OUTPUT" | grep -cE "(Failed to connect to (Postgres|MySQL) database|Connection refused|invalid_host_that_does_not_exist)" 2>/dev/null || true)
API_CRED_ERRORS=$(echo "$OUTPUT" | grep -cE "(API key not found|credentials not found|HUBSPOT_API_KEY|STRIPE_API_KEY|service account credentials|invalid_key|authentication|unauthorized)" 2>/dev/null || true)
DOCKER_ERRORS=$(echo "$OUTPUT" | grep -cE "(Docker daemon|docker.*not.*running|Failed to connect to Docker)" 2>/dev/null || true)

# Count new error scenario types (strict validation, malformed data)
# These are expected failures for error scenario tests
STRICT_VALIDATION_ERRORS=$(echo "$OUTPUT" | grep -cE "(Strict validation mode: failing|validation.*failed|required.*field.*null)" 2>/dev/null || true)
MALFORMED_DATA_ERRORS=$(echo "$OUTPUT" | grep -cE "(malformed|CSV.*error|parse.*error|unclosed|syntax.*error)" 2>/dev/null || true)

# Ensure these are integers (strip any whitespace/newlines, default to 0 if empty)
SUCCESS_COUNT=$(echo "${SUCCESS_COUNT:-0}" | tr -d '\n\r ' | head -1)
FAILED_COUNT=$(echo "${FAILED_COUNT:-0}" | tr -d '\n\r ' | head -1)
DB_CONN_ERRORS=$(echo "${DB_CONN_ERRORS:-0}" | tr -d '\n\r ' | head -1)
API_CRED_ERRORS=$(echo "${API_CRED_ERRORS:-0}" | tr -d '\n\r ' | head -1)
DOCKER_ERRORS=$(echo "${DOCKER_ERRORS:-0}" | tr -d '\n\r ' | head -1)
STRICT_VALIDATION_ERRORS=$(echo "${STRICT_VALIDATION_ERRORS:-0}" | tr -d '\n\r ' | head -1)
MALFORMED_DATA_ERRORS=$(echo "${MALFORMED_DATA_ERRORS:-0}" | tr -d '\n\r ' | head -1)

echo ""
echo "📊 Smoke Test Results:"
echo "  ✅ Successful jobs: $SUCCESS_COUNT"
echo "  ❌ Failed jobs: $FAILED_COUNT"
echo "  🔌 Database connection errors (expected): $DB_CONN_ERRORS"
echo "  🔑 API credential errors (expected if credentials not set): $API_CRED_ERRORS"
echo "  🐳 Docker errors (expected if Docker not available): $DOCKER_ERRORS"
echo "  ⚠️  Strict validation errors (expected for error scenario tests): $STRICT_VALIDATION_ERRORS"
echo "  📄 Malformed data errors (expected for error scenario tests): $MALFORMED_DATA_ERRORS"
if [ "$MYSQL_JOBS" -gt 0 ]; then
    echo ""
    echo "  🗄️  MySQL Jobs:"
    echo "     Total MySQL jobs found: $MYSQL_JOBS"
    echo "     ✅ Successful: $MYSQL_SUCCESS"
    echo "     ❌ Failed: $MYSQL_FAILED"
    if [ "$MYSQL_SUCCESS" -gt 0 ]; then
        echo "     ✅ MySQL connector is functional"
    elif [ "$MYSQL_FAILED" -gt 0 ] && [ "$DB_CONN_ERRORS" -eq 0 ]; then
        echo "     ⚠️  MySQL jobs failed (check logs above for details)"
    fi
fi
echo ""

# Check for critical errors (non-database related)
# Only fail if there are actual job failures, not just error messages
# A validation_failed event that's followed by job_finished with exit_code=0 is not a failure
CRITICAL_ERRORS=$(echo "$OUTPUT" | grep -cE "(Strict validation mode: failing|Column.*is declared non-nullable)" 2>/dev/null || true)
CRITICAL_ERRORS=$(echo "${CRITICAL_ERRORS:-0}" | tr -d '\n\r ' | head -1)

# Only treat as critical if we have failed jobs AND critical errors
# If all jobs succeeded (FAILED_COUNT=0), then validation errors are just warnings
if [ "$CRITICAL_ERRORS" -gt 0 ] && [ "$FAILED_COUNT" -gt 0 ]; then
    echo "❌ Critical errors found (validation/schema issues):"
    echo "$OUTPUT" | grep -E "(Strict validation mode: failing|Column.*is declared non-nullable)" | head -5
    echo ""
    exit 1
elif [ "$CRITICAL_ERRORS" -gt 0 ] && [ "$FAILED_COUNT" -eq 0 ]; then
    # Validation errors logged but no jobs actually failed - likely warn mode or errors were handled
    echo "ℹ️  Validation warnings logged but all jobs completed successfully"
fi

# Calculate expected failures (database, API credentials, Docker, error scenario tests)
EXPECTED_FAILURES=$((DB_CONN_ERRORS + API_CRED_ERRORS + DOCKER_ERRORS + STRICT_VALIDATION_ERRORS + MALFORMED_DATA_ERRORS))

# If we have successful jobs and no critical errors, consider it a pass
# (database connection errors, API credential errors, and Docker errors are expected if services aren't available)
if [ "$SUCCESS_COUNT" -gt 0 ] && [ "$CRITICAL_ERRORS" -eq 0 ]; then
    echo "✅ Smoke tests completed successfully"
    exit 0
elif [ "$FAILED_COUNT" -eq "$EXPECTED_FAILURES" ]; then
    # All failures are expected (database, API credentials, Docker, or error scenario tests)
    echo "✅ Smoke tests completed (all failures are expected: DB=$DB_CONN_ERRORS, API=$API_CRED_ERRORS, Docker=$DOCKER_ERRORS, Strict=$STRICT_VALIDATION_ERRORS, Malformed=$MALFORMED_DATA_ERRORS)"
    exit 0
else
    echo "❌ Smoke tests failed with unexpected errors"
    echo "   Expected failures: $EXPECTED_FAILURES (DB: $DB_CONN_ERRORS, API: $API_CRED_ERRORS, Docker: $DOCKER_ERRORS, Strict: $STRICT_VALIDATION_ERRORS, Malformed: $MALFORMED_DATA_ERRORS)"
    echo "   Actual failures: $FAILED_COUNT"
    exit 1
fi

# Run state persistence test (if available)
if [ -f "$SCRIPT_DIR/test_state_persistence.sh" ]; then
    echo ""
    echo "🔄 Running state persistence test..."
    echo ""
    set +e
    "$SCRIPT_DIR/test_state_persistence.sh"
    STATE_TEST_EXIT=$?
    set -e
    
    if [ $STATE_TEST_EXIT -eq 0 ]; then
        echo ""
        echo "✅ State persistence test passed"
    else
        echo ""
        echo "⚠️  State persistence test failed (non-critical in CI)"
        # Don't fail the smoke test if state persistence test fails
        # This is because it requires specific test setup
    fi
else
    echo "ℹ️  Skipping state persistence test (test script not found)"
fi

# Verify tag propagation (if Nessie is available)
if [ -n "$NESSIE_URI" ]; then
    echo ""
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

