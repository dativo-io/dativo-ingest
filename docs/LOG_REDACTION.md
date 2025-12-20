# Log Secret Redaction

Dativo-Ingest includes built-in secret redaction to prevent sensitive credentials from appearing in logs. This is a critical security feature that helps protect API keys, passwords, tokens, and other sensitive information from being exposed in log files, monitoring systems, or error reports.

## Overview

When log redaction is enabled, the logging system automatically detects and redacts:

- **Passwords**: Database passwords, API passwords, etc.
- **API Keys**: Service API keys (e.g., `sk_live_...`, `AKIA...`)
- **Tokens**: Authentication tokens, bearer tokens, JWT tokens
- **Secret Keys**: AWS secret access keys, private keys
- **Credentials**: Any field containing "credential", "secret", "key", "token", or "password"
- **Long Base64 Strings**: Any string 20+ characters that looks like a base64-encoded secret

Redacted values are replaced with `[REDACTED]` in log output.

## Enabling Log Redaction

### Via Job Configuration

Enable redaction in your job YAML configuration:

```yaml
logging:
  level: INFO
  redaction: true  # Enable secret redaction
```

### Via CLI

Use the `--log-redaction` flag (if available) or configure in job config:

```bash
dativo ingest --config job.yaml --log-redaction
```

### Programmatically

```python
from dativo_ingest.logging import setup_logging

logger = setup_logging(
    level="INFO",
    redact_secrets=True,  # Enable redaction
    tenant_id="acme-corp"
)
```

## How It Works

The redaction system operates at multiple levels:

1. **Message Redaction**: Secrets in log messages are detected and redacted
2. **Extra Data Redaction**: Secrets in `extra` dictionary fields are redacted
3. **Nested Redaction**: Secrets in nested dictionaries are recursively redacted
4. **Pattern Matching**: Multiple patterns detect common secret field names and formats

## Examples

### Before Redaction

```json
{
  "timestamp": "2025-01-15T10:30:00",
  "level": "INFO",
  "message": "Connecting with password: mysecret123",
  "api_key": "sk_live_1234567890abcdef",
  "credentials": {
    "username": "admin",
    "password": "super_secret_password"
  }
}
```

### After Redaction

```json
{
  "timestamp": "2025-01-15T10:30:00",
  "level": "INFO",
  "message": "Connecting with password: [REDACTED]",
  "api_key": "[REDACTED]",
  "credentials": {
    "username": "admin",
    "password": "[REDACTED]"
  }
}
```

## Supported Secret Types

The redaction system recognizes the following secret field patterns (case-insensitive):

- `password`
- `token`
- `api_key`
- `secret`
- `credential`
- `access_key`
- `secret_key`
- `secret_access_key`
- `private_key`
- `auth_token`
- `bearer`

Additionally, any string value 20+ characters that matches a base64-like pattern (alphanumeric + `/`, `+`, `=`) will be redacted, even if it doesn't have an obvious secret field name.

## Log Output Examples

### Example 1: API Key in Message

**Input:**
```python
logger.info('API key: "sk_live_1234567890abcdef"')
```

**Output (redaction enabled):**
```json
{
  "message": "API key: [REDACTED]",
  "level": "INFO"
}
```

### Example 2: Secrets in Extra Data

**Input:**
```python
logger.info(
    "Connecting to database",
    extra={
        "host": "db.example.com",
        "username": "admin",
        "password": "super_secret_password_123",
        "api_key": "sk_live_abcdef1234567890"
    }
)
```

**Output (redaction enabled):**
```json
{
  "message": "Connecting to database",
  "level": "INFO",
  "host": "db.example.com",
  "username": "admin",
  "password": "[REDACTED]",
  "api_key": "[REDACTED]"
}
```

### Example 3: Nested Secrets

**Input:**
```python
logger.info(
    "Configuration loaded",
    extra={
        "config": {
            "database": {
                "host": "localhost",
                "password": "db_secret_123"
            },
            "api": {
                "key": "sk_live_1234567890"
            }
        }
    }
)
```

**Output (redaction enabled):**
```json
{
  "message": "Configuration loaded",
  "level": "INFO",
  "config": {
    "database": {
      "host": "localhost",
      "password": "[REDACTED]"
    },
    "api": {
      "key": "[REDACTED]"
    }
  }
}
```

## Coverage

Log redaction applies consistently across:

- ✅ **Orchestrator Logs**: Main execution logs from the orchestrator
- ✅ **Plugin Logs**: Logs from Python and Rust plugins
- ✅ **Runtime Logs**: All runtime logging output
- ✅ **Error Logs**: Exception traces and error messages
- ✅ **Structured Logs**: JSON-formatted log output

## Best Practices

1. **Always Enable in Production**: Enable log redaction in all production environments
2. **Test Redaction**: Verify that secrets are properly redacted before deploying
3. **Monitor Logs**: Even with redaction, monitor logs for suspicious patterns
4. **Use Secret Managers**: Combine log redaction with proper secret management (Vault, AWS Secrets Manager, etc.)
5. **Review Log Output**: Periodically review log output to ensure redaction is working correctly

## Limitations

- **Short Secrets**: Secrets shorter than 20 characters may not be detected if they don't match field name patterns
- **Custom Formats**: Very unusual secret formats may not be automatically detected
- **Performance**: Redaction adds minimal overhead but processes all log messages
- **Plugin Output**: Plugin stdout/stderr may not be redacted if plugins log directly (use the logging framework)

## Testing Redaction

You can test that redaction is working by checking log output:

```python
from dativo_ingest.logging import setup_logging
import json

logger = setup_logging(level="INFO", redact_secrets=True)

logger.info('API key: "sk_live_test1234567890"')

# Check that logs contain [REDACTED] and not the actual secret
```

## Security Note

While log redaction provides important protection, it should be combined with:

- Proper secret management (never hardcode secrets)
- Secure log storage (encrypted log files, secure log aggregation)
- Access controls on log viewing systems
- Regular security audits

Log redaction is a defense-in-depth measure, not a replacement for proper secret management practices.
