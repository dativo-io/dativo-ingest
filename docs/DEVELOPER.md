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

# TODO: Add metrics initialization (Prometheus/StatsD)
# TODO: Add tracing initialization (OpenTelemetry)
```

**Note**: Metrics and tracing are planned for future releases. The current logging infrastructure provides structured JSON logs with tenant tagging and secret redaction, which is sufficient for most operational needs.

### 2. Load Secrets from Secrets Storage

**Purpose**: Load credentials and sensitive configuration from secure storage

**Current State**:
- ✅ Connector recipes reference secrets via `file_template` (e.g., `/secrets/{tenant}/gsheets.json`)
- ✅ Environment variables are supported (e.g., `${NESSIE_URI}`)
- ✅ Secrets loading mechanism is fully implemented with pluggable backends
- ✅ Secrets validation is implemented (`validate_secrets_for_connector()`)

**Implementation**:
The secrets system supports multiple backends via the `--secret-manager` CLI flag:
- **Environment (default)**: Uses `DATIVO_SECRET__{TENANT}__{SECRET}__[json|env|text]` pattern
- **Filesystem**: Legacy `/secrets/{tenant}/` directory structure
- **HashiCorp Vault**: KV v1/v2 mounts with token or AppRole auth
- **AWS Secrets Manager**: Discrete secrets or bundle documents
- **GCP Secret Manager**: Similar to AWS with GCP-specific configuration

All secret managers support environment variable substitution and handle missing secrets gracefully.

**Secret manager options** (see [docs/SECRET_MANAGEMENT.md](SECRET_MANAGEMENT.md) for full reference):

- **Environment (default):** Populate variables matching `DATIVO_SECRET__{TENANT}__{SECRET}__[json|env|text]`. Supports global secrets (`DATIVO_SECRET__GLOBAL__...`) and inline JSON/.env payloads.
- **Filesystem:** Legacy `/secrets/{tenant}/` layout (JSON, `.env`, or plaintext files). Enable via `--secret-manager filesystem --secrets-dir <path>`.
- **HashiCorp Vault:** Configure KV paths, auth (token or AppRole), and mount points through `--secret-manager-config`.
- **AWS Secrets Manager / GCP Secret Manager:** Fetch specific secret definitions or bundle documents using templates (e.g., `"prod/{tenant}/{name}"`).

CLI defaults can be overridden with:

```
--secret-manager <env|filesystem|vault|aws|gcp>
--secret-manager-config <path or inline JSON>
```

or environment variables `DATIVO_SECRET_MANAGER` / `DATIVO_SECRET_MANAGER_CONFIG`.

### 3. Load Jobs from Directory

**Purpose**: Load all job configurations from a directory

**Current State**:
- ✅ Single job loading is implemented (`JobConfig.from_yaml()`)
- ✅ Directory-based job loading is fully implemented (`JobConfig.load_jobs_from_directory()`)
- ✅ Job discovery and validation is implemented

**Implementation**:
The `--job-dir` CLI argument loads all YAML files from a directory (recursively scans for `*.yaml` and `*.yml` files). Each job config is validated during loading, and errors are reported while allowing valid jobs to proceed.

**Usage**:
```bash
dativo run --job-dir tests/fixtures/jobs --mode self_hosted
```

**Implementation Details** (`src/dativo_ingest/config.py`):
- Recursively scans directory for `*.yaml` and `*.yml` files
- Validates each job config using `JobConfig.from_yaml()`
- Reports errors for invalid jobs but continues loading valid ones
- Raises `ValueError` only if no valid jobs are found

### 4. Resolve Environment Variables

**Purpose**: Substitute environment variables in configurations

**Current State**:
- ✅ Environment variable expansion in paths (`os.path.expandvars()`)
- ✅ Environment variable references in connector templates (e.g., `${NESSIE_URI}`)
- ✅ Environment variable validation is implemented (`JobConfig.validate_environment_variables()`)
- ✅ Missing environment variable detection is implemented

**Implementation**:
The `JobConfig.validate_environment_variables()` method checks for required environment variables based on connector type and target configuration. It's called automatically during the startup sequence and provides clear error messages for missing variables.

**Required Environment Variables** (for smoke tests):
- `NESSIE_URI` - Nessie catalog URI
- `S3_ENDPOINT` - S3/MinIO endpoint
- `AWS_ACCESS_KEY_ID` - S3 access key
- `AWS_SECRET_ACCESS_KEY` - S3 secret key
- `AWS_REGION` - S3 region

### 5. Validate Infrastructure Dependencies

**Purpose**: Ensure required infrastructure services are available

**Current State**:
- ✅ Infrastructure health checks are implemented (`validate_infrastructure()`)
- ✅ Connection validation is implemented (`dativo check` command)

**Implementation**:
The `validate_infrastructure()` function (`src/dativo_ingest/infrastructure.py`) checks:
- Nessie catalog connectivity (if catalog is configured)
- S3/MinIO connectivity and credentials
- Required ports accessibility

The `dativo check` command provides comprehensive connection validation:
```bash
dativo check --config jobs/acme/stripe_customers.yaml --mode self_hosted
```

This validates both source and target connections before running the full job.

**Infrastructure Dependencies** (for smoke tests):
- Nessie catalog (default: `http://localhost:19120/api/v1`)
- MinIO/S3 (default: `http://localhost:9000`)
- Test data files accessible

### 6. Initialize State Management

**Purpose**: Set up incremental sync state tracking

**Current State**:
- ✅ State path generation in job configs
- ✅ State directory creation is implemented (`initialize_state_directory()`)
- ✅ State file validation is implemented (writability checks)

**Implementation**:
The `initialize_state_directory()` function (`src/dativo_ingest/validator.py`):
- Creates parent directories if they don't exist (`mkdir(parents=True, exist_ok=True)`)
- Validates that the state directory is writable
- Handles missing incremental config gracefully
- Automatically called during startup sequence for all jobs

State files are stored at `.local/state/{tenant_id}/` by default (configurable via `STATE_DIR` environment variable).

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

The following components are still planned for future implementation:

1. **Observability Enhancements**:
   - Metrics collection (Prometheus, StatsD)
   - Distributed tracing (OpenTelemetry)
   - Health check endpoints

**Note**: All other components listed in previous versions have been implemented:
- ✅ Secrets Loader (`src/dativo_ingest/secrets/`) - Multiple backends (env, filesystem, vault, aws, gcp)
- ✅ Infrastructure Validator (`src/dativo_ingest/infrastructure.py`) - Health checks and connection validation
- ✅ Job Directory Loader (`JobConfig.load_jobs_from_directory()`) - `--job-dir` CLI support
- ✅ Environment Variable Validator (`JobConfig.validate_environment_variables()`) - Required variable detection
- ✅ State Directory Initialization (`initialize_state_directory()`) - Directory creation and validation

## WAL Implementation Details

### Architecture Overview

The WAL (Write-Ahead Log) checkpointing system implements a two-layer state architecture:

1. **Incremental State** (Cross-Run): Logical cursors updated after successful commit
2. **WAL / Checkpoints** (Intra-Run): Page/offset/chunk boundaries updated during extraction

### Implementation Status

**All Connectors Support WAL:**
- ✅ Native Extractors: CSV (chunk-based), Postgres/MySQL (offset-based), Google Sheets/GDrive CSV (chunk/spreadsheet-based)
- ✅ Engine-Based Extractors: Airbyte (STATE message mapping), HubSpot, Stripe (inherit from AirbyteExtractor)
- ✅ Custom Plugins: All BaseReader implementations accept `checkpoint_context` parameter

**Core Components:**
- `src/dativo_ingest/wal_manager.py`: WAL file lifecycle management
- `src/dativo_ingest/job_executor.py`: WAL integration with job execution
- All extractors updated to accept and use `checkpoint_context`

**Checkpoint Types:**
- `chunk_based`: CSV, GDrive CSV extractors
- `offset_based`: Postgres, MySQL extractors
- `spreadsheet_based`: Google Sheets extractor
- `state_based`: Airbyte, Meltano, Singer extractors

**File Structure:**
```
/app/
├── state/                    # Incremental state (existing)
│   └── {tenant_id}/
│       └── {job_name}.json
└── wal/                      # WAL files (new)
    └── {tenant_id}/
        └── {job_name}/
            └── {run_id}.wal.json
```

**Backward Compatibility:**
- WAL is opt-in via `source.wal.enabled: true`
- All extractors accept optional `checkpoint_context` parameter
- Existing incremental state mechanism unchanged

For detailed WAL documentation, see [WAL_CHECKPOINTING.md](WAL_CHECKPOINTING.md).

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

