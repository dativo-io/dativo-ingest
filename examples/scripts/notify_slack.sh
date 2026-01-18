#!/bin/sh
# Dativo Notification Hook: Slack Webhook
#
# This script sends job failure notifications to Slack via incoming webhook.
# It uses the Slack Block Kit format for a rich, formatted message.
#
# Required Environment Variables (injected by runner):
#   DATIVO_TENANT_ID    - Tenant identifier
#   DATIVO_JOB_NAME     - Job/schedule name
#   DATIVO_RUN_ID       - Unique run identifier
#   DATIVO_SUMMARY_PATH - Path to failure summary JSON file
#
# User-Provided Environment Variables (via runner.yaml):
#   SLACK_WEBHOOK_URL   - Slack incoming webhook URL (required)
#   SLACK_CHANNEL       - Override channel (optional)
#   SLACK_USERNAME      - Override bot username (optional, default: "Dativo")
#
# Usage in runner.yaml:
#   notifications:
#     on_failure:
#       command: ["/app/scripts/notify_slack.sh"]
#       env:
#         SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL}
#
# Exit Codes:
#   0 - Success
#   1 - Missing required environment variables
#   2 - curl command failed
#

set -e

# Validate required environment variables
if [ -z "$SLACK_WEBHOOK_URL" ]; then
    echo "ERROR: SLACK_WEBHOOK_URL environment variable is not set" >&2
    exit 1
fi

if [ -z "$DATIVO_TENANT_ID" ] || [ -z "$DATIVO_JOB_NAME" ] || [ -z "$DATIVO_RUN_ID" ]; then
    echo "ERROR: Required DATIVO_* environment variables are not set" >&2
    exit 1
fi

# Set defaults
SLACK_USERNAME="${SLACK_USERNAME:-Dativo}"

# Extract error message from summary file if available
ERROR_MESSAGE="Job execution failed"
if [ -n "$DATIVO_SUMMARY_PATH" ] && [ -f "$DATIVO_SUMMARY_PATH" ]; then
    # Try to extract error message using grep/sed (pure shell, no jq dependency)
    ERROR_MESSAGE=$(grep -o '"message"[[:space:]]*:[[:space:]]*"[^"]*"' "$DATIVO_SUMMARY_PATH" | head -1 | sed 's/.*"message"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/' || echo "Job execution failed")
    
    # Escape special characters for JSON
    ERROR_MESSAGE=$(echo "$ERROR_MESSAGE" | sed 's/\\/\\\\/g' | sed 's/"/\\"/g' | sed 's/\n/\\n/g')
fi

# Build Slack Block Kit payload
# Using heredoc for multiline JSON
PAYLOAD=$(cat <<EOF
{
    "username": "${SLACK_USERNAME}",
    "icon_emoji": ":warning:",
    "blocks": [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": ":x: Dativo Job Failed",
                "emoji": true
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": "*Tenant:*\n${DATIVO_TENANT_ID}"
                },
                {
                    "type": "mrkdwn",
                    "text": "*Job:*\n${DATIVO_JOB_NAME}"
                },
                {
                    "type": "mrkdwn",
                    "text": "*Run ID:*\n\`${DATIVO_RUN_ID}\`"
                }
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Error:*\n\`\`\`${ERROR_MESSAGE}\`\`\`"
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "Summary: \`${DATIVO_SUMMARY_PATH:-N/A}\`"
                }
            ]
        }
    ]
}
EOF
)

# Add optional channel override
if [ -n "$SLACK_CHANNEL" ]; then
    PAYLOAD=$(echo "$PAYLOAD" | sed "s/\"username\"/\"channel\": \"${SLACK_CHANNEL}\", \"username\"/")
fi

# Send to Slack
HTTP_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d "$PAYLOAD" \
    "$SLACK_WEBHOOK_URL")

if [ "$HTTP_RESPONSE" -ge 200 ] && [ "$HTTP_RESPONSE" -lt 300 ]; then
    echo "Slack notification sent successfully (HTTP $HTTP_RESPONSE)"
    exit 0
else
    echo "ERROR: Slack notification failed (HTTP $HTTP_RESPONSE)" >&2
    exit 2
fi
