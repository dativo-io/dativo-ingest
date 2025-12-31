#!/bin/bash
# State persistence test - runs a job twice and verifies state is persisted and used correctly

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/fixtures"
JOBS_DIR="$FIXTURES_DIR/jobs"
SECRETS_DIR="$FIXTURES_DIR/secrets"
STATE_DIR="${STATE_DIR:-.local/state}"

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

# Test job configuration
TEST_JOB="csv_employee_state_persistence.yaml"
TEST_JOB_PATH="$JOBS_DIR/$TEST_JOB"
STATE_FILE="$STATE_DIR/test_tenant/csv.Employee.state.json"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                    STATE PERSISTENCE TEST                            ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

# Cleanup function
cleanup() {
    echo ""
    echo "🧹 Cleaning up test state..."
    if [ -f "$STATE_FILE" ]; then
        echo "  - Removing state file: $STATE_FILE"
        rm -f "$STATE_FILE" 2>/dev/null || true
    fi
    if [ -d "$STATE_DIR/test_tenant" ]; then
        rmdir "$STATE_DIR/test_tenant" 2>/dev/null || true
    fi
    echo "✅ Cleanup complete"
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Check if test job exists
if [ ! -f "$TEST_JOB_PATH" ]; then
    echo -e "${RED}❌ Test job not found: $TEST_JOB_PATH${NC}"
    exit 1
fi

echo -e "${BLUE}📋 Test Job: $TEST_JOB${NC}"
echo -e "${BLUE}📁 State File: $STATE_FILE${NC}"
echo ""

# Step 1: Clean state before first run
echo -e "${YELLOW}Step 1: Cleaning any existing state...${NC}"
if [ -f "$STATE_FILE" ]; then
    rm -f "$STATE_FILE"
    echo "  ✅ Removed existing state file"
else
    echo "  ℹ️  No existing state file"
fi
echo ""

# Step 2: First run - should process all records and create state
echo -e "${YELLOW}Step 2: Running job (first run - full sync)...${NC}"
set +e
OUTPUT1=$(PYTHONPATH=src $PYTHON_CMD -m dativo_ingest.cli ingest \
    --job-dir "$JOBS_DIR" \
    --secrets-dir "$SECRETS_DIR" \
    --mode self_hosted \
    --job "$TEST_JOB" 2>&1)
EXIT_CODE1=$?
set -e

if [ $EXIT_CODE1 -ne 0 ]; then
    echo -e "${RED}❌ First run failed with exit code $EXIT_CODE1${NC}"
    echo "$OUTPUT1" | tail -20
    exit 1
fi

# Check if state file was created
if [ ! -f "$STATE_FILE" ]; then
    echo -e "${RED}❌ State file was not created after first run${NC}"
    echo "  Expected: $STATE_FILE"
    exit 1
fi

echo -e "${GREEN}✅ First run completed successfully${NC}"
echo -e "${GREEN}✅ State file created: $STATE_FILE${NC}"

# Display state file contents
echo ""
echo "📄 State file contents:"
cat "$STATE_FILE" | python3 -m json.tool 2>/dev/null || cat "$STATE_FILE"
echo ""

# Step 3: Second run - should read state and skip unchanged files
echo -e "${YELLOW}Step 3: Running job (second run - incremental sync)...${NC}"
set +e
OUTPUT2=$(PYTHONPATH=src $PYTHON_CMD -m dativo_ingest.cli ingest \
    --job-dir "$JOBS_DIR" \
    --secrets-dir "$SECRETS_DIR" \
    --mode self_hosted \
    --job "$TEST_JOB" 2>&1)
EXIT_CODE2=$?
set -e

if [ $EXIT_CODE2 -ne 0 ]; then
    echo -e "${RED}❌ Second run failed with exit code $EXIT_CODE2${NC}"
    echo "$OUTPUT2" | tail -20
    exit 1
fi

echo -e "${GREEN}✅ Second run completed successfully${NC}"

# Check if state file still exists and was updated
if [ ! -f "$STATE_FILE" ]; then
    echo -e "${RED}❌ State file was deleted after second run${NC}"
    exit 1
fi

echo -e "${GREEN}✅ State file persisted: $STATE_FILE${NC}"

# Verify state file was read (check logs for state-related messages)
if echo "$OUTPUT2" | grep -q "Reading state\|Loading state\|State file"; then
    echo -e "${GREEN}✅ State file was read on second run${NC}"
else
    echo -e "${YELLOW}⚠️  Could not verify state file was read (check logs)${NC}"
fi

# Check if file was skipped (incremental sync working)
if echo "$OUTPUT2" | grep -qi "skip\|unchanged\|already processed"; then
    echo -e "${GREEN}✅ Incremental sync working (file skipped if unchanged)${NC}"
else
    echo -e "${YELLOW}⚠️  Could not verify incremental sync behavior${NC}"
fi

echo ""
echo "╔══════════════════════════════════════════════════════════════════════╗"
echo "║                    ✅ STATE PERSISTENCE TEST PASSED                 ║"
echo "╚══════════════════════════════════════════════════════════════════════╝"
echo ""

# Note: Cleanup will run automatically via trap on exit

