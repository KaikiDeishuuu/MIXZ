#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG='/root/.openclaw/workspace/logs/mixz_crawl.log'
LOCK='/tmp/mixz_crawl.lock'

mkdir -p /root/.openclaw/workspace/logs

if [[ -x "$ROOT_DIR/.venv/bin/python" ]]; then
  PY="$ROOT_DIR/.venv/bin/python"
else
  PY='/usr/bin/python3'
fi

# Cron does not reliably source interactive shell init files. Load nvm explicitly so
# the pipeline can find npm/node during Astro builds.
if [[ -s "$HOME/.nvm/nvm.sh" ]]; then
  # shellcheck disable=SC1090
  . "$HOME/.nvm/nvm.sh"
  nvm use --silent >/dev/null 2>&1 || true
fi
export PATH="$HOME/.nvm/versions/node/v24.14.0/bin:${PATH:-}"

{
  echo "[$(date '+%F %T %z')] START mixz pipeline $*"
  flock -n 9 || { echo "[$(date '+%F %T %z')] SKIP: lock busy"; exit 0; }
  cd "$ROOT_DIR"
  "$PY" -m apps.worker.main "$@"
  echo "[$(date '+%F %T %z')] DONE"
} 9>"$LOCK" >> "$LOG" 2>&1
