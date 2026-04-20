# Mixz Literature Pipeline + Static Site

Modern production-grade literature crawler and static site generator for https://mixz.wulab.tech.

**Core Architecture (2026 rewrite)**:
- **SQLite is Single Source of Truth** (`site/data/papers.db`)
- HTML pages (`index.html`, `archive.html`) are **pure derived views** — regenerated from DB on every run.
- Idempotent by DOI, batch tracking, abstract backfill from multiple sources.
- No more data loss from fragile HTML-only manipulation.

## Features

- Daily Crossref-based crawling focused on immunohistochemistry, microscopy, histology, tissue imaging.
- Smart abstract enrichment (Crossref → OpenAlex → Semantic Scholar) with quality filtering.
- Beautiful static site with:
  - Latest batch + collapsible historical batches
  - Real-time search + journal filters
  - Expandable abstracts
  - Protocol Library tab
  - Full archive page
- Prune redundant no-change batches automatically.
- Dual deployment: workspace source + production (`/var/www/mixz/`)

## Project Structure

```
mixz/
├── scripts/                    # Pipeline scripts (main entrypoint)
│   ├── mixz_daily_crawl.py     # Core v2 pipeline (crawl, enrich, render, stats)
│   ├── mixz_daily_crawl.sh     # Cron wrapper
│   ├── mixz_backfill_abstracts.py
│   └── ...
├── site/                       # Static site (source of truth for templates)
│   ├── index.html
│   ├── archive.html
│   ├── protocols/
│   ├── data/
│   │   ├── papers.db           # SQLite SSOT (gitignored by default)
│   │   └── stats.json
│   └── feed.xml
├── docs/                       # Additional documentation
├── .gitignore
└── README.md
```

## Quick Start

1. **Install dependencies** (if any — mostly stdlib):
   ```bash
   pip install -r requirements.txt  # (create if needed)
   ```

2. **Initialize DB and render**:
   ```bash
   cd scripts
   python3 mixz_daily_crawl.py --render-only
   ```

3. **Full daily run** (crawl + enrich + render):
   ```bash
   python3 mixz_daily_crawl.py
   ```

4. **Clean history** (remove duplicate no-change batches):
   ```bash
   python3 mixz_daily_crawl.py --prune-redundant-batches --render-only
   ```

5. **Deploy to production**:
   The script automatically syncs to `/var/www/mixz/` (or configure paths in script).

## Development

- Edit `scripts/mixz_daily_crawl.py` — all rendering logic, templates, and DB schema live there.
- Modify `JOURNALS` list and `QUERY` at the top for different focus areas.
- Run with `--render-only` during local debugging to avoid hitting APIs.
- After changes, run the script and verify both `site/` and production copy.

See `mixz-literature-pipeline` skill in Hermes for detailed architecture, lessons learned, verification checklist, and pitfalls.

## License

MIT. Feel free to adapt for your own literature/static content sites.

---

**Last updated:** 2026-04-20 (after pruning redundant batches and UI/stats improvements)
