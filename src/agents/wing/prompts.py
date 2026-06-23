from __future__ import annotations

from src.agents.wing.configuration import WingAgentConfiguration


DEFAULT_SYSTEM_PROMPT = "You are Wing, the WealthWing AI assistant."

SYSTEM_PROMPTS = {
    "default": DEFAULT_SYSTEM_PROMPT,
}


def get_system_prompt(configuration: WingAgentConfiguration) -> str:
    return SYSTEM_PROMPTS.get(
        configuration.system_prompt_name,
        DEFAULT_SYSTEM_PROMPT,
    )
