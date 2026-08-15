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

### Run and debug in VS Code

Install the workspace's recommended Python extensions, then select the
`venv` interpreter with **Python: Select Interpreter**.

- To debug with breakpoints, open **Run and Debug**, select
  **FastAPI: Debug**, and press `F5`.
- To debug while automatically reloading after file changes, select
  **FastAPI: Debug with reload**. The no-reload profile is more predictable
  when stepping through code.
- To run without a debugger, use **Terminal > Run Task > FastAPI: Run
  normally**. You can also press `Ctrl+F5` (`Control+F5` on macOS) with a
  FastAPI launch profile selected.

All FastAPI VS Code profiles listen on `http://localhost:8080` and load `.env`.

## Docker

Create `.env` from the example and fill in the provider and Cognito values before
starting the container:

```bash
cp .env.example .env
docker compose up --build --detach
docker compose ps
```

The API is available only on the local machine at `http://localhost:8001`. Point
the React application's AI API base URL there, then verify the container with:

```bash
curl http://localhost:8001/health/ping
docker compose logs --follow api
```

Compose passes `.env` to the container at runtime; `.env` remains excluded from
the image and Git. If Wealth Wing Data runs directly on host port `8000`, use
`http://host.docker.internal:8000` for `WEALTH_WING_DATA_URL`. A remote backend
should use its normal HTTPS URL. The container still listens internally on port
`8000`; only the local host port is changed to avoid a conflict with Wealth Wing
Data.

Stop the local service with:

```bash
docker compose down
```

The container writes JSON logs to stdout, which is the expected pattern for
Docker, ECS, CloudWatch, and similar log collectors.

For the ECR and ECS Express Mode deployment workflow, see
[AWS_DEPLOYMENT.md](AWS_DEPLOYMENT.md).

## Configuration

Important environment values:

- `ENABLE_DOCS=false` keeps `/docs`, `/redoc`, and `/openapi.json` disabled by default.
- `LOG_FORMAT=pretty` emits readable local terminal logs; use `json` for
  container platforms and `text` for the minimal legacy format.
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

For the Docker Compose service:

```bash
curl http://localhost:8001/health/ping
```

Expected response:

```json
{"message":"healthy"}
```

Provider health is available at `/health`:

```bash
curl http://localhost:8001/health
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
