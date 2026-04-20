#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "${MIXZ_POSTGRES_DSN:-}" ]]; then
  echo "ERROR: MIXZ_POSTGRES_DSN is not set"
  echo "Hint: export MIXZ_POSTGRES_DSN='postgresql+psycopg://user:pass@host:5432/db'"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker command not found"
  exit 1
fi

cd "$ROOT_DIR"
docker compose up -d --build

echo "MIXZ services started."
echo "Static site: http://localhost:${MIXZ_WEB_PORT:-8080}"
echo "API health:  http://localhost:${MIXZ_WEB_PORT:-8080}/api/health"
