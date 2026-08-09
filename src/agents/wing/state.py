from __future__ import annotations

from typing import Annotated, Any, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langchain_core.tools import BaseTool
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field

from src.providers.ww_data_client import WWDataClient

ProfileId = Literal["insights", "imports", "planning"]


class WingAgentProfile(TypedDict):
    instructions: str
    tools: tuple[BaseTool, ...]


class RouteDecision(BaseModel):
    agent_profile: ProfileId
    reason: str


#class IntentDecision(TypedDict):
#    intent: Literal[
#        "summarize_spending",
#        "list_transactions",
#        "compare_spending",
#        "account_overview",
#        "subscription_review",
#        "project_spending",
#        "unknown",
#    ]
#    confidence: float
#    needs_clarification: bool
#    clarification_question: str | None


class ToolResult(TypedDict):
    result_id: str
    result_type: str
    source_tool: str
    data: Any
    metadata: dict[str, Any]
    ui: NotRequired[str | None]


class ToolResultPayload(TypedDict):
    result_type: str
    data: Any
    metadata: NotRequired[dict[str, Any]]
    ui: str | None


#class UIBlock(TypedDict):
#    id: str
#    component: str
#    data_ref: str
#    title: NotRequired[str]
#    props: NotRequired[dict[str, Any]]


#class PresentationPlan(TypedDict):
#    blocks: list[UIBlock]

class FinalAnswer(BaseModel):
    answer: str = Field(
        description=(
            "Concise financial answer grounded only in the supplied tool results."
        )
    )


class CurrentTurn(TypedDict, total=False):
    turn_id: str
    user_input: str
    #intent: IntentDecision
    tool_round_count: int
    tool_call_signatures: list[str]
    tool_results: list[ToolResult]
    tool_errors: list[dict[str, Any]]
    #presentation: PresentationPlan
    final_answer: str
    error: str


class WingRuntimeContext(TypedDict, total=False):
    request_id: str
    agent_run_id: str
    user_id: str
    organization_id: str
    agent_profile: ProfileId
    additional_prompt: str | None
    resolved_system_prompt: str
    enabled_tools: tuple[str, ...]
    metadata: dict[str, Any]
    ww_data_client: WWDataClient
    access_token: str


class WingGraphState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    current_turn_id: str | None
    #turns: dict[str, CurrentTurn]
    current_turn: CurrentTurn


WingAgentState = WingGraphState
