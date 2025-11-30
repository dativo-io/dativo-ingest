# Testing Quick Reference Guide

Quick commands and shortcuts for testing dativo-ingest capabilities.

## 🚀 Quick Start (2 Minutes)

### 1. Set Up Environment Variables

```bash
# Source the .env file (contains all required variables)
source .env

# Verify variables are set
echo $S3_ENDPOINT        # Should show: http://localhost:9000
echo $AWS_ACCESS_KEY_ID  # Should show: minioadmin
echo $NESSIE_URI         # Should show: http://localhost:19120/api/v1
```

**For detailed variable reference, see [ENVIRONMENT_SETUP_GUIDE.md](ENVIRONMENT_SETUP_GUIDE.md)**

### 2. Verify Services

```bash
# Check Docker services are running
docker ps | grep -E '(nessie|minio|postgres)'

# Test endpoints
curl http://localhost:19120/api/v1/config  # Nessie
curl http://localhost:9000/minio/health/live  # MinIO

# Check MinIO data
mc ls local/test-bucket --recursive
# Or visit: http://localhost:9001 (minioadmin/minioadmin)
```

### 3. Run First Test

```bash
# Generate test data
./scripts/generate-test-data.sh

# Run smoke test
dativo run \
  --job-dir tests/fixtures/jobs \
  --secret-manager filesystem \
  --secrets-dir tests/fixtures/secrets \
  --mode self_hosted
```

---

## Setup Commands (Run Once)

```bash
# Complete setup
./scripts/setup-dev.sh && source .env

# Or minimal setup
pip install -e .
docker-compose -f docker-compose.dev.yml up -d
source .env
```

## CLI Commands Cheat Sheet

### Run Jobs

```bash
# Single job
dativo run --config jobs/mytenant/myjob.yaml --mode self_hosted

# All jobs in directory (with filesystem secrets)
dativo run --job-dir jobs/mytenant \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# With environment variable secrets
export DATIVO_SECRET__MYTENANT__postgres__env=$'PGHOST=localhost\nPGUSER=postgres'
dativo run --config jobs/mytenant/myjob.yaml --mode self_hosted
```

### Connection Testing

```bash
# Test connection before running
dativo check --config jobs/mytenant/myjob.yaml --verbose

# JSON output for scripting
dativo check --config jobs/mytenant/myjob.yaml --json
```

### Discovery

```bash
# Discover available data sources
dativo discover --config jobs/mytenant/myjob.yaml --verbose

# Discover by connector type
dativo discover --connector stripe --verbose
```

### Orchestration

```bash
# Start Dagster scheduler
dativo start orchestrated --runner-config configs/runner.yaml

# Access Dagster UI
open http://localhost:3000
```

## Common Job Patterns

### Basic CSV to Iceberg

```yaml
tenant_id: mycompany
source_connector: csv
source_connector_path: connectors/csv.yaml
target_connector: iceberg
target_connector_path: connectors/iceberg.yaml
asset: mydata
asset_path: assets/csv/v1.0/mydata.yaml
source:
  files:
    - path: data/myfile.csv
      object: mydata
target:
  connection:
    s3:
      bucket: "${S3_BUCKET}"
      prefix: "mycompany/mydata"
```

### Incremental Sync

```yaml
source:
  files:
    - path: data/myfile.csv
  incremental:
    enabled: true
    cursor_field: updated_at
    lookback_days: 1
```

### Strict Validation

```yaml
# In asset definition
validation:
  mode: strict  # Fail on any error
```

### Custom Python Reader

```yaml
source:
  custom_reader: "/app/plugins/my_reader.py:MyReader"
  connection:
    api_url: "https://api.example.com"
```

### Catalog Integration

```yaml
catalog:
  type: openmetadata
  connection:
    api_url: "${OPENMETADATA_API_URL}"
  database: my_database
  push_lineage: true
  push_metadata: true
```

## Secret Management Patterns

### Filesystem (Development)

```bash
# Directory structure
secrets/
  mytenant/
    postgres.env
    stripe.env
    iceberg.env

# Run with filesystem secrets
dativo run --config jobs/mytenant/job.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted
```

### Environment Variables (Production)

```bash
# Set secrets
export DATIVO_SECRET__MYTENANT__postgres__env=$'PGHOST=localhost\nPGUSER=postgres\nPGPASSWORD=secret'
export DATIVO_SECRET__MYTENANT__stripe__text="sk_live_123"

# Run with env secrets (default)
dativo run --config jobs/mytenant/job.yaml --mode self_hosted
```

### Global Secrets (All Tenants)

```bash
export DATIVO_SECRET__GLOBAL__aws_key__text="AKIAIOSFODNN7EXAMPLE"
export DATIVO_SECRET__GLOBAL__aws_secret__text="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
```

## Stripe Test Account Setup (1 minute)

```bash
# 1. Sign up: https://stripe.com (free)
# 2. Enable Test Mode (orange toggle)
# 3. Get API key: Developers → API keys → Secret key (sk_test_...)
# 4. Create test customers in dashboard or with Stripe CLI:

stripe customers create --email=test1@example.com --name="Test Customer"
stripe charges create --amount=5000 --currency=usd --source=tok_visa

# 5. Add to secrets
cat > secrets/mytenant/stripe.env << EOF
STRIPE_API_KEY=sk_test_YOUR_KEY_HERE
EOF
```

## HubSpot Test Account Setup (2 minutes)

```bash
# 1. Sign up: https://www.hubspot.com/products/get-started (free)
# 2. Complete onboarding (choose CRM)
# 3. Get API key: Settings → Integrations → Private Apps
#    - Create app with scopes: crm.objects.contacts.read, crm.objects.companies.read
# 4. Create test data in UI or via API:

export HUBSPOT_API_KEY="pat-na1-YOUR_KEY"

curl -X POST "https://api.hubapi.com/crm/v3/objects/contacts" \
  -H "Authorization: Bearer $HUBSPOT_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "properties": {
      "email": "test@example.com",
      "firstname": "Test",
      "lastname": "Contact"
    }
  }'

# 5. Add to secrets
cat > secrets/mytenant/hubspot.env << EOF
HUBSPOT_API_KEY=pat-na1-YOUR_KEY
EOF
```

## Troubleshooting

### "Missing required environment variables" Warnings

**Problem:** Environment variables not set after running jobs  
**Symptoms:**
```
WARNING: Missing required environment variables: AWS_ACCESS_KEY_ID, AWS_REGION, S3_ENDPOINT
```

**Solution:**

```bash
# 1. Source the .env file
source .env

# 2. Verify variables are set
env | grep -E "(S3_|AWS_|MINIO_|NESSIE|PG)"

# 3. Check .env file exists
ls -la .env

# 4. If missing, the file should exist in the repository root
# It contains all required variables for local testing
```

**Common Issues:**
- ⚠️ **Not sourcing .env:** Must run `source .env` in your terminal session
- ⚠️ **Missing .env file:** The `.env` file should be in the repository root
- ⚠️ **Wrong format:** Variables must be `KEY=value` (no spaces around `=`)
- ⚠️ **New terminal:** Need to re-run `source .env` in each new terminal

**See:** [ENVIRONMENT_SETUP_GUIDE.md](ENVIRONMENT_SETUP_GUIDE.md) for complete reference

### "Package requires a different Python: 3.9.x not in '>=3.10'"

**Problem:** You have Python 3.9 or below  
**Solution:** Upgrade to Python 3.10+

```bash
# Quick fix using Conda
conda create -n dativo python=3.10 -y
conda activate dativo
pip install -e .

# Or using Homebrew (macOS)
brew install python@3.10
python3.10 -m venv venv
source venv/bin/activate
pip install -e .
```

**See:** [PYTHON_SETUP_GUIDE.md](PYTHON_SETUP_GUIDE.md) for detailed instructions

### "Command not found: dativo"

```bash
# Ensure virtual environment is activated
source venv/bin/activate  # or conda activate dativo

# Reinstall
pip install -e .

# Or use full path:
python -m dativo_ingest.cli run --config ...
```

### "Connection refused" to MinIO/Nessie

```bash
docker-compose -f docker-compose.dev.yml ps
docker-compose -f docker-compose.dev.yml restart minio nessie
```

### "Bucket does not exist"

```bash
mc mb local/test-bucket
```

### "No such file or directory" for secrets

```bash
mkdir -p secrets/mytenant
cat > secrets/mytenant/iceberg.env << 'EOF'
S3_ENDPOINT=http://localhost:9000
AWS_ACCESS_KEY_ID=minioadmin
AWS_SECRET_ACCESS_KEY=minioadmin
AWS_REGION=us-east-1
S3_BUCKET=test-bucket
NESSIE_URI=http://localhost:19120/api/v1
EOF
```

### View state files

```bash
# Check what tenants have state
ls -la .local/state/

# View specific state
cat .local/state/mytenant/myobject_state.json
```

### Clear state (force full re-sync)

```bash
rm -rf .local/state/mytenant/
```

## Test Data Generators

### Generate Large CSV

```python
# generate_test_data.py
import csv
import random
from datetime import datetime, timedelta

with open('large_test.csv', 'w', newline='') as f:
    writer = csv.writer(f)
    writer.writerow(['id', 'name', 'email', 'created_at', 'value'])
    
    for i in range(100000):
        writer.writerow([
            i,
            f"User_{i}",
            f"user{i}@example.com",
            (datetime.now() - timedelta(days=random.randint(0, 365))).isoformat(),
            round(random.uniform(10.0, 1000.0), 2)
        ])
```

### Generate Test Database Data

```bash
# PostgreSQL
docker exec -i $(docker ps -q -f name=postgres) psql -U postgres << 'EOF'
CREATE TABLE test_data (
  id SERIAL PRIMARY KEY,
  name VARCHAR(100),
  value DECIMAL(10,2),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO test_data (name, value)
SELECT 
  'Item_' || generate_series,
  random() * 1000
FROM generate_series(1, 10000);
EOF
```

## Performance Testing

```bash
# Time execution
time dativo run --config jobs/mytenant/large_job.yaml --mode self_hosted

# Compare Python vs Rust plugins
time dativo run --config jobs/python_reader.yaml --mode self_hosted
time dativo run --config jobs/rust_reader.yaml --mode self_hosted

# Monitor memory
/usr/bin/time -v dativo run --config jobs/mytenant/job.yaml --mode self_hosted
```

## Exit Codes

- `0`: Success - All jobs completed
- `1`: Partial success - Some jobs failed
- `2`: Failure - Configuration errors or validation warnings

## Docker Commands

```bash
# Build image
docker build -t dativo:1.1.0 .

# Run single job
docker run --rm \
  -v $(pwd)/jobs:/app/jobs:ro \
  -v $(pwd)/assets:/app/assets:ro \
  -v $(pwd)/connectors:/app/connectors:ro \
  -v $(pwd)/secrets:/app/secrets:ro \
  dativo:1.1.0 run --config /app/jobs/mytenant/job.yaml --mode self_hosted

# Start orchestrator
docker run --rm -p 3000:3000 \
  -v $(pwd)/jobs:/app/jobs:ro \
  -v $(pwd)/configs:/app/configs:ro \
  dativo:1.1.0 start orchestrated --runner-config /app/configs/runner.yaml
```

## Verification Commands

```bash
# Check Parquet files in MinIO
mc ls local/test-bucket/mytenant/ --recursive

# Download and inspect Parquet
mc cp local/test-bucket/mytenant/data/file.parquet .
python -c "import pandas as pd; print(pd.read_parquet('file.parquet'))"

# Check Iceberg tables in Nessie
curl http://localhost:19120/api/v1/trees/mytenant

# View Dagster assets
open http://localhost:3000

# View OpenMetadata catalog
open http://localhost:8585
```

## Testing Checklist

- [ ] Setup complete (`./scripts/setup-dev.sh`)
- [ ] Services running (Nessie, MinIO, PostgreSQL)
- [ ] Basic CSV to Iceberg working (Test Case 1)
- [ ] Incremental sync working (Test Case 2)
- [ ] Stripe integration working (Test Case 3)
- [ ] HubSpot integration working (Test Case 4)
- [ ] Schema validation working (Test Cases 5-6)
- [ ] PostgreSQL extraction working (Test Cases 7-8)
- [ ] Custom plugins working (Test Cases 10-11)
- [ ] Multi-tenant isolation working (Test Case 14)
- [ ] Orchestration working (Test Case 18)
- [ ] End-to-end pipeline working (Test Case 20)

## Quick Test Sequence

```bash
# 1. Setup (one time)
./scripts/setup-dev.sh && source .env

# 2. Test basic CSV ingestion (30 seconds)
dativo run \
  --job-dir tests/fixtures/jobs \
  --secret-manager filesystem \
  --secrets-dir tests/fixtures/secrets \
  --mode self_hosted

# 3. Verify results
mc ls local/test-bucket --recursive

# 4. Check state files
ls -la .local/state/

# Success! Now try custom test cases from TESTING_PLAYBOOK.md
```

## Additional Resources

- Full playbook: [TESTING_PLAYBOOK.md](TESTING_PLAYBOOK.md)
- Platform docs: [README.md](README.md)
- Quick start: [QUICKSTART.md](QUICKSTART.md)
- Custom plugins: [docs/CUSTOM_PLUGINS.md](docs/CUSTOM_PLUGINS.md)
