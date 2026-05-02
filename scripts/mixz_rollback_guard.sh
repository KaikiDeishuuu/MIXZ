#!/usr/bin/env bash
set -euo pipefail

LIVE_URL="${MIXZ_GUARD_LIVE_URL:-https://mixz.wulab.tech/}"
PROTOCOLS_URL="${MIXZ_GUARD_PROTOCOLS_URL:-https://mixz.wulab.tech/protocols}"
LOG="${MIXZ_GUARD_LOG:-/root/.openclaw/workspace/logs/mixz_rollback_guard.log}"
PIPELINE_SCRIPT="/root/.openclaw/workspace/mixz/scripts/mixz_daily_crawl.sh"
LOCK="/tmp/mixz_rollback_guard.lock"
CANONICAL_SUMMARY="/root/.openclaw/workspace/mixz/site/data/articles/archive_summary.json"
PROD_SUMMARY="/var/www/mixz/data/articles/archive_summary.json"

mkdir -p /root/.openclaw/workspace/logs

count_marker() {
  local marker="$1"
  local html="$2"
  printf "%s" "$html" | { grep -o "$marker" 2>/dev/null || true; } | wc -l | tr -d ' '
}

json_field() {
  local path="$1"
  local field="$2"
  python3 - "$path" "$field" <<'PY'
import json, sys
path, field = sys.argv[1:3]
try:
    with open(path, encoding='utf-8') as f:
        data = json.load(f)
    value = data
    for part in field.split('.'):
        value = value.get(part) if isinstance(value, dict) else None
    print('' if value is None else value)
except Exception:
    print('')
PY
}

{
  echo "[$(date '+%F %T %z')] START rollback guard"
  flock -n 9 || { echo "[$(date '+%F %T %z')] SKIP: guard lock busy"; exit 0; }

  live_html="$(curl -fsS -A 'Mozilla/5.0 MixzRollbackGuard' "$LIVE_URL")"
  protocols_html="$(curl -fsSL -A 'Mozilla/5.0 MixzRollbackGuard' "$PROTOCOLS_URL")"
  article_card_count="$(count_marker 'article-card' "$live_html")"
  legacy_protocol_grid_count="$(count_marker 'protocol-grid' "$live_html")"
  protocol_library_count="$(count_marker 'Protocol Library' "$protocols_html")"

  canonical_latest="$(json_field "$CANONICAL_SUMMARY" latest_batch_id)"
  prod_latest="$(json_field "$PROD_SUMMARY" latest_batch_id)"
  canonical_total="$(json_field "$CANONICAL_SUMMARY" total_articles)"
  prod_total="$(json_field "$PROD_SUMMARY" total_articles)"

  echo "[$(date '+%F %T %z')] MARKERS article-card=${article_card_count} legacy-protocol-grid=${legacy_protocol_grid_count} protocol-library=${protocol_library_count} canonical_latest=${canonical_latest} prod_latest=${prod_latest} canonical_total=${canonical_total} prod_total=${prod_total}"

  needs_heal=0
  # Current UI expectation: Astro homepage has article cards; /protocols has protocol library;
  # the previous embedded protocol-grid marker should not come back.
  if [[ "$article_card_count" -eq 0 || "$legacy_protocol_grid_count" -gt 0 || "$protocol_library_count" -eq 0 ]]; then
    needs_heal=1
  fi
  # Data-source drift expectation: production JSON must match canonical repo export.
  # This catches stale compatibility paths rendering from anything except canonical SQLite.
  if [[ -n "$canonical_latest" && "$canonical_latest" != "$prod_latest" ]]; then
    needs_heal=1
  fi
  if [[ -n "$canonical_total" && "$canonical_total" != "$prod_total" ]]; then
    needs_heal=1
  fi

  if [[ "$needs_heal" -eq 1 ]]; then
    echo "[$(date '+%F %T %z')] ROLLBACK_OR_DATA_DRIFT_DETECTED -> running self-heal render"
    /bin/bash "$PIPELINE_SCRIPT" --render-only

    healed_html="$(curl -fsS -A 'Mozilla/5.0 MixzRollbackGuard' "$LIVE_URL")"
    healed_protocols_html="$(curl -fsSL -A 'Mozilla/5.0 MixzRollbackGuard' "$PROTOCOLS_URL")"
    healed_article_card="$(count_marker 'article-card' "$healed_html")"
    healed_legacy_protocol="$(count_marker 'protocol-grid' "$healed_html")"
    healed_protocol_library="$(count_marker 'Protocol Library' "$healed_protocols_html")"
    healed_prod_latest="$(json_field "$PROD_SUMMARY" latest_batch_id)"
    healed_prod_total="$(json_field "$PROD_SUMMARY" total_articles)"
    echo "[$(date '+%F %T %z')] POST_HEAL article-card=${healed_article_card} legacy-protocol-grid=${healed_legacy_protocol} protocol-library=${healed_protocol_library} prod_latest=${healed_prod_latest} prod_total=${healed_prod_total}"

    if [[ "$healed_article_card" -eq 0 || "$healed_legacy_protocol" -gt 0 || "$healed_protocol_library" -eq 0 ]]; then
      echo "[$(date '+%F %T %z')] ERROR self-heal did not restore expected UI markers"
      exit 2
    fi
    if [[ -n "$canonical_latest" && "$canonical_latest" != "$healed_prod_latest" ]]; then
      echo "[$(date '+%F %T %z')] ERROR self-heal did not restore latest batch parity"
      exit 3
    fi
    if [[ -n "$canonical_total" && "$canonical_total" != "$healed_prod_total" ]]; then
      echo "[$(date '+%F %T %z')] ERROR self-heal did not restore total article parity"
      exit 4
    fi
  else
    echo "[$(date '+%F %T %z')] OK no rollback or data drift signature"
  fi

  echo "[$(date '+%F %T %z')] DONE"
} 9>"$LOCK" >> "$LOG" 2>&1
