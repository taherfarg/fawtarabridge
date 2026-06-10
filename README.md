# FawtaraBridge

UAE e-invoicing compliance platform for SMEs. Converts SME invoice data into valid
PINT-AE (UBL 2.1) XML and transmits it through an Accredited Service Provider (ASP)
over the Peppol 5-corner network.

See [docs/PRD.md](docs/PRD.md) for the full product requirements and
[docs/DECISIONS.md](docs/DECISIONS.md) for the running architecture-decision log.

## Stack

- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2 + Alembic, Pydantic v2, PostgreSQL 16, Celery + Redis
- **Frontend:** React 18 + Vite + TypeScript, TailwindCSS, react-i18next (Arabic-first RTL) — lands in M6
- **Local dev:** Docker Compose (db, redis, api, worker)

## Local development

```bash
# 1. Start everything (db + redis + api + worker)
docker compose up --build

# API: http://localhost:8000  (docs at /docs)
# Postgres: localhost:5433 (user/pass/db: fawtara)  — app role: fawtara_app
# Redis: localhost:6380
```

Backend-only workflow (host Python, db/redis from compose):

```bash
docker compose up -d db redis
cd backend
uv sync                                   # creates .venv with Python 3.12
uv run alembic upgrade head               # uses FAWTARA_ADMIN_DATABASE_URL
uv run uvicorn app.main:app --reload
```

## Tests, lint, types

```bash
cd backend
uv run pytest --cov=app                   # needs db container running (port 5433)
uv run ruff check .
uv run ruff format --check .
uv run mypy app
```

Tests create and migrate a disposable `fawtara_test` database; they never touch the
dev database. Override connection via `TEST_DB_HOST` / `TEST_DB_PORT` /
`TEST_DB_ADMIN_USER` / `TEST_DB_ADMIN_PASSWORD` (CI sets port 5432).

## Multi-tenancy model (M1)

- Every tenant-owned table carries `tenant_id` and is protected by PostgreSQL
  row-level security (`ENABLE` + `FORCE`), keyed on per-transaction GUCs
  `app.current_tenant_id` / `app.current_user_id` set via `set_config(..., true)`.
- The application connects as `fawtara_app`, a non-superuser role without
  `BYPASSRLS`. Migrations run as the `fawtara` admin role.
- On top of RLS, the repository layer (`app/repositories`) requires an explicit
  `tenant_id` for every query — defense in depth.
