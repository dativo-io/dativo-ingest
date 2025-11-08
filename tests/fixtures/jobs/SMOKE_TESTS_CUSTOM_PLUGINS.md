# Custom Plugin Smoke Tests

This directory contains smoke test job configurations that demonstrate the use of custom Python and Rust plugins in the Dativo ETL platform.

## Overview

These smoke tests validate:
- **Python custom readers** - Easy-to-develop custom data extraction
- **Rust custom readers** - High-performance data extraction (10-100x faster)
- **Rust custom writers** - Optimized data writing with better compression
- **Mixed combinations** - Python readers with Rust writers, etc.

## Test Jobs

### Test 1: Postgres Employee (Python Reader + Rust Writer)
**File:** `smoke_test_1_postgres_employee_python_rust.yaml`

- **Source:** Postgres AdventureWorks Employee table
- **Reader:** Python custom reader (`PostgresEmployeeReader`)
- **Writer:** Rust Parquet writer
- **Target:** Iceberg with Markdown-KV storage

**Demonstrates:**
- Python custom reader for database extraction
- Rust custom writer for high-performance Parquet writing
- Incremental sync support

### Test 2: CSV Employee (Python Reader)
**File:** `smoke_test_2_csv_employee_python_reader.yaml`

- **Source:** CSV Employee file
- **Reader:** Python custom reader (`CSVEmployeeReader`)
- **Writer:** Default Parquet writer
- **Target:** Iceberg table

**Demonstrates:**
- Python custom reader for CSV files
- Custom data transformation and cleaning
- Batch processing

### Test 3: MySQL Employees (Rust Writer)
**File:** `smoke_test_3_mysql_employees_rust_writer.yaml`

- **Source:** MySQL employees database
- **Reader:** Built-in MySQL extractor
- **Writer:** Rust Parquet writer
- **Target:** Iceberg with Markdown-KV storage

**Demonstrates:**
- Built-in extractor with custom Rust writer
- High-performance Parquet writing
- Compression options

### Test 4: Postgres Person (Python Reader)
**File:** `smoke_test_4_postgres_person_python_reader.yaml`

- **Source:** Postgres AdventureWorks Person table
- **Reader:** Python custom reader (`PostgresPersonReader`)
- **Writer:** Default Parquet writer
- **Target:** Iceberg with Markdown-KV storage

**Demonstrates:**
- Python custom reader for different table types
- Incremental sync with state management

### Test 5: CSV Product (Rust Reader + Writer)
**File:** `smoke_test_5_csv_product_rust_reader_writer.yaml`

- **Source:** CSV Product file
- **Reader:** Rust CSV reader
- **Writer:** Rust Parquet writer
- **Target:** Iceberg table

**Demonstrates:**
- Maximum performance with Rust reader and writer
- Large batch processing
- Best compression ratios

## Running the Tests

### Prerequisites

1. **Build Rust plugins** (required for tests 1, 3, and 5):
   ```bash
   cd examples/plugins/rust
   cargo build --release
   ```

2. **Set up test environment:**
   - PostgreSQL with AdventureWorks database
   - MySQL with employees database
   - MinIO or S3-compatible storage
   - Test data files in `tests/fixtures/seeds/`

3. **Set environment variables:**
   ```bash
   export PGHOST=localhost
   export PGPORT=5432
   export PGDATABASE=Adventureworks
   export PGUSER=postgres
   export PGPASSWORD=postgres
   
   export MYSQL_HOST=localhost
   export MYSQL_PORT=3306
   export MYSQL_DATABASE=employees
   export MYSQL_USER=test
   export MYSQL_PASSWORD=test
   
   export MINIO_ENDPOINT=http://localhost:9000
   export MINIO_ACCESS_KEY=minioadmin
   export MINIO_SECRET_KEY=minioadmin
   export AWS_REGION=us-east-1
   export S3_ENDPOINT=http://localhost:9000
   export AWS_ACCESS_KEY_ID=minioadmin
   export AWS_SECRET_ACCESS_KEY=minioadmin
   ```

### Run All Tests

```bash
cd tests
./smoke_tests_custom_plugins.sh
```

### Run Individual Test

```bash
python -m dativo_ingest.cli run \
    --job-file tests/fixtures/jobs/smoke_test_1_postgres_employee_python_rust.yaml \
    --secrets-dir tests/fixtures/secrets \
    --mode self_hosted
```

## Custom Plugins

### Python Custom Readers

Located in `tests/fixtures/plugins/`:

- **`postgres_employee_reader.py`** - Postgres Employee table reader
- **`postgres_person_reader.py`** - Postgres Person table reader
- **`csv_employee_reader.py`** - CSV Employee file reader

### Rust Custom Plugins

Located in `examples/plugins/rust/`:

- **`libcsv_reader_plugin.so`** (or `.dylib` on macOS) - High-performance CSV reader
- **`libparquet_writer_plugin.so`** (or `.dylib` on macOS) - Optimized Parquet writer

## Performance Comparison

| Test | Reader | Writer | Performance |
|------|--------|--------|-------------|
| Test 1 | Python | Rust | Balanced (easy dev + fast write) |
| Test 2 | Python | Default | Standard |
| Test 3 | Default | Rust | Fast write |
| Test 4 | Python | Default | Standard |
| Test 5 | Rust | Rust | Maximum performance |

**Expected Performance Gains:**
- Rust CSV Reader: **15x faster**, **12x less memory**
- Rust Parquet Writer: **3.5x faster**, **27% better compression**

## Troubleshooting

### Rust Plugins Not Found

If you see "Rust plugin not found" errors:

1. Build the plugins:
   ```bash
   cd examples/plugins/rust
   cargo build --release
   ```

2. Check the file extension:
   - Linux: `.so`
   - macOS: `.dylib`
   - Windows: `.dll`

3. Verify the path in the job configuration matches your build location.

### Database Connection Errors

Ensure your databases are running and accessible:

```bash
# Check PostgreSQL
psql -h localhost -U postgres -d Adventureworks -c "SELECT COUNT(*) FROM humanresources.employee;"

# Check MySQL
mysql -h localhost -u test -ptest employees -e "SELECT COUNT(*) FROM employees;"
```

### Missing Test Data

Ensure test data files exist:

```bash
ls tests/fixtures/seeds/adventureworks/
# Should show: Employee.csv, Product.csv, etc.
```

## Next Steps

- Create your own custom readers/writers based on these examples
- See `examples/plugins/` for more plugin examples
- Read `docs/CUSTOM_PLUGINS.md` for detailed documentation

