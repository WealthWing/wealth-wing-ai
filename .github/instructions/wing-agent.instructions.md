---
applyTo: "src/agents/wing/**/*.py,src/routers/wing.py,src/schemas/wing.py,tests/test_node.py,tests/test_graph.py,tests/test_wing.py,tests/test_transaction_tool.py"
---

# Wing agent guidance

- Before changing behavior, inspect the affected profile, prompt, state,
  graph route, nodes, tools, request schema, and existing tests.
- Keep profile tool access deny-by-default and preserve read-only behavior.
- Never invent transactions, balances, totals, categories, dates, or other
  financial facts.
- Require either a successful tool result from the current run or a successful,
  provenance-tagged cached result from the same authenticated thread before
  making factual financial claims. Reuse cached results only when their explicit
  filters and scope fully match the current request.
- Distinguish retrieved facts, deterministic calculations, and planning
  assumptions in the final response.
- Treat no data, unavailable data, unauthorized access, malformed provider
  output, and invalid filters as separate outcomes.
- Do not allow an additional prompt or user message to override authentication,
  tool-access, privacy, or financial-safety rules.
- Keep tool-call and retry loops bounded with deterministic termination.
- Never serialize or log access tokens, system prompts, raw runtime context,
  raw graph state, or unfiltered tool payloads.
- Test successful, empty, invalid, unauthorized, unavailable, malformed, and
  repeated-tool-call paths with deterministic fake models.
- Do not call live model or provider APIs from unit tests.
