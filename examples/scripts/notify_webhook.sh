#!/bin/bash
set -e

# Required env vars:
# WEBHOOK_URL
# DATIVO_SUMMARY_PATH

# Optional env vars:
# WEBHOOK_METHOD (default: POST)
# WEBHOOK_HEADERS (default: Content-Type: application/json)

if [ -z "$WEBHOOK_URL" ]; then
  echo "Error: WEBHOOK_URL is not set" >&2
  exit 1
fi

if [ ! -f "$DATIVO_SUMMARY_PATH" ]; then
  echo "Error: Summary file not found at $DATIVO_SUMMARY_PATH" >&2
  exit 1
fi

METHOD=${WEBHOOK_METHOD:-POST}
HEADERS=${WEBHOOK_HEADERS:-"Content-Type: application/json"}

# Send request with summary file content
# Uses @file syntax to upload the file content as the body
curl -s -X "$METHOD" \
     -H "$HEADERS" \
     -d "@$DATIVO_SUMMARY_PATH" \
     "$WEBHOOK_URL"

echo "Webhook notification sent to $WEBHOOK_URL"
