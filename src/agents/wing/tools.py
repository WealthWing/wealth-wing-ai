from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from src.agents.wing.state import ProfileId


@tool
def echo_context(text: str) -> str:
    """Return the provided text unchanged."""
    return text


def get_tools(profile: ProfileId) -> tuple[BaseTool, ...]:
    from src.agents.wing.profiles import get_profile

    return get_profile(profile)["tools"]

