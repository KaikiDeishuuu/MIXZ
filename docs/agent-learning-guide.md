# MIXZ Agent Learning Guide (Hermes / OpenClaw)

This document is a practical handoff for coding agents working on MIXZ after the Astro cutover.

## 1. Project Purpose

MIXZ is a literature crawl + enrichment + JSON export + Astro static-site publishing pipeline with an optional FastAPI read API.

There is no longer a production legacy static/Jinja runtime track. Old generated HTML and old `mixz-site` paths must not be reintroduced.

## 2. Source Of Truth Rules

Respect these rules before editing:

1. SQLite remains the canonical source of truth at `site/data/papers.db`.
2. JSON exports under `site/data/articles/` and `site/data/stats.json` are derived from SQLite and are the frontend contract.
3. Astro under `apps/web/` builds static pages from JSON exports only.
4. `apps/web/dist/` and `/var/www/mixz` are disposable build/deploy artifacts.
5. PostgreSQL schema and Alembic may exist for future/API work, but production static generation must not hard-depend on remote Postgres.
6. Canonical batch assignment is first-discovery based and should stay stable.

If your change conflicts with any of the above, stop and re-check design intent.

## 3. Where Things Live

- Canonical worker entrypoint: `apps/worker/main.py`
- Compatibility wrapper only: `scripts/mixz_daily_crawl.py`
- Cron wrapper: `scripts/mixz_daily_crawl.sh`
- API entrypoint: `apps/api/main.py`
- Astro frontend: `apps/web/`
- Frontend JSON contract: `site/data/articles/*.json` + `site/data/stats.json`
- Domain logic: `packages/domain/`
- Crawler clients: `packages/crawler/`
- JSON export helpers: `packages/rendering/`
- Storage and Postgres models/services: `packages/storage/`
- Pipeline orchestration: `packages/worker/pipeline.py`
- Deploy helper: `scripts/deploy_astro_site.sh`
- Production static root: `/var/www/mixz`

## 4. High-Value Commands

Install deps:

```bash
pip install -r requirements.txt
npm --prefix apps/web install
```

Render/export/build/deploy from existing DB:

```bash
python3 -m apps.worker.main --render-only
```

Full crawl + enrich + export + build + deploy:

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

API smoke bundle:

```bash
bash scripts/mixz_self_check.sh
```

Full local regression bundle:

```bash
python3 -m py_compile apps/api/service.py packages/rendering/static_site.py packages/worker/pipeline.py scripts/mixz_daily_crawl.py
npm --prefix apps/web run build
python3 scripts/check_article_normalization.py
python3 scripts/check_crawl_selection.py
bash scripts/mixz_rollback_guard.sh
```

## 5. Verification Checklist (Agent)

After meaningful changes, verify at least:

1. `python3 -m apps.worker.main --render-only` exits successfully.
2. `site/data/stats.json` and `site/data/articles/archive_summary.json` are internally consistent.
3. `apps/web/dist/index.html`, `apps/web/dist/archive/index.html`, `apps/web/dist/protocols/index.html`, and at least one `apps/web/dist/papers/*.html` exist after build.
4. Live pages load: `/`, `/archive`, `/protocols`, one `/papers/*.html` route.
5. API health/read routes return 200 if API-related code changed.
6. No references to old `mixz-site` or `/root/.openclaw/workspace/scripts/mixz_*` paths remain in active source, cron, or deploy scripts.

If `sqlite3` CLI is unavailable, use Python snippets with the stdlib `sqlite3` module.

## 6. Known Pitfalls

1. DOI route in FastAPI must use `/papers/{doi:path}`; plain `{doi}` breaks on slashes.
2. Static pages must remain usable even if remote PostgreSQL/Supabase is unavailable.
3. Local development should prefer source changes in `apps/web/` and data exports under `site/data/`, not manual edits in `/var/www/*`.
4. In some environments, `rg` and `sqlite3` CLIs are missing. Fallback to Python.
5. Old generated HTML under `site/index.html`, `site/archive.html`, `site/papers/`, or `site/protocols/` is intentionally removed. Do not resurrect it.
6. `scripts/mixz_daily_crawl.py` must stay a thin wrapper around `apps.worker.main`; do not add crawler/render logic there.
7. Rollback guard can still use legacy marker names like `protocol-grid` only as negative detection signals.

## 7. Safe Edit Strategy

When operating as Hermes/OpenClaw/coding agent:

1. Read relevant files first; do not assume migration status.
2. Keep SQLite → JSON export → Astro build → deploy as the only static publishing path.
3. Avoid broad refactors unless asked.
4. Never revert user changes you did not author.
5. Validate outcomes with runnable commands and live route checks.
6. Summarize exactly what changed and what was verified.

## 8. Suggested Task Prompts For Agents

### Prompt A: Astro Render Regression Check

```text
Run MIXZ in --render-only mode, verify JSON exports, Astro build output, and live / /archive /protocols /papers route health.
```

### Prompt B: Full Pipeline Validation

```text
Run a full crawl, summarize source retries/failures, then verify stats.json, archive_summary.json, Astro pages, and DB counts are consistent.
```

### Prompt C: API Smoke + Data Path

```text
Start or use the running API, run /health /meta /papers /batches /archive /stats smoke tests, and report failures with root cause.
```

### Prompt D: Migration Safety Review

```text
Review recent changes for violations of SQLite SSOT, JSON contract stability, Astro-only frontend publishing, and canonical batch first-discovery assignment.
```

## 9. Push Discipline

Before pushing:

1. Run `git status --short --branch`.
2. Ensure docs, code, and generated/data outputs in the commit are intentional.
3. Use git author name `Hikki` for MIXZ commits.
4. Use a commit message that states scope clearly.
5. Push to the correct branch and report resulting commit hash.

---

Last updated: 2026-05-02 — Astro cutover and old static/Jinja frontend removal.
