---
applyTo: "**/*"
---

# Repository-wide guidance

## Architecture

- App bootstrap: `main.py`.
- Settings: `src/config.py`.
- HTTP routers: `src/routers/`.
- Middleware: `src/middleware/`.
- Wing agent graph, prompts, profiles, state, nodes, and tools:
  `src/agents/wing/`.
- External API boundaries: `src/providers/`.
- Shared business services: `src/services/`.
- Tests: `tests/`.
- Public endpoints include `/health` and `/health/ping`.
- `/agents/wing/invoke` is protected and must remain deny-by-default.
- FastAPI documentation is enabled only when `ENABLE_DOCS=true`.

## Development rules

- Use async-compatible patterns for network and application code.
- Keep routers limited to request parsing, dependency access, orchestration,
  and response serialization.
- Centralize environment-backed settings in `src/config.py`.
- Preserve structured JSON logging, request IDs, security headers, explicit
  CORS origins, and explicit allowed hosts.
- Return sanitized errors with a request ID; do not expose internal exception
  details.
- Run containers as a non-root user.
- Do not add a production dependency without explaining why it is required.
- Avoid unrelated refactors and preserve existing user changes.

## Commands

- Runtime dependencies: `pip install -r requirements.txt`.
- Development dependencies: `pip install -r requirements-dev.txt`.
- Tests: `pytest -q`.
- Start locally: `./run.sh`.
- Direct start: `uvicorn main:app --reload --env-file .env`.
- Docker: `docker compose up --build`.

## Required verification

- Run focused tests for the changed behavior.
- Run `pytest -q` before hand-off when dependencies are available.
- Verify `python -c "import main"` after application wiring changes.
- Verify `/health/ping` after middleware, routing, lifespan, or container
  changes.
- Build the Docker image after Dockerfile or dependency changes, or report the
  blocker clearly.
