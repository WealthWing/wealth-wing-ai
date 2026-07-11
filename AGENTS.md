# Agent instruction router

The canonical repository guidance lives under `.github/` so GitHub Copilot and
other coding agents use the same source material.

Before doing any work in this repository:

1. Read `.github/copilot-instructions.md`.
2. Read `.github/instructions/repository.instructions.md`.
3. Identify the files in scope and read every matching
   `.github/instructions/*.instructions.md` file according to its `applyTo`
   frontmatter.
4. Inspect `.github/skills/*/SKILL.md`. When the task matches a skill's
   description, read that skill completely and follow its workflow.

Treat these steps as mandatory. If instructions conflict, the most narrowly
scoped applicable instruction wins. Direct user instructions have higher
priority than repository guidance.
