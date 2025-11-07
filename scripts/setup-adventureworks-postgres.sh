#!/bin/bash
# Setup script for AdventureWorks Postgres database
# Based on: https://github.com/lorint/AdventureWorks-for-Postgres

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
SEEDS_DIR="$PROJECT_ROOT/tests/fixtures/seeds/AdventureWorks-oltp-install-script"

echo "Setting up AdventureWorks Postgres database..."

# Check if Postgres container is running
if ! docker ps | grep -q dativo-postgres; then
    echo "Error: Postgres container (dativo-postgres) is not running."
    echo "Please start it with: docker-compose -f docker-compose.dev.yml up -d postgres"
    exit 1
fi

# Wait for Postgres to be ready
echo "Waiting for Postgres to be ready..."
until docker exec dativo-postgres pg_isready -U postgres > /dev/null 2>&1; do
    echo "Waiting for Postgres..."
    sleep 2
done

# Check if database already exists
DB_EXISTS=$(docker exec dativo-postgres psql -U postgres -tAc "SELECT 1 FROM pg_database WHERE datname='Adventureworks'" || echo "")

if [ "$DB_EXISTS" = "1" ]; then
    echo "Database 'Adventureworks' already exists. Skipping setup."
    echo "To recreate, run: docker exec dativo-postgres psql -U postgres -c 'DROP DATABASE \"Adventureworks\";'"
    exit 0
fi

# Check if we have the Postgres install script
if [ ! -f "$SEEDS_DIR/install.sql" ]; then
    echo "Error: install.sql not found in $SEEDS_DIR"
    echo ""
    echo "Please follow the AdventureWorks-for-Postgres setup instructions:"
    echo "1. Download Adventure Works 2014 OLTP Script from CodePlex"
    echo "2. Extract and copy CSV files to $SEEDS_DIR"
    echo "3. Run: ruby update_csvs.rb (if update_csvs.rb exists)"
    echo "4. Copy install.sql from the AdventureWorks-for-Postgres repo to $SEEDS_DIR"
    echo ""
    echo "See: https://github.com/lorint/AdventureWorks-for-Postgres"
    exit 1
fi

# Create database
echo "Creating database 'Adventureworks'..."
docker exec -i dativo-postgres psql -U postgres <<EOF
CREATE DATABASE "Adventureworks";
EOF

# Load data using install.sql
echo "Loading AdventureWorks data (this may take a few minutes)..."
docker exec -i dativo-postgres psql -U postgres -d Adventureworks < "$SEEDS_DIR/install.sql"

echo ""
echo "AdventureWorks database setup complete!"
echo ""
echo "Connection details:"
echo "  Host: localhost"
echo "  Port: 5432"
echo "  Database: Adventureworks"
echo "  User: postgres"
echo "  Password: postgres"
echo ""
echo "To connect:"
echo "  docker exec -it dativo-postgres psql -U postgres -d Adventureworks"
echo ""
echo "To verify tables:"
echo "  docker exec dativo-postgres psql -U postgres -d Adventureworks -c \"\\dt (humanresources|person|production|purchasing|sales).*\""

