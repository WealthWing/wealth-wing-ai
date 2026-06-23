# AGENTS.md

## Purpose
Use this guide when assisting on `wealth-wing-ai`. Keep changes small, correct, and consistent with the sibling `wealth-wing-data` FastAPI codebase.

## Project Snapshot
- Backend API for WealthWing AI integrations.
- Current surface area is intentionally small: authentication middleware and a health check router.
- Default app routes should stay minimal; `/health/ping` is the only route exposed unless new work explicitly adds more.
- FastAPI docs are opt-in via `ENABLE_DOCS=true`, not exposed by default.
- Future AI integration code should keep router handlers thin and move provider/business logic into `src/services`.

## Stack
- Python 3.12
- FastAPI
- AWS Cognito JWT authentication via PyJWT

## Key Entry Points
- App bootstrap: `main.py`
- Settings/config: `src/config.py`
- Routers: `src/routers/`
- Middleware: `src/middleware/`

## Local Commands
- Install runtime deps: `pip install -r requirements.txt`
- Install dev/test deps: `pip install -r requirements-dev.txt`
- Start API (script): `./run.sh`
- Start API (direct): `uvicorn main:app --reload --env-file .env`
- Start API (Docker): `docker compose up --build`
- Run tests: `pytest`

## Environment Notes
- Common app vars: `FE_URL`
- Safety/edge vars:
  - `ENVIRONMENT`
  - `LOG_LEVEL`
  - `ENABLE_DOCS`
  - `CORS_ORIGINS`
  - `ALLOWED_HOSTS`
- Auth/Cognito-related vars used by middleware:
  - `COGNITO_JWKS_URL`
  - `COGNITO_USER_POOL_ID`
  - `AWS_REGION`
  - `COGNITO_ISSUER`
  - `COGNITO_CLIENT_ID`

## Coding Rules For This Repo
- Prefer async-compatible patterns.
- Keep router layer thin; put AI/provider logic in `src/services` as the project grows.
- Preserve naming and file organization conventions from `wealth-wing-data` where they apply.
- Treat authentication defaults as deny-by-default. Add public routes explicitly.
- Do not leak JWT validation internals or provider secrets to API clients.
- Keep Cognito/JWT settings centralized in `src/config.py`.
- Keep docs, CORS origins, and allowed hosts explicit for each environment.
- Keep baseline security headers in place for all responses.
- Logs should be structured JSON by default and safe for stdout-based collectors.
- Error responses should include a request ID and avoid exposing internal exception details.
- Docker images should run as a non-root user.
- Avoid unrelated refactors while fixing a specific issue.

## Validation Checklist Before Hand-off
- App imports cleanly.
- `pytest` passes.
- App starts locally with `uvicorn main:app --reload --env-file .env` when dependencies are installed.
- Docker image builds, or blockers are reported clearly.
- Health endpoint responds at `/health/ping`.
