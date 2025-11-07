#!/bin/bash
# Smoke tests: Run actual CLI commands with test fixtures
# This is a simple wrapper that runs the CLI with test fixtures
# Users can also run this directly: dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FIXTURES_DIR="$SCRIPT_DIR/fixtures"
JOBS_DIR="$FIXTURES_DIR/jobs"
SECRETS_DIR="$FIXTURES_DIR/secrets"

# Run the CLI with test fixtures
python -m dativo_ingest.cli run \
    --job-dir "$JOBS_DIR" \
    --secrets-dir "$SECRETS_DIR" \
    --mode self_hosted

