#!/usr/bin/env bash
set -euo pipefail
SCRIPT='/root/.openclaw/workspace/scripts/mixz_daily_crawl.py'
LOG='/root/.openclaw/workspace/logs/mixz_crawl.log'
LOCK='/tmp/mixz_crawl.lock'
{
  echo "[$(date '+%F %T %z')] START mixz crawl"
  flock -n 9 || { echo "[$(date '+%F %T %z')] SKIP: lock busy"; exit 0; }
  /usr/bin/python3 "$SCRIPT"
  echo "[$(date '+%F %T %z')] DONE"
} 9>"$LOCK" >> "$LOG" 2>&1
