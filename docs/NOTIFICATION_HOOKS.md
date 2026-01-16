# Notification Hooks

Notification hooks allow you to execute external scripts when jobs fail (or on other exit codes). Hooks are configured at the runner level and execute after job completion.

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
      - name: slack_alert
        command: ["/app/scripts/slack_alert.sh"]
        timeout_seconds: 15
        trigger_on_exit_codes: [2]  # Only on hard failures
        env:
          SLACK_WEBHOOK_URL: "${SLACK_WEBHOOK_URL}"
          JOB_NAME: "${DATIVO_JOB_NAME}"
      
      - name: pagerduty_alert
        command: ["/app/scripts/pagerduty.sh", "--severity", "critical"]
        timeout_seconds: 10
        trigger_on_exit_codes: [2]
        env:
          PAGERDUTY_KEY: "${PAGERDUTY_KEY}"
```

## Hook Configuration Fields

- **name**: Hook name for logging (required)
- **command**: Command and arguments as an array (required, no shell execution)
- **timeout_seconds**: Maximum execution time in seconds (default: 15, max: 60)
- **trigger_on_exit_codes**: List of exit codes that trigger this hook (default: `[2]` for hard failures)
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

- **Hooks execute only when the job exit code matches `trigger_on_exit_codes`** (default: `[2]` for hard failures)
- **Hooks run as external processes** (no shell execution, direct argv array)
- **Hooks have a timeout** (default: 15 seconds, max: 60 seconds)
- **Hook failures are logged but never crash the runner** - ingestion results remain accurate even if hooks fail
- **Secrets are redacted in logs** - command arguments and environment variables with secret patterns (token, key, secret, password) are redacted

## Exit Codes

- `0`: Success - hooks do not execute (unless configured with `trigger_on_exit_codes: [0]`)
- `1`: Partial success - hooks do not execute by default
- `2`: Hard failure - hooks execute by default

## Security

- Command arguments and environment variables are redacted in logs if they match secret patterns
- Hooks execute with the same environment as the runner process
- Hooks should not perform long-running operations (use timeout to prevent this)
- Hooks must not modify ingestion state or data

## Limitations

- Hooks are runner-level only (not per-job)
- Summary path may not be available in orchestrated mode (subprocess execution)
- Hooks execute synchronously after job completion (may add latency)
