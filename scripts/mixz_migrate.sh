#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_ALEMBIC="$ROOT_DIR/.venv/bin/alembic"

if [[ -z "${MIXZ_POSTGRES_DSN:-}" ]]; then
  echo "ERROR: MIXZ_POSTGRES_DSN is not set"
  echo "Hint: export MIXZ_POSTGRES_DSN='postgresql+psycopg://user:pass@host:5432/mixz'"
  exit 1
fi

if [[ -x "$VENV_ALEMBIC" ]]; then
  ALEMBIC_BIN="$VENV_ALEMBIC"
else
  ALEMBIC_BIN="alembic"
fi

cd "$ROOT_DIR"
"$ALEMBIC_BIN" upgrade head

echo "Migration completed: head"
