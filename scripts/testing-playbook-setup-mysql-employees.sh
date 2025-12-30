#!/bin/bash
# Testing Playbook: Setup MySQL employees table
# This script creates the employees table required for test cases
# 
# Note: If you're using docker-compose, the employees table is automatically
# created from tests/fixtures/seeds/mysql_employees_setup.sql when the
# container is first created. This script is useful for:
# - Re-running setup without recreating containers
# - Setting up on existing databases
# - Manual setup outside of docker-compose
#
# This script uses the shared seed file to ensure consistency between
# tests and the testing playbook. The schema matches the PostgreSQL
# employees table for cross-database compatibility.
#
# Usage: ./scripts/testing-playbook-setup-mysql-employees.sh

set -e

# Get the script directory and project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SEED_FILE="$PROJECT_ROOT/tests/fixtures/seeds/mysql_employees_setup.sql"

# Verify seed file exists
if [ ! -f "$SEED_FILE" ]; then
    echo "❌ Error: Seed file not found: $SEED_FILE"
    exit 1
fi

# Load connection details from environment or use defaults
MYSQL_HOST="${MYSQL_HOST:-localhost}"
MYSQL_PORT="${MYSQL_PORT:-3307}"
MYSQL_DATABASE="${MYSQL_DATABASE:-employees}"
MYSQL_USER="${MYSQL_USER:-test}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-test}"

echo "Setting up employees table in MySQL..."
echo "Host: $MYSQL_HOST:$MYSQL_PORT"
echo "Database: $MYSQL_DATABASE"
echo "User: $MYSQL_USER"
echo "Using seed file: $SEED_FILE"

# Check if we should use docker exec or direct mysql
if command -v docker &> /dev/null; then
    MYSQL_CONTAINER=$(docker ps --filter "name=mysql" --format "{{.Names}}" 2>/dev/null | head -1)
    
    if [ -n "$MYSQL_CONTAINER" ]; then
        echo "Using Docker container: $MYSQL_CONTAINER"
        # Use the shared seed file
        docker exec -i "$MYSQL_CONTAINER" mysql -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" < "$SEED_FILE"
        # Verify the table was created
        docker exec -i "$MYSQL_CONTAINER" mysql -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) as employee_count FROM employees;"
        echo "✅ Employees table created successfully in Docker container"
        exit 0
    fi
fi

# Fallback to direct mysql connection
if command -v mysql &> /dev/null; then
    echo "Using direct mysql connection"
    # Use the shared seed file
    mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" < "$SEED_FILE"
    # Verify the table was created
    mysql -h "$MYSQL_HOST" -P "$MYSQL_PORT" -u "$MYSQL_USER" -p"$MYSQL_PASSWORD" "$MYSQL_DATABASE" -e "SELECT COUNT(*) as employee_count FROM employees;"
    echo "✅ Employees table created successfully"
else
    echo "❌ Error: Neither Docker nor mysql command found"
    echo "Please install MySQL client tools or ensure Docker is running"
    exit 1
fi

