# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial Alembic migration (`84dc31ec57af_initial_schema`) creating the
  `users`, `workouts`, `recovery_scores`, and `training_plans` tables.

### Fixed
- Backend startup crash from a name-shadowing bug in `schemas/workout.py`: a
  field named `date` annotated `date | None = None` shadowed the imported
  `date` type, raising `TypeError` at import. The type is now imported under an
  alias (`date_`); the same guard was applied in `schemas/recovery.py`.
- `/auth/register` 500 from the passlib/bcrypt incompatibility: pinned
  `bcrypt==4.0.1`, since passlib 1.7.4 breaks on bcrypt >= 4.1.

### Planned
- Encryption of OAuth tokens at rest in `core/security.py`.
- Expanded test coverage (recovery, AI, auth-failure, and user-isolation cases).
- Frontend "Connect Strava / WHOOP" buttons wired to the authorize endpoints.

### Known issues
- OAuth access/refresh tokens are currently stored in plaintext.

## [0.1.0] - 2026-06-02

Initial scaffold: a working full-stack skeleton with real (non-placeholder)
integrations, pending the first DB migration.

### Added

**Backend (FastAPI + async SQLAlchemy 2.0)**
- App factory in `app/main.py` with CORS and a `/health` endpoint.
- Config via Pydantic `BaseSettings` reading from `.env` (`core/config.py`).
- Async database engine + session factory using asyncpg (`core/database.py`).
- JWT auth helpers and password hashing with bcrypt (`core/security.py`).
- Dependency-injection providers `get_db` and `get_current_user`
  (`dependencies.py`).
- ORM models: `User`, `Workout`, `RecoveryScore`, `TrainingPlan`.
- Pydantic schemas for users, workouts, recovery, and training plans.
- **Auth router**: register, login, and Strava/WHOOP OAuth authorize +
  callback endpoints.
- **Workouts router**: list, create, get, delete (all scoped to the current
  user), plus `POST /workouts/sync`.
- **Recovery router**: read/write daily recovery records.
- **AI router**: `/ai/insights` and `/ai/training-plan` backed by Claude.
- **Services**:
  - `strava.py` — OAuth code exchange, automatic token refresh, activity sync.
  - `whoop.py` — OAuth (PKCE) code exchange, recovery/sleep sync.
  - `sync.py` — orchestrates a full multi-source sync per user.
  - `claude.py` — coaching insights and weekly training-plan generation.
- Alembic environment configured for the async engine (`alembic/env.py`).
- Initial test scaffold: `conftest.py` fixtures and `test_workouts.py`.

**Frontend (Next.js 15 + React 19)**
- App Router pages: dashboard, workouts, recovery, AI, and login/register.
- Typed API client (one file per backend router) over a shared HTTP helper.
- `AuthContext` for client-side auth state and a React Query provider.
- Reusable UI (Card, Button) and a sidebar layout.
- Tailwind CSS configured.

**Infrastructure**
- `docker-compose.yml` running Postgres 16, the FastAPI backend (hot-reload),
  and the Next.js frontend.
- Backend `Dockerfile` (Python 3.12-slim).
- `.env.example` documenting all required environment variables.

### Notes
- Backend is fully asynchronous end to end (async SQLAlchemy + `httpx.AsyncClient`).
- Designed multi-user from the start: every query filters by `user_id`.

[Unreleased]: https://github.com/Land784/fitness-platform/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Land784/fitness-platform/releases/tag/v0.1.0
