from __future__ import annotations

from typing import Annotated, Any, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langchain_core.tools import BaseTool
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field
from datetime import datetime
from typing import List, Optional
from src.providers.ww_data_client import WWDataClient

ProfileId = Literal["insights", "imports", "planning"]

class FilterByInputs(BaseModel):
    field_name: str
    values: List[str]

class StandardParams(BaseModel):
    """
    Example of a standard set of parameters

    filter_by:[{"field_name": "category", "values": ["Dining", "Income"]}]
    page:1
    page_size:20
    sort_order:asc
    sort_by:file_size
    from_date: "2021-01-01T00:00:00"
    to_date: "2021-01-31T23:59:59"
    search: "example search term"
    """

    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
    sort_by: Literal["amount", "date", "title"] | None = None
    sort_order: Literal["asc", "desc"] = "desc"
    search: Optional[str] = None
    filter_by: list[FilterByInputs] = Field(default_factory=list)
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None



class WingAgentProfile(TypedDict):
    instructions: str
    tools: tuple[BaseTool, ...]


class RouteDecision(BaseModel):
    agent_profile: ProfileId
    reason: str


class ResolvedFilters(BaseModel):
    params: StandardParams = Field(default_factory=StandardParams)
    date_source: Literal[
        "explicit",
        "default_last_completed_month",
        "default_last_30_days",
        "not_applicable",
    ] = "not_applicable"


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
    ui: NotRequired[Optional[str]]


class ToolResultPayload(TypedDict):
    result_type: str
    data: Any
    metadata: NotRequired[dict[str, Any]]
    ui: Optional[str]


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
    filters: ResolvedFilters
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
