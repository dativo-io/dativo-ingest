# Notification Hooks

Notification hooks allow you to execute external scripts when jobs fail. Hooks are configured at the runner level and execute only on hard failures (exit_code = 2).

## Configuration

Hooks are configured in `runner.yaml` under `runner.notifications.on_failure`:

```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: dagster
    schedules:
      - name: my_job
        config: /app/jobs/my_job.yaml
        cron: "0 * * * *"
  
  notifications:
    on_failure:
      command: ["/app/scripts/slack_alert.sh"]
      timeout_seconds: 15
      env:
        SLACK_WEBHOOK_URL: "${SLACK_WEBHOOK_URL}"
```

## Hook Configuration Fields

- **command**: Command and arguments as an array (required, no shell execution, supports `${VAR}` expansion)
- **timeout_seconds**: Maximum execution time in seconds (default: 15, max: 60)
- **env**: Optional environment variables (supports `${VAR}` expansion)

## Environment Variable Expansion

Hooks support environment variable expansion in command arguments and environment variables:

- `${VAR}` - Expands to the value of `VAR`, or empty string if not set
- `${VAR:-default}` - Expands to `default` if `VAR` is not set

Example:
```yaml
command: ["/app/scripts/alert.sh", "--url", "${ALERT_URL:-https://default.example.com}"]
env:
  API_KEY: "${ALERT_API_KEY}"
```

## Hook Payload

Hooks receive job information via a JSON payload file, accessible via the `DATIVO_HOOK_PAYLOAD` environment variable:

```json
{
  "tenant_id": "acme",
  "job_name": "stripe_customers",
  "config_path": "/app/jobs/acme/stripe_customers.yaml",
  "exit_code": 2,
  "failure_reason": "Connection timeout",
  "summary_path": "/app/state/acme/stripe_customers/runs/run-20240101T120000Z.json"
}
```

## Example Hook Script

Here's a simple example hook script that sends a Slack notification:

```bash
#!/bin/bash
# /app/scripts/slack_alert.sh

set -e

# Read payload
PAYLOAD_FILE="${DATIVO_HOOK_PAYLOAD}"
if [ -z "$PAYLOAD_FILE" ] || [ ! -f "$PAYLOAD_FILE" ]; then
  echo "ERROR: DATIVO_HOOK_PAYLOAD not set or file not found" >&2
  exit 1
fi

# Parse payload
TENANT_ID=$(jq -r '.tenant_id' "$PAYLOAD_FILE")
JOB_NAME=$(jq -r '.job_name' "$PAYLOAD_FILE")
EXIT_CODE=$(jq -r '.exit_code' "$PAYLOAD_FILE")
FAILURE_REASON=$(jq -r '.failure_reason // "Unknown error"' "$PAYLOAD_FILE")

# Send Slack notification
curl -X POST "${SLACK_WEBHOOK_URL}" \
  -H 'Content-Type: application/json' \
  -d "{
    \"text\": \"Job Failed: ${JOB_NAME}\",
    \"blocks\": [
      {
        \"type\": \"section\",
        \"text\": {
          \"type\": \"mrkdwn\",
          \"text\": \"*Job Failed*\n*Job:* ${JOB_NAME}\n*Tenant:* ${TENANT_ID}\n*Exit Code:* ${EXIT_CODE}\n*Reason:* ${FAILURE_REASON}\"
        }
      }
    ]
  }"

exit 0
```

## Behavior

- **Hooks execute only when exit_code is 2** (hard failure)
- **Hooks run as external processes** (no shell execution, direct argv array)
- **Hooks have a timeout** (default: 15 seconds, max: 60 seconds)
- **Hook failures are logged but never crash the runner** - ingestion results remain accurate even if hooks fail
- **Secrets are redacted in logs** - command arguments and environment variables with secret patterns (token, key, secret, password) are redacted

## Exit Codes

- `0`: Success - hooks do not execute
- `1`: Partial success - hooks do not execute
- `2`: Hard failure - hooks execute automatically

## Security

- Command arguments and environment variables are redacted in logs if they match secret patterns
- Hooks execute with the same environment as the runner process
- Hooks should not perform long-running operations (use timeout to prevent this)
- Hooks must not modify ingestion state or data

## Limitations

- Hooks are runner-level only (not per-job)
- Summary path may not be available in orchestrated mode (subprocess execution)
- Hooks execute synchronously after job completion (may add latency)
