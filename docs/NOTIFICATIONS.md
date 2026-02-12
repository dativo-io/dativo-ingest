# Notification Hooks

Dativo supports external notification hooks that execute when job lifecycle
events occur. This enables integration with Slack, PagerDuty, email, or any
custom alerting system via simple shell scripts or binaries.

## Overview

- **Trigger**: hooks fire after a job completes with a non-zero exit code
  (failure or partial failure).
- **Isolation**: hook failures are logged but **never change the job's exit
  code** or affect the pipeline result.
- **Timeout**: each hook has a configurable timeout (default 30 s, max 300 s).
- **Environment**: hooks receive Dativo-specific environment variables with
  tenant, job, run, and error context.

## Configuration

### Runner-level (applies to all jobs)

Add a `notifications` block inside your `runner.yaml`:

```yaml
runner:
  mode: orchestrated
  orchestrator:
    type: dagster
    schedules:
      - name: stripe_hourly
        config: /app/jobs/acme/stripe.yaml
        cron: "0 * * * *"
        enabled: true

  notifications:
    on_failure:
      command: ["/app/scripts/notify_slack.sh"]
      timeout_seconds: 30
      env:
        SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL}
```

### Job-level (overrides runner-level)

Add a `notifications` block in a job YAML file. Job-level configuration
**takes precedence** over runner-level when both are present.

```yaml
tenant_id: acme
source_connector_path: /app/connectors/stripe.yaml
target_connector_path: /app/connectors/iceberg.yaml
asset_path: /app/assets/stripe/customers.yaml

notifications:
  on_failure:
    command: ["/app/scripts/notify_slack.sh", "--channel", "#stripe-alerts"]
    timeout_seconds: 15
    env:
      SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL}
      TEAM_MENTION: "@data-eng"
```

### Multiple hooks

You can configure multiple hooks per event by passing a list:

```yaml
notifications:
  on_failure:
    - command: ["/app/scripts/notify_slack.sh"]
      env:
        SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL}
    - command: ["/app/scripts/notify_pagerduty.sh"]
      env:
        PD_ROUTING_KEY: ${PD_ROUTING_KEY}
```

## Environment Variables

The following environment variables are injected into every hook process:

| Variable | Description | Example |
|---|---|---|
| `DATIVO_TENANT_ID` | Tenant identifier | `acme` |
| `DATIVO_JOB_NAME` | Job / asset name | `stripe_customers` |
| `DATIVO_RUN_ID` | Unique run identifier | `20250212T143000Z` |
| `DATIVO_RUN_STATUS` | Human-readable status | `failure`, `partial`, `success` |
| `DATIVO_EXIT_CODE` | Numeric exit code | `0`, `1`, `2` |
| `DATIVO_SUMMARY_PATH` | Path to run summary JSON | `/app/state/acme/stripe_customers/runs/run-20250212T143000Z.json` |
| `DATIVO_ERROR_MESSAGE` | Short error description | `Connection refused` |
| `DATIVO_ENVIRONMENT` | Environment name | `production` |

Additionally, any variables configured in the hook's `env` block are set after
expanding `${VAR}` references from the current process environment.

## Example: Slack Notifier

An example Slack notifier script is provided at
[`examples/scripts/notify_slack.sh`](../examples/scripts/notify_slack.sh).

### Setup

1. Create a Slack Incoming Webhook at
   <https://api.slack.com/messaging/webhooks>.
2. Set the `SLACK_WEBHOOK_URL` environment variable or configure it in
   your secret manager.
3. Copy or mount the script into your container:

```bash
cp examples/scripts/notify_slack.sh /app/scripts/notify_slack.sh
chmod +x /app/scripts/notify_slack.sh
```

4. Add the notification configuration to your `runner.yaml`:

```yaml
notifications:
  on_failure:
    command: ["/app/scripts/notify_slack.sh"]
    env:
      SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL}
```

### How It Works

The script:
- Reads the `DATIVO_*` environment variables.
- Builds a formatted Slack Block Kit message with job details, error info,
  and color-coded status.
- Sends the message via `curl` to the Slack webhook URL.
- Uses `jq` for JSON construction when available; falls back to heredoc.

## Writing Custom Hook Scripts

Any executable can serve as a notification hook. Follow these guidelines:

1. **Exit code 0** on success, non-zero on failure.
2. **Read context from `DATIVO_*` env vars** (see table above).
3. **Keep execution fast** -- the hook timeout defaults to 30 seconds.
4. **Handle errors gracefully** -- the runner logs hook failures but does
   not retry them.
5. **Do not modify state** -- hooks should be side-effect-free with respect
   to the pipeline.

### Minimal example

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "Job ${DATIVO_JOB_NAME} failed for tenant ${DATIVO_TENANT_ID}"
echo "Status: ${DATIVO_RUN_STATUS}, Exit code: ${DATIVO_EXIT_CODE}"
echo "Error: ${DATIVO_ERROR_MESSAGE}"

# Send to your alerting system here
curl -X POST https://alerts.example.com/api/v1/alert \
  -H "Content-Type: application/json" \
  -d "{\"job\": \"${DATIVO_JOB_NAME}\", \"tenant\": \"${DATIVO_TENANT_ID}\"}"
```

## Troubleshooting

### Hook script not found

**Symptom**: Log message `Notification hook script not found: /app/scripts/notify.sh`

**Cause**: The script path in the `command` field does not exist in the
container or on the host.

**Fix**:
- Verify the script is mounted/copied into the container.
- Check the path is absolute and correct.
- Ensure the Docker volume mount includes the scripts directory.

### Permission denied

**Symptom**: Log message `Notification hook permission denied`

**Cause**: The script file lacks execute permission.

**Fix**:
```bash
chmod +x /app/scripts/notify_slack.sh
```

### Hook timed out

**Symptom**: Log message `Notification hook timed out after 30s`

**Cause**: The hook script took longer than `timeout_seconds` to complete.

**Fix**:
- Increase `timeout_seconds` in the notification config (max 300).
- Check network connectivity from the container to the webhook endpoint.
- Add `--max-time` to curl commands inside the script.

### Environment variable not expanded

**Symptom**: Webhook URL is literally `${SLACK_WEBHOOK_URL}` instead of
the actual URL.

**Cause**: The referenced environment variable is not set in the process
environment.

**Fix**:
- Verify the variable is set: `echo $SLACK_WEBHOOK_URL`
- If using Docker, pass it via `-e SLACK_WEBHOOK_URL=...` or in
  `docker-compose.yml` under `environment:`.
- If using a secret manager, ensure secrets are loaded before notifications
  are configured.

### Slack webhook returns HTTP 403/404

**Symptom**: Script logs `Slack webhook returned HTTP 403` or `HTTP 404`.

**Cause**: The webhook URL is invalid, expired, or the Slack app was
removed.

**Fix**:
- Regenerate the webhook URL in Slack App settings.
- Verify the URL has the format:
  `https://hooks.slack.com/services/T.../B.../...`
- Check that the Slack app has `incoming-webhooks` scope enabled.

### Notifications not firing

**Symptom**: Job fails but no notification is sent.

**Cause**: Possible causes include:
1. No `notifications` block in runner.yaml or job config.
2. Job exited with code 0 (success) -- notifications only fire on non-zero.
3. The `on_failure` key is missing or misspelled.

**Fix**:
- Verify configuration with `grep -A5 notifications runner.yaml`.
- Check runner logs for `notification_hook_started` or
  `notification_hooks_triggered` events.
- Test the hook manually:

```bash
DATIVO_TENANT_ID=test \
DATIVO_JOB_NAME=test_job \
DATIVO_RUN_ID=test-001 \
DATIVO_RUN_STATUS=failure \
DATIVO_EXIT_CODE=2 \
DATIVO_ERROR_MESSAGE="Test error" \
SLACK_WEBHOOK_URL="https://hooks.slack.com/services/YOUR/WEBHOOK/URL" \
/app/scripts/notify_slack.sh
```

## Configuration Reference

### `notifications.on_failure`

| Field | Type | Required | Default | Description |
|---|---|---|---|---|
| `command` | `list[string]` | Yes | -- | Command and arguments |
| `env` | `map[string, string]` | No | `{}` | Extra env vars (`${VAR}` expanded) |
| `timeout_seconds` | `integer` | No | `30` | Max execution time (1-300) |

### Precedence

1. **Job-level** `notifications` (in job YAML) takes full precedence.
2. **Runner-level** `notifications` (in runner.yaml) applies when no
   job-level config is present.
3. If neither is configured, no hooks execute.
