# Quick Start Guide

Get up and running with Dativo Ingestion Platform in 5 minutes.

## Prerequisites

- **Python 3.10+** (REQUIRED - Python 3.9 and below will not work)
- Docker and Docker Compose

### Python Version Requirement

Dativo-ingest requires **Python 3.10 or higher**. Check your version:

```bash
python3 --version
```

If you see Python 3.9 or below, you must upgrade:

#### Using Conda (Recommended)
```bash
conda create -n dativo python=3.10 -y
conda activate dativo
```

#### Using Homebrew (macOS)
```bash
brew install python@3.10
python3.10 -m venv venv
source venv/bin/activate
```

#### Using pyenv
```bash
pyenv install 3.10.13
pyenv local 3.10.13
python -m venv venv
source venv/bin/activate
```

## Setup Steps

### 1. Setup

```bash
# Run automated setup script
./scripts/setup-dev.sh
```

This installs dependencies, starts infrastructure (Nessie, MinIO), creates buckets, and sets up environment variables.

### 2. Source Environment Variables

```bash
source .env
```

### 3. Run End-to-End Test

```bash
dativo run --job-dir tests/fixtures/jobs --secrets-dir tests/fixtures/secrets --mode self_hosted
```

## Expected Output

JSON logs showing job execution: startup, extraction, validation, writing Parquet files, and completion. Exit code: `0` (success) or `2` (warnings present).

## Verify Results

```bash
# Check services
curl http://localhost:19120/api/v1/config  # Nessie
curl http://localhost:9000/minio/health/live  # MinIO

# Check MinIO bucket (if mc installed)
mc ls local/test-bucket --recursive

# Or visit MinIO console: http://localhost:9001 (minioadmin/minioadmin)
```

## Troubleshooting

**Services not starting?**
```bash
docker-compose -f docker-compose.dev.yml ps
docker-compose -f docker-compose.dev.yml logs
```

**Command not found?**
```bash
# Reinstall package
pip install -e .
```

**Environment variables?**
```bash
source .env
```

## Clean Up

```bash
# Stop and remove infrastructure
docker-compose -f docker-compose.dev.yml down -v
```

## Creating Your First Job

1. **Create a job config** (`jobs/mytenant/my_job.yaml`):
```yaml
tenant_id: mytenant
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: my_asset
asset_path: assets/csv/v1.0/my_asset.yaml
source:
  files:
    - path: data/myfile.csv
      object: my_asset
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
      prefix: "raw/mytenant"
```

2. **Create an asset definition** (`assets/csv/v1.0/my_asset.yaml`):
```yaml
$schema: schemas/odcs/dativo-odcs-3.0.2-extended.schema.json
apiVersion: v3.0.2
kind: DataContract
name: my_asset
version: "1.0"
source_type: csv
object: my_asset
schema:
  - name: id
    type: integer
    required: true
  - name: name
    type: string
    required: true
target:
  file_format: parquet
  partitioning: [ingest_date]
team:
  owner: your-email@company.com
compliance:
  classification: []
```

3. **Set up secrets** (`secrets/mytenant/iceberg.env`):
```bash
S3_ENDPOINT=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_REGION=us-east-1
S3_BUCKET=test-bucket
```

4. **Run the job**:
```bash
dativo run --config jobs/mytenant/my_job.yaml --mode self_hosted
```

## Next Steps

- [Setup Guide](docs/SETUP_AND_ONBOARDING.md) - Comprehensive setup
- [Config Reference](docs/CONFIG_REFERENCE.md) - Configuration options
- [Custom Plugins](docs/CUSTOM_PLUGINS.md) - Create custom readers/writers

