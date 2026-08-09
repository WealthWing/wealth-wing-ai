from __future__ import annotations

import asyncio
import json
from typing import cast

from langchain_core.messages import AnyMessage
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import Annotated, TypedDict

from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.nodes import WingAgentNodes
from src.agents.wing.state import (
    CurrentTurn,
    FinalAnswer,
    WingGraphState,
    WingRuntimeContext,
)
from src.agents.wing.tools import get_transactions_summary
from src.config import Settings
from src.providers.ww_data_schemas import TransactionSummaryResponse


def required_current_turn(state: WingGraphState) -> CurrentTurn:
    current_turn = state.get("current_turn")
    assert current_turn is not None
    return current_turn


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


class FakeFinalAnswerLLM:
    def __init__(self) -> None:
        self.messages: object | None = None

    def with_structured_output(self, schema: object) -> FakeFinalAnswerLLM:
        assert schema is FinalAnswer
        return self

    async def ainvoke(self, messages: object) -> FinalAnswer:
        self.messages = messages
        return FinalAnswer(answer="Summary complete.")


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


def make_nodes(llm: object | None = None) -> WingAgentNodes:
    settings = make_settings()
    chat_model = cast(ChatOpenAI, llm or object())

    return WingAgentNodes(
        settings=settings,
        configuration=WingAgentConfiguration.from_settings(settings),
        tools_by_name={},
        llm=chat_model,
        llm_with_tools=chat_model,
    )


def test_collect_results_uses_tool_payload_and_runtime_identity() -> None:
    nodes = make_nodes()

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

    current_turn = required_current_turn(result)
    assert current_turn.get("tool_results") == [
        {
            "result_id": "call-1",
            "result_type": "transaction_summary",
            "source_tool": "get_transactions_summary",
            "data": {"total": 100},
            "metadata": {"currency": "USD"},
        }
    ]
    assert current_turn.get("tool_errors") == []
    assert current_turn.get("tool_round_count") == 1
    assert current_turn.get("tool_call_signatures") == [
        "get_transactions_summary:{}"
    ]


def test_collect_results_records_invalid_tool_payload() -> None:
    nodes = make_nodes()

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

    current_turn = required_current_turn(result)
    assert current_turn.get("tool_results") == []
    assert current_turn.get("tool_errors") == [
        {
            "tool_call_id": "call-1",
            "tool_name": "get_transactions_summary",
            "message": "Invalid tool result format: result_type is required",
        }
    ]
    assert nodes.route_after_tool_results(result) == "final_answer"


def test_final_response_uses_tool_results_without_turn_filters() -> None:
    llm = FakeFinalAnswerLLM()
    nodes = make_nodes(llm)

    result = asyncio.run(
        nodes.final_response(
            {
                "current_turn": {
                    "turn_id": "turn-1",
                    "user_input": "Summarize June.",
                    "tool_results": [
                        {
                            "result_id": "call-1",
                            "result_type": "transaction_summary",
                            "source_tool": "get_transactions_summary",
                            "data": {"net_activity": 338000},
                            "metadata": {
                                "filters": {
                                    "from_date": "2026-06-01",
                                    "to_date": "2026-06-30",
                                }
                            },
                        }
                    ],
                }
            }
        )
    )

    assert result["current_turn"]["final_answer"] == "Summary complete."
    assert isinstance(llm.messages, list)
    prompt_message = llm.messages[-1]
    assert isinstance(prompt_message, HumanMessage)
    assert json.loads(str(prompt_message.content)) == {
        "user_question": "Summarize June.",
        "resolved_filters": {},
        "tool_results": [
            {
                "result_type": "transaction_summary",
                "data": {"net_activity": 338000},
                "metadata": {
                    "filters": {
                        "from_date": "2026-06-01",
                        "to_date": "2026-06-30",
                    }
                },
            }
        ],
    }


def test_route_after_llm_starts_first_tool_round() -> None:
    nodes = make_nodes()

    state: WingGraphState = {
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

    assert nodes.route_after_llm(state) == "tools"


def test_route_after_llm_stops_duplicate_tool_call() -> None:
    nodes = make_nodes()

    state: WingGraphState = {
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


def test_route_after_llm_allows_same_tool_with_different_filters() -> None:
    nodes = make_nodes()

    state: WingGraphState = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_transactions",
                        "args": {"category_names": ["Dining"]},
                        "id": "call-2",
                    }
                ],
            )
        ],
        "current_turn": {
            "tool_round_count": 1,
            "tool_call_signatures": [
                'get_transactions:{"category_names":["Groceries"]}'
            ],
        },
    }

    assert nodes.route_after_llm(state) == "tools"


def test_route_after_llm_stops_after_configured_tool_round_limit() -> None:
    nodes = make_nodes()

    state: WingGraphState = {
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
    nodes = make_nodes()

    assert nodes.route_after_tool_results({"current_turn": {}}) == "llm"


def test_record_direct_response_stores_answer_on_current_turn() -> None:
    nodes = make_nodes()

    result = nodes.record_direct_response(
        {
            "messages": [AIMessage(content="I can help reconcile that import.")],
            "current_turn": {"turn_id": "turn-1", "user_input": "help"},
        }
    )

    assert result.get("current_turn") == {
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
                                "args": {
                                    "from_date": "2026-06-01",
                                    "to_date": "2026-06-30",
                                },
                                "id": "call-1",
                                "type": "tool_call",
                            }
                        ],
                    )
                ],
                "current_turn": {},
            },
            context=cast(
                WingRuntimeContext,
                {
                    "ww_data_client": FakeTransactionSummaryClient(),
                    "access_token": "secret-token",
                },
            ),
        )
    )

    nodes = make_nodes()
    result = nodes.collect_results(
        {
            "messages": tool_state["messages"],
            "current_turn": {"turn_id": "turn-1"},
        }
    )

    current_turn = required_current_turn(result)
    tool_results = current_turn.get("tool_results")
    assert tool_results is not None
    assert tool_results[0]["result_id"] == "call-1"
    assert tool_results[0]["result_type"] == (
        "transaction_summary"
    )
    assert tool_results[0]["source_tool"] == (
        "get_transactions_summary"
    )
    data = tool_results[0]["data"]
    assert data["net_activity"] == 338000
    assert data["included_account_types"] == ["CHECKING", "CREDIT_CARD"]
    assert current_turn.get("tool_errors") == []
