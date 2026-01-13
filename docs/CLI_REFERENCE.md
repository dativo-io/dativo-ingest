# CLI Reference

Complete reference for Dativo Ingestion Platform command-line interface.

## Command Overview

```bash
dativo <command> [options]
```

**Commands:**
- `ingest` - Run a single job in oneshot mode (recommended)
- `run` - Legacy alias for `ingest` (backward compatibility)
- `validate` - Validate configuration files and asset definitions
- `start` - Start orchestrated mode with Dagster
- `check` - Test connectivity and credentials
- `discover` - List available tables/streams from a connector
- `connectors` - Manage and inspect connectors

## Ingest Data (Run a Single Job)

Execute a single ingestion job and exit. Validates configuration, schema presence, and connector restrictions before execution.

### Syntax

```bash
# Recommended: use 'ingest' for clarity
dativo ingest --config <path> --mode <self_hosted|cloud>

# Alternative: 'run' is also supported (alias for ingest)
dativo run --config <path> --mode <self_hosted|cloud>
```

### Options

| Option | Required | Description |
|--------|----------|-------------|
| `--config` | Yes* | Path to job configuration YAML file |
| `--job-dir` | Yes* | Path to directory containing job YAML files (mutually exclusive with --config) |
| `--mode` | Yes | Execution mode: `self_hosted` or `cloud` |
| `--secret-manager` | No | Secret backend (`env`, `filesystem`, `vault`, `aws`, `gcp`). Defaults to environment variables or `DATIVO_SECRET_MANAGER` |
| `--secret-manager-config` | No | Path to YAML/JSON (or inline JSON string) with manager-specific settings. Defaults to `DATIVO_SECRET_MANAGER_CONFIG` |
| `--secrets-dir` | No | Path to secrets directory (used only when `--secret-manager filesystem`). Default: `/secrets` |
| `--tenant-id` | No | Tenant ID override (optional; if not provided, inferred from job configurations). If provided, validates all jobs belong to this tenant |
| `--dry-run` | No | Perform discovery and schema validation without writing to storage |
| `--sample-size` | No | Number of sample rows to fetch in dry-run mode (10-50, default: 50). Values outside this range will be rejected |
| `--timeout` | No | Timeout for dry-run execution in seconds (default: 300). Values below 30 seconds will trigger a warning |
| `--verbose` | No | Enable verbose output with phase timing details (for dry-run mode) |
| `--json` | No | Output results in JSON format (for dry-run mode) |

\* Either `--config` or `--job-dir` is required (mutually exclusive)

### Examples

```bash
# Single job
dativo ingest --config jobs/acme/stripe_customers.yaml --mode self_hosted

# Multiple jobs from directory (filesystem secrets)
dativo ingest --job-dir jobs/acme \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted

# Using environment variable secret manager (default)
dativo ingest --config jobs/mytenant/my_job.yaml --mode self_hosted

# Using AWS Secrets Manager
dativo ingest --config jobs/mytenant/my_job.yaml \
  --secret-manager aws \
  --secret-manager-config '{"region": "us-east-1"}' \
  --mode self_hosted

# Using Vault
dativo ingest --config jobs/mytenant/my_job.yaml \
  --secret-manager vault \
  --secret-manager-config vault-config.yaml \
  --mode self_hosted

# Dry-run mode (validate data contract without writing)
dativo ingest --config jobs/acme/stripe_customers.yaml \
  --mode self_hosted \
  --dry-run

# Dry-run with custom sample size
dativo ingest --config jobs/acme/stripe_customers.yaml \
  --mode self_hosted \
  --dry-run --sample-size 25

# Dry-run with JSON output (for CI/CD)
dativo ingest --config jobs/acme/stripe_customers.yaml \
  --mode self_hosted \
  --dry-run --json

# Dry-run with verbose phase timing
dativo ingest --config jobs/acme/stripe_customers.yaml \
  --mode self_hosted \
  --dry-run --verbose
```

### Dry-Run Mode

The `--dry-run` flag enables validation mode where:

1. **Configuration Validation**: Job configuration is validated
2. **Asset Loading**: Asset definition is loaded and validated
3. **Extractor Initialization**: Source connector is initialized
4. **Discovery**: Source schema and available streams are discovered
5. **Schema Negotiation**: Source schema is matched against asset definition
6. **Sample Extraction**: 10-50 rows are fetched from the source (configurable via `--sample-size`)
7. **Data Contract Validation**: Sample data is validated against the asset schema

**Safety Guarantees** (enforced at execution level):
- ❌ Never writes to Iceberg or object storage
- ❌ Never updates incremental state
- ❌ Never commits transactions

**Options:**
- `--sample-size N`: Number of rows to fetch (10-50, default: 50). Values outside this range are rejected.
- `--timeout SECONDS`: Execution timeout (default: 300s). Values below 30s trigger a warning.
- `--verbose`: Show phase timing details
- `--json`: Output structured JSON for CI/CD integration

This is useful for:
- Validating configurations before production runs
- Testing data contracts with actual source data
- Debugging schema mismatches
- Pre-flight checks in CI/CD pipelines

**Dry-Run Output Example (Human-Readable):**
```
============================================================
DRY-RUN EXECUTION RESULTS
============================================================

Status: ✅ PASSED
Exit Code: 0

Phases Completed: 4/7

Sample Metrics:
  Records fetched: 25
  Valid records: 25
  Invalid records: 0

🔒 Safety Assertions:
  No writes attempted: ✓
  No state updates: ✓
  No commits: ✓

Configuration:
  Source: stripe
  Target: iceberg
  Asset: stripe_customers

============================================================
```

**Dry-Run Output Example (JSON):**
```json
{
  "valid": true,
  "exit_code": 0,
  "errors": [],
  "warnings": [],
  "phases_completed": ["discovery", "schema_negotiation", "sample_fetch", "sample_validation"],
  "phases": [
    {"phase": "discovery", "status": "success", "duration_seconds": 0.012},
    {"phase": "schema_negotiation", "status": "success", "duration_seconds": 0.001},
    {"phase": "sample_fetch", "status": "success", "duration_seconds": 1.234},
    {"phase": "sample_validation", "status": "success", "duration_seconds": 0.045}
  ],
  "metrics": {
    "sample_size": 25,
    "valid_records": 25,
    "invalid_records": 0
  },
  "safety_assertions": {
    "no_writes": true,
    "no_state_updates": true,
    "no_commits": true
  },
  "source_connector": "stripe",
  "target_connector": "iceberg",
  "asset_name": "stripe_customers"
}
```

### Exit Codes

- `0`: Success - All jobs completed successfully
- `1`: Partial success - Some jobs succeeded, some failed
- `2`: Failure - Configuration errors, missing files, or startup failures. Note: Jobs may complete with validation warnings but still return exit code 2.

## Check Connection

Test connectivity and credentials without running the full job. This validates source connection, authentication, and target connection (S3 bucket access, etc.).

### Syntax

```bash
dativo check --config <path> [--json] [--verbose] --mode <self_hosted|cloud>
```

### Options

| Option | Required | Description |
|--------|----------|-------------|
| `--config` | Yes | Path to job configuration YAML file |
| `--mode` | Yes | Execution mode: `self_hosted` or `cloud` |
| `--json` | No | Output results in JSON format |
| `--verbose` | No | Show detailed information including error details |
| `--secret-manager` | No | Secret backend (same as `ingest` command) |
| `--secret-manager-config` | No | Secret manager configuration (same as `ingest` command) |
| `--secrets-dir` | No | Secrets directory path (same as `ingest` command) |

### Examples

```bash
# Basic connection check
dativo check --config jobs/acme/stripe_customers.yaml --mode self_hosted

# JSON output
dativo check --config jobs/acme/stripe_customers.yaml --json --mode self_hosted

# Verbose output with error details
dativo check --config jobs/acme/stripe_customers.yaml --verbose --mode self_hosted
```

### What It Validates

- Source connection and authentication
- Target connection (S3 bucket access, etc.)
- Returns detailed error information with retryable flags

## Validate Configuration

Validate job configurations and asset definitions against schemas and check connector registry compatibility. This command performs static validation without connecting to source/target systems.

### Validate Job Configuration

```bash
dativo validate config --path <job.yaml> [--mode <mode>] [--json] [--verbose]
```

**Options:**

| Option | Required | Description |
|--------|----------|-------------|
| `--path` | Yes | Path to job configuration YAML file |
| `--mode` | No | Execution mode for connector restriction validation (`self_hosted` or `cloud`). Default: `self_hosted` |
| `--json` | No | Output results in JSON format |
| `--verbose` | No | Show detailed validation information |

**What It Validates:**
- YAML syntax
- Job configuration schema compliance
- Source/target connector file existence
- Connector type existence in registry
- Mode restrictions (e.g., database connectors blocked in cloud mode)
- Asset definition file existence

**Examples:**
```bash
# Basic validation
dativo validate config --path jobs/acme/stripe_customers.yaml

# Validate for cloud mode restrictions
dativo validate config --path jobs/acme/stripe_customers.yaml --mode cloud

# JSON output for CI/CD integration
dativo validate config --path jobs/acme/stripe_customers.yaml --json

# Verbose output with all info messages
dativo validate config --path jobs/acme/stripe_customers.yaml --verbose
```

### Validate Asset Definition

```bash
dativo validate asset --path <spec.yaml> [--json] [--verbose]
```

**Options:**

| Option | Required | Description |
|--------|----------|-------------|
| `--path` | Yes | Path to asset definition YAML file |
| `--json` | No | Output results in JSON format |
| `--verbose` | No | Show detailed validation information |

**What It Validates:**
- YAML syntax
- ODCS v3.0.2 schema compliance
- Required ODCS fields (name, version, schema, team)
- Team owner presence (strong ownership requirement)
- Dativo extensions (source_type, object)
- Optional sections (compliance, finops, data_quality)

**Examples:**
```bash
# Basic validation
dativo validate asset --path assets/stripe/customers.yaml

# JSON output
dativo validate asset --path assets/stripe/customers.yaml --json

# Verbose output with all info messages
dativo validate asset --path assets/stripe/customers.yaml --verbose
```

### Validation Output

**Human-readable output:**
```
============================================================
Job Configuration Validation Results
============================================================

File: jobs/acme/stripe_customers.yaml
Status: ✅ VALID

Summary: 0 error(s), 1 warning(s)

⚠️  Warnings:
  - [SCHEMA_FILE_NOT_FOUND] Schema file not found, skipping JSON schema validation

ℹ️  Info:
  - [CONFIG_STRUCTURE_VALID] Job configuration structure validation passed
  - [SOURCE_CONNECTOR_REGISTERED] Source connector 'stripe' found in registry

============================================================
```

**JSON output:**
```json
{
  "valid": true,
  "errors": [],
  "warnings": [
    {
      "message": "Schema file not found, skipping JSON schema validation",
      "code": "SCHEMA_FILE_NOT_FOUND",
      "path": null,
      "severity": "warning"
    }
  ],
  "info": [
    {
      "message": "Job configuration structure validation passed",
      "code": "CONFIG_STRUCTURE_VALID",
      "path": null,
      "severity": "info"
    }
  ],
  "summary": {
    "error_count": 0,
    "warning_count": 1,
    "info_count": 1
  },
  "path": "jobs/acme/stripe_customers.yaml",
  "resource_type": "Job Configuration"
}
```

### Exit Codes

- `0`: Validation passed (no errors)
- `2`: Validation failed (one or more errors)

## Discover Available Streams

List available tables/streams from a connector.

### Syntax

```bash
# Using connector type
dativo discover --connector <name> [--json] [--verbose]

# Using job config
dativo discover --config <path> [--json] [--verbose]
```

### Options

| Option | Required | Description |
|--------|----------|-------------|
| `--connector` | Yes* | Connector name to discover (e.g., `stripe`, `hubspot`) |
| `--config` | Yes* | Path to job configuration YAML file |
| `--json` | No | Output results in JSON format |
| `--verbose` | No | Show detailed information |
| `--secret-manager` | No | Secret backend (same as `ingest` command) |
| `--secret-manager-config` | No | Secret manager configuration (same as `ingest` command) |
| `--secrets-dir` | No | Secrets directory path (same as `ingest` command) |

\* Either `--connector` or `--config` is required (mutually exclusive)

### Examples

```bash
# Discover using connector name
dativo discover --connector stripe

# Discover using job config
dativo discover --config jobs/acme/stripe_customers.yaml

# JSON output
dativo discover --connector hubspot --json

# Verbose output
dativo discover --config jobs/acme/hubspot_contacts.yaml --verbose
```

## Start Orchestrated Mode

Start Dagster orchestrator with scheduled jobs.

### Syntax

```bash
dativo start orchestrated --runner-config <path>
```

### Options

| Option | Required | Description |
|--------|----------|-------------|
| `--runner-config` | No | Path to runner configuration YAML file. Default: `/app/configs/runner.yaml` |

### Examples

```bash
# Start with default config
dativo start orchestrated

# Start with custom config
dativo start orchestrated --runner-config configs/my-runner.yaml
```

### What It Does

- Starts Dagster orchestrator with scheduled jobs
- Runs jobs according to cron schedules in `runner.yaml`
- Provides web UI at `http://localhost:3000` (default port)
- Continues running until stopped

**Security Note**: The Dagster web UI does not include built-in authentication. For production deployments, you MUST secure the Dagster UI by deploying behind a reverse proxy with authentication (OAuth, SAML, LDAP, or basic auth), placing behind a VPN, and enabling HTTPS/TLS. See [SECURITY.md](../SECURITY.md) for detailed guidance.

## Connectors Command

Manage and inspect connectors.

### List Connectors

```bash
dativo connectors list [--json] [--verbose]
```

**Options:**
- `--json`: Output results in JSON format
- `--verbose`: Show detailed information

**Example:**
```bash
dativo connectors list
dativo connectors list --json
```

### Inspect Connector

```bash
dativo connectors inspect <name> [--engine <engine>] [--json]
```

**Options:**
- `name`: Connector name to inspect (required)
- `--engine`: Engine override (e.g., `airbyte`, `singer`)
- `--json`: Output results in JSON format

**Example:**
```bash
dativo connectors inspect stripe
dativo connectors inspect hubspot --engine airbyte --json
```

### Sync Connector Catalogs

```bash
dativo connectors sync [<name>] [--url <url>] [--catalog-file <path>] [--insecure] [--json] [--verbose]
```

**Options:**
- `name`: Name of the catalog to sync (default: `airbyte`)
- `--url` / `--catalog-url`: URL to fetch catalog JSON from
- `--catalog-file`: Path to local catalog JSON file to ingest
- `--insecure`: Disable SSL verification (INSECURE)
- `--json`: Output results in JSON format
- `--verbose`: Enable verbose output

**Example:**
```bash
dativo connectors sync airbyte
dativo connectors sync airbyte --url https://example.com/catalog.json
dativo connectors sync airbyte --catalog-file local-catalog.json --json
```

## Secret Manager Configuration

Dativo supports multiple secret management backends. See [Secret Management](SECRET_MANAGEMENT.md) for complete configuration examples.

### Environment Variables (Default)

```bash
# Set secrets as environment variables
export STRIPE_API_KEY=sk_test_123
export S3_BUCKET=my-bucket

# Run job
dativo ingest --config job.yaml --mode self_hosted
```

### Filesystem

```bash
dativo ingest --config job.yaml \
  --secret-manager filesystem \
  --secrets-dir secrets \
  --mode self_hosted
```

### AWS Secrets Manager

```bash
dativo ingest --config job.yaml \
  --secret-manager aws \
  --secret-manager-config '{"region": "us-east-1"}' \
  --mode self_hosted
```

### HashiCorp Vault

```bash
dativo ingest --config job.yaml \
  --secret-manager vault \
  --secret-manager-config vault-config.yaml \
  --mode self_hosted
```

### GCP Secret Manager

```bash
dativo ingest --config job.yaml \
  --secret-manager gcp \
  --secret-manager-config '{"project_id": "my-project"}' \
  --mode self_hosted
```

## Environment Variables

Dativo respects the following environment variables:

- `DATIVO_SECRET_MANAGER`: Default secret manager backend
- `DATIVO_SECRET_MANAGER_CONFIG`: Default secret manager configuration (JSON string or file path)
- `DATIVO_LOG_LEVEL`: Logging level (default: `INFO`)

## Docker Usage

### Run Single Job

```bash
docker run --rm \
  -v $(pwd)/connectors:/app/connectors:ro \
  -v $(pwd)/assets:/app/assets:ro \
  -v $(pwd)/jobs:/app/jobs \
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/secrets:/app/secrets \
  -v $(pwd)/state:/app/state \
  dativo:1.1.0 ingest \
  --config /app/jobs/acme/stripe_customers_to_iceberg.yaml \
  --mode self_hosted
```

### Start Orchestrated Mode

```bash
docker run --rm -p 3000:3000 \
  -v $(pwd)/connectors:/app/connectors:ro \
  -v $(pwd)/assets:/app/assets:ro \
  -v $(pwd)/jobs:/app/jobs \
  -v $(pwd)/configs:/app/configs \
  -v $(pwd)/secrets:/app/secrets \
  -v $(pwd)/state:/app/state \
  dativo:1.1.0 start orchestrated \
  --runner-config /app/configs/runner.yaml
```

> **Note**: Omit the `/app/secrets` volume and `--secrets-dir` flag when using non-filesystem secret managers.

## Exit Codes

All commands return standard exit codes:

- `0`: Success
- `1`: Partial success (some jobs succeeded, some failed)
- `2`: Failure (configuration errors, missing files, or startup failures)

## Getting Help

```bash
# Show help for main command
dativo --help

# Show help for specific command
dativo ingest --help
dativo check --help
dativo discover --help
dativo start --help
dativo connectors --help
```

## Troubleshooting

### Command Not Found

```bash
# Reinstall package
pip install -e .
```

### Configuration Errors

Check your job configuration YAML syntax and validate against [Configuration Reference](CONFIG_REFERENCE.md).

### Secret Manager Errors

Verify secret manager configuration. See [Secret Management](SECRET_MANAGEMENT.md) for troubleshooting.

### Connection Errors

Use `dativo check` to validate connections before running full jobs.

## See Also

- [Configuration Reference](CONFIG_REFERENCE.md) - Job and asset configuration
- [Secret Management](SECRET_MANAGEMENT.md) - Secret manager backends
- [Quick Start Guide](quickstart.md) - Getting started tutorial
- [FAQ](FAQ.md) - Frequently asked questions

