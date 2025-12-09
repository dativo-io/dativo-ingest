# Performance Tests

Performance tests for dativo-ingest measure end-to-end performance of CSV and Iceberg operations.

## Overview

Performance tests follow the same **config-driven approach** as smoke tests:
- Job configurations in `tests/fixtures/jobs/performance_test_*.yaml`
- Asset definitions in `tests/fixtures/assets/csv/v1.0/perf_test_data.yaml`
- Synthetic data generation: `tests/fixtures/jobs/mimesis_perf_test.yaml` (using Mimesis connector)
- Legacy script (deprecated): `tests/scripts/generate_perf_test_data.py`
- CSV writer plugin: `tests/fixtures/plugins/csv_writer.py`

## Test Scenarios

The suite tests 4 scenarios:

1. **CSV Reader (Python) → Iceberg Table**
   - Uses standard Python CSV reader
   - Writes to Iceberg table on S3 (MinIO)
   - Job config: `performance_test_1_csv_python_to_iceberg.yaml`

2. **CSV Reader (Rust) → Iceberg Table**
   - Uses Rust CSV reader plugin (10-100x faster)
   - Writes to Iceberg table on S3 (MinIO)
   - Job config: `performance_test_2_csv_rust_to_iceberg.yaml`

3. **Iceberg Table → CSV Writer (Python)**
   - Reads Parquet files from Iceberg table
   - Writes as CSV using Python writer plugin
   - Job config: `performance_test_3_iceberg_to_csv_python.yaml`

4. **Iceberg Table → CSV Writer (Rust)**
   - Reads Parquet files from Iceberg table
   - Writes as CSV using Rust writer plugin
   - Job config: `performance_test_4_iceberg_to_csv_rust.yaml`

## Requirements

- **Docker** (for MinIO and Nessie infrastructure)
- **Python 3.10+** with dependencies installed
- **Rust toolchain** (optional, for Rust plugin tests)
- **~2GB free disk space** (for 1GB test data + results)

## Quick Start

```bash
# Run all performance tests
make performance-test

# Or directly:
./tests/run_performance_tests.sh
```

## Test Data Generation

### Recommended: Mimesis Connector (Standard Approach)

Performance tests should use synthetic data generated via the **Mimesis connector**:

```bash
# Generate 1 million rows of realistic test data
python -m dativo_ingest.cli execute tests/fixtures/jobs/mimesis_perf_test.yaml
```

**Why Mimesis?**
- ✅ **Realistic synthetic data** (names, emails, addresses vs "User_123")
- ✅ **Reproducible results** (with seed parameter for consistent benchmarks)
- ✅ **Schema-driven** (automatically matches your asset definitions)
- ✅ **Platform integrated** (structured logging, monitoring, validation)
- ✅ **Configurable** (row count, batch size, locales, numeric ranges)

**Customization:**
```yaml
# Edit tests/fixtures/jobs/mimesis_perf_test.yaml
source:
  engine:
    options:
      row_count: 1000000  # Adjust as needed
      batch_size: 10000
      seed: 42            # For reproducible benchmarks
```

**Output location:**
- Configured in job's target section (typically S3/MinIO)
- Parquet format for Iceberg performance tests

### Legacy: Python Script (Deprecated)

The legacy script `tests/scripts/generate_perf_test_data.py` is **deprecated** and kept only for backwards compatibility:

```bash
# Not recommended - use Mimesis connector instead
python tests/scripts/generate_perf_test_data.py --size-gb 0.5
```

**Migration:** Replace any CI/automation scripts that use `generate_perf_test_data.py` with the Mimesis job above.

## Running Tests

### Full Suite

```bash
# Run all tests (sets up infrastructure, generates data, runs all 4 scenarios)
make performance-test
```

### With Options

```bash
# Skip infrastructure setup (if services already running)
./tests/run_performance_tests.sh --skip-infrastructure-setup

# Skip data generation (use existing CSV file)
./tests/run_performance_tests.sh --skip-data-generation

# Both options
./tests/run_performance_tests.sh --skip-infrastructure-setup --skip-data-generation
```

### Individual Tests

You can run individual test jobs directly:

```bash
# Set environment variables
export PERF_TEST_CSV_FILE=tests/fixtures/seeds/perf_test_data_1gb.csv
export S3_ENDPOINT=http://localhost:9000
export AWS_ACCESS_KEY_ID=minioadmin
export AWS_SECRET_ACCESS_KEY=minioadmin
export AWS_REGION=us-east-1
export NESSIE_URI=http://localhost:19120/api/v1

# Run a specific test
PYTHONPATH=src python -m dativo_ingest.cli run \
  --job-config tests/fixtures/jobs/performance_test_1_csv_python_to_iceberg.yaml \
  --secrets-dir tests/fixtures/secrets \
  --mode self_hosted
```

## Results

Test results are stored in `/tmp/dativo_perf_test_results/`:
- `{test_name}_output.log` - Full CLI output
- `{test_name}_result.json` - Test results (if available)

The script prints a summary table with:
- Test name
- Status (PASSED/FAILED/SKIPPED)
- Duration in seconds

## CSV Writer Plugin

The CSV writer plugin (`tests/fixtures/plugins/csv_writer.py`) follows the same pattern as other test plugins:

- **Location**: `tests/fixtures/plugins/csv_writer.py`
- **Class**: `CSVWriter`
- **Usage**: `custom_writer: "tests/fixtures/plugins/csv_writer.py:CSVWriter"`

### Configuration Options

```yaml
target:
  custom_writer: "tests/fixtures/plugins/csv_writer.py:CSVWriter"
  engine:
    options:
      delimiter: ","          # CSV delimiter (default: ",")
      include_header: true    # Include header row (default: true)
```

## Integration with Standard Tests

Performance tests are **separate** from standard tests:

- **Standard tests**: `make test` (excludes performance tests)
- **Performance tests**: `make performance-test` (opt-in)

Performance tests are marked with `@pytest.mark.performance` and excluded from regular test runs using `-m "not performance"`.

## Troubleshooting

### Rust Plugin Not Found

If Rust plugin tests are skipped:

```bash
# Build Rust plugins
cd examples/plugins/rust
cargo build --release

# Verify build output
ls -lh target/release/libcsv_reader_plugin.*
```

### Infrastructure Not Available

If infrastructure services aren't running:

```bash
# Start infrastructure manually
./tests/setup_smoke_test_infrastructure.sh

# Or use docker-compose
docker compose -f docker-compose.dev.yml up -d
```

### Test Data Generation Fails

If data generation fails:

```bash
# Check Python dependencies (including Mimesis)
pip install -e ".[dev]"

# Generate using Mimesis connector (recommended)
python -m dativo_ingest.cli execute tests/fixtures/jobs/mimesis_perf_test.yaml

# Or use legacy script
python tests/scripts/generate_perf_test_data.py --size-gb 0.1
```

## See Also

- [tests/README.md](README.md) - General testing documentation
- [tests/fixtures/jobs/](fixtures/jobs/) - Job configurations
- [tests/fixtures/plugins/](fixtures/plugins/) - Test plugins
- [examples/plugins/rust/](../../examples/plugins/rust/) - Rust plugin examples
