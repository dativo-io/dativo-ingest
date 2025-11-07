# Setup and End-to-End Testing Guide

This guide explains how to set up a local development environment and run end-to-end tests after cloning the repository.

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
dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted
```

### Option B: Manual Setup

### 1. Clone and Install Dependencies

```bash
# Clone the repository
git clone <repository-url>
cd dativo-ingest

# Create a virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install Python dependencies
pip install -r requirements.txt

# Install package in development mode
pip install -e .
```

### 2. Start Local Infrastructure

Start Nessie (catalog) and MinIO (S3-compatible storage) using Docker Compose:

```bash
docker-compose -f docker-compose.dev.yml up -d
```

Wait for services to be healthy (about 30 seconds):

```bash
# Check services are running
docker-compose -f docker-compose.dev.yml ps

# Check Nessie is ready
curl http://localhost:19120/api/v1/config

# Check MinIO is ready
curl http://localhost:9000/minio/health/live
```

### 3. Set Up MinIO Bucket

Create the test bucket in MinIO:

```bash
# Using MinIO client (mc) - install if needed: https://min.io/docs/minio/linux/reference/minio-mc.html
mc alias set local http://localhost:9000 minioadmin minioadmin
mc mb local/test-bucket
mc anonymous set download local/test-bucket
```

Or use the MinIO web console at http://localhost:9001 (login: minioadmin/minioadmin) to create a bucket named `test-bucket`.

### 4. Set Environment Variables

Export the required environment variables:

```bash
export NESSIE_URI="http://localhost:19120/api/v1"
export S3_ENDPOINT="http://localhost:9000"
export AWS_ACCESS_KEY_ID="minioadmin"
export AWS_SECRET_ACCESS_KEY="minioadmin"
export AWS_REGION="us-east-1"
export S3_BUCKET="test-bucket"
```

Or create a `.env` file in the project root:

```bash
cat > .env << EOF
NESSIE_URI=http://localhost:19120/api/v1
S3_ENDPOINT=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_REGION=us-east-1
S3_BUCKET=test-bucket
EOF

# Source it (if using bash/zsh)
source .env
```

### 5. Create State Directory

```bash
# State directory is created automatically, but you can pre-create it:
mkdir -p .local/state/test_tenant
```

**Note:** State files are stored in `.local/state/` by default (hidden directory, gitignored). For production, set `STATE_DIR` environment variable to point to your state storage (database, S3, etc.).

### 6. Run End-to-End Test

```bash
# Set PYTHONPATH if not installed in editable mode
export PYTHONPATH=src:$PYTHONPATH

# Run the test
dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted
```

Or using Python module:

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

3. **Exit code**: `0` (success)

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

## Next Steps

- Read [INGESTION_EXECUTION.md](INGESTION_EXECUTION.md) for detailed execution flow
- Check [CONFIG_REFERENCE.md](CONFIG_REFERENCE.md) for configuration options
- Review [MILESTONE_1_2_HANDOFF.md](MILESTONE_1_2_HANDOFF.md) for implementation details

