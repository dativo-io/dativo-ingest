#!/bin/bash
# Setup script for MySQL test database (employees)
# Uses test_db dataset: https://github.com/datacharmer/test_db

set -e

MYSQL_HOST="${MYSQL_HOST:-localhost}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-root}"
MYSQL_PASSWORD="${MYSQL_PASSWORD:-root}"
MYSQL_DATABASE="${MYSQL_DATABASE:-employees}"

echo "Setting up MySQL test database..."

# Check if MySQL container is running
if ! docker ps | grep -q dativo-mysql; then
    echo "MySQL container (dativo-mysql) is not running. Please start it with: docker-compose up -d mysql"
    exit 1
fi

# Wait for MySQL to be ready
echo "Waiting for MySQL to be ready..."
until docker exec dativo-mysql mysqladmin ping -h localhost -u root -proot --silent; do
    echo "Waiting for MySQL..."
    sleep 2
done

echo "MySQL is ready!"

# Check if database already exists and has data
DB_EXISTS=$(docker exec dativo-mysql mysql -u root -proot -e "SHOW DATABASES LIKE '${MYSQL_DATABASE}';" | grep -c "${MYSQL_DATABASE}" || true)

if [ "$DB_EXISTS" -gt 0 ]; then
    ROW_COUNT=$(docker exec dativo-mysql mysql -u root -proot -e "USE ${MYSQL_DATABASE}; SELECT COUNT(*) FROM employees;" 2>/dev/null | tail -1 || echo "0")
    if [ "$ROW_COUNT" -gt 0 ]; then
        echo "Database ${MYSQL_DATABASE} already exists with data. Skipping setup."
        exit 0
    fi
fi

# Load schema
echo "Loading schema..."
docker exec -i dativo-mysql mysql -u root -proot < tests/fixtures/seeds/test_db/employees.sql

# Load data from dump files
echo "Loading data..."
for dump_file in tests/fixtures/seeds/test_db/load_*.dump; do
    if [ -f "$dump_file" ]; then
        echo "Loading $(basename $dump_file)..."
        docker exec -i dativo-mysql mysql -u root -proot employees < "$dump_file"
    fi
done

echo "✅ MySQL test database setup complete!"
echo "Database: ${MYSQL_DATABASE}"
echo "Tables: employees, departments, dept_emp, dept_manager, titles, salaries"

