# Wealth Wing AI

FastAPI service for WealthWing AI integrations.

The default app surface is intentionally small and locked down. Only
`/health/ping` is exposed by default; API docs are opt-in through environment
configuration.

## Setup

```bash
pip install -r requirements-dev.txt
cp .env.example .env
```

## Run

```bash
./run.sh
```

Or run directly:

```bash
uvicorn main:app --reload --env-file .env
```

## Docker

Build and run the API locally:

```bash
docker compose up --build
```

The container listens on `http://localhost:8000` and writes JSON logs to stdout,
which is the expected pattern for Docker, ECS, CloudWatch, and similar log
collectors.

## Configuration

Important environment values:

- `ENABLE_DOCS=false` keeps `/docs`, `/redoc`, and `/openapi.json` disabled by default.
- `LOG_FORMAT=json` emits structured logs for container platforms.
- `CORS_ORIGINS` should be a comma-separated list of trusted frontend origins.
- `ALLOWED_HOSTS` should be a comma-separated list of valid API hostnames.
- `TOGETHER_API_KEY` is required for the Together provider health check.
- `WEALTH_WING_DATA_URL` is required for agents to retrieve real transaction data.
- `WEALTH_WING_DATA_HEALTH_URL` enables the Wealth Wing Data health check.
- Cognito JWT validation uses `COGNITO_JWKS_URL`, `COGNITO_ISSUER`, and `COGNITO_CLIENT_ID`.

Protected routes fail closed. Missing credentials return `401`; a request with a
token returns `503` if Cognito auth is not configured.

Error responses include a `request_id`, and the same ID is returned as the
`X-Request-ID` response header for log correlation.

## Health Check

```bash
curl http://localhost:8000/health/ping
```

Expected response:

```json
{"message":"healthy"}
```

Provider health is available at `/health`:

```bash
curl http://localhost:8000/health
```

Expected healthy response:

```json
{
  "status": "healthy",
  "providers": {
    "together": {"status": "healthy"},
    "wealth-wing-data": {"status": "healthy"}
  }
}
```

## Tests

```bash
pytest
```
