# Quick Start Guide

Get up and running with Dativo Ingestion Platform in 5 minutes.

## Prerequisites

- Python 3.10+
- Docker and Docker Compose
- Git

## Setup Steps

### 1. Clone and Setup

```bash
git clone <repository-url>
cd dativo-ingest

# Run automated setup script
./scripts/setup-dev.sh
```

The setup script will:
- ✅ Install all Python dependencies
- ✅ Start Nessie and MinIO containers
- ✅ Create MinIO bucket
- ✅ Set up environment variables
- ✅ Create state directories

### 2. Source Environment Variables

```bash
source .env
```

### 3. Run End-to-End Test

```bash
dativo_ingest run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted
```

## Expected Output

You should see logs showing:
- ✅ Startup sequence completed
- ✅ Job execution started
- ✅ Records extracted and validated
- ✅ Parquet files written
- ✅ Files committed to Iceberg
- ✅ Job execution completed (exit code: 0)

## Verify Results

### Check Services

```bash
# Check Nessie
curl http://localhost:19120/api/v1/config

# Check MinIO
curl http://localhost:9000/minio/health/live
```

### Check MinIO Bucket

```bash
# Using MinIO client
mc ls local/test-bucket --recursive

# Or visit MinIO console
open http://localhost:9001  # Login: minioadmin/minioadmin
```

## Troubleshooting

**Services not starting?**
```bash
docker-compose -f docker-compose.dev.yml ps
docker-compose -f docker-compose.dev.yml logs
```

**Missing dependencies?**
```bash
pip install -r requirements.txt
pip install -e .
```

**Environment variables not set?**
```bash
source .env
# or
export $(cat .env | xargs)
```

## Clean Up

```bash
# Stop and remove infrastructure
docker-compose -f docker-compose.dev.yml down -v
```

## Next Steps

- Read [docs/SETUP_AND_ONBOARDING.md](docs/SETUP_AND_ONBOARDING.md) for comprehensive setup and onboarding guide
- Read [docs/SETUP_AND_TESTING.md](docs/SETUP_AND_TESTING.md) for detailed testing instructions
- Read [docs/INGESTION_EXECUTION.md](docs/INGESTION_EXECUTION.md) for execution flow details
- Check [docs/CONFIG_REFERENCE.md](docs/CONFIG_REFERENCE.md) for configuration options

