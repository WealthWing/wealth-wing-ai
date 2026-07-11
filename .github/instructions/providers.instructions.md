---
applyTo: "src/providers/**/*.py,src/services/health.py,tests/test_ww_data_client.py,tests/test_health.py"
---

# Provider boundary guidance

- Reuse the application-scoped `httpx.AsyncClient` for request-path calls.
- Set explicit connection, read, write, and pool timeouts.
- Forward authorization only to the intended WealthWing service.
- Never log authorization headers, secrets, or secret-bearing URLs.
- Validate successful JSON responses with Pydantic before returning them.
- Translate transport, authorization, status, and validation failures into
  typed internal exceptions.
- Do not expose raw upstream response bodies or provider exception details to
  routers, models, or API clients.
- Retry only transient, idempotent operations with a bounded attempt count.
- Do not retry authorization failures, validation failures, or deterministic
  client errors.
- Use `httpx.MockTransport` in unit tests and assert the method, URL, query
  parameters, headers, response validation, and error mapping.
