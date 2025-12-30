#!/bin/bash
# Testing Playbook: Setup PostgreSQL employees table
# This script creates the employees table required for test cases 7, 8, and 9
# 
# Note: If you're using docker-compose, the employees table is automatically
# created from tests/fixtures/seeds/postgres_employees_setup.sql when the
# container is first created. This script is useful for:
# - Re-running setup without recreating containers
# - Setting up on existing databases
# - Manual setup outside of docker-compose
#
# This script uses the shared seed file to ensure consistency between
# tests and the testing playbook.
#
# Usage: ./scripts/testing-playbook-setup-postgres-employees.sh

set -e

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SEED_FILE="$PROJECT_ROOT/tests/fixtures/seeds/postgres_employees_setup.sql"

# Verify seed file exists
if [ ! -f "$SEED_FILE" ]; then
    echo "❌ Error: Seed file not found: $SEED_FILE"
    exit 1
fi

# Load connection details from environment or use defaults
PGHOST="${PGHOST:-localhost}"
PGPORT="${PGPORT:-5432}"
PGDATABASE="${PGDATABASE:-postgres}"
PGUSER="${PGUSER:-postgres}"
PGPASSWORD="${PGPASSWORD:-postgres}"

echo "Setting up employees table in PostgreSQL..."
echo "Host: $PGHOST:$PGPORT"
echo "Database: $PGDATABASE"
echo "User: $PGUSER"
echo "Using seed file: $SEED_FILE"

# Check if we should use docker exec or direct psql
if command -v docker &> /dev/null; then
    POSTGRES_CONTAINER=$(docker ps --filter "name=postgres" --format "{{.Names}}" 2>/dev/null | head -1)
    
    if [ -n "$POSTGRES_CONTAINER" ]; then
        echo "Using Docker container: $POSTGRES_CONTAINER"
        # Use the shared seed file
        docker exec -i "$POSTGRES_CONTAINER" psql -U "$PGUSER" -d "$PGDATABASE" < "$SEED_FILE"
        # Verify the table was created
        docker exec -i "$POSTGRES_CONTAINER" psql -U "$PGUSER" -d "$PGDATABASE" -c "SELECT COUNT(*) as employee_count FROM employees;"
        echo "✅ Employees table created successfully in Docker container"
        exit 0
    fi
fi

# Fallback to direct psql connection
if command -v psql &> /dev/null; then
    echo "Using direct psql connection"
    export PGPASSWORD
    # Use the shared seed file
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -f "$SEED_FILE"
    # Verify the table was created
    psql -h "$PGHOST" -p "$PGPORT" -U "$PGUSER" -d "$PGDATABASE" -c "SELECT COUNT(*) as employee_count FROM employees;"
    echo "✅ Employees table created successfully"
else
    echo "❌ Error: Neither Docker nor psql command found"
    echo "Please install PostgreSQL client tools or ensure Docker is running"
    exit 1
fi

