# Secret Managers

The Dativo ingestion system supports multiple secret management backends, allowing you to choose the most appropriate secure credential storage for your environment.

## Overview

The pluggable secret manager architecture supports:

- **Environment Variables** (default) - Simple and portable
- **Filesystem** - Legacy approach for backward compatibility
- **HashiCorp Vault** - Enterprise secret management
- **AWS Secrets Manager** - Native AWS integration
- **Google Cloud Secret Manager** - Native GCP integration

## Quick Start

### Using Environment Variables (Default)

The simplest approach - just set environment variables:

```bash
# Tenant-specific secrets
export ACME_STRIPE_API_KEY="sk_test_123"
export ACME_PGHOST="localhost"
export ACME_PGPASSWORD="secret"

# Run ingestion
dativo-ingest run --job-file job.yaml --tenant-id acme
```

### Using Filesystem (Backward Compatible)

```bash
# Create secrets directory
mkdir -p /secrets/acme
echo "sk_test_123" > /secrets/acme/stripe_api_key.txt

# Run with secrets directory
dativo-ingest run --job-dir jobs/ --secrets-dir /secrets --tenant-id acme
```

### Using HashiCorp Vault

```bash
# Set Vault configuration
export SECRET_MANAGER_TYPE="vault"
export VAULT_ADDR="https://vault.example.com"
export VAULT_TOKEN="s.123456"

# Run ingestion
dativo-ingest run --job-file job.yaml --tenant-id acme
```

## Configuration

### Method 1: Environment Variables

The simplest configuration method:

```bash
# Select secret manager type
export SECRET_MANAGER_TYPE="env|filesystem|vault|aws|gcp"

# Optional: Provide additional configuration as JSON
export SECRET_MANAGER_CONFIG='{"mount_point": "secret/data"}'
```

### Method 2: Auto-Detection

The system can auto-detect the appropriate manager based on your environment:

1. **Vault** - If `VAULT_ADDR` is set
2. **AWS** - If `AWS_SECRETS_MANAGER` is set
3. **GCP** - If `GOOGLE_CLOUD_PROJECT` is set
4. **Filesystem** - If `/secrets` directory exists
5. **Environment** - Default fallback

## Environment Variable Manager

### Configuration Options

```python
config = {
    "prefix": "",              # Optional prefix for all env vars
    "uppercase": True,         # Convert names to uppercase (default)
    "allow_generic": True,     # Allow non-tenant-specific fallback (default)
}
```

### Naming Conventions

#### 1. Tenant-Specific Secrets

Format: `{TENANT}_{SECRET_NAME}`

```bash
export ACME_STRIPE_API_KEY="sk_test_123"
export ACME_DATABASE_URL="postgres://localhost/db"
```

#### 2. Generic Secrets (Shared)

Format: `{SECRET_NAME}`

```bash
export STRIPE_API_KEY="sk_test_generic"  # Used if tenant-specific not found
export NESSIE_URI="http://nessie:19120/api/v1"
```

#### 3. Structured JSON Secrets

Format: `{TENANT}_{SECRET_NAME}_JSON`

```bash
export ACME_GSHEETS_JSON='{"type":"service_account","project_id":"my-project"}'
```

### Common Patterns

The manager automatically recognizes common database and API patterns:

#### PostgreSQL
```bash
export ACME_PGHOST="localhost"
export ACME_PGPORT="5432"
export ACME_PGDATABASE="mydb"
export ACME_PGUSER="postgres"
export ACME_PGPASSWORD="secret"
```

#### MySQL
```bash
export ACME_MYSQL_HOST="localhost"
export ACME_MYSQL_PORT="3306"
export ACME_MYSQL_DATABASE="mydb"
export ACME_MYSQL_USER="root"
export ACME_MYSQL_PASSWORD="secret"
```

#### Common APIs
```bash
export ACME_STRIPE_API_KEY="sk_test_..."
export ACME_HUBSPOT_API_KEY="..."
export ACME_AWS_ACCESS_KEY_ID="..."
export ACME_AWS_SECRET_ACCESS_KEY="..."
```

## Filesystem Manager

### Configuration Options

```python
config = {
    "secrets_dir": "/secrets",  # Base directory for secrets
}
```

### Directory Structure

```
/secrets/
  ├── tenant1/
  │   ├── stripe_api_key.txt      # Plain text
  │   ├── gsheets.json            # JSON credentials
  │   └── postgres.env            # Environment-style
  └── tenant2/
      └── api_key.txt
```

### Supported File Formats

#### JSON Files (`.json`)
```json
{
  "type": "service_account",
  "project_id": "my-project",
  "private_key": "-----BEGIN PRIVATE KEY-----\n..."
}
```

#### Environment Files (`.env`)
```bash
PGHOST=localhost
PGPORT=5432
PGPASSWORD=secret
```

#### Plain Text (`.txt`, `.key`, etc.)
```
sk_test_12345
```

## HashiCorp Vault Manager

### Prerequisites

```bash
pip install hvac
```

### Configuration Options

```python
config = {
    "url": "https://vault.example.com",       # Required (or VAULT_ADDR)
    "token": "s.123456",                      # For token auth (or VAULT_TOKEN)
    "auth_method": "token",                   # token, approle, kubernetes, aws
    "mount_point": "secret",                  # KV mount point (default: secret)
    "kv_version": 2,                          # KV version 1 or 2 (default: 2)
    "path_template": "{tenant}",              # Secret path template
    "namespace": None,                        # Vault namespace (Enterprise)
}
```

### Authentication Methods

#### Token Authentication
```bash
export VAULT_ADDR="https://vault.example.com"
export VAULT_TOKEN="s.123456"
export SECRET_MANAGER_TYPE="vault"
```

#### AppRole Authentication
```bash
export VAULT_ADDR="https://vault.example.com"
export SECRET_MANAGER_TYPE="vault"
export SECRET_MANAGER_CONFIG='{
  "auth_method": "approle",
  "role_id": "abc123",
  "secret_id": "xyz789"
}'
```

#### Kubernetes Authentication
```bash
export VAULT_ADDR="https://vault.example.com"
export SECRET_MANAGER_CONFIG='{
  "auth_method": "kubernetes",
  "k8s_role": "my-app-role"
}'
```

#### AWS IAM Authentication
```bash
export VAULT_ADDR="https://vault.example.com"
export SECRET_MANAGER_CONFIG='{
  "auth_method": "aws",
  "aws_role": "my-iam-role"
}'
```

### Vault Secret Structure

Store secrets in Vault at path `{mount_point}/{tenant}`:

```bash
# Write secrets to Vault (KV v2)
vault kv put secret/acme \
  stripe_api_key="sk_test_123" \
  database_url="postgres://localhost/db"

# Read secrets
vault kv get secret/acme
```

## AWS Secrets Manager

### Prerequisites

```bash
pip install boto3
```

### Configuration Options

```python
config = {
    "region_name": "us-east-1",                  # AWS region
    "secret_name_template": "{tenant}/secrets",  # Secret name template
    "aws_access_key_id": None,                   # Optional (uses default AWS auth)
    "aws_secret_access_key": None,               # Optional
    "endpoint_url": None,                        # For testing with LocalStack
}
```

### AWS Authentication

Uses standard boto3 authentication chain:

1. Environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`)
2. AWS credentials file (`~/.aws/credentials`)
3. IAM roles (EC2, ECS, Lambda)
4. AWS SSO

```bash
# Option 1: Environment variables
export AWS_ACCESS_KEY_ID="AKIA..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_DEFAULT_REGION="us-east-1"
export SECRET_MANAGER_TYPE="aws"

# Option 2: IAM Role (automatic in AWS)
export SECRET_MANAGER_TYPE="aws"
export AWS_DEFAULT_REGION="us-east-1"
```

### Secret Structure

Store secrets as JSON in AWS Secrets Manager:

```bash
# Create secret via AWS CLI
aws secretsmanager create-secret \
  --name acme/secrets \
  --secret-string '{
    "stripe_api_key": "sk_test_123",
    "database_url": "postgres://localhost/db"
  }'

# Or use separate secrets per credential
aws secretsmanager create-secret \
  --name acme/stripe_api_key \
  --secret-string "sk_test_123"
```

## Google Cloud Secret Manager

### Prerequisites

```bash
pip install google-cloud-secretmanager
```

### Configuration Options

```python
config = {
    "project_id": "my-project",                  # Required (or GOOGLE_CLOUD_PROJECT)
    "secret_name_template": "{tenant}-secrets",  # Secret name template
    "credentials_file": None,                    # Optional service account key
}
```

### GCP Authentication

Uses standard Application Default Credentials (ADC):

1. Service account key file (`GOOGLE_APPLICATION_CREDENTIALS`)
2. Workload Identity (GKE)
3. Compute Engine service account
4. `gcloud auth application-default login`

```bash
# Option 1: Service account key
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/key.json"
export GOOGLE_CLOUD_PROJECT="my-project"
export SECRET_MANAGER_TYPE="gcp"

# Option 2: Workload Identity (automatic in GKE)
export GOOGLE_CLOUD_PROJECT="my-project"
export SECRET_MANAGER_TYPE="gcp"
```

### Secret Structure

Store secrets as JSON in GCP Secret Manager:

```bash
# Create secret via gcloud CLI
echo -n '{
  "stripe_api_key": "sk_test_123",
  "database_url": "postgres://localhost/db"
}' | gcloud secrets create acme-secrets \
  --data-file=- \
  --project=my-project

# Or use separate secrets per credential
echo -n "sk_test_123" | gcloud secrets create acme-stripe-api-key \
  --data-file=- \
  --project=my-project
```

## Migration Guide

### From Filesystem to Environment Variables

1. **Extract secrets from files:**
   ```bash
   # Example: Convert text file to env var
   export ACME_STRIPE_API_KEY=$(cat /secrets/acme/stripe_api_key.txt)
   ```

2. **Convert .env files:**
   ```bash
   # Source the .env file with tenant prefix
   while IFS='=' read -r key value; do
     export "ACME_${key}=${value}"
   done < /secrets/acme/postgres.env
   ```

3. **Convert JSON files:**
   ```bash
   # Store JSON as environment variable
   export ACME_GSHEETS_JSON=$(cat /secrets/acme/gsheets.json)
   ```

### From Filesystem to Cloud Providers

#### To AWS Secrets Manager
```bash
# Create JSON payload from filesystem secrets
jq -n \
  --arg stripe_key "$(cat /secrets/acme/stripe_api_key.txt)" \
  --arg db_url "postgres://..." \
  '{stripe_api_key: $stripe_key, database_url: $db_url}' | \
aws secretsmanager create-secret \
  --name acme/secrets \
  --secret-string file:///dev/stdin
```

#### To GCP Secret Manager
```bash
# Create secret from filesystem
cat /secrets/acme/gsheets.json | \
gcloud secrets create acme-gsheets \
  --data-file=- \
  --project=my-project
```

#### To HashiCorp Vault
```bash
# Write secrets to Vault
vault kv put secret/acme \
  stripe_api_key="$(cat /secrets/acme/stripe_api_key.txt)" \
  gsheets=@/secrets/acme/gsheets.json
```

## Best Practices

### Security

1. **Never commit secrets to version control**
2. **Use least-privilege access** - Grant only necessary permissions
3. **Rotate secrets regularly** - Especially for production
4. **Audit secret access** - Enable logging for all managers
5. **Use encryption at rest** - All cloud providers support this

### Environment-Specific Configuration

Use different secret managers per environment:

```bash
# Development - Simple environment variables
export SECRET_MANAGER_TYPE="env"
export ACME_STRIPE_API_KEY="sk_test_..."

# Staging - AWS Secrets Manager
export SECRET_MANAGER_TYPE="aws"
export AWS_DEFAULT_REGION="us-east-1"

# Production - HashiCorp Vault with AppRole
export SECRET_MANAGER_TYPE="vault"
export VAULT_ADDR="https://vault.prod.example.com"
export SECRET_MANAGER_CONFIG='{"auth_method":"approle",...}'
```

### Kubernetes Deployment

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: secret-manager-config
data:
  SECRET_MANAGER_TYPE: "vault"
  VAULT_ADDR: "https://vault.example.com"
---
apiVersion: v1
kind: Pod
spec:
  containers:
  - name: ingestion
    env:
    - name: SECRET_MANAGER_TYPE
      valueFrom:
        configMapKeyRef:
          name: secret-manager-config
          key: SECRET_MANAGER_TYPE
    - name: VAULT_ADDR
      valueFrom:
        configMapKeyRef:
          name: secret-manager-config
          key: VAULT_ADDR
    # Use Vault Agent for token injection or Kubernetes auth
```

## Troubleshooting

### Debug Secret Loading

Enable debug logging:

```bash
export LOG_LEVEL=DEBUG
dativo-ingest run --job-file job.yaml --tenant-id acme
```

### Common Issues

#### "Secret not found"
- Verify tenant ID matches secret path/name
- Check secret naming conventions
- Ensure proper authentication

#### "Access denied"
- Verify IAM/RBAC permissions
- Check authentication credentials
- Review policy configurations

#### "Authentication failed"
- Verify credentials are valid
- Check token expiration
- Ensure proper auth method configuration

### Testing Secret Managers

Use the Python API to test secret loading:

```python
from dativo_ingest.secret_managers import create_secret_manager

# Test environment variable manager
manager = create_secret_manager(manager_type="env")
secrets = manager.load_secrets("acme")
print(f"Loaded {len(secrets)} secrets")

# Test specific secret
api_key = manager.get_secret("acme", "stripe_api_key")
print(f"API Key: {api_key[:10]}...")
```

## API Reference

See the [API documentation](./API.md) for programmatic usage.

## Related Documentation

- [Setup and Onboarding](./SETUP_AND_ONBOARDING.md)
- [Configuration Reference](./CONFIG_REFERENCE.md)
- [Custom Plugins](./CUSTOM_PLUGINS.md)
