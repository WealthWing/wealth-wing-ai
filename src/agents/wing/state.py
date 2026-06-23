from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class WingAgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    additional_prompt: str | None
    resolved_system_prompt: str
    enabled_tools: tuple[str, ...]
    metadata: dict[str, Any]
