# Secrets Management

Dativo supports multiple secret management backends to securely store and retrieve credentials for your data connectors. You can choose the secret manager that best fits your infrastructure and security requirements.

## Supported Secret Managers

- **Environment Variables** (default) - Simple and works everywhere
- **Filesystem** - File-based secrets storage (legacy default)
- **HashiCorp Vault** - Enterprise secret management
- **AWS Secrets Manager** - AWS-native secret storage
- **Google Cloud Secret Manager** - GCP-native secret storage
- **Azure Key Vault** - Azure-native secret storage

## Configuration

Secret manager configuration is specified in the `secrets` section of your `runner.yaml` file:

```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: dagster
    schedules:
      - name: my_job
        config: /app/jobs/my_job.yaml
        cron: "0 * * * *"
  
  # Secrets configuration
  secrets:
    type: env  # or filesystem, vault, aws, gcp, azure
    # ... type-specific options ...
```

If the `secrets` section is omitted, the default behavior is to use environment variables.

## 1. Environment Variables (Default)

The simplest option - secrets are loaded from environment variables. This is the **default** if no secrets configuration is provided.

### Configuration

```yaml
runner:
  # ... orchestrator config ...
  secrets:
    type: env
    prefix: DATIVO_  # Optional: prefix for environment variables
```

### Usage

Set environment variables with the pattern: `{PREFIX}{TENANT_ID}_{SECRET_NAME}` or `{PREFIX}{SECRET_NAME}`

```bash
# Tenant-specific secrets
export DATIVO_ACME_STRIPE_API_KEY="sk_live_..."
export DATIVO_ACME_DATABASE_PASSWORD="secret123"

# Global secrets (used if tenant-specific not found)
export DATIVO_NESSIE_URI="http://nessie:19120/api/v1"
export DATIVO_S3_ENDPOINT="http://minio:9000"
```

### Minimal Configuration

```yaml
# No secrets section needed - environment variables are the default
runner:
  mode: orchestrated
  orchestrator:
    type: dagster
    schedules:
      - name: stripe_sync
        config: /app/jobs/stripe.yaml
        cron: "0 * * * *"
```

## 2. Filesystem

File-based secrets storage (original implementation). Secrets are stored in files organized by tenant.

### Configuration

```yaml
runner:
  # ... orchestrator config ...
  secrets:
    type: filesystem
    secrets_dir: /secrets  # Default: /secrets
```

### Directory Structure

```
/secrets/
  acme/
    stripe.json         # JSON secret
    postgres.env        # Environment file
    api_key.txt         # Plain text secret
  globex/
    hubspot.json
    mysql.env
```

### Secret Files

**JSON format** (`.json`):
```json
{
  "api_key": "sk_live_...",
  "webhook_secret": "whsec_..."
}
```

**Environment format** (`.env`):
```
DB_HOST=postgres.example.com
DB_PORT=5432
DB_USER=readonly
DB_PASSWORD=secret123
```

**Plain text** (`.txt`, `.key`, etc):
```
sk_live_51234567890abcdef...
```

## 3. HashiCorp Vault

Enterprise-grade secret management with encryption, audit logging, and fine-grained access control.

### Configuration

```yaml
runner:
  # ... orchestrator config ...
  secrets:
    type: vault
    url: https://vault.example.com:8200
    token: ${VAULT_TOKEN}  # Can also be set via VAULT_TOKEN env var
    mount_point: secret  # KV secrets engine mount point (default: secret)
    namespace: my-namespace  # Optional: Vault namespace
    verify: true  # Verify SSL certificates (default: true)
```

### Vault Secret Structure

Secrets are stored at path: `{mount_point}/data/{tenant_id}`

```bash
# Write secrets for tenant 'acme'
vault kv put secret/acme \
  stripe_api_key="sk_live_..." \
  database_password="secret123" \
  hubspot_api_key="pat-na1-..."

# Read secrets
vault kv get secret/acme
```

### Authentication

You can provide the Vault token in three ways:
1. In the configuration: `token: s.AbCdEf123456...`
2. Environment variable: `export VAULT_TOKEN=s.AbCdEf123456...`
3. Vault agent (automatic authentication)

### Example

```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: dagster
    schedules:
      - name: stripe_sync
        config: /app/jobs/stripe.yaml
        cron: "0 * * * *"
  
  secrets:
    type: vault
    url: https://vault.prod.example.com:8200
    mount_point: dativo
    namespace: engineering
```

## 4. AWS Secrets Manager

AWS-native secret storage with encryption, rotation, and IAM-based access control.

### Configuration

```yaml
runner:
  # ... orchestrator config ...
  secrets:
    type: aws
    region_name: us-east-1  # Optional: defaults to AWS config
    prefix: dativo/  # Optional: prefix for secret names
```

### Secret Structure

**Option 1: Single secret per tenant** (recommended)

Create a secret named `{prefix}{tenant_id}` with JSON value:

```bash
# AWS CLI
aws secretsmanager create-secret \
  --name dativo/acme \
  --secret-string '{
    "stripe_api_key": "sk_live_...",
    "database_password": "secret123",
    "hubspot_api_key": "pat-na1-..."
  }' \
  --region us-east-1
```

**Option 2: Multiple secrets per tenant**

Create secrets with pattern `{prefix}{tenant_id}/{secret_name}`:

```bash
# AWS CLI
aws secretsmanager create-secret \
  --name dativo/acme/stripe_api_key \
  --secret-string 'sk_live_...' \
  --region us-east-1

aws secretsmanager create-secret \
  --name dativo/acme/database_password \
  --secret-string 'secret123' \
  --region us-east-1
```

### IAM Permissions

The application needs these IAM permissions:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:ListSecrets"
      ],
      "Resource": "arn:aws:secretsmanager:us-east-1:123456789012:secret:dativo/*"
    }
  ]
}
```

### Example

```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: dagster
    schedules:
      - name: stripe_sync
        config: /app/jobs/stripe.yaml
        cron: "0 * * * *"
  
  secrets:
    type: aws
    region_name: us-east-1
    prefix: dativo/production/
```

## 5. Google Cloud Secret Manager

GCP-native secret storage with encryption, versioning, and IAM-based access control.

### Configuration

```yaml
runner:
  # ... orchestrator config ...
  secrets:
    type: gcp
    project_id: my-project-123  # Can also be set via GCP_PROJECT_ID env var
    prefix: dativo-  # Optional: prefix for secret names
```

### Secret Structure

**Option 1: Single secret per tenant** (recommended)

Create a secret named `{prefix}{tenant_id}` with JSON value:

```bash
# gcloud CLI
echo '{
  "stripe_api_key": "sk_live_...",
  "database_password": "secret123",
  "hubspot_api_key": "pat-na1-..."
}' | gcloud secrets create dativo-acme \
  --data-file=- \
  --project=my-project-123
```

**Option 2: Multiple secrets per tenant**

Create secrets with pattern `{prefix}{tenant_id}-{secret_name}`:

```bash
# gcloud CLI
echo 'sk_live_...' | gcloud secrets create dativo-acme-stripe-api-key \
  --data-file=- \
  --project=my-project-123

echo 'secret123' | gcloud secrets create dativo-acme-database-password \
  --data-file=- \
  --project=my-project-123
```

### IAM Permissions

The service account needs the Secret Manager Secret Accessor role:

```bash
gcloud projects add-iam-policy-binding my-project-123 \
  --member="serviceAccount:dativo@my-project-123.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### Authentication

Use Application Default Credentials (ADC):

```bash
# For development (uses your user account)
gcloud auth application-default login

# For production (uses service account)
export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account-key.json
```

### Example

```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: dagster
    schedules:
      - name: stripe_sync
        config: /app/jobs/stripe.yaml
        cron: "0 * * * *"
  
  secrets:
    type: gcp
    project_id: my-production-project
    prefix: dativo-prod-
```

## 6. Azure Key Vault

Azure-native secret storage with encryption, versioning, and Azure AD-based access control.

### Configuration

```yaml
runner:
  # ... orchestrator config ...
  secrets:
    type: azure
    vault_url: https://my-vault.vault.azure.net/
    prefix: dativo-  # Optional: prefix for secret names
```

### Secret Structure

Create secrets with pattern `{prefix}{tenant_id}-{secret_name}`:

**Note**: Azure Key Vault secret names can only contain alphanumeric characters and hyphens.

```bash
# Azure CLI
az keyvault secret set \
  --vault-name my-vault \
  --name dativo-acme-stripe-api-key \
  --value 'sk_live_...'

az keyvault secret set \
  --vault-name my-vault \
  --name dativo-acme-database-password \
  --value 'secret123'

az keyvault secret set \
  --vault-name my-vault \
  --name dativo-acme-hubspot-api-key \
  --value 'pat-na1-...'
```

### Access Policy

Grant the application access to read secrets:

```bash
# Using service principal
az keyvault set-policy \
  --name my-vault \
  --spn <service-principal-id> \
  --secret-permissions get list

# Using managed identity
az keyvault set-policy \
  --name my-vault \
  --object-id <managed-identity-object-id> \
  --secret-permissions get list
```

### Authentication

The application uses DefaultAzureCredential which tries multiple authentication methods:
1. Environment variables (AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID)
2. Managed identity (when running in Azure)
3. Azure CLI credentials (for local development)

```bash
# For local development
az login

# For production (using service principal via environment variables)
export AZURE_CLIENT_ID=<client-id>
export AZURE_CLIENT_SECRET=<client-secret>
export AZURE_TENANT_ID=<tenant-id>
```

### Example

```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: dagster
    schedules:
      - name: stripe_sync
        config: /app/jobs/stripe.yaml
        cron: "0 * * * *"
  
  secrets:
    type: azure
    vault_url: https://dativo-prod.vault.azure.net/
    prefix: app-
```

## Migration Guide

### From Filesystem to Environment Variables

If you're currently using filesystem secrets and want to migrate to environment variables:

1. **Export existing secrets to environment variables:**

```bash
# For each tenant and secret file, create corresponding env vars
export DATIVO_ACME_STRIPE_API_KEY=$(cat /secrets/acme/stripe.json | jq -r '.api_key')
export DATIVO_ACME_DATABASE_PASSWORD=$(cat /secrets/acme/postgres.env | grep DB_PASSWORD | cut -d= -f2)
```

2. **Update your runner.yaml:**

```yaml
runner:
  # ... orchestrator config ...
  secrets:
    type: env  # Change from filesystem to env
```

Or simply remove the `secrets` section entirely (env is the default).

### From Filesystem to Cloud Secret Manager

1. **Upload secrets to your cloud provider** (see examples above)

2. **Update your runner.yaml:**

```yaml
runner:
  # ... orchestrator config ...
  secrets:
    type: aws  # or gcp, azure, vault
    # ... provider-specific config ...
```

3. **Configure authentication** (IAM roles, service accounts, etc.)

4. **Test the configuration** before removing filesystem secrets

## Best Practices

1. **Use Environment Variables for Development**
   - Simple setup
   - No infrastructure dependencies
   - Works well with Docker Compose

2. **Use Cloud Secret Managers for Production**
   - Centralized secret management
   - Audit logging
   - Automatic rotation
   - Fine-grained access control

3. **Never Commit Secrets to Git**
   - Use `.gitignore` for local secret files
   - Use environment variables or secret managers
   - Rotate secrets if accidentally committed

4. **Use Separate Secrets per Tenant**
   - Better security isolation
   - Easier access control
   - Simplified debugging

5. **Implement Secret Rotation**
   - Regular rotation schedule
   - Automated rotation where possible
   - Monitor for expiring secrets

6. **Use Appropriate Permissions**
   - Principle of least privilege
   - Read-only access for applications
   - Separate admin and app credentials

## Troubleshooting

### Secret Not Found

**Environment Variables:**
```bash
# Check if variable is set
echo $DATIVO_ACME_STRIPE_API_KEY

# List all DATIVO variables
env | grep DATIVO
```

**Filesystem:**
```bash
# Check if file exists
ls -la /secrets/acme/

# Check file permissions
ls -l /secrets/acme/stripe.json
```

**Cloud Providers:**
- Verify secret exists in the provider's console
- Check authentication (credentials, IAM roles, service accounts)
- Verify network connectivity
- Check application logs for detailed error messages

### Authentication Errors

**HashiCorp Vault:**
```bash
# Test vault connection
vault status -address=https://vault.example.com:8200

# Check token
vault token lookup
```

**AWS:**
```bash
# Check credentials
aws sts get-caller-identity

# Test secret access
aws secretsmanager get-secret-value --secret-id dativo/acme
```

**GCP:**
```bash
# Check credentials
gcloud auth list

# Test secret access
gcloud secrets versions access latest --secret=dativo-acme
```

**Azure:**
```bash
# Check credentials
az account show

# Test secret access
az keyvault secret show --vault-name my-vault --name dativo-acme-stripe-api-key
```

## Security Considerations

1. **Encryption in Transit**: All cloud secret managers use TLS/SSL encryption
2. **Encryption at Rest**: Secrets are encrypted by the provider
3. **Access Logging**: Enable audit logging for all secret access
4. **Network Security**: Use private endpoints/VPC when available
5. **Credential Rotation**: Implement regular rotation policies
6. **Least Privilege**: Grant only necessary permissions
7. **Secret Scanning**: Use tools to detect secrets in code
8. **Environment Separation**: Use different secrets for dev/staging/prod

## Additional Resources

- [HashiCorp Vault Documentation](https://www.vaultproject.io/docs)
- [AWS Secrets Manager Documentation](https://docs.aws.amazon.com/secretsmanager/)
- [Google Cloud Secret Manager Documentation](https://cloud.google.com/secret-manager/docs)
- [Azure Key Vault Documentation](https://docs.microsoft.com/en-us/azure/key-vault/)
