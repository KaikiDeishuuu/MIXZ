# Mixz Literature Pipeline + Static Site

Modern production-grade literature crawler and static site generator for <https://mixz.wulab.tech>.

## Migration Status (Incremental)

This repository has started a phased migration toward:

- Backend: FastAPI
- Worker jobs: modular Python services
- Data layer: migration-ready schema evolution path
- Frontend migration: planned in later phases

Current state in Phase 1:

- Existing script `scripts/mixz_daily_crawl.py` remains available for compatibility.
- New modular worker pipeline is available at `apps/worker/main.py`.
- New API scaffold is available at `apps/api/main.py` (`/health`, `/meta`).
- SQLite remains the active database in this phase.
- Existing HTML output remains unchanged.

Current state in Phase 2:

- PostgreSQL target schema is implemented with SQLAlchemy 2.0 models.
- Alembic migration scaffold + initial revision are added.
- Canonical batch data model is introduced across: crawl_runs, observation_events, canonical_batches, canonical_batch_memberships, papers, paper_sources.
- Rule support: a paper is assigned to canonical batch at first discovery and kept stable afterward.
- Runtime remains backward compatible with Phase 1 SQLite pipeline until API/worker cutover.

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

```text
mixz/
├── apps/
│   ├── api/
│   │   └── main.py             # FastAPI scaffold (Phase 1)
│   └── worker/
│       └── main.py             # New modular worker entrypoint
├── packages/
│   ├── domain/                 # Config + core models + shared text logic
│   ├── crawler/                # External source clients (Crossref/OpenAlex/S2)
│   ├── storage/                # SQLite repository layer
│   ├── rendering/              # Static renderer compatibility adapter
│   └── worker/                 # Crawl orchestration pipeline
├── infra/
│   ├── migrations/             # Reserved for Alembic migrations (Phase 2)
│   └── docker/                 # Docker build/runtime configs
├── docker-compose.yml          # API + Nginx runtime orchestration
├── alembic.ini                 # Alembic config for PostgreSQL migrations
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

Install dependencies:

```bash
pip install -r requirements.txt
```

Initialize DB and render:

```bash
cd scripts
python3 mixz_daily_crawl.py --render-only
```

Or use the new modular worker entrypoint:

```bash
cd ..
python3 -m apps.worker.main --render-only
```

Full daily run (crawl + enrich + render):

```bash
python3 mixz_daily_crawl.py
```

New modular entrypoint equivalent:

```bash
python3 -m apps.worker.main
```

Clean history (remove duplicate no-change batches):

```bash
python3 mixz_daily_crawl.py --prune-redundant-batches --render-only
```

Deploy to production:

The script automatically syncs to `/var/www/mixz/` (or configure paths in script).

## Development

- Edit `scripts/mixz_daily_crawl.py` — all rendering logic, templates, and DB schema live there.
- New development target for modular logic is under `packages/`.
- Modify `JOURNALS` list and `QUERY` at the top for different focus areas.
- Run with `--render-only` during local debugging to avoid hitting APIs.
- After changes, run the script and verify both `site/` and production copy.

### API scaffold (Phase 1)

Install dependencies and run:

```bash
pip install -r requirements.txt
uvicorn apps.api.main:app --reload
```

Available endpoints now:

- `GET /health`
- `GET /meta`
- `GET /papers/{doi:path}`

### PostgreSQL schema (Phase 2)

Key files:

- `packages/storage/postgres/models.py`
- `packages/storage/postgres/repositories.py`
- `packages/storage/postgres/services.py`
- `infra/migrations/env.py`
- `infra/migrations/versions/20260420_0001_phase2_core_schema.py`

Run migration:

```bash
# 推荐 psycopg DSN；Supabase 等托管库建议启用 SSL
export MIXZ_POSTGRES_DSN='postgresql+psycopg://user:password@localhost:5432/mixz?sslmode=require'
alembic upgrade head
```

注意：如果密码包含 `/`、`@`、`:` 等特殊字符，需要 URL 编码（例如 `/` -> `%2F`）。

Backfill legacy SQLite data into PostgreSQL:

```bash
export MIXZ_POSTGRES_DSN='postgresql+psycopg://user:password@host:5432/db'
.venv/bin/python scripts/mixz_backfill_postgres.py --sqlite-path site/data/papers.db
```

Dry run mode:

```bash
export MIXZ_POSTGRES_DSN='postgresql+psycopg://user:password@host:5432/db'
.venv/bin/python scripts/mixz_backfill_postgres.py --sqlite-path site/data/papers.db --dry-run
```

Notes:

- Phase 2 introduces the new canonical-batch-first schema, but does not force immediate production cutover.
- Existing SQLite path remains available during transition.

### Docker deployment (Phase 6 baseline)

Files:

- `docker-compose.yml`
- `infra/docker/Dockerfile.api`
- `infra/docker/nginx.conf`
- `scripts/mixz_compose_up.sh`
- `scripts/mixz_compose_down.sh`

Start services:

```bash
export MIXZ_POSTGRES_DSN='postgresql+psycopg://user:password@host:5432/db'
export MIXZ_WEB_PORT=8080
bash scripts/mixz_compose_up.sh
```

Stop services:

```bash
bash scripts/mixz_compose_down.sh
```

After startup:

- Static site: `http://localhost:8080`
- API health: `http://localhost:8080/api/health`

Notes:

- Compose uses external PostgreSQL via `MIXZ_POSTGRES_DSN` (for example, Supabase).
- Nginx serves `site/` and proxies `/api/*` to FastAPI.

See `mixz-literature-pipeline` skill in Hermes for detailed architecture, lessons learned, verification checklist, and pitfalls.

## Agent Learning Pack (Hermes / OpenClaw)

For coding agents working in this repository, read:

- `docs/agent-learning-guide.md`

It includes:

- Current migration status and architecture map
- Source-of-truth invariants (SQLite, rendering outputs, canonical batches)
- High-value run/test commands
- Agent-safe edit workflow and verification checklist
- Known pitfalls and ready-to-use task prompt templates

## License

MIT. Feel free to adapt for your own literature/static content sites.

---

**Last updated:** 2026-04-20 (after pruning redundant batches and UI/stats improvements)
