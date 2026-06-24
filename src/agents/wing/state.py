from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from pydantic import BaseModel


ProfileId = Literal["insights", "imports", "planning"]


class RouteDecision(BaseModel):
    profile: ProfileId
    reason: str


class WingAgentState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    # user
    user_id: str
    organization_id: str
    profile: ProfileId

    tool_results: list[dict]
    validation_errors: list[str]
    retry_count: int

    ui_response: dict

    additional_prompt: str | None
    resolved_system_prompt: str
    enabled_tools: tuple[str, ...]
    metadata: dict[str, Any]
