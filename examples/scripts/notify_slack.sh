#!/usr/bin/env bash
# ===========================================================================
# Slack Notification Hook for Dativo Job Failures
# ===========================================================================
#
# This script sends a formatted message to a Slack channel via an Incoming
# Webhook when a Dativo ingestion job fails.
#
# Usage (configured in runner.yaml or job config):
#
#   notifications:
#     on_failure:
#       command: ["/app/scripts/notify_slack.sh"]
#       env:
#         SLACK_WEBHOOK_URL: ${SLACK_WEBHOOK_URL}
#
# Environment variables injected by the runner:
#   DATIVO_TENANT_ID      - Tenant identifier
#   DATIVO_JOB_NAME       - Job/asset name
#   DATIVO_RUN_ID         - Unique run identifier
#   DATIVO_RUN_STATUS     - Run status (failure | partial | success)
#   DATIVO_EXIT_CODE      - Numeric exit code (0, 1, 2)
#   DATIVO_SUMMARY_PATH   - Path to run summary JSON (may be empty)
#   DATIVO_ERROR_MESSAGE  - Short error description (may be empty)
#   DATIVO_ENVIRONMENT    - Environment name (dev, staging, prod)
#
# Required environment variables (supplied via hook env config):
#   SLACK_WEBHOOK_URL     - Slack Incoming Webhook URL
#
# Exit codes:
#   0 - Notification sent successfully
#   1 - Failed to send notification (curl error or missing config)
# ===========================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Validate required configuration
# ---------------------------------------------------------------------------
if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
    echo "ERROR: SLACK_WEBHOOK_URL is not set. Cannot send Slack notification." >&2
    echo "Hint: Add SLACK_WEBHOOK_URL to the notification hook env config or" >&2
    echo "      set it as a process environment variable." >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Build the Slack message payload
# ---------------------------------------------------------------------------
TENANT="${DATIVO_TENANT_ID:-unknown}"
JOB="${DATIVO_JOB_NAME:-unknown}"
RUN_ID="${DATIVO_RUN_ID:-unknown}"
STATUS="${DATIVO_RUN_STATUS:-failure}"
EXIT_CODE="${DATIVO_EXIT_CODE:-2}"
SUMMARY_PATH="${DATIVO_SUMMARY_PATH:-}"
ERROR_MSG="${DATIVO_ERROR_MESSAGE:-No error details available}"
ENVIRONMENT="${DATIVO_ENVIRONMENT:-unknown}"

# Choose emoji based on status
if [[ "${STATUS}" == "failure" ]]; then
    EMOJI=":red_circle:"
    COLOR="#E01E5A"
elif [[ "${STATUS}" == "partial" ]]; then
    EMOJI=":large_orange_circle:"
    COLOR="#ECB22E"
else
    EMOJI=":white_check_mark:"
    COLOR="#2EB67D"
fi

# Truncate error message if very long
if [[ ${#ERROR_MSG} -gt 500 ]]; then
    ERROR_MSG="${ERROR_MSG:0:497}..."
fi

# Build JSON payload using a heredoc.
# We use jq if available for proper escaping; fall back to manual construction.
if command -v jq &>/dev/null; then
    PAYLOAD=$(jq -n \
        --arg emoji "$EMOJI" \
        --arg status "$STATUS" \
        --arg tenant "$TENANT" \
        --arg job "$JOB" \
        --arg run_id "$RUN_ID" \
        --arg exit_code "$EXIT_CODE" \
        --arg error_msg "$ERROR_MSG" \
        --arg environment "$ENVIRONMENT" \
        --arg color "$COLOR" \
        --arg summary_path "$SUMMARY_PATH" \
        '{
            "attachments": [{
                "color": $color,
                "blocks": [
                    {
                        "type": "header",
                        "text": {
                            "type": "plain_text",
                            "text": ("\($emoji) Dativo Job " + ($status | ascii_upcase)),
                            "emoji": true
                        }
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": ("*Tenant:*\n" + $tenant)},
                            {"type": "mrkdwn", "text": ("*Job:*\n" + $job)},
                            {"type": "mrkdwn", "text": ("*Environment:*\n" + $environment)},
                            {"type": "mrkdwn", "text": ("*Exit Code:*\n" + $exit_code)},
                            {"type": "mrkdwn", "text": ("*Run ID:*\n`" + $run_id + "`")}
                        ]
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": ("*Error:*\n```" + $error_msg + "```")
                        }
                    }
                ]
            }]
        }')
else
    # Fallback: simple JSON without jq (basic escaping)
    # Escape double quotes and backslashes in error message
    ESCAPED_ERROR=$(echo "${ERROR_MSG}" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\n/\\n/g')
    PAYLOAD=$(cat <<EOF
{
    "attachments": [{
        "color": "${COLOR}",
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "${EMOJI} Dativo Job ${STATUS^^}",
                    "emoji": true
                }
            },
            {
                "type": "section",
                "fields": [
                    {"type": "mrkdwn", "text": "*Tenant:*\n${TENANT}"},
                    {"type": "mrkdwn", "text": "*Job:*\n${JOB}"},
                    {"type": "mrkdwn", "text": "*Environment:*\n${ENVIRONMENT}"},
                    {"type": "mrkdwn", "text": "*Exit Code:*\n${EXIT_CODE}"},
                    {"type": "mrkdwn", "text": "*Run ID:*\n\`${RUN_ID}\`"}
                ]
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Error:*\n\`\`\`${ESCAPED_ERROR}\`\`\`"
                }
            }
        ]
    }]
}
EOF
)
fi

# ---------------------------------------------------------------------------
# Send the notification
# ---------------------------------------------------------------------------
HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X POST \
    -H "Content-Type: application/json" \
    -d "${PAYLOAD}" \
    --max-time 10 \
    "${SLACK_WEBHOOK_URL}")

if [[ "${HTTP_CODE}" == "200" ]]; then
    echo "Slack notification sent successfully (tenant=${TENANT}, job=${JOB})"
    exit 0
else
    echo "ERROR: Slack webhook returned HTTP ${HTTP_CODE}" >&2
    echo "Hint: Verify SLACK_WEBHOOK_URL is correct and the webhook is active." >&2
    exit 1
fi
