from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

import pytest
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langchain_core.tools import ToolException
from langgraph.graph import START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import Annotated, TypedDict

from src.agents.wing.state import (
    FilterByInputs,
    ResolvedFilters,
    StandardParams,
    WingRuntimeContext,
)
from src.agents.wing.tools import get_transactions
from src.providers.ww_data_schemas import TransactionsAllResponse


class FakeWWDataClient:
    def __init__(self, response: TransactionsAllResponse) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def get_transactions(self, **kwargs: Any) -> TransactionsAllResponse:
        self.calls.append(kwargs)
        return self.response


class FakeToolRuntime:
    def __init__(self, state: dict[str, Any], context: dict[str, Any]) -> None:
        self.state = state
        self.context = context


class ToolState(TypedDict, total=False):
    messages: Annotated[list[AnyMessage], add_messages]
    current_turn: dict[str, Any]


def _invoke(runtime: FakeToolRuntime) -> dict[str, Any]:
    assert get_transactions.coroutine is not None
    return asyncio.run(
        get_transactions.coroutine(text="show transactions", runtime=runtime)
    )


def _provider_response() -> TransactionsAllResponse:
    return TransactionsAllResponse.model_validate(
        {
            "transactions": [
                {
                    "uuid": "47c45f67-93a0-4cb2-a2ef-01d241b16a6c",
                    "user_id": "87f9df12-5851-4937-9e5e-d357fee7d436",
                    "category_id": "43581d15-1a1d-49ce-adc6-f0fe6184f18a",
                    "account_id": "f219bb47-8f12-455e-b575-e384ac524999",
                    "project_id": None,
                    "title": "ShopRite",
                    "amount": -8423,
                    "description": "Weekly groceries",
                    "date": "2026-06-14T12:30:00Z",
                    "currency": "USD",
                    "type": "expense",
                    "subscription_candidate": False,
                    "subscription_id": None,
                    "category": "Groceries",
                    "account_name": "Chase Checking",
                }
            ],
            "has_more": True,
            "total_pages": 3,
            "total_count": 41,
        }
    )


def test_get_transactions_returns_stable_payload_and_forwards_filters() -> None:
    client = FakeWWDataClient(_provider_response())
    filters = ResolvedFilters(
        params=StandardParams(
            page=2,
            page_size=20,
            sort_by="date",
            sort_order="asc",
            search="ShopRite",
            from_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
            to_date=datetime(2026, 6, 30, tzinfo=timezone.utc),
        ),
        date_source="explicit",
    )
    runtime = FakeToolRuntime(
        state={"current_turn": {"filters": filters}},
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    result = _invoke(runtime)

    assert client.calls[0]["access_token"] == "secret-token"
    query = client.calls[0]["params"]
    assert query.model_dump() == {
        "page": 2,
        "page_size": 20,
        "sort_by": "date",
        "sort_order": "asc",
        "search": "ShopRite",
        "from_date": datetime(2026, 6, 1, tzinfo=timezone.utc),
        "to_date": datetime(2026, 6, 30, tzinfo=timezone.utc),
    }
    assert result["data"] == {
        "transactions": [
            {
                "id": "47c45f67-93a0-4cb2-a2ef-01d241b16a6c",
                "date": "2026-06-14T12:30:00+00:00",
                "title": "ShopRite",
                "description": "Weekly groceries",
                "amount_cents": -8423,
                "amount": "$-84.23",
                "currency": "USD",
                "type": "expense",
                "category": {
                    "id": "43581d15-1a1d-49ce-adc6-f0fe6184f18a",
                    "name": "Groceries",
                },
                "account": {
                    "id": "f219bb47-8f12-455e-b575-e384ac524999",
                    "name": "Chase Checking",
                },
            }
        ],
        "page": 2,
        "page_size": 20,
        "total_count": 41,
        "total_pages": 3,
        "has_more": True,
    }
    assert result["metadata"]["source"] == "wealth-wing-data"
    assert "secret-token" not in str(result)


def test_toolnode_injects_state_and_runtime_context() -> None:
    client = FakeWWDataClient(_provider_response())
    graph = StateGraph(ToolState, context_schema=WingRuntimeContext)
    graph.add_node("tools", ToolNode([get_transactions]))
    graph.add_edge(START, "tools")
    app = graph.compile()

    result = asyncio.run(
        app.ainvoke(
            {
                "messages": [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "get_transactions",
                                "args": {"text": "show transactions"},
                                "id": "call-1",
                                "type": "tool_call",
                            }
                        ],
                    )
                ],
                "current_turn": {"filters": ResolvedFilters()},
            },
            context={
                "ww_data_client": client,
                "access_token": "secret-token",
            },
        )
    )

    tool_message = result["messages"][-1]
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.status == "success"
    assert client.calls[0]["access_token"] == "secret-token"


def test_get_transactions_rejects_unsupported_filters_without_calling_provider() -> None:
    client = FakeWWDataClient(_provider_response())
    runtime = FakeToolRuntime(
        state={
            "current_turn": {
                "filters": ResolvedFilters(
                    params=StandardParams(
                        filter_by=[
                            FilterByInputs(
                                field_name="category",
                                values=["Groceries"],
                            )
                        ]
                    )
                )
            }
        },
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    with pytest.raises(ToolException, match="not supported"):
        _invoke(runtime)
    assert client.calls == []


@pytest.mark.parametrize(
    "context",
    [{}, {"ww_data_client": FakeWWDataClient(_provider_response())}],
)
def test_get_transactions_requires_runtime_dependencies(context: dict[str, Any]) -> None:
    runtime = FakeToolRuntime(
        state={"current_turn": {"filters": ResolvedFilters()}},
        context=context,
    )

    with pytest.raises(ToolException):
        _invoke(runtime)
