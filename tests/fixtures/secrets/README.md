# Test Secrets

This directory contains test secrets for smoke tests.

## Structure

Secrets are organized by tenant:
```
secrets/
  {tenant_id}/
    iceberg.env      # Nessie and S3 configuration for Iceberg
    s3.env           # S3/MinIO configuration
    gsheets.json     # Google Sheets service account (if needed)
    gdrive.json      # Google Drive service account (if needed)
    postgres.env     # PostgreSQL connection string (if needed)
    mysql.env        # MySQL connection string (if needed)
```

## Test Tenant Secrets

The `test_tenant/` directory contains placeholder secrets for smoke tests:

- **iceberg.env**: Nessie catalog URI and S3/MinIO credentials for Iceberg tables
- **s3.env**: S3/MinIO credentials for direct S3 targets

## Required Environment Variables

For smoke tests with Iceberg targets, the following environment variables should be set (or provided in `.env` files):

- `NESSIE_URI`: Nessie catalog URI (default: `http://localhost:19120/api/v1`)
- `S3_ENDPOINT`: S3/MinIO endpoint (default: `http://localhost:9000`)
- `AWS_ACCESS_KEY_ID`: S3 access key (default: `minioadmin`)
- `AWS_SECRET_ACCESS_KEY`: S3 secret key (default: `minioadmin`)
- `AWS_REGION`: S3 region (default: `us-east-1`)

## Security Note

**IMPORTANT**: These are test secrets with default values. In production:
- Never commit real secrets to version control
- Use a secrets management system (e.g., HashiCorp Vault, AWS Secrets Manager)
- Rotate secrets regularly
- Use different credentials per environment

## Usage

Secrets are automatically loaded by the `startup_sequence()` function when running with `--job-dir`:

```bash
dativo_ingest run --job-dir tests/fixtures/jobs \
  --secrets-dir tests/fixtures/secrets \
  --tenant-id test_tenant \
  --mode self_hosted
```

The secrets loader will:
1. Read all files in `{secrets_dir}/{tenant_id}/`
2. Parse `.env` files as key=value pairs
3. Parse `.json` files as JSON objects
4. Parse plain text files as string values
5. Expand environment variables in all values

