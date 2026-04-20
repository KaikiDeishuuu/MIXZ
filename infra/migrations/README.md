# Phase 2 Migrations (PostgreSQL)

This folder contains Alembic migrations for the new PostgreSQL schema.

## Run migrations

1. Set DSN:

   export MIXZ_POSTGRES_DSN='postgresql+psycopg://user:password@localhost:5432/mixz'

2. Upgrade:

   alembic upgrade head

3. Downgrade one step:

   alembic downgrade -1

## Notes

- SQLite remains active for the Phase 1 runtime path.
- These migrations are introduced in Phase 2 to support canonical batch modeling.
