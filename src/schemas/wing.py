from __future__ import annotations

from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, Field

from src.agents.wing.state import ProfileId


class WingAgentRequest(BaseModel):
    message: str = Field(..., min_length=1)
    additional_prompt: str | None = None
    agent_profile: ProfileId = Field(
        default="imports",
        validation_alias=AliasChoices("agent_profile", "profile"),
    )


AgentResultType = Literal[
    "spending_by_category",
    "transaction_summary",
    "transaction_list",
    "transactions_by_category",
]


class WingAgentResult(BaseModel):
    """A UI-safe, structured result produced during the current turn."""

    id: str
    type: AgentResultType
    data: dict[str, Any] | list[dict[str, Any]]
    ui: str | None = None


class WingAgentError(BaseModel):
    code: Literal["agent_error", "data_unavailable"]
    message: str


class WingAgentResponse(BaseModel):
    """The public outcome of one Wing agent turn."""

    turn_id: str
    answer: str
    results: list[WingAgentResult] = Field(default_factory=list)
    applied_filters: dict[str, Any] | None = None
    error: WingAgentError | None = None
