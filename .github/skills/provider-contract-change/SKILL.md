---
name: provider-contract-change
description: Change a WealthWing upstream provider endpoint, client, Pydantic response schema, error mapping, or consuming agent tool contract. Use for WWDataClient and external API contract changes; do not use for prompt-only or graph-only changes.
---

# Change a provider contract

1. Read the repository and provider instruction files under
   `.github/instructions/`.
2. Identify the upstream method, path, query parameters, authorization rules,
   timeout expectations, and response schema.
3. Update the Pydantic boundary schema first when the response contract changes.
4. Update the provider client and typed exception mapping.
5. Update consuming services or tools without leaking transport details into
   routers or prompts.
6. Add `httpx.MockTransport` contract tests for:
   - request method, path, query parameters, and headers;
   - successful response validation;
   - 401 and 403 mapping;
   - deterministic 4xx and transient 5xx behavior;
   - timeout or network failure;
   - invalid JSON and schema drift.
7. Run provider and tool tests, then affected graph/API tests and `pytest -q`.
8. Report contract changes, compatibility risks, and verification results.

Never log or serialize credentials or raw upstream error bodies. Do not add
unbounded retries or retry deterministic client failures.
