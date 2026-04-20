#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_HOST="${MIXZ_API_HOST:-127.0.0.1}"
API_PORT="${MIXZ_API_PORT:-8000}"
API_BASE="http://${API_HOST}:${API_PORT}"
LOG_FILE="${MIXZ_SELF_CHECK_LOG:-/tmp/mixz_self_check_api.log}"
START_TIMEOUT_SEC="${MIXZ_SELF_CHECK_TIMEOUT_SEC:-30}"

if [[ -z "${MIXZ_POSTGRES_DSN:-}" ]]; then
  echo "ERROR: MIXZ_POSTGRES_DSN is not set"
  echo "Hint: export MIXZ_POSTGRES_DSN='postgresql+psycopg://user:pass@host:5432/db'"
  exit 1
fi

started_by_script=0
api_pid=""

cleanup() {
  if [[ "$started_by_script" -eq 1 ]] && [[ -n "$api_pid" ]] && kill -0 "$api_pid" >/dev/null 2>&1; then
    kill "$api_pid" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

endpoint_status() {
  local path="$1"
  local code
  code="$(curl -sS -o /tmp/mixz_self_check_response.out -w "%{http_code}" "${API_BASE}${path}" || true)"
  echo "$code"
}

wait_for_api() {
  local elapsed=0
  while [[ "$elapsed" -lt "$START_TIMEOUT_SEC" ]]; do
    if [[ "$(endpoint_status "/health")" == "200" ]]; then
      return 0
    fi
    sleep 1
    elapsed=$((elapsed + 1))
  done
  return 1
}

ensure_api_running() {
  if [[ "$(endpoint_status "/health")" == "200" ]]; then
    echo "API already running at ${API_BASE}"
    return 0
  fi

  cd "$ROOT_DIR"
  MIXZ_POSTGRES_DSN="$MIXZ_POSTGRES_DSN" .venv/bin/uvicorn apps.api.main:app --host "$API_HOST" --port "$API_PORT" >"$LOG_FILE" 2>&1 &
  api_pid="$!"
  started_by_script=1

  if ! wait_for_api; then
    echo "ERROR: API failed to become healthy within ${START_TIMEOUT_SEC}s"
    echo "See log: $LOG_FILE"
    exit 1
  fi

  echo "API started by self-check at ${API_BASE}"
}

check_endpoint() {
  local name="$1"
  local path="$2"
  local code
  code="$(endpoint_status "$path")"
  if [[ "$code" == "200" ]]; then
    echo "PASS  ${name} ${path} -> ${code}"
    return 0
  fi
  echo "FAIL  ${name} ${path} -> ${code}"
  return 1
}

ensure_api_running

failures=0
check_endpoint "health" "/health" || failures=$((failures + 1))
check_endpoint "meta" "/meta" || failures=$((failures + 1))
check_endpoint "papers" "/papers?page=1&page_size=5" || failures=$((failures + 1))
check_endpoint "batches" "/batches?page=1&page_size=5" || failures=$((failures + 1))
check_endpoint "archive" "/archive?page=1&page_size=5" || failures=$((failures + 1))
check_endpoint "stats" "/stats" || failures=$((failures + 1))

if [[ "$failures" -gt 0 ]]; then
  echo "SELF-CHECK FAILED: ${failures} endpoint(s) failed"
  exit 1
fi

echo "SELF-CHECK PASSED: all endpoints returned 200"
