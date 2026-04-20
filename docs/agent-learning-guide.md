# MIXZ Agent Learning Guide (Hermes / OpenClaw)

This document is a practical handoff for coding agents working on MIXZ.
It focuses on architecture, invariants, safe workflows, and verification.

## 1. Project Purpose

MIXZ is a literature crawl + enrichment + static-site publishing pipeline.

Two runtime tracks currently coexist:

- Legacy-compatible static pipeline centered on `scripts/mixz_daily_crawl.py`
- Modularized app packages under `apps/` and `packages/`

The migration is incremental. Do not assume all runtime paths are cut over at once.

## 2. Source Of Truth Rules

Respect these rules before editing:

1. SQLite remains the static-site source of truth at `site/data/papers.db` for the renderer workflow.
2. Rendered pages (`site/index.html`, `site/archive.html`, `site/papers/*.html`) are derived artifacts.
3. PostgreSQL schema and Alembic exist for the API and migration path.
4. Canonical batch assignment is first-discovery based and should stay stable.

If your change conflicts with any of the above, stop and re-check design intent.

## 3. Where Things Live

- Crawl + compatibility pipeline: `scripts/mixz_daily_crawl.py`
- Worker entrypoint: `apps/worker/main.py`
- API entrypoint: `apps/api/main.py`
- Domain logic: `packages/domain/`
- Crawler clients: `packages/crawler/`
- Rendering bridge + templates: `packages/rendering/`
- Storage and Postgres models/services: `packages/storage/`
- Pipeline orchestration: `packages/worker/pipeline.py`
- Migrations: `infra/migrations/` + `alembic.ini`
- Static output: `site/`

## 4. High-Value Commands

Install deps:

```bash
pip install -r requirements.txt
```

Render only (no network crawl):

```bash
python3 scripts/mixz_daily_crawl.py --render-only
```

Full crawl + enrich + render:

```bash
python3 scripts/mixz_daily_crawl.py
```

Run modular worker:

```bash
python3 -m apps.worker.main --render-only
```

API local run:

```bash
export MIXZ_POSTGRES_DSN='postgresql+psycopg://user:password@host:5432/db'
.venv/bin/uvicorn apps.api.main:app --host 127.0.0.1 --port 8000
```

API smoke bundle:

```bash
bash scripts/mixz_self_check.sh
```

## 5. Verification Checklist (Agent)

After meaningful changes, verify at least:

1. Pipeline command exits successfully.
2. `site/data/stats.json` is updated and internally consistent.
3. `site/index.html` and `site/archive.html` contain expected sections and links.
4. At least one detail page in `site/papers/*.html` contains expected blocks (`Abstract`, `Batch History`).
5. API health route returns 200 if API-related code changed.

If `sqlite3` CLI is unavailable, use Python snippets with the stdlib `sqlite3` module.

## 6. Known Pitfalls

1. DOI route in FastAPI must use `/papers/{doi:path}`; plain `{doi}` breaks on slashes.
2. Missing `MIXZ_POSTGRES_DSN` should return explicit 503 behavior in API paths.
3. Local development should prefer writing under `site/`, not `/var/www/*`.
4. In some environments, `rg` and `sqlite3` CLIs are missing. Fallback to `grep` + Python.
5. Protocol pages under `site/protocols/*.html` may need direct edits if they are not template-generated.
6. Docker group changes may require re-login; short-term workaround is `sg docker -c '...'`.

## 7. Safe Edit Strategy

When operating as Hermes/OpenClaw/coding agent:

1. Read relevant files first; do not assume migration status.
2. Make the smallest patch that satisfies the request.
3. Avoid broad refactors unless asked.
4. Never revert user changes you did not author.
5. Validate outcomes with runnable commands.
6. Summarize exactly what changed and what was verified.

## 8. Suggested Task Prompts For Agents

Use prompts like the following to get reliable outcomes:

### Prompt A: Render Regression Check

```text
Run MIXZ in --render-only mode, verify index/archive/detail outputs, and report any regressions with file paths.
```

### Prompt B: Full Pipeline Validation

```text
Run a full crawl, summarize source retries/failures, then verify stats.json and generated pages are consistent with DB counts.
```

### Prompt C: API Smoke + Data Path

```text
Use MIXZ_POSTGRES_DSN, start the API, run /health /meta /papers /stats smoke tests, and report failures with root cause.
```

### Prompt D: Migration Safety Review

```text
Review recent changes for violations of canonical batch first-discovery assignment and report any behavior regressions.
```

## 9. Push Discipline

Before pushing:

1. Run `git status --short --branch`.
2. Ensure docs, code, and generated outputs in the commit are intentional.
3. Use a commit message that states scope clearly.
4. Push to the correct branch and report resulting commit hash.

---

Last updated: 2026-04-20