# Environment Setup Guide

Complete guide to setting up environment variables for dativo-ingest.

---

## Quick Setup (2 Minutes)

### Step 1: Source the .env File

An `.env` file has been created for you with all necessary variables:

```bash
source .env
```

### Step 2: Verify Variables Are Set

```bash
echo $S3_ENDPOINT
echo $AWS_ACCESS_KEY_ID
echo $NESSIE_URI
```

**Expected output:**
```
http://localhost:9000
minioadmin
http://localhost:19120/api/v1
```

### Step 3: Run Your First Test

```bash
dativo run \
  --job-dir tests/fixtures/jobs \
  --secret-manager filesystem \
  --secrets-dir tests/fixtures/secrets \
  --mode self_hosted
```

---

## Environment Variables Explained

### MinIO / S3 Configuration

These variables configure object storage (MinIO for local development):

```bash
S3_ENDPOINT=http://localhost:9000          # MinIO API endpoint
S3_BUCKET=test-bucket                      # Default bucket name
AWS_ACCESS_KEY_ID=minioadmin               # MinIO access key
AWS_SECRET_ACCESS_KEY=minioadmin           # MinIO secret key
AWS_REGION=us-east-1                       # AWS region (required even for MinIO)

# Some jobs use MINIO_ prefix
MINIO_ENDPOINT=http://localhost:9000
MINIO_BUCKET=test-bucket
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
```

**Why both S3_ and MINIO_ prefixes?**
- Some connectors use standard AWS S3 variables (`S3_*`, `AWS_*`)
- Others use MinIO-specific variables (`MINIO_*`)
- Both are set to ensure compatibility

### Nessie Catalog Configuration

```bash
NESSIE_URI=http://localhost:19120/api/v1   # Nessie catalog REST API
```

**What is Nessie?**
- Git-like data catalog for Iceberg tables
- Optional - files are written to S3/MinIO even without catalog
- See [docs/CATALOG_LIMITATIONS.md](docs/CATALOG_LIMITATIONS.md)

### PostgreSQL Configuration

```bash
PGHOST=localhost                           # PostgreSQL hostname
PGPORT=5432                                # PostgreSQL port
PGDATABASE=postgres                        # Database name
PGUSER=postgres                            # Username
PGPASSWORD=postgres                        # Password
```

### MySQL Configuration

```bash
MYSQL_HOST=localhost                       # MySQL hostname
MYSQL_PORT=3306                            # MySQL port
MYSQL_DB=test_db                           # Database name
MYSQL_USER=root                            # Username
MYSQL_PASSWORD=mysql                       # Password
```

### External API Keys (Optional)

For testing Stripe and HubSpot integrations:

```bash
# Leave empty for local-only tests
STRIPE_API_KEY=sk_test_your_key_here
HUBSPOT_API_KEY=pat-na1-your_key_here
GOOGLE_SHEETS_CREDENTIALS_PATH=/path/to/service-account.json
```

**See:** 
- [TESTING_PLAYBOOK.md](TESTING_PLAYBOOK.md) - Test Case 3 for Stripe setup
- [TESTING_PLAYBOOK.md](TESTING_PLAYBOOK.md) - Test Case 4 for HubSpot setup

---

## Complete .env File Template

The `.env` file in the root directory contains all variables. You can customize it:

```bash
# Edit the .env file
vim .env  # or nano, code, etc.

# Source the changes
source .env

# Verify
env | grep -E "(S3_|AWS_|MINIO_|NESSIE|PG|MYSQL)"
```

---

## Troubleshooting

### Issue: Variables Not Set After `source .env`

**Symptoms:**
```bash
$ echo $S3_ENDPOINT
# (empty output)
```

**Solutions:**

1. **Verify .env file exists:**
   ```bash
   ls -la .env
   ```

2. **Check .env format:**
   ```bash
   cat .env | head
   # Should show: VARIABLE=value (no spaces around =)
   ```

3. **Re-source the file:**
   ```bash
   source .env
   ```

4. **Check for syntax errors:**
   ```bash
   # Bad format (will not work):
   S3_ENDPOINT = http://localhost:9000  # spaces around =
   
   # Good format:
   S3_ENDPOINT=http://localhost:9000    # no spaces
   ```

### Issue: "Missing required environment variables" Warnings

**This is normal!** The warnings occur because:
- Some test jobs use Stripe/HubSpot APIs (require API keys)
- Some jobs use MySQL (requires MySQL connection)
- Tests run all jobs simultaneously, including those needing external services

**How to reduce warnings:**

1. **Run specific job instead of all jobs:**
   ```bash
   # Instead of --job-dir (all jobs)
   dativo run --config tests/fixtures/jobs/csv_employee_to_iceberg.yaml \
     --mode self_hosted
   ```

2. **Set API keys for Stripe/HubSpot** (optional):
   ```bash
   export STRIPE_API_KEY=sk_test_your_key
   export HUBSPOT_API_KEY=pat-na1-your_key
   source .env  # Re-source to include new variables
   ```

### Issue: Services Not Accessible

**Symptoms:**
```
WARNING: Infrastructure validation warning for job: S3_ENDPOINT environment variable is not set
```

**Solutions:**

1. **Check services are running:**
   ```bash
   docker ps | grep -E "(minio|nessie|postgres)"
   ```

2. **Start services if not running:**
   ```bash
   docker-compose -f docker-compose.dev.yml up -d
   ```

3. **Source environment variables:**
   ```bash
   source .env
   ```

4. **Verify endpoints are accessible:**
   ```bash
   curl http://localhost:9000/minio/health/live  # MinIO
   curl http://localhost:19120/api/v1/config     # Nessie
   ```

---

## Environment Variable Precedence

Dativo loads variables in this order (later overrides earlier):

1. **.env file** (via `source .env`)
2. **System environment** (existing variables)
3. **Command-line** (inline: `S3_ENDPOINT=... dativo run`)
4. **Job config** (specified in YAML files)

**Example:**
```bash
# .env file sets:
S3_ENDPOINT=http://localhost:9000

# You can override:
S3_ENDPOINT=http://other-server:9000 dativo run --config job.yaml
```

---

## Production vs Development

### Development (.env file)
```bash
S3_ENDPOINT=http://localhost:9000
NESSIE_URI=http://localhost:19120/api/v1
```

### Production (environment variables)
```bash
# Don't use .env file in production
# Set via system environment, Kubernetes secrets, etc.

export S3_ENDPOINT=s3.amazonaws.com
export NESSIE_URI=https://nessie.company.com/api/v1
export AWS_ACCESS_KEY_ID=AKIA...
export AWS_SECRET_ACCESS_KEY=...
```

---

## Quick Reference Table

| Variable | Required For | Default Value |
|----------|-------------|---------------|
| `S3_ENDPOINT` | All Iceberg/S3 jobs | http://localhost:9000 |
| `AWS_ACCESS_KEY_ID` | All Iceberg/S3 jobs | minioadmin |
| `AWS_SECRET_ACCESS_KEY` | All Iceberg/S3 jobs | minioadmin |
| `AWS_REGION` | All Iceberg/S3 jobs | us-east-1 |
| `S3_BUCKET` | Some S3 jobs | test-bucket |
| `NESSIE_URI` | Iceberg catalog (optional) | http://localhost:19120/api/v1 |
| `PGHOST` | PostgreSQL jobs | localhost |
| `PGUSER` | PostgreSQL jobs | postgres |
| `PGPASSWORD` | PostgreSQL jobs | postgres |
| `MYSQL_HOST` | MySQL jobs | localhost |
| `STRIPE_API_KEY` | Stripe jobs | (none - add for API tests) |
| `HUBSPOT_API_KEY` | HubSpot jobs | (none - add for API tests) |

---

## Validation

Run the preflight check to validate your environment:

```bash
./scripts/preflight-check.sh
```

**Expected output:**
```
4. Environment Variables
  ✓ S3_ENDPOINT is set
  ✓ AWS_ACCESS_KEY_ID is set
  ✓ AWS_SECRET_ACCESS_KEY is set
  ✓ AWS_REGION is set
  ✓ NESSIE_URI is set
  ...
```

---

## Next Steps

Once your environment is set up:

1. ✅ **Run preflight check:** `./scripts/preflight-check.sh`
2. ✅ **Generate test data:** `./scripts/generate-test-data.sh`
3. ✅ **Source environment:** `source .env`
4. ✅ **Run first test:** Start with [TESTING_PLAYBOOK.md](TESTING_PLAYBOOK.md) Test Case 1

---

## Related Documentation

- [TESTING_GUIDE_INDEX.md](TESTING_GUIDE_INDEX.md) - Complete testing guide
- [TESTING_QUICK_REFERENCE.md](TESTING_QUICK_REFERENCE.md) - Command cheat sheet
- [docs/SECRET_MANAGEMENT.md](docs/SECRET_MANAGEMENT.md) - Secret management patterns

---

**Questions?** Run `./scripts/preflight-check.sh` for diagnostic information.
