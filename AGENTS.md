# Agent instruction router

The canonical repository guidance lives under `.github/` so GitHub Copilot and
other coding agents use the same source material.

Before doing any work in this repository:

1. Read `.github/copilot-instructions.md`.
2. Read `.github/instructions/repository.instructions.md`.
3. Identify the files in scope and read every matching
   `.github/instructions/*.instructions.md` file according to its `applyTo`
   frontmatter.

Treat these steps as mandatory. If instructions conflict, the most narrowly
scoped applicable instruction wins. Direct user instructions have higher
priority than repository guidance.

## Repository Skills

Repository-specific skills live under `.github/skills/`. Before taking action,
check whether the task matches a skill. When it does:

1. Read the matching `SKILL.md` completely before changing or reviewing code.
2. Follow any references that the skill identifies as relevant to the task.
3. State briefly that the skill is being used and why.

Use skills together with the repository instructions. If generic skill guidance
conflicts with this project's established architecture or conventions, follow
`.github/copilot-instructions.md` and the existing codebase unless the user
explicitly requests a change in direction.

### FastAPI Skill (Required)

You **must** load and use [`.github/skills/fastapi/SKILL.md`](.github/skills/fastapi/SKILL.md)
