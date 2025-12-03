# Setup and Testing Guide

This guide explains how to set up a local testing environment and run end-to-end tests for dativo-ingest.

**Note:** For comprehensive setup and onboarding instructions, see [SETUP_AND_ONBOARDING.md](SETUP_AND_ONBOARDING.md).

## Prerequisites

- Python 3.10+
- Docker and Docker Compose
- Git

## Quick Setup (5 minutes)

### Option A: Automated Setup (Recommended)

Run the setup script:

```bash
./scripts/setup-dev.sh
```

This script will:
- Install Python dependencies
- Start Nessie and MinIO containers
- Create MinIO bucket
- Set up environment variables
- Create state directories

Then source the environment variables and run:

```bash
source .env
dativo run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted
```

### Option B: Manual Setup

For detailed manual setup instructions, see [SETUP_AND_ONBOARDING.md](SETUP_AND_ONBOARDING.md). The key steps are:

1. Install dependencies: `pip install -r requirements.txt && pip install -e .`
2. Start infrastructure: `docker-compose -f docker-compose.dev.yml up -d`
3. Set environment variables (see `.env` file or export them)
4. Run tests

```bash
# Set PYTHONPATH if not installed in editable mode
export PYTHONPATH=src:$PYTHONPATH

# Run the test
dativo run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted
```

**Note:** If the `dativo` command is not available, use:
```bash
python -m dativo_ingest.cli run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted
```

## Expected Output

You should see:

1. **Startup sequence logs**:
   - Tenant inferred
   - Secrets loaded
   - Environment variables validated
   - Infrastructure validated
   - State management initialized

2. **Job execution logs**:
   - Job started
   - Schema validation passed
   - Connector validation passed
   - Asset definition loaded
   - Extractor initialized
   - Schema validator initialized
   - Parquet writer initialized
   - Iceberg committer initialized
   - Iceberg table ensured
   - Records extracted and validated
   - Parquet files written
   - Files committed to Iceberg
   - Job execution completed

3. **Exit code**: `0` (success) or `2` (if validation warnings present)

## Verify Results

### Check Parquet Files

Parquet files should be written locally (before upload to MinIO):

```bash
# Find Parquet files
find . -name "*.parquet" -type f

# Check file size
ls -lh s3://test-lake/adventureworks/csv_person/ 2>/dev/null || \
  find . -path "*/csv_person/*.parquet" -exec ls -lh {} \;
```

### Check MinIO (S3)

```bash
# List files in bucket
mc ls local/test-bucket --recursive

# Or using AWS CLI
aws --endpoint-url=http://localhost:9000 s3 ls s3://test-bucket --recursive
```

### Check Nessie Catalog

```bash
# List branches
curl http://localhost:19120/api/v1/branches

# List tables (if Nessie API supports it)
curl http://localhost:19120/api/v1/trees/test_tenant
```

## Troubleshooting

### Issue: "pyiceberg is required"

**Solution**: Install missing dependencies:
```bash
pip install pyiceberg pynessie boto3 pandas pyarrow
```

### Issue: "Connection refused" to Nessie

**Solution**: 
1. Check Nessie is running: `docker ps | grep nessie`
2. Check port: `curl http://localhost:19120/api/v1/config`
3. Restart: `docker-compose -f docker-compose.dev.yml restart nessie`

### Issue: "Connection refused" to MinIO

**Solution**:
1. Check MinIO is running: `docker ps | grep minio`
2. Check port: `curl http://localhost:9000/minio/health/live`
3. Restart: `docker-compose -f docker-compose.dev.yml restart minio`

### Issue: "Bucket does not exist"

**Solution**: Create the bucket:
```bash
mc mb local/test-bucket
```

### Issue: "Read-only file system: '/state'"

**Solution**: Create state directory locally:
```bash
mkdir -p .local/state/test_tenant
```

Or update the job config to use a local path.

### Issue: "CSV file not found"

**Solution**: Ensure test data exists:
```bash
ls -la tests/fixtures/seeds/adventureworks/Person.csv
```

### Issue: Environment variables not set

**Solution**: Export them or use a `.env` file:
```bash
export NESSIE_URI="http://localhost:19120/api/v1"
export S3_ENDPOINT="http://localhost:9000"
# ... etc
```

## Clean Up

Stop and remove infrastructure:

```bash
docker-compose -f docker-compose.dev.yml down -v
```

This removes containers and volumes (data will be lost).

## Alternative: Using Makefile

The Makefile includes a smoke test target:

```bash
# Install dependencies first
pip install -r requirements.txt
pip install -e .

# Set up infrastructure
docker-compose -f docker-compose.dev.yml up -d

# Set environment variables
export NESSIE_URI="http://localhost:19120/api/v1"
export S3_ENDPOINT="http://localhost:9000"
export AWS_ACCESS_KEY_ID="minioadmin"
export AWS_SECRET_ACCESS_KEY="minioadmin"
export AWS_REGION="us-east-1"

# Run smoke test
make test-smoke
```

## WAL Testing

The WAL (Write-Ahead Log) checkpointing system has comprehensive test coverage:

### Test Categories

1. **Unit Tests** (`tests/test_wal_manager.py`): 13 test cases covering WAL Manager core functionality
   - WAL file creation, loading, checkpoint updates
   - Resume detection, finalization, cleanup
   - Multiple checkpoint types and atomic writes

2. **Integration Tests** (`tests/integration/test_wal_integration.py`): 8 test cases
   - CSV, Postgres, MySQL, GDrive CSV, Google Sheets extractors with WAL
   - Airbyte extractor STATE message mapping
   - WAL finalization and cleanup

3. **Infrastructure Tests** (`tests/test_wal_infrastructure.py`): 11 test cases
   - Directory creation, permissions, concurrent access
   - Atomic writes, cleanup, persistence
   - Multi-tenant and multi-job scenarios

4. **Smoke Tests** (`tests/smoke_tests_wal.sh`): End-to-end testing
   - WAL file creation during job execution
   - Checkpoint updates and resume scenarios
   - WAL finalization verification

### Running WAL Tests

```bash
# Run all WAL tests
pytest tests/test_wal_manager.py \
       tests/integration/test_wal_integration.py \
       tests/test_wal_infrastructure.py -v

# Run smoke tests
./tests/smoke_tests_wal.sh
```

**Test Results**: All 32 test cases passing (13 unit + 8 integration + 11 infrastructure)

For detailed WAL documentation, see [WAL_CHECKPOINTING.md](WAL_CHECKPOINTING.md).

## Additional Resources

- [SETUP_AND_ONBOARDING.md](SETUP_AND_ONBOARDING.md) - Comprehensive setup and onboarding guide
- [INGESTION_EXECUTION.md](INGESTION_EXECUTION.md) - Detailed execution flow
- [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) - Configuration options
- [WAL_CHECKPOINTING.md](WAL_CHECKPOINTING.md) - WAL checkpointing documentation
- [QUICKSTART.md](../QUICKSTART.md) - Quick start guide
- [README.md](../README.md) - Project overview

