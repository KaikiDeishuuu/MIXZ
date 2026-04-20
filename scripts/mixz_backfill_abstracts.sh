#!/usr/bin/env bash
set -euo pipefail
SCRIPT='/root/.openclaw/workspace/scripts/mixz_backfill_abstracts.py'
LOG='/root/.openclaw/workspace/logs/mixz_abstract_backfill.log'
LOCK='/tmp/mixz_abstract_backfill.lock'
mkdir -p /root/.openclaw/workspace/logs
{
  echo "[$(date '+%F %T %z')] START abstract backfill"
  flock -n 9 || { echo "[$(date '+%F %T %z')] SKIP: lock busy"; exit 0; }
  /usr/bin/python3 "$SCRIPT"
  echo "[$(date '+%F %T %z')] DONE"
} 9>"$LOCK" >> "$LOG" 2>&1
