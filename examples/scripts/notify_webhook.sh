#!/bin/sh
# Dativo Notification Hook: Generic HTTP Webhook
#
# This script sends job failure notifications to any HTTP endpoint.
# It POSTs the failure summary JSON (or wraps it in a minimal envelope).
#
# Required Environment Variables (injected by runner):
#   DATIVO_TENANT_ID    - Tenant identifier
#   DATIVO_JOB_NAME     - Job/schedule name
#   DATIVO_RUN_ID       - Unique run identifier
#   DATIVO_SUMMARY_PATH - Path to failure summary JSON file
#
# User-Provided Environment Variables (via runner.yaml):
#   WEBHOOK_URL         - HTTP endpoint URL (required)
#   WEBHOOK_METHOD      - HTTP method (optional, default: POST)
#   WEBHOOK_HEADERS     - Additional headers, comma-separated (optional)
#                         Example: "Authorization: Bearer token,X-Custom: value"
#   WEBHOOK_WRAP        - If "true", wrap summary in envelope (optional)
#
# Usage in runner.yaml:
#   notifications:
#     on_failure:
#       command: ["/app/scripts/notify_webhook.sh"]
#       env:
#         WEBHOOK_URL: ${WEBHOOK_URL}
#         WEBHOOK_HEADERS: "Authorization: Bearer ${API_TOKEN}"
#
# Exit Codes:
#   0 - Success (2xx response)
#   1 - Missing required environment variables
#   2 - curl command failed or non-2xx response
#

set -e

# Validate required environment variables
if [ -z "$WEBHOOK_URL" ]; then
    echo "ERROR: WEBHOOK_URL environment variable is not set" >&2
    exit 1
fi

if [ -z "$DATIVO_TENANT_ID" ] || [ -z "$DATIVO_JOB_NAME" ] || [ -z "$DATIVO_RUN_ID" ]; then
    echo "ERROR: Required DATIVO_* environment variables are not set" >&2
    exit 1
fi

# Set defaults
WEBHOOK_METHOD="${WEBHOOK_METHOD:-POST}"

# Build payload
if [ -n "$DATIVO_SUMMARY_PATH" ] && [ -f "$DATIVO_SUMMARY_PATH" ]; then
    if [ "$WEBHOOK_WRAP" = "true" ]; then
        # Wrap summary in envelope
        SUMMARY_CONTENT=$(cat "$DATIVO_SUMMARY_PATH")
        PAYLOAD=$(cat <<EOF
{
    "event_type": "dativo.job.failure",
    "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "tenant_id": "${DATIVO_TENANT_ID}",
    "job_name": "${DATIVO_JOB_NAME}",
    "run_id": "${DATIVO_RUN_ID}",
    "summary": ${SUMMARY_CONTENT}
}
EOF
)
    else
        # Send raw summary JSON
        PAYLOAD=$(cat "$DATIVO_SUMMARY_PATH")
    fi
else
    # Summary file not available - create minimal payload
    PAYLOAD=$(cat <<EOF
{
    "event_type": "dativo.job.failure",
    "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
    "tenant_id": "${DATIVO_TENANT_ID}",
    "job_name": "${DATIVO_JOB_NAME}",
    "run_id": "${DATIVO_RUN_ID}",
    "status": "failure",
    "error": {
        "message": "Summary file not available",
        "type": "UnknownError"
    }
}
EOF
)
fi

# Build curl command
CURL_CMD="curl -s -o /dev/null -w \"%{http_code}\" -X $WEBHOOK_METHOD"
CURL_CMD="$CURL_CMD -H \"Content-Type: application/json\""

# Add custom headers if provided
if [ -n "$WEBHOOK_HEADERS" ]; then
    # Parse comma-separated headers
    echo "$WEBHOOK_HEADERS" | tr ',' '\n' | while read -r header; do
        header=$(echo "$header" | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
        if [ -n "$header" ]; then
            CURL_CMD="$CURL_CMD -H \"$header\""
        fi
    done
fi

# Execute request
# Note: Using a temp file to avoid issues with special characters in payload
TEMP_PAYLOAD=$(mktemp)
echo "$PAYLOAD" > "$TEMP_PAYLOAD"

HTTP_RESPONSE=$(curl -s -o /dev/null -w "%{http_code}" \
    -X "$WEBHOOK_METHOD" \
    -H "Content-Type: application/json" \
    ${WEBHOOK_HEADERS:+-H "$WEBHOOK_HEADERS"} \
    -d @"$TEMP_PAYLOAD" \
    "$WEBHOOK_URL")

# Cleanup
rm -f "$TEMP_PAYLOAD"

if [ "$HTTP_RESPONSE" -ge 200 ] && [ "$HTTP_RESPONSE" -lt 300 ]; then
    echo "Webhook notification sent successfully (HTTP $HTTP_RESPONSE)"
    exit 0
else
    echo "ERROR: Webhook notification failed (HTTP $HTTP_RESPONSE)" >&2
    exit 2
fi
