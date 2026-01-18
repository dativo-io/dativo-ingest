# Dativo Notification Hook Scripts

This directory contains example notification hook scripts for Dativo's runner-level failure notifications.

## Overview

Notification hooks are triggered only on job failure (exit code = 2). They execute external commands provided by the user, following Dativo's philosophy:

- **Headless, config-only**: No built-in integrations, just hooks
- **No embedded services**: External scripts handle all integrations
- **User-controlled**: You decide how and where to send notifications

## Available Scripts

### `notify_slack.sh` - Slack Webhook

Sends formatted failure notifications to Slack using incoming webhooks.

**Required Environment Variables:**
- `SLACK_WEBHOOK_URL`: Slack incoming webhook URL

**Optional Environment Variables:**
- `SLACK_CHANNEL`: Override target channel
- `SLACK_USERNAME`: Override bot username (default: "Dativo")

**Example Configuration:**

```yaml
# runner.yaml
notifications:
  on_failure:
    command: ["/app/scripts/notify_slack.sh"]
    env:
      SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL}
```

### `notify_webhook.sh` - Generic HTTP Webhook

Sends failure notifications to any HTTP endpoint. Useful for custom integrations, monitoring systems, or incident management tools.

**Required Environment Variables:**
- `WEBHOOK_URL`: HTTP endpoint URL

**Optional Environment Variables:**
- `WEBHOOK_METHOD`: HTTP method (default: POST)
- `WEBHOOK_HEADERS`: Additional headers, comma-separated
- `WEBHOOK_WRAP`: If "true", wrap summary in an envelope

**Example Configuration:**

```yaml
# runner.yaml
notifications:
  on_failure:
    command: ["/app/scripts/notify_webhook.sh"]
    env:
      WEBHOOK_URL: ${WEBHOOK_URL}
      WEBHOOK_HEADERS: "Authorization: Bearer ${API_TOKEN}"
```

## Environment Contract

All notification hooks receive these environment variables from the runner:

| Variable | Description | Example |
|----------|-------------|---------|
| `DATIVO_TENANT_ID` | Tenant identifier | `acme` |
| `DATIVO_JOB_NAME` | Job or schedule name | `stripe_hourly` |
| `DATIVO_RUN_ID` | Unique run identifier | `2026-01-16T10:03:12Z` |
| `DATIVO_SUMMARY_PATH` | Absolute path to summary JSON | `/logs/runs/2026-01-16T10-03-12Z/summary.json` |

## Summary File Format

The summary JSON file contains failure details:

```json
{
  "tenant_id": "acme",
  "job_name": "stripe_hourly",
  "run_id": "2026-01-16T10:03:12Z",
  "status": "failure",
  "timestamp": "2026-01-16T10:03:12Z",
  "config_path": "/app/configs/jobs/stripe.yaml",
  "error": {
    "message": "Stripe API timeout",
    "type": "UpstreamError"
  }
}
```

## Writing Custom Hook Scripts

You can write your own notification hooks for any system. Requirements:

1. **Executable**: Script must be executable (`chmod +x`)
2. **No shell required**: Scripts are invoked directly via argv (no shell)
3. **Graceful failure**: Return non-zero on error, but don't crash
4. **Timeout**: Scripts should complete within the configured timeout (default: 15s)

### Example: PagerDuty Integration

```bash
#!/bin/sh
# notify_pagerduty.sh
curl -X POST \
  -H "Authorization: Token token=${PAGERDUTY_TOKEN}" \
  -H "Content-Type: application/json" \
  -d "{
    \"routing_key\": \"${PAGERDUTY_ROUTING_KEY}\",
    \"event_action\": \"trigger\",
    \"dedup_key\": \"${DATIVO_RUN_ID}\",
    \"payload\": {
      \"summary\": \"Dativo job failed: ${DATIVO_JOB_NAME}\",
      \"source\": \"dativo-ingest\",
      \"severity\": \"error\",
      \"custom_details\": {
        \"tenant_id\": \"${DATIVO_TENANT_ID}\",
        \"run_id\": \"${DATIVO_RUN_ID}\"
      }
    }
  }" \
  "https://events.pagerduty.com/v2/enqueue"
```

### Example: Kafka Integration

Dativo does **not** ship built-in Kafka support. If you need Kafka notifications, write a custom hook script:

```bash
#!/bin/sh
# notify_kafka.sh
#
# Required: kafka-console-producer (or kafkacat/kcat)
# Environment: KAFKA_BROKERS, KAFKA_TOPIC

if [ -z "$KAFKA_BROKERS" ] || [ -z "$KAFKA_TOPIC" ]; then
    echo "ERROR: KAFKA_BROKERS and KAFKA_TOPIC required" >&2
    exit 1
fi

# Read summary file and publish to Kafka
if [ -f "$DATIVO_SUMMARY_PATH" ]; then
    cat "$DATIVO_SUMMARY_PATH" | \
        kafka-console-producer \
            --broker-list "$KAFKA_BROKERS" \
            --topic "$KAFKA_TOPIC"
else
    echo "{\"tenant_id\":\"$DATIVO_TENANT_ID\",\"job_name\":\"$DATIVO_JOB_NAME\",\"status\":\"failure\"}" | \
        kafka-console-producer \
            --broker-list "$KAFKA_BROKERS" \
            --topic "$KAFKA_TOPIC"
fi
```

**Note**: For Kafka, you'll need to ensure `kafka-console-producer` or `kcat` is available in your Docker image.

## Non-Goals

Dativo explicitly does **not** implement:

- Built-in Slack/Teams/Discord integrations
- Built-in Kafka/RabbitMQ publishers
- Built-in PagerDuty/OpsGenie integrations
- Built-in email notifications

These are all achievable via custom hook scripts, giving you full control over the integration.

## Troubleshooting

### Script not found

```
ERROR: Hook command not found: /app/scripts/notify_slack.sh
```

Ensure the script path is correct and the file exists in your Docker container.

### Permission denied

```
ERROR: Hook command not executable: /app/scripts/notify_slack.sh
```

Run `chmod +x /app/scripts/notify_slack.sh` to make the script executable.

### Missing environment variables

```
ERROR: SLACK_WEBHOOK_URL environment variable is not set
```

Configure the required environment variables in your `runner.yaml`:

```yaml
notifications:
  on_failure:
    env:
      SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL}  # Reads from process env
```

### Webhook errors

Check the HTTP response code in the logs. Common issues:
- **401/403**: Authentication failed - check API tokens
- **404**: Webhook URL is incorrect
- **500**: Target service error - check service status

### Finding summary.json

The summary file location is logged when a hook is triggered. Default path pattern:
```
/logs/runs/{run_id}/summary.json
```

You can customize the base directory via the `summary_base_dir` parameter.
