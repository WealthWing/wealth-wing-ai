from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from src.agents.wing.state import ProfileId


class WingAgentRequest(BaseModel):
    message: str = Field(min_length=1)
    additional_prompt: str | None = None
    agent_profile: ProfileId = "imports"


class WingAgentMessage(BaseModel):
    role: Literal["ai", "human", "system", "tool", "unknown"]
    content: str


class WingAgentResponse(BaseModel):
    messages: list[WingAgentMessage]
    additional_prompt: str | None = None
    agent_profile: ProfileId | None = None
    resolved_system_prompt: str
    enabled_tools: tuple[str, ...]
    metadata: dict[str, Any]
