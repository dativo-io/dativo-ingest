#!/bin/bash
# Setup script for smoke test environment
# This script sets up environment variables for running smoke tests

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "🔧 Setting up smoke test environment..."

# PostgreSQL configuration
export PGHOST="${PGHOST:-localhost}"
export PGPORT="${PGPORT:-5432}"
export PGDATABASE="${PGDATABASE:-Adventureworks}"
export PGUSER="${PGUSER:-postgres}"
export PGPASSWORD="${PGPASSWORD:-postgres}"

# MySQL configuration
export MYSQL_HOST="${MYSQL_HOST:-localhost}"
export MYSQL_PORT="${MYSQL_PORT:-3306}"
export MYSQL_DATABASE="${MYSQL_DATABASE:-employees}"
export MYSQL_DB="${MYSQL_DB:-employees}"
export MYSQL_USER="${MYSQL_USER:-test}"
export MYSQL_PASSWORD="${MYSQL_PASSWORD:-test}"

# MinIO/S3 configuration
export MINIO_ENDPOINT="${MINIO_ENDPOINT:-http://localhost:9000}"
export MINIO_ACCESS_KEY="${MINIO_ACCESS_KEY:-minioadmin}"
export MINIO_SECRET_KEY="${MINIO_SECRET_KEY:-minioadmin}"
export MINIO_BUCKET="${MINIO_BUCKET:-test-bucket}"

# S3 configuration (alias for MinIO)
export S3_ENDPOINT="${S3_ENDPOINT:-${MINIO_ENDPOINT}}"
export AWS_ACCESS_KEY_ID="${AWS_ACCESS_KEY_ID:-${MINIO_ACCESS_KEY}}"
export AWS_SECRET_ACCESS_KEY="${AWS_SECRET_ACCESS_KEY:-${MINIO_SECRET_KEY}}"
export AWS_REGION="${AWS_REGION:-us-east-1}"
export S3_BUCKET="${S3_BUCKET:-test-bucket}"

echo "✅ Environment variables set:"
echo "   PostgreSQL: ${PGHOST}:${PGPORT}/${PGDATABASE} (user: ${PGUSER})"
echo "   MySQL: ${MYSQL_HOST}:${MYSQL_PORT}/${MYSQL_DATABASE} (user: ${MYSQL_USER})"
echo "   MinIO/S3: ${MINIO_ENDPOINT} (bucket: ${MINIO_BUCKET})"
echo ""

# Check if services are available (optional, non-blocking)
echo "🔍 Checking service availability..."

# Check PostgreSQL
if command -v psql &> /dev/null; then
    if psql -h "${PGHOST}" -p "${PGPORT}" -U "${PGUSER}" -d "${PGDATABASE}" -c "SELECT 1;" &> /dev/null; then
        echo "   ✅ PostgreSQL: Connected"
    else
        echo "   ⚠️  PostgreSQL: Cannot connect (may not be running)"
    fi
else
    echo "   ⚠️  PostgreSQL: psql not found"
fi

# Check MySQL
if command -v mysql &> /dev/null; then
    if mysql -h "${MYSQL_HOST}" -P "${MYSQL_PORT}" -u "${MYSQL_USER}" -p"${MYSQL_PASSWORD}" -e "SELECT 1;" &> /dev/null; then
        echo "   ✅ MySQL: Connected"
    else
        echo "   ⚠️  MySQL: Cannot connect (may not be running)"
    fi
else
    echo "   ⚠️  MySQL: mysql client not found"
fi

# Check MinIO
if command -v curl &> /dev/null; then
    if curl -f "${MINIO_ENDPOINT}/minio/health/live" &> /dev/null; then
        echo "   ✅ MinIO: Available"
    else
        echo "   ⚠️  MinIO: Not available (may not be running)"
    fi
else
    echo "   ⚠️  MinIO: curl not found (cannot check)"
fi

# Only show help text if script is run directly (not sourced)
# When sourced, the caller will handle messaging
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    echo ""
    echo "💡 To use these settings, source this script:"
    echo "   source tests/setup_smoke_test_env.sh"
    echo ""
    echo "   Or run tests with:"
    echo "   source tests/setup_smoke_test_env.sh && ./tests/run_all_smoke_tests.sh"
fi

