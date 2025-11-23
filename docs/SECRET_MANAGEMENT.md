# Secret Management

> Secrets are now loaded via pluggable managers so you can keep credentials wherever it best fits your operations model. Environment variables are the default fallback, while the legacy filesystem loader stays available for backwards compatibility.

## Quick Reference

| Option | Purpose |
|---|---|
| `--secret-manager {env|filesystem|vault|aws|gcp}` | Selects the backend (defaults to `env` or `$DATIVO_SECRET_MANAGER`). |
| `--secret-manager-config <path-or-json>` | Supplies backend-specific settings (defaults to `$DATIVO_SECRET_MANAGER_CONFIG`). |
| `--secrets-dir <path>` | Filesystem root used only when `--secret-manager filesystem`. |

All commands from the CLI and orchestrated runner support the same flags. When omitted, the runner uses the environment manager and returns an empty secret map if no variables are present.

## Environment Secret Manager (default)

Environment secrets use namespaced variables that follow this pattern:

```
DATIVO_SECRET__{TENANT}__{SECRET_NAME}__[json|env|text]
```

- `TENANT`: Case-insensitive tenant ID (e.g., `ACME`).
- `SECRET_NAME`: Free-form token (underscores are preserved). Example: `POSTGRES`, `stripe_api_key`.
- Optional suffix indicates parsing mode:
  - `json` – JSON payload (`{"user": "service", "password": "..."}`).
  - `env` – `.env` style multiline blob (`KEY=VALUE` per line).
  - `text`/`raw` – stored as-is (after environment expansion).
  - Omitted – auto-detect (`json` if it starts with `{`/`[`, `.env` if multi-line `KEY=value`, otherwise plain text).
- `GLOBAL` or `ALL` can replace `{TENANT}` to share a secret across every tenant.

Example:

```bash
export DATIVO_SECRET__ACME_CORP__postgres__env=$'PGHOST=db\nPGUSER=reader\nPGPASSWORD=${POSTGRES_PASSWORD}'
export DATIVO_SECRET__GLOBAL__stripe_api_key__text="sk_live_123"
```

The loader yields:

```json
{
  "postgres": {"PGHOST": "db", "PGUSER": "reader", "PGPASSWORD": "..."},
  "stripe_api_key": "sk_live_123"
}
```

## Filesystem Secret Manager

Structure mirrors the prior `/secrets/{tenant}` layout:

```
/secrets/
  {tenant}/
    postgres.env
    gsheets.json
    stripe_api_key
```

JSON, `.env`, and plaintext files are supported. Enable it via:

```bash
dativo run --job-dir jobs/acme \
  --secret-manager filesystem \
  --secrets-dir /path/to/secrets
```

A missing tenant directory raises a `ValueError`, matching the legacy behaviour.

## HashiCorp Vault Secret Manager

- Depends on the `hvac` library (now declared in `pyproject.toml`).
- Supports token and AppRole auth.
- Reads data from KV v1 or v2 mounts; you can specify multiple paths.

Configuration example (`vault-secrets.yaml`):

```yaml
address: https://vault.example.com
mount_point: secret
path_template: dativo/{tenant}
kv_version: 2
auth_method: approle
role_id: "${VAULT_ROLE_ID}"
secret_id: "${VAULT_SECRET_ID}"
paths:
  - path: dativo/{tenant}/database
  - path: global/payments
```

Invoke:

```bash
dativo run --job-dir jobs/acme \
  --secret-manager vault \
  --secret-manager-config vault-secrets.yaml
```

Each path is formatted with `{tenant}` and merged into the final secret map.

## AWS Secrets Manager

AWS support uses either discrete secret definitions or a “bundle” secret that contains a JSON object.

### Discrete secrets

```yaml
region_name: us-east-1
secret_id_template: prod/{tenant}/{name}
secrets:
  - name: postgres
    format: env
  - name: stripe_api_key
    format: text
    id: prod/shared/stripe_api_key
```

`secret_id_template` accepts `{tenant}` and `{name}` placeholders. Every `secret` entry can override the resolved ID and specify `format`, `version_stage`, or `version_id`.

### Bundle secret

```yaml
region_name: us-east-1
bundle_secret_id_template: prod/{tenant}/bundle
bundle_format: json
```

The bundle secret must deserialize into a JSON object (keys become individual secrets). Use this when you already store tenant credentials as a single document.

## GCP Secret Manager

Configuration mirrors the AWS model.

```yaml
project_id: dativo-prod
secret_id_template: dativo-{tenant}-{name}
version: latest
secrets:
  - name: postgres
    format: env
  - name: gsheets
    format: json
```

or bundle mode:

```yaml
project_id: dativo-prod
bundle_secret_id_template: dativo-{tenant}-bundle
bundle_format: json
```

Provide the file via `--secret-manager-config` or inline JSON.

## Environment Variables

| Variable | Description |
|---|---|
| `DATIVO_SECRET_MANAGER` | Overrides the CLI default secret manager. |
| `DATIVO_SECRET_MANAGER_CONFIG` | Inline JSON or path to config file (used when the CLI flag is omitted). |
| `VAULT_ADDR`, `VAULT_TOKEN`, `VAULT_ROLE_ID`, `VAULT_SECRET_ID`, `VAULT_NAMESPACE` | Vault defaults. |
| `GOOGLE_CLOUD_PROJECT` | Default `project_id` for GCP manager. |

## Choosing a Manager

- **env**: Best for containerized deployments where orchestration already injects secrets as environment variables.
- **filesystem**: Legacy installs or local testing with checked-in fixtures.
- **vault/aws/gcp**: Production integrations with centralized secret stores. Use discrete definitions for fine-grained control or bundle templates to mirror existing layouts.

Regardless of backend, `load_secrets()` always returns a simple dictionary that downstream validation logic can consume without knowing where secrets originated.
