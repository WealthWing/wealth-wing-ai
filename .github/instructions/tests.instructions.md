---
applyTo: "tests/**/*.py"
---

# Test guidance

- Keep unit tests deterministic, isolated, and free of real network calls.
- Use fake chat models for agent behavior and `httpx.MockTransport` for
  provider contracts.
- Prefer pytest fixtures and parametrization over repeated setup.
- Test externally observable behavior rather than private implementation
  details unless a state transition or graph route is the contract.
- Cover security and failure paths alongside the successful path.
- Add a regression test with every bug fix.
- Mark credentialed or live-provider tests as `integration`; exclude them from
  the default test run.
- Do not weaken assertions merely to make a failing test pass.
