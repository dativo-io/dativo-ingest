# Developer Guide: Startup Sequence

This document describes the initial startup sequence required for running E2E smoke tests and the internal architecture of the Dativo Ingestion Platform.

## Command Structure

For smoke tests, you would run:
```bash
dativo run --job-dir tests/fixtures/jobs --mode self_hosted
```

Or for orchestrated mode:
```bash
dativo start orchestrated --runner-config tests/fixtures/runner.yaml
```

## Startup Sequence

### 1. Initialize Observability

**Purpose**: Set up logging, metrics, and tracing infrastructure

**Current State**:
- ✅ Structured JSON logging is implemented (`src/dativo_ingest/logging.py`)
- ✅ Secret redaction is supported
- ✅ Tenant tagging is supported
- ❌ Metrics collection (not yet implemented)
- ❌ Distributed tracing (not yet implemented)

**Required Actions**:
- Initialize logging with appropriate level and redaction settings
- Set up metrics exporter (e.g., Prometheus, StatsD)
- Initialize tracing (e.g., OpenTelemetry)
- Configure observability endpoints

**Implementation**:
```python
# In startup sequence
from dativo_ingest.logging import setup_logging
logger = setup_logging(level="INFO", redact_secrets=True)

# TODO: Add metrics initialization
# TODO: Add tracing initialization
```

### 2. Load Secrets from Secrets Storage

**Purpose**: Load credentials and sensitive configuration from secure storage

**Current State**:
- ✅ Connector recipes reference secrets via `file_template` (e.g., `/secrets/{tenant}/gsheets.json`)
- ✅ Environment variables are supported (e.g., `${NESSIE_URI}`)
- ❌ Secrets loading mechanism (not yet implemented)
- ❌ Secrets validation (not yet implemented)

**Required Actions**:
- Implement secrets loader that:
  - Reads from `/secrets/{tenant}/` directory structure
  - Supports environment variable substitution
  - Validates required secrets are present
  - Handles missing secrets gracefully
- Create test secrets directory structure
- Document required secrets per connector type

**Secrets Structure**:
```
/secrets/
  {tenant}/
    gsheets.json          # Google Sheets service account
    gdrive.json           # Google Drive service account
    postgres.env          # PostgreSQL connection string
    mysql.env             # MySQL connection string
    stripe_api_key        # Stripe API key
    hubspot_api_key       # Hubspot API key
```

**Implementation**:
```python
# In startup sequence
def load_secrets(tenant_id: str, secrets_dir: Path = Path("/secrets")) -> Dict[str, Any]:
    """Load secrets for a tenant from secrets storage."""
    tenant_secrets_dir = secrets_dir / tenant_id
    if not tenant_secrets_dir.exists():
        raise ValueError(f"Secrets directory not found: {tenant_secrets_dir}")
    
    secrets = {}
    # Load all secret files
    for secret_file in tenant_secrets_dir.glob("*"):
        # Load and parse based on file type
        # ...
    return secrets
```

### 3. Load Jobs from Directory

**Purpose**: Load all job configurations from a directory

**Current State**:
- ✅ Single job loading is implemented (`JobConfig.from_yaml()`)
- ❌ Directory-based job loading (not yet implemented)
- ❌ Job discovery and validation (not yet implemented)

**Required Actions**:
- Add `--job-dir` CLI argument to load jobs from directory
- Implement job discovery:
  - Scan directory for `*.yaml` files
  - Validate each job config
  - Report any invalid jobs
- Create runner config generator from job directory

**Implementation**:
```python
# In CLI
def load_jobs_from_directory(job_dir: Path) -> List[JobConfig]:
    """Load all job configs from a directory."""
    jobs = []
    for job_file in job_dir.glob("*.yaml"):
        try:
            job = JobConfig.from_yaml(job_file)
            jobs.append(job)
        except Exception as e:
            logger.error(f"Failed to load job {job_file}: {e}")
    return jobs
```

### 4. Resolve Environment Variables

**Purpose**: Substitute environment variables in configurations

**Current State**:
- ✅ Environment variable expansion in paths (`os.path.expandvars()`)
- ✅ Environment variable references in connector templates (e.g., `${NESSIE_URI}`)
- ❌ Environment variable validation (not yet implemented)
- ❌ Missing environment variable detection (not yet implemented)

**Required Actions**:
- Validate all required environment variables are set
- Provide clear error messages for missing variables
- Document required environment variables per connector

**Required Environment Variables** (for smoke tests):
- `NESSIE_URI` - Nessie catalog URI
- `S3_ENDPOINT` - S3/MinIO endpoint
- `AWS_ACCESS_KEY_ID` - S3 access key
- `AWS_SECRET_ACCESS_KEY` - S3 secret key
- `AWS_REGION` - S3 region

### 5. Validate Infrastructure Dependencies

**Purpose**: Ensure required infrastructure services are available

**Current State**:
- ❌ Infrastructure health checks (not yet implemented)
- ❌ Connection validation (not yet implemented)

**Required Actions**:
- Check Nessie catalog is accessible
- Check S3/MinIO is accessible
- Validate credentials work
- Check required ports are open

**Infrastructure Dependencies** (for smoke tests):
- Nessie catalog (default: `http://localhost:19120/api/v1`)
- MinIO/S3 (default: `http://localhost:9000`)
- Test data files accessible

### 6. Initialize State Management

**Purpose**: Set up incremental sync state tracking

**Current State**:
- ✅ State path generation in job configs
- ❌ State directory creation (not yet implemented)
- ❌ State file validation (not yet implemented)

**Required Actions**:
- Create state directory structure if it doesn't exist
- Validate state directory is writable
- Initialize state files if needed

### 7. Load and Validate Configurations

**Purpose**: Load and validate all configurations before execution

**Required Actions**:
- Load connector recipes
- Load asset definitions
- Validate job configurations
- Check schema presence
- Validate connector capabilities

**Current State**:
- ✅ Job config loading
- ✅ Connector recipe loading
- ✅ Asset definition loading
- ✅ Schema validation
- ✅ Connector validation

## Complete Startup Sequence

```python
def startup_sequence(job_dir: Path, secrets_dir: Path, tenant_id: str):
    """Complete startup sequence for E2E smoke tests."""
    
    # 1. Initialize observability
    logger = setup_logging(level="INFO", redact_secrets=True)
    logger.info("Starting E2E smoke test", extra={"event_type": "startup_begin"})
    
    # 2. Load secrets
    secrets = load_secrets(tenant_id, secrets_dir)
    logger.info("Secrets loaded", extra={"event_type": "secrets_loaded"})
    
    # 3. Validate environment variables
    validate_environment_variables()
    logger.info("Environment variables validated", extra={"event_type": "env_validated"})
    
    # 4. Validate infrastructure
    validate_infrastructure()
    logger.info("Infrastructure validated", extra={"event_type": "infra_validated"})
    
    # 5. Initialize state management
    initialize_state_directory()
    logger.info("State management initialized", extra={"event_type": "state_initialized"})
    
    # 6. Load jobs
    jobs = load_jobs_from_directory(job_dir)
    logger.info(f"Loaded {len(jobs)} jobs", extra={"event_type": "jobs_loaded", "job_count": len(jobs)})
    
    # 7. Validate all configurations
    for job in jobs:
        job.validate_schema_presence()
        validator = ConnectorValidator()
        validator.validate_job(job, mode="self_hosted")
    
    logger.info("Startup sequence completed", extra={"event_type": "startup_complete"})
    return jobs
```

## Missing Components

The following components need to be implemented:

1. **Secrets Loader** (`src/dativo_ingest/secrets.py`):
   - Load secrets from filesystem
   - Support environment variable substitution
   - Validate required secrets

2. **Infrastructure Validator** (`src/dativo_ingest/infrastructure.py`):
   - Health checks for Nessie, S3/MinIO
   - Connection validation
   - Credential validation

3. **Job Directory Loader** (CLI enhancement):
   - `--job-dir` argument
   - Job discovery and loading
   - Batch validation

4. **Environment Variable Validator**:
   - Check required variables are set
   - Provide helpful error messages

5. **Observability Enhancements**:
   - Metrics collection
   - Distributed tracing
   - Health check endpoints

## Test Infrastructure Setup

For smoke tests, you'll need:

1. **MinIO** (S3-compatible storage):
   ```bash
   docker run -d -p 9000:9000 -p 9001:9001 \
     -e MINIO_ROOT_USER=minioadmin \
     -e MINIO_ROOT_PASSWORD=minioadmin \
     minio/minio server /data --console-address ":9001"
   ```

2. **Nessie** (Iceberg catalog):
   ```bash
   docker run -d -p 19120:19120 \
     projectnessie/nessie:latest
   ```

3. **Secrets Directory**:
   ```bash
   mkdir -p tests/fixtures/secrets/test_tenant
   # Create test secret files
   ```

4. **State Directory**:
   ```bash
   mkdir -p .local/state/test_tenant
   # Or use STATE_DIR env var: export STATE_DIR=/tmp/dativo-state
   ```

