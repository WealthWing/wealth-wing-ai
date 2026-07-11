---
name: wing-agent-change
description: Modify WealthWing's Wing LangGraph agent, including profiles, prompts, tools, state, nodes, response schemas, or graph routing. Use for agent behavior changes and agent bug fixes; do not use for provider-only, container-only, or generic FastAPI work.
---

# Change the Wing agent

1. Read `.github/instructions/repository.instructions.md` and
   `.github/instructions/wing-agent.instructions.md`.
2. Define the expected user-visible behavior and affected profile.
3. Trace the relevant request schema, prompt, profile, state fields, graph
   edges, nodes, tools, and response serialization before editing.
4. Identify the authorization context and financial facts the path may access.
5. Add or update a deterministic regression test before or with the change.
6. Implement the smallest coherent change. Keep tools deterministic and graph
   routing explicit.
7. Verify successful, no-data, invalid-input, unauthorized, provider-failure,
   and retry-termination behavior when relevant.
8. Run focused agent tests, then `pytest -q`.
9. Report the behavior changed, safety implications, and verification results.

Never use live credentials or provider APIs in unit tests. Never weaken
grounding, privacy, authentication, or read-only constraints to satisfy a test.
