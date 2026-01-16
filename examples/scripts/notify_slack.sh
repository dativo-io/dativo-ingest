#!/bin/bash
set -e

# Required env vars:
# SLACK_WEBHOOK_URL
# DATIVO_TENANT_ID
# DATIVO_JOB_NAME
# DATIVO_RUN_ID
# DATIVO_SUMMARY_PATH

if [ -z "$SLACK_WEBHOOK_URL" ]; then
  echo "Error: SLACK_WEBHOOK_URL is not set" >&2
  exit 1
fi

if [ ! -f "$DATIVO_SUMMARY_PATH" ]; then
  echo "Error: Summary file not found at $DATIVO_SUMMARY_PATH" >&2
  exit 1
fi

# Extract fields (using grep/sed since jq might not be available)
# Assuming simple flattened JSON structure from runner
STATUS=$(grep -o '"status": *"[^"]*"' "$DATIVO_SUMMARY_PATH" | cut -d'"' -f4)
TIMESTAMP=$(grep -o '"timestamp": *"[^"]*"' "$DATIVO_SUMMARY_PATH" | cut -d'"' -f4)

# Error message might contain quotes or be complex, so we grab it carefully
# This is a best-effort extraction for the Slack message
ERROR_MSG=$(grep -o '"message": *"[^"]*"' "$DATIVO_SUMMARY_PATH" | head -1 | cut -d'"' -f4)

# Fallbacks
STATUS=${STATUS:-failure}
ERROR_MSG=${ERROR_MSG:-Unknown error (check summary file)}
TIMESTAMP=${TIMESTAMP:-$(date -u +"%Y-%m-%dT%H:%M:%SZ")}

# Construct payload
# We use Python for JSON escaping if available, otherwise simple string interpolation
# This avoids issues with special characters in error messages
if command -v python3 &> /dev/null; then
  PAYLOAD=$(python3 -c "
import json
import os

print(json.dumps({
    'text': f'🚨 *Job Failed: {os.environ.get(\"DATIVO_JOB_NAME\")}\*',
    'blocks': [
        {
            'type': 'header',
            'text': {
                'type': 'plain_text',
                'text': f'🚨 Job Failed: {os.environ.get(\"DATIVO_JOB_NAME\")}',
                'emoji': True
            }
        },
        {
            'type': 'section',
            'fields': [
                {
                    'type': 'mrkdwn',
                    'text': f'*Tenant:*\n{os.environ.get(\"DATIVO_TENANT_ID\")}'
                },
                {
                    'type': 'mrkdwn',
                    'text': f'*Run ID:*\n{os.environ.get(\"DATIVO_RUN_ID\")}'
                },
                {
                    'type': 'mrkdwn',
                    'text': f'*Timestamp:*\n{os.environ.get(\"TIMESTAMP\")}'
                },
                {
                    'type': 'mrkdwn',
                    'text': f'*Status:*\n{os.environ.get(\"STATUS\")}'
                }
            ]
        },
        {
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': f'*Error:*\n{os.environ.get(\"ERROR_MSG\")}'
            }
        }
    ]
}))
")
else
  # Minimal fallback without proper JSON escaping (risky but satisfies 'pure shell' if python missing)
  PAYLOAD=$(cat <<EOF
{
  "text": "🚨 *Job Failed: ${DATIVO_JOB_NAME}*",
  "blocks": [
    {
      "type": "section",
      "fields": [
        { "type": "mrkdwn", "text": "*Job:* ${DATIVO_JOB_NAME}" },
        { "type": "mrkdwn", "text": "*Run ID:* ${DATIVO_RUN_ID}" },
        { "type": "mrkdwn", "text": "*Error:* ${ERROR_MSG}" }
      ]
    }
  ]
}
EOF
)
fi

# Send request
curl -s -X POST -H 'Content-type: application/json' --data "$PAYLOAD" "$SLACK_WEBHOOK_URL"

echo "Slack notification sent"
