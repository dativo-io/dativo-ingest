# AdventureWorks for Postgres Setup

This directory contains the AdventureWorks sample database data for Postgres.

## Setup Instructions

Based on: https://github.com/lorint/AdventureWorks-for-Postgres

### 1. Get the Postgres Installation Script

You need the Postgres-specific `install.sql` file from the AdventureWorks-for-Postgres repository:

```bash
# Clone or download the repository
git clone https://github.com/lorint/AdventureWorks-for-Postgres.git /tmp/adventureworks-postgres

# Copy the install.sql file to this directory
cp /tmp/adventureworks-postgres/install.sql tests/fixtures/seeds/AdventureWorks-oltp-install-script/
```

### 2. Prepare CSV Files (if needed)

If you have the original SQL Server CSV files, you may need to convert them using the `update_csvs.rb` script:

```bash
# If you have update_csvs.rb from the repo
cd tests/fixtures/seeds/AdventureWorks-oltp-install-script
ruby update_csvs.rb
```

### 3. Start Postgres Container

```bash
# Start the Postgres container
docker-compose -f docker-compose.dev.yml up -d postgres

# Wait for it to be ready
docker exec dativo-postgres pg_isready -U postgres
```

### 4. Load the Database

Use the setup script:

```bash
./scripts/setup-adventureworks-postgres.sh
```

Or manually:

```bash
# Create database
docker exec -i dativo-postgres psql -U postgres -c 'CREATE DATABASE "Adventureworks";'

# Load data
docker exec -i dativo-postgres psql -U postgres -d Adventureworks < tests/fixtures/seeds/AdventureWorks-oltp-install-script/install.sql
```

### 5. Verify Installation

```bash
# Connect to the database
docker exec -it dativo-postgres psql -U postgres -d Adventureworks

# List tables in schemas
\dt (humanresources|person|production|purchasing|sales).*

# Check Person table
SELECT COUNT(*) FROM person.person;

# Check Product table
SELECT COUNT(*) FROM production.product;
```

### Connection Details

- **Host**: localhost (or `dativo-postgres` from within Docker network)
- **Port**: 5432
- **Database**: Adventureworks
- **User**: postgres
- **Password**: postgres

### Environment Variables

Set these for the jobs to connect:

```bash
export PGHOST=localhost
export PGPORT=5432
export PGDATABASE=Adventureworks
export PGUSER=postgres
export PGPASSWORD=postgres
```

### Notes

- The database name is case-sensitive: `Adventureworks` (not `adventureworks`)
- Tables are in schemas: `person`, `production`, `sales`, `purchasing`, `humanresources`
- The `instawdb.sql` file in this directory is the SQL Server version and won't work with Postgres
- You need the Postgres-specific `install.sql` from the AdventureWorks-for-Postgres repository

