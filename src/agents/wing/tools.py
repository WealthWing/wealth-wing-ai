from __future__ import annotations

from langchain_core.tools import BaseTool, tool

from src.agents.wing.configuration import WingAgentConfiguration


@tool
def echo_context(text: str) -> str:
    """Return the provided text unchanged."""
    return text


def get_tools(configuration: WingAgentConfiguration) -> tuple[BaseTool, ...]:
    configured_tool_names = set(configuration.enabled_tools)
    available_tools: tuple[BaseTool, ...] = (echo_context,)

    if not configured_tool_names:
        return available_tools

    return tuple(tool for tool in available_tools if tool.name in configured_tool_names)
