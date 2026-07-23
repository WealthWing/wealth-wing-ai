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
from src.agents.wing.tools import get_transactions_summary
from src.config import Settings
from src.providers.ww_data_schemas import TransactionSummaryResponse


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


class FakeTransactionSummaryClient:
    async def get_transaction_summary(
        self,
        **kwargs: object,
    ) -> TransactionSummaryResponse:
        return TransactionSummaryResponse.model_validate(
            {
                "gross_expense": 184500,
                "refunds": 2500,
                "net_spending": 182000,
                "income": 520000,
                "net_activity": 338000,
                "expense_transaction_count": 68,
                "refund_transaction_count": 2,
                "income_transaction_count": 3,
                "average_expense": 2713.24,
                "average_monthly_spending": 182000.0,
                "from_date": "2026-06-01",
                "to_date": "2026-06-30",
                "included_account_types": ["CHECKING", "CREDIT_CARD"],
            }
        )


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
                            "result_type": "transaction_summary",
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
            "result_type": "transaction_summary",
            "source_tool": "get_transactions_summary",
            "data": {"total": 100},
            "metadata": {"currency": "USD"},
        }
    ]
    assert result["current_turn"]["tool_errors"] == []
    assert result["current_turn"]["tool_round_count"] == 1
    assert result["current_turn"]["tool_call_signatures"] == [
        "get_transactions_summary:{}"
    ]


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


def test_route_after_llm_starts_first_tool_round() -> None:
    nodes = make_nodes(ResolvedFilters())

    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_transactions_summary",
                        "args": {"text": "summarize the last three months"},
                        "id": "call-1",
                    }
                ],
            )
        ],
        "current_turn": {},
    }

    assert nodes.route_after_llm(state) == "resolve_filters"


def test_route_after_llm_stops_duplicate_tool_call() -> None:
    nodes = make_nodes(ResolvedFilters())

    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_transactions_summary",
                        "args": {"text": "try the summary again"},
                        "id": "call-2",
                    }
                ],
            )
        ],
        "current_turn": {
            "tool_round_count": 1,
            "tool_call_signatures": ["get_transactions_summary:{}"],
        },
    }

    assert nodes.route_after_llm(state) == "final_answer"


def test_route_after_llm_stops_after_configured_tool_round_limit() -> None:
    nodes = make_nodes(ResolvedFilters())

    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_cash_flow_history",
                        "args": {"text": "monthly history", "granularity": "month"},
                        "id": "call-4",
                    }
                ],
            )
        ],
        "current_turn": {
            "tool_round_count": nodes.configuration.max_tool_rounds,
            "tool_call_signatures": [],
        },
    }

    assert nodes.route_after_llm(state) == "final_answer"


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


def test_collect_results_accepts_transaction_summary_toolnode_payload() -> None:
    graph = StateGraph(ToolSmokeState, context_schema=WingRuntimeContext)
    graph.add_node("tools", ToolNode([get_transactions_summary]))
    graph.add_edge(START, "tools")
    app = graph.compile()

    tool_state = asyncio.run(
        app.ainvoke(
            {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "get_transactions_summary",
                                "args": {"text": "summarize June"},
                                "id": "call-1",
                                "type": "tool_call",
                            }
                        ],
                    )
                ],
                "current_turn": {
                    "filters": ResolvedFilters(
                        params=StandardParams(
                            from_date=datetime(2026, 6, 1),
                            to_date=datetime(2026, 6, 30),
                        ),
                        date_source="explicit",
                    )
                },
            },
            context={
                "ww_data_client": FakeTransactionSummaryClient(),
                "access_token": "secret-token",
            },
        )
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
        "transaction_summary"
    )
    assert result["current_turn"]["tool_results"][0]["source_tool"] == (
        "get_transactions_summary"
    )
    data = result["current_turn"]["tool_results"][0]["data"]
    assert data["net_activity"] == 338000
    assert data["included_account_types"] == ["CHECKING", "CREDIT_CARD"]
    assert result["current_turn"]["tool_errors"] == []
