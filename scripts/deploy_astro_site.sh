#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/.openclaw/workspace/mixz"
WEB_DIST="$ROOT/apps/web/dist"
TARGET="/var/www/mixz"

if [[ ! -d "$WEB_DIST" ]]; then
  echo "Astro dist not found: $WEB_DIST" >&2
  exit 1
fi

mkdir -p "$TARGET"
# Deploy Astro artifact atomically enough for this single-host setup without rsync.
find "$TARGET" -mindepth 1 -maxdepth 1 ! -name 'data' -exec rm -rf {} +
cp -a "$WEB_DIST/." "$TARGET/"

# Keep canonical static data and SQLite available under the same public paths.
rm -rf "$TARGET/data/articles"
mkdir -p "$TARGET/data"
cp -a "$ROOT/site/data/articles" "$TARGET/data/articles"
cp -f "$ROOT/site/data/stats.json" "$TARGET/data/stats.json"
cp -f "$ROOT/site/data/papers.db" "$TARGET/data/papers.db"

# Astro file-format emits archive.html/protocols.html; Nginx pretty routes expect directories.
if [[ -f "$TARGET/archive.html" ]]; then
  mkdir -p "$TARGET/archive"
  cp -f "$TARGET/archive.html" "$TARGET/archive/index.html"
fi
if [[ -f "$TARGET/protocols.html" ]]; then
  mkdir -p "$TARGET/protocols"
  cp -f "$TARGET/protocols.html" "$TARGET/protocols/index.html"
fi

# Preserve WeCom verification file served by Nginx config.
printf '%s' 'FlipnvaLPlSkTdT0' > "$TARGET/WW_verify_FlipnvaLPlSkTdT0.txt"

echo "Astro site deployed to $TARGET"
