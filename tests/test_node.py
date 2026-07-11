from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import cast

from langchain_core.messages import AnyMessage
from langchain_core.messages import AIMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import Annotated, TypedDict

from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.nodes import WingAgentNodes
from src.agents.wing.state import (
    FilterByInputs,
    ResolvedFilters,
    StandardParams,
    WingRuntimeContext,
)
from src.agents.wing.tools import get_transactions_by_category
from src.config import Settings


class FakeStructuredLLM:
    def __init__(self, response: ResolvedFilters | dict[str, object]) -> None:
        self.response = response

    def invoke(self, messages: object) -> ResolvedFilters | dict[str, object]:
        return self.response


class FakeLLM:
    def __init__(self, response: ResolvedFilters | dict[str, object]) -> None:
        self.response = response

    def with_structured_output(self, schema: object) -> FakeStructuredLLM:
        return FakeStructuredLLM(self.response)


class FakeRuntime:
    context: WingRuntimeContext = {"timezone": "America/New_York"}


class ToolSmokeState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    current_turn: dict[str, object]


def make_settings(**overrides: object) -> Settings:
    settings_values = {
        "ALLOWED_HOSTS": "testserver",
        "COGNITO_JWKS_URL": "",
        "COGNITO_USER_POOL_ID": "",
        "AWS_REGION": "",
        "COGNITO_ISSUER": "",
        "COGNITO_CLIENT_ID": "",
        "TOGETHER_API_KEY": "test-key",
        "WEALTH_WING_DATA_HEALTH_URL": None,
    }
    settings_values.update(overrides)
    return Settings(**settings_values)


def make_nodes(response: ResolvedFilters | dict[str, object]) -> WingAgentNodes:
    settings = make_settings()
    llm = cast(ChatOpenAI, FakeLLM(response))

    return WingAgentNodes(
        settings=settings,
        configuration=WingAgentConfiguration.from_settings(settings),
        tools_by_name={},
        llm=llm,
        llm_with_tools=llm,
    )


def test_resolve_filters_defaults_spending_to_last_completed_month() -> None:
    nodes = make_nodes(ResolvedFilters())

    result = asyncio.run(
        nodes.resolve_filters(
            {
                "current_turn": {
                    "turn_id": "turn-1",
                    "user_input": "summarize my spending",
                    "intent": {
                        "intent": "summarize_spending",
                        "confidence": 1.0,
                        "needs_clarification": False,
                        "clarification_question": None,
                    },
                }
            },
            FakeRuntime(),
        )
    )

    filters = result["current_turn"]["filters"]

    assert filters.date_source == "default_last_completed_month"
    assert filters.params.from_date is not None
    assert filters.params.to_date is not None
    assert filters.params.from_date.month == 6
    assert filters.params.to_date.month == 6


def test_resolve_filters_preserves_explicit_dates_from_llm_dict() -> None:
    nodes = make_nodes(
        {
            "params": {
                "from_date": "2026-05-01T00:00:00",
                "to_date": "2026-05-31T23:59:59",
                "page": 2,
            },
            "date_source": "explicit",
        }
    )

    result = asyncio.run(
        nodes.resolve_filters(
            {
                "current_turn": {
                    "turn_id": "turn-1",
                    "user_input": "show May spending page 2",
                    "intent": {
                        "intent": "summarize_spending",
                        "confidence": 1.0,
                        "needs_clarification": False,
                        "clarification_question": None,
                    },
                }
            },
            FakeRuntime(),
        )
    )

    filters = result["current_turn"]["filters"]

    assert filters.date_source == "explicit"
    assert filters.params.from_date == datetime(2026, 5, 1, 0, 0, 0)
    assert filters.params.to_date == datetime(2026, 5, 31, 23, 59, 59)
    assert filters.params.page == 2


def test_resolve_filters_infers_category_filter_when_llm_omits_it() -> None:
    nodes = make_nodes(
        {
            "params": {
                "from_date": "2026-07-01T00:00:00Z",
                "to_date": "2026-07-03T02:53:25.037505Z",
                "sort_by": "date",
                "search": None,
                "filter_by": [],
            },
            "date_source": "explicit",
        }
    )

    result = asyncio.run(
        nodes.resolve_filters(
            {
                "current_turn": {
                    "turn_id": "turn-1",
                    "user_input": (
                        "Can you explain how is my spending for dining this month?"
                    ),
                    "intent": {
                        "intent": "summarize_spending",
                        "confidence": 1.0,
                        "needs_clarification": False,
                        "clarification_question": None,
                    },
                }
            },
            FakeRuntime(),
        )
    )

    filters = result["current_turn"]["filters"]

    assert filters.params.search is None
    assert filters.params.filter_by == [
        FilterByInputs(field_name="category", values=["Dining"])
    ]
    assert filters.params.sort_by == "date"


def test_collect_results_uses_tool_payload_and_runtime_identity() -> None:
    nodes = make_nodes(ResolvedFilters())

    result = nodes.collect_results(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_transactions_summary",
                            "args": {"text": "summary"},
                            "id": "call-1",
                        }
                    ],
                ),
                ToolMessage(
                    content=json.dumps(
                        {
                            "result_type": "transactions_summary",
                            "data": {"total": 100},
                            "metadata": {"currency": "USD"},
                        }
                    ),
                    tool_call_id="call-1",
                ),
            ],
            "current_turn": {"turn_id": "turn-1"},
        }
    )

    assert result["current_turn"]["tool_results"] == [
        {
            "result_id": "call-1",
            "result_type": "transactions_summary",
            "source_tool": "get_transactions_summary",
            "data": {"total": 100},
            "metadata": {"currency": "USD"},
        }
    ]
    assert result["current_turn"]["tool_errors"] == []


def test_collect_results_records_invalid_tool_payload() -> None:
    nodes = make_nodes(ResolvedFilters())

    result = nodes.collect_results(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_transactions_summary",
                            "args": {"text": "summary"},
                            "id": "call-1",
                        }
                    ],
                ),
                ToolMessage(
                    content=json.dumps({"data": {"total": 100}}),
                    tool_call_id="call-1",
                ),
            ],
            "current_turn": {"turn_id": "turn-1"},
        }
    )

    assert result["current_turn"]["tool_results"] == []
    assert result["current_turn"]["tool_errors"] == [
        {
            "tool_call_id": "call-1",
            "tool_name": "get_transactions_summary",
            "message": "Invalid tool result format: result_type is required",
        }
    ]
    assert nodes.route_after_tool_results(result) == "final_answer"


def test_route_after_tool_results_continues_without_errors() -> None:
    nodes = make_nodes(ResolvedFilters())

    assert nodes.route_after_tool_results({"current_turn": {}}) == "llm"


def test_record_direct_response_stores_answer_on_current_turn() -> None:
    nodes = make_nodes(ResolvedFilters())

    result = nodes.record_direct_response(
        {
            "messages": [AIMessage(content="I can help reconcile that import.")],
            "current_turn": {"turn_id": "turn-1", "user_input": "help"},
        }
    )

    assert result["current_turn"] == {
        "turn_id": "turn-1",
        "user_input": "help",
        "final_answer": "I can help reconcile that import.",
    }


def test_collect_results_accepts_injected_state_toolnode_payload() -> None:
    graph = StateGraph(ToolSmokeState)
    graph.add_node("tools", ToolNode([get_transactions_by_category]))
    graph.add_edge(START, "tools")
    app = graph.compile()

    tool_state = app.invoke(
        {
            "messages": [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "get_transactions_by_category",
                            "args": {},
                            "id": "call-1",
                            "type": "tool_call",
                        }
                    ],
                )
            ],
            "current_turn": {
                "filters": ResolvedFilters(
                    params=StandardParams(
                        filter_by=[
                            FilterByInputs(
                                field_name="category",
                                values=["Dining"],
                            )
                        ]
                    )
                )
            },
        }
    )

    nodes = make_nodes(ResolvedFilters())
    result = nodes.collect_results(
        {
            "messages": tool_state["messages"],
            "current_turn": {"turn_id": "turn-1"},
        }
    )

    assert result["current_turn"]["tool_results"][0]["result_id"] == "call-1"
    assert result["current_turn"]["tool_results"][0]["result_type"] == (
        "transactions_by_category"
    )
    assert result["current_turn"]["tool_results"][0]["source_tool"] == (
        "get_transactions_by_category"
    )
    data = result["current_turn"]["tool_results"][0]["data"]
    assert len(data) == 1
    assert data[0]["category"] == "Dining"
    assert data[0]["total_amount"] == 61.02
    assert [
        transaction["description"] for transaction in data[0]["transactions"]
    ] == ["Starbucks", "Chipotle", "DoorDash"]
    assert result["current_turn"]["tool_errors"] == []
