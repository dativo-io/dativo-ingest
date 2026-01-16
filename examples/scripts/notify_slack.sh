#!/usr/bin/env sh

if [ -z "${SLACK_WEBHOOK_URL:-}" ]; then
  echo "SLACK_WEBHOOK_URL is required" >&2
  exit 1
fi

tenant="${DATIVO_TENANT_ID:-unknown}"
job="${DATIVO_JOB_NAME:-unknown}"
run_id="${DATIVO_RUN_ID:-unknown}"
summary_path="${DATIVO_SUMMARY_PATH:-}"

summary_json=""
error_message=""

if [ -n "$summary_path" ] && [ -f "$summary_path" ]; then
  summary_json="$(cat "$summary_path" 2>/dev/null || true)"
  error_message="$(printf '%s' "$summary_json" | sed -n 's/.*"message"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"
fi

if [ -z "$error_message" ]; then
  error_message="(see summary)"
fi

text="Dativo job failed. tenant=${tenant} job=${job} run=${run_id} error=${error_message}"
if [ -n "$summary_json" ]; then
  text="${text}\nsummary=${summary_json}"
fi

json_escape() {
  printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g; s/\r//g; s/\n/\\n/g'
}

payload=$(printf '{"text":"%s"}' "$(json_escape "$text")")

if ! curl -sS -X POST -H "Content-Type: application/json" --data "$payload" "$SLACK_WEBHOOK_URL"; then
  echo "Failed to post Slack notification" >&2
  exit 1
fi
