# Wealth Wing AI repository instructions

This repository is a Python 3.12 FastAPI service for authenticated WealthWing
AI features. It includes Cognito JWT middleware, provider clients, a LangGraph
Wing agent, financial-data tools, and health endpoints.

- Read `.github/instructions/repository.instructions.md` before changing code.
- Apply every `.github/instructions/*.instructions.md` file whose `applyTo`
  glob matches the files being inspected or changed.
- Use a workflow under `.github/skills/` when the task matches its description.
- Keep changes small and avoid unrelated refactors.
- Treat authentication as deny-by-default and add public routes explicitly.
- Never expose tokens, secrets, system prompts, raw graph state, or upstream
  provider payloads in client responses or logs.
- Keep routers thin. Put agent orchestration under `src/agents`, provider
  boundaries under `src/providers`, and reusable business logic under
  `src/services`.
- Run focused tests while iterating and the complete test suite before hand-off.
- Preserve user changes already present in the worktree.
