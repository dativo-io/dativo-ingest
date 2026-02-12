#!/usr/bin/env bash
set -euo pipefail

# Required input for Slack Incoming Webhooks.
if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
  echo "SLACK_WEBHOOK_URL is required" >&2
  exit 1
fi

tenant="${DATIVO_TENANT_ID:-unknown-tenant}"
job="${DATIVO_JOB_NAME:-unknown-job}"
schedule="${DATIVO_SCHEDULE_NAME:-unknown-schedule}"
run_id="${DATIVO_RUN_ID:-unknown-run}"
summary_path="${DATIVO_SUMMARY_PATH:-not-available}"
exit_code="${DATIVO_RUN_EXIT_CODE:-2}"

slack_message="[dativo] job failure
tenant: ${tenant}
job: ${job}
schedule: ${schedule}
run_id: ${run_id}
exit_code: ${exit_code}
summary: ${summary_path}"

export SLACK_MESSAGE="${slack_message}"
payload="$(
  python - <<'PY'
import json
import os

print(json.dumps({"text": os.environ["SLACK_MESSAGE"]}))
PY
)"

curl -fsS -X POST \
  -H "Content-Type: application/json" \
  --data "${payload}" \
  "${SLACK_WEBHOOK_URL}"
