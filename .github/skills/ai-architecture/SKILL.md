---
name: ai-architecture
description: Design or refactor WealthWing AI application architecture across APIs, orchestration, agents, tools, prompts, retrieval, evaluation, and observability. Use for architecture planning or cross-layer AI feature design; do not use for isolated bug fixes.
---

# AI Architecture Skill

## Goal

Build production-style AI applications with clear separation between API, orchestration, agents, tools, retrieval, prompts, evaluation, and observability.

Do not build AI features as one large service file.

## Core Principles

1. API routes are thin.
2. Orchestration owns workflow decisions.
3. Agents own LLM instructions, model config, tool access, and structured outputs.
4. Tools are deterministic functions that return structured data.
5. Retrieval is testable without the LLM.
6. Prompts live in prompt files or a prompt registry.
7. Outputs should be structured, not random prose.
8. Evaluation and tracing are first-class parts of the repo.
9. Business logic should not be hidden inside prompts.
10. Do not add unnecessary abstractions until there is a clear reason.

## Preferred Folder Structure

```txt
app/
  main.py

  api/
    routes/
      health.py
      chat.py
      documents.py
      evals.py
    deps.py

  core/
    config.py
    logging.py
    errors.py

  ai/
    orchestration/
      graph.py
      state.py
      nodes.py
      edges.py

    agents/
      main_agent.py
      document_agent.py
      finance_agent.py

    prompts/
      system_rules.md
      query_normalizer.md
      answer_synthesizer.md

    tools/
      transaction_tools.py
      document_tools.py
      search_tools.py

    retrieval/
      chunking.py
      embeddings.py
      vector_store.py
      hybrid_search.py
      reranking.py
      citations.py

    memory/
      short_term.py
      long_term.py
      checkpointer.py

    schemas/
      chat.py
      tool_results.py
      retrieval.py
      structured_outputs.py

    evals/
      datasets/
      evaluators.py
      run_eval.py
      metrics.py

    observability/
      tracing.py
      cost_tracking.py

  db/
    session.py
    models/
    repositories/

  tests/
    api/
    ai/
    retrieval/
    evals/
```
