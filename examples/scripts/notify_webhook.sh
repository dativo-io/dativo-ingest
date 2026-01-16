#!/usr/bin/env sh

if [ -z "${WEBHOOK_URL:-}" ]; then
  echo "WEBHOOK_URL is required" >&2
  exit 1
fi

method="${WEBHOOK_METHOD:-POST}"
headers="${WEBHOOK_HEADERS:-}"
summary_path="${DATIVO_SUMMARY_PATH:-}"

if [ -n "$summary_path" ] && [ -f "$summary_path" ]; then
  payload="$(cat "$summary_path" 2>/dev/null || true)"
else
  timestamp="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  tenant="${DATIVO_TENANT_ID:-unknown}"
  job="${DATIVO_JOB_NAME:-unknown}"
  run_id="${DATIVO_RUN_ID:-unknown}"
  payload=$(printf '{"tenant_id":"%s","job_name":"%s","run_id":"%s","status":"failure","timestamp":"%s"}' "$tenant" "$job" "$run_id" "$timestamp")
fi

set -- -sS -X "$method" -H "Content-Type: application/json"

if [ -n "$headers" ]; then
  old_ifs=$IFS
  IFS=','
  for header in $headers; do
    trimmed="$(printf '%s' "$header" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
    if [ -n "$trimmed" ]; then
      set -- "$@" -H "$trimmed"
    fi
  done
  IFS=$old_ifs
fi

if ! curl "$@" --data-binary "$payload" "$WEBHOOK_URL"; then
  echo "Failed to post webhook notification" >&2
  exit 1
fi
