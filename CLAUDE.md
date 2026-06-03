# AI Fitness Platform — Project Context

## Project overview
Personal AI fitness platform integrating Strava and WHOOP data with Claude for
training plans, recovery insights, and natural language coaching. Full-stack:
FastAPI backend + React frontend. Designed multi-user from the start even if
solo initially.

**This is a learning project.** When writing or modifying code, always explain:
- What the code does and why it's structured that way
- What the relevant concept is (e.g. "this is dependency injection — here's why
  we use it instead of importing the DB session directly")
- Any tradeoffs or alternatives that exist
- What to watch out for or common mistakes with this pattern

Go at a teaching pace. Don't just produce code — produce understanding.

---

## Repo structure
```
fitness-platform/
├── backend/
│   ├── app/
│   │   ├── routers/        # auth.py, workouts.py, recovery.py, ai.py, users.py
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── schemas/        # Pydantic request/response schemas
│   │   ├── services/       # strava.py, whoop.py, claude.py, sync.py
│   │   ├── core/           # config.py, security.py, database.py
│   │   └── main.py
│   ├── alembic/            # DB migrations
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   ├── pages/
│   │   ├── hooks/
│   │   ├── api/            # typed API client (one file per backend router)
│   │   └── types/
│   ├── Dockerfile
│   └── package.json
├── docker-compose.yml
└── .env.example
```

---

## Teaching approach

Before writing any non-trivial code, briefly explain the plan: what files will
be touched, what pattern is being used, and why. For example:

> "We're about to write the Strava OAuth callback. OAuth2 is an authorization
> framework — the user grants our app permission to read their Strava data
> without giving us their password. Here's how the flow works in this codebase..."

After writing code, call out anything that might be surprising or that a
junior developer would commonly get wrong. Use inline comments generously —
not to describe what each line does literally, but to explain *why*.

If there are two valid ways to do something, briefly mention both and explain
why the chosen approach fits this project better.

---

## Commands

### Backend
```bash
cd backend
uvicorn app.main:app --reload          # dev server (port 8000)
pytest                                  # run all tests
pytest tests/test_workouts.py -v       # single test file
alembic upgrade head                   # apply DB migrations
alembic revision --autogenerate -m ""  # generate a new migration from model changes
ruff check . && ruff format .          # lint and auto-format
```

### Frontend
```bash
cd frontend
npm run dev       # dev server (port 5173)
npm run build     # production build
npm run lint      # ESLint
npm run typecheck # tsc --noEmit (type-check without compiling)
```

### Docker
```bash
docker-compose up --build   # build images and start all services
docker-compose down -v      # stop containers and delete volumes (fresh slate)
```

---

## Backend conventions

- **Python 3.12+**. Use type hints on all function signatures and Pydantic
  models — this makes the code self-documenting and catches bugs early.
- **Async by default.** All route handlers and service functions use `async`/
  `await`. Use `httpx.AsyncClient` for external API calls so the server isn't
  blocked waiting on Strava or WHOOP responses.
- **Routers handle HTTP only.** No business logic in routers — they validate
  the request and call a service. Business logic lives in `services/`. This
  separation makes logic easier to test and reuse.
- **Every DB query filters by `user_id`.** No exceptions. This is the
  multi-user data isolation boundary — without it, any user could read any
  other user's data.
- **OAuth tokens** (Strava, WHOOP) are stored encrypted in the DB via
  `core/security.py`. Never in `.env`, never logged, never returned in API
  responses.
- **Secrets** come from `.env` via `core/config.py` (Pydantic `BaseSettings`).
  No hardcoded values anywhere in the codebase.
- Error handling: raise `HTTPException` in routers for HTTP-level errors; raise
  plain Python exceptions in services (routers catch and convert). This keeps
  HTTP concerns out of the business logic layer.
- Use `alembic` for all schema changes — never edit the DB directly or you'll
  lose track of what's in production vs development.

When introducing any of these patterns for the first time, explain them inline
before using them.

---

## Frontend conventions

- **TypeScript strict mode.** No `any`. If a type is genuinely unknown, use
  `unknown` and narrow it with a type guard. This prevents an entire class of
  runtime bugs.
- **Functional components + hooks only.** No class components — the React
  ecosystem has moved fully to hooks and they're simpler to reason about.
- `api/` contains one file per backend router, each exporting typed async
  functions. Components never call `fetch` directly — this keeps network logic
  in one place and makes it easy to mock in tests.
- Use **React Query** (`@tanstack/react-query`) for all server state. Explain
  the concept of "server state vs client state" the first time this comes up —
  it's a key mental model shift for React developers.
- Keep components small. If a component exceeds ~100 lines, explain the
  refactor and split it.

---

## Key data models

- `User` — id, email, hashed_password, strava_token (encrypted), whoop_token
  (encrypted)
- `Workout` — id, user_id, strava_id, date, type, duration_seconds,
  distance_meters, avg_hr, tss (training stress score)
- `RecoveryScore` — id, user_id, date, whoop_recovery_score, hrv_ms,
  resting_hr, sleep_score
- `TrainingPlan` — id, user_id, generated_at, week_start, plan_json (Claude
  output), prompt_summary

When creating or modifying models, explain the SQLAlchemy ORM concepts involved
(relationships, lazy vs eager loading, etc.) rather than just producing code.

---

## External API notes

- **Strava:** base URL `https://www.strava.com/api/v3`. Rate limit: 100
  req/15 min, 1000/day. Token refresh is automatic in `services/strava.py`.
  For integration questions, see `docs/strava-api.md`.
- **WHOOP:** base URL `https://api.prod.whoop.com/developer/v1`. OAuth2 PKCE
  flow. For integration questions, see `docs/whoop-api.md`.
- **Claude:** model id lives in `settings.claude_model` (currently
  `claude-sonnet-4-6`) — don't hardcode it at call sites. Use `AsyncAnthropic`
  with `await` so calls don't block the event loop. Stream responses for the
  chat endpoint; non-streaming for plan generation (streaming not yet wired).
  System prompt lives in `services/claude.py` — always include the user's recent
  workout load and latest recovery score as context.

When touching any external API integration, explain the authentication model
being used (OAuth2, API key, etc.) and why it works the way it does.

---

## Auth flow
JWT-based. `POST /auth/register` and `POST /auth/login` return a bearer token.
All protected routes use `Depends(get_current_user)` from `core/security.py`.
Strava and WHOOP OAuth redirect URIs in dev:
- `http://localhost:8000/auth/strava/callback`
- `http://localhost:8000/auth/whoop/callback`

When first implementing auth, explain JWTs — what they contain, why they're
stateless, and what the tradeoffs are vs session-based auth.

---

## Testing approach
- Write tests before or alongside new features, not after.
- Use `pytest` + `httpx.AsyncClient` with a test Postgres DB (separate from dev).
- Mock external APIs (Strava, WHOOP, Claude) — never hit real endpoints in tests.
  Fixtures live in `tests/conftest.py`.
- Every new endpoint needs at least: happy path, auth failure (401), and
  a user isolation test (confirm user A cannot access user B's data).
- When writing a test, explain what it's testing and why that scenario matters.

---

## Git workflow
- Branch naming: `feat/`, `fix/`, `chore/` prefixes (e.g. `feat/strava-sync`)
- Commit messages: imperative, present tense ("add Strava OAuth callback")
- Never commit `.env`, secrets, or tokens
- Run `ruff` and `npm run typecheck` before committing

### Authorship — important
When committing, use only the user's own git identity. Do not add Claude as a
co-author. Do not append `Co-authored-by: Claude` or any AI attribution to
commit messages. Every commit should be authored solely by the developer.

---

## When compacting
Preserve: list of modified files, any migration names created, current
endpoint being built, unresolved TODOs, and any concepts that were mid-explanation.