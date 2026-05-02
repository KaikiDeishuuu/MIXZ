# Mixz Literature Pipeline + Astro Static Site

Modern production-grade literature crawler, JSON exporter, Astro static frontend, and FastAPI read API for <https://mixz.wulab.tech>.

## Current Architecture

Mixz is **not** a Next.js app. The production path is:

```text
Crossref / OpenAlex / Semantic Scholar
        ↓
Python worker: apps.worker.main
        ↓
SQLite canonical DB: site/data/papers.db
        ↓
JSON export: site/data/articles/*.json + site/data/stats.json
        ↓
Astro frontend: apps/web
        ↓
Static artifact deployed to /var/www/mixz
        ↓
Nginx serves static pages; /api/* proxies to FastAPI on 127.0.0.1:8000
```

## Invariants

- `site/data/papers.db` is the single source of truth.
- `site/data/articles/*.json` is the frontend contract derived from SQLite.
- `apps/web/dist/` and `/var/www/mixz` are disposable build/deploy artifacts.
- Astro never connects to SQLite/PostgreSQL directly; it only reads exported JSON.
- FastAPI is optional for dynamic read endpoints; static pages must work even if the API is down.
- There must be only one production worker entrypoint: `python3 -m apps.worker.main`.

## Project Structure

```text
mixz/
├── apps/
│   ├── api/                    # FastAPI read API
│   ├── worker/                 # Python worker entrypoint
│   └── web/                    # Astro static frontend
├── packages/
│   ├── crawler/                # Crossref/OpenAlex/Semantic Scholar clients
│   ├── domain/                 # Config, models, text utilities
│   ├── rendering/              # JSON export helpers only
│   ├── storage/                # SQLite + optional PostgreSQL storage layers
│   └── worker/                 # Crawl/export/build/deploy orchestration
├── scripts/
│   ├── mixz_daily_crawl.py     # Thin compatibility wrapper to apps.worker.main
│   ├── mixz_daily_crawl.sh     # Cron/system wrapper
│   ├── deploy_astro_site.sh    # Deploy apps/web/dist + canonical data to /var/www/mixz
│   ├── mixz_self_check.sh      # API smoke check
│   └── mixz_rollback_guard.sh  # Data/UI drift guard
├── site/
│   └── data/
│       ├── papers.db           # SQLite canonical DB, gitignored
│       ├── stats.json
│       └── articles/           # JSON contract consumed by Astro
├── infra/
├── docs/
├── requirements.txt
└── package.json
```

## Setup

Python dependencies:

```bash
pip install -r requirements.txt
```

Astro dependencies:

```bash
npm --prefix apps/web install
```

## Main Commands

Render/export/build/deploy from existing DB:

```bash
python3 -m apps.worker.main --render-only
```

Full daily run:

```bash
python3 -m apps.worker.main
```

Compatibility command, kept only to avoid breaking old invocations:

```bash
python3 scripts/mixz_daily_crawl.py --render-only
```

Build frontend only:

```bash
npm --prefix apps/web run build
```

Deploy already-built Astro artifact:

```bash
bash scripts/deploy_astro_site.sh
```

Self-check:

```bash
bash scripts/mixz_self_check.sh
bash scripts/mixz_rollback_guard.sh
python3 scripts/check_article_normalization.py
python3 scripts/check_crawl_selection.py
```

## Production Runtime

- Static root: `/var/www/mixz`
- API service: `mixz-api.service`
- API local URL: `http://127.0.0.1:8000`
- Nginx routes:
  - `/` static Astro site
  - `/archive` static pretty route
  - `/protocols` static pretty route
  - `/papers/*.html` static detail pages
  - `/api/*` reverse proxy to FastAPI

Cron currently calls `scripts/mixz_daily_crawl.sh`, which calls the canonical worker entrypoint.

## API

FastAPI provides read endpoints:

- `GET /health`
- `GET /meta`
- `GET /papers`
- `GET /papers/{doi:path}`
- `GET /batches`
- `GET /archive`
- `GET /stats`

The API can fall back to canonical SQLite for public read paths if remote PostgreSQL is unavailable.

## PostgreSQL Migration Path

PostgreSQL/Alembic files remain for future migration and analytics, but production static generation currently treats SQLite as canonical. Do not make Postgres a hard dependency for the public static site.

## Notes for Agents

Read `docs/agent-learning-guide.md` and the `mixz-literature-pipeline` Hermes skill before changing crawler, data, export, or deploy behavior.

**Last updated:** 2026-05-02 — Astro migration and old static/Jinja frontend removal.
