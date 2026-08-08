from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from datetime import date, datetime, timezone, tzinfo
from typing import Any, cast
from uuid import UUID

import pytest
from langchain_core.messages import AIMessage, AnyMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool, ToolException
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
from src.agents.wing.tools import (
    get_cash_flow_history,
    get_spending_by_category,
    get_transactions,
    get_transactions_summary,
)
from src.providers.ww_data_client import (
    WWDataAuthorizationError,
    WWDataResponseError,
    WWDataUnavailableError,
)
from src.providers.ww_data_schemas import (
    AccountTypeEnum,
    CashFlowHistoryResponse,
    CategorySpendingResponse,
    TransactionSummaryResponse,
    TransactionsAllResponse,
)


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


ToolCoroutine = Callable[..., Coroutine[Any, Any, dict[str, Any]]]


def _tool_coroutine(tool: BaseTool) -> ToolCoroutine:
    assert isinstance(tool, StructuredTool)
    assert tool.coroutine is not None
    return cast(ToolCoroutine, tool.coroutine)


def _invoke(runtime: FakeToolRuntime, **kwargs: Any) -> dict[str, Any]:
    return asyncio.run(_tool_coroutine(get_transactions)(runtime=runtime, **kwargs))


def _invoke_cash_flow(
    runtime: FakeToolRuntime,
    **kwargs: Any,
) -> dict[str, Any]:
    return asyncio.run(
        _tool_coroutine(get_cash_flow_history)(
            runtime=runtime,
            **kwargs,
        )
    )


def _invoke_spending_by_category(
    runtime: FakeToolRuntime,
    **kwargs: Any,
) -> dict[str, Any]:
    return asyncio.run(
        _tool_coroutine(get_spending_by_category)(
            runtime=runtime,
            **kwargs,
        )
    )


def _invoke_transaction_summary(
    runtime: FakeToolRuntime,
    **kwargs: Any,
) -> dict[str, Any]:
    return asyncio.run(
        _tool_coroutine(get_transactions_summary)(
            runtime=runtime,
            **kwargs,
        )
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


def _cash_flow_response() -> CashFlowHistoryResponse:
    return CashFlowHistoryResponse.model_validate(
        {
            "timezone": "America/New_York",
            "from_date": "2026-06-01",
            "to_date": "2026-06-30",
            "granularity": "month",
            "periods": [
                {
                    "period_start": "2026-06-01T00:00:00-04:00",
                    "period_end": "2026-06-30T23:59:59.999999-04:00",
                    "income": 520000,
                    "expense": -184500,
                    "refunds": 2500,
                    "net": 338000,
                    "transaction_count": 73,
                }
            ],
        }
    )


def _transaction_summary_response() -> TransactionSummaryResponse:
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


class FakeTransactionSummaryWWDataClient:
    def __init__(self, response: TransactionSummaryResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def get_transaction_summary(
        self,
        **kwargs: Any,
    ) -> TransactionSummaryResponse:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_get_transactions_summary_returns_stable_payload_and_forwards_dates() -> None:
    client = FakeTransactionSummaryWWDataClient(_transaction_summary_response())
    stale_filters = ResolvedFilters(
        params=StandardParams(
            from_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            to_date=datetime(2025, 1, 2, tzinfo=timezone.utc),
        ),
        date_source="explicit",
    )
    runtime = FakeToolRuntime(
        state={"current_turn": {"filters": stale_filters}},
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    result = _invoke_transaction_summary(
        runtime,
        from_date=date(2026, 6, 1),
        to_date=date(2026, 6, 30),
        account_types=[
            AccountTypeEnum.CHECKING,
            AccountTypeEnum.CREDIT_CARD,
            AccountTypeEnum.CHECKING,
        ],
    )

    assert client.calls[0]["access_token"] == "secret-token"
    assert client.calls[0]["request"].model_dump(mode="json") == {
        "from_date": "2026-06-01",
        "to_date": "2026-06-30",
        "account_types": ["CHECKING", "CREDIT_CARD"],
    }
    assert result == {
        "result_type": "transaction_summary",
        "data": {
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
        },
        "metadata": {
            "filters": {
                "from_date": "2026-06-01",
                "to_date": "2026-06-30",
                "account_types": ["CHECKING", "CREDIT_CARD"],
            },
            "source": "wealth-wing-data",
        },
        "ui": "transactions_summary_ui",
    }
    assert "secret-token" not in str(result)


def test_get_transactions_summary_defaults_to_last_completed_month(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> FrozenDateTime:
            return cls(2026, 7, 22, tzinfo=tz)

    monkeypatch.setattr("src.agents.wing.tools.datetime", FrozenDateTime)
    client = FakeTransactionSummaryWWDataClient(_transaction_summary_response())
    runtime = FakeToolRuntime(
        state={"current_turn": {"filters": ResolvedFilters()}},
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    _invoke_transaction_summary(runtime)

    request = client.calls[0]["request"]
    assert request.from_date == date(2026, 6, 1)
    assert request.to_date == date(2026, 6, 30)


def test_get_transactions_summary_preserves_zero_activity() -> None:
    response = _transaction_summary_response().model_copy(
        update={
            "gross_expense": 0,
            "refunds": 0,
            "net_spending": 0,
            "income": 0,
            "net_activity": 0,
            "expense_transaction_count": 0,
            "refund_transaction_count": 0,
            "income_transaction_count": 0,
            "average_expense": 0.0,
            "average_monthly_spending": 0.0,
        }
    )
    runtime = FakeToolRuntime(
        state={"current_turn": {"filters": ResolvedFilters()}},
        context={
            "ww_data_client": FakeTransactionSummaryWWDataClient(response),
            "access_token": "secret-token",
        },
    )

    result = _invoke_transaction_summary(runtime)

    assert result["data"]["net_activity"] == 0
    assert result["data"]["expense_transaction_count"] == 0


def test_get_transactions_summary_rejects_partial_date_range() -> None:
    client = FakeTransactionSummaryWWDataClient(_transaction_summary_response())
    runtime = FakeToolRuntime(
        state={
            "current_turn": {
                "filters": ResolvedFilters(
                    params=StandardParams(
                        from_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
                    )
                )
            }
        },
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    with pytest.raises(ToolException, match="filters are invalid"):
        _invoke_transaction_summary(runtime, from_date=date(2026, 6, 1))
    assert client.calls == []


def test_get_transactions_summary_ignores_resolved_filters() -> None:
    client = FakeTransactionSummaryWWDataClient(_transaction_summary_response())
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

    _invoke_transaction_summary(
        runtime,
        from_date=date(2026, 6, 1),
        to_date=date(2026, 6, 30),
    )

    assert len(client.calls) == 1
    assert client.calls[0]["request"].from_date == date(2026, 6, 1)
    assert client.calls[0]["request"].to_date == date(2026, 6, 30)


def test_get_transactions_summary_exposes_filters_to_the_model() -> None:
    schema_type = cast(BaseTool, get_transactions_summary).tool_call_schema
    assert not isinstance(schema_type, dict)
    schema = schema_type.model_json_schema()

    assert set(schema["properties"]) == {
        "from_date",
        "to_date",
        "account_types",
    }
    assert "runtime" not in schema["properties"]
    assert "last completed month" in schema["properties"]["from_date"][
        "description"
    ]
    assert "quarter without a year" in schema["properties"]["from_date"][
        "description"
    ]


@pytest.mark.parametrize(
    "context",
    [
        {},
        {
            "ww_data_client": FakeTransactionSummaryWWDataClient(
                _transaction_summary_response()
            )
        },
    ],
)
def test_get_transactions_summary_requires_runtime_dependencies(
    context: dict[str, Any],
) -> None:
    runtime = FakeToolRuntime(
        state={"current_turn": {"filters": ResolvedFilters()}},
        context=context,
    )

    with pytest.raises(ToolException):
        _invoke_transaction_summary(runtime)


@pytest.mark.parametrize(
    ("provider_error", "message"),
    [
        (WWDataAuthorizationError(), "authorization failed"),
        (WWDataUnavailableError(), "service is unavailable"),
        (WWDataResponseError(), "could not be retrieved"),
    ],
)
def test_get_transactions_summary_maps_provider_errors(
    provider_error: Exception,
    message: str,
) -> None:
    runtime = FakeToolRuntime(
        state={"current_turn": {"filters": ResolvedFilters()}},
        context={
            "ww_data_client": FakeTransactionSummaryWWDataClient(provider_error),
            "access_token": "secret-token",
        },
    )

    with pytest.raises(ToolException, match=message):
        _invoke_transaction_summary(runtime)


def test_get_transactions_returns_stable_payload_and_forwards_filters() -> None:
    client = FakeWWDataClient(_provider_response())
    stale_filters = ResolvedFilters(
        params=StandardParams(
            page=99,
            page_size=1,
            sort_by="title",
            search="stale resolved search",
            from_date=datetime(2025, 1, 1, tzinfo=timezone.utc),
            to_date=datetime(2025, 1, 2, tzinfo=timezone.utc),
        ),
        date_source="explicit",
    )
    runtime = FakeToolRuntime(
        state={"current_turn": {"filters": stale_filters}},
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    result = _invoke(
        runtime,
        page=2,
        page_size=20,
        sort_by="date",
        sort_order="asc",
        search="ShopRite",
        from_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
        to_date=datetime(2026, 6, 30, tzinfo=timezone.utc),
        category_ids=[UUID("43581d15-1a1d-49ce-adc6-f0fe6184f18a")],
        category_names=["Groceries", "Dining"],
        account_ids=[UUID("f219bb47-8f12-455e-b575-e384ac524999")],
        account_names=["Chase Checking"],
        merchant_search="ShopRite",
        transaction_types=["expense", "refund"],
        minimum_amount_cents=5000,
        maximum_amount_cents=10000,
        account_type=AccountTypeEnum.CHECKING,
    )

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
    assert client.calls[0]["transaction_filters"].model_dump(mode="json") == {
        "category_ids": ["43581d15-1a1d-49ce-adc6-f0fe6184f18a"],
        "category_names": ["Groceries", "Dining"],
        "account_ids": ["f219bb47-8f12-455e-b575-e384ac524999"],
        "account_names": ["Chase Checking"],
        "merchant_search": "ShopRite",
        "transaction_types": ["expense", "refund"],
        "minimum_amount_cents": 5000,
        "maximum_amount_cents": 10000,
        "account_type": "CHECKING",
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
    assert result["metadata"]["filters"] == {
        "page": 2,
        "page_size": 20,
        "sort_by": "date",
        "sort_order": "asc",
        "search": "ShopRite",
        "from_date": "2026-06-01T00:00:00Z",
        "to_date": "2026-06-30T00:00:00Z",
        "category_ids": ["43581d15-1a1d-49ce-adc6-f0fe6184f18a"],
        "category_names": ["Groceries", "Dining"],
        "account_ids": ["f219bb47-8f12-455e-b575-e384ac524999"],
        "account_names": ["Chase Checking"],
        "merchant_search": "ShopRite",
        "transaction_types": ["expense", "refund"],
        "minimum_amount_cents": 5000,
        "maximum_amount_cents": 10000,
        "account_type": "CHECKING",
    }
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
                                "args": {
                                    "page": 3,
                                    "sort_by": "date",
                                    "search": "weekly",
                                    "from_date": "2026-06-01T00:00:00Z",
                                    "to_date": "2026-06-30T23:59:59Z",
                                    "category_names": ["Groceries"],
                                    "minimum_amount_cents": 5000,
                                },
                                "id": "call-1",
                                "type": "tool_call",
                            }
                        ],
                    )
                ],
                "current_turn": {"filters": ResolvedFilters()},
            },
            context=cast(
                WingRuntimeContext,
                {
                    "ww_data_client": client,
                    "access_token": "secret-token",
                },
            ),
        )
    )

    tool_message = result["messages"][-1]
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.status == "success"
    assert client.calls[0]["access_token"] == "secret-token"
    assert client.calls[0]["params"].model_dump(mode="json") == {
        "page": 3,
        "page_size": 20,
        "sort_by": "date",
        "sort_order": "desc",
        "search": "weekly",
        "from_date": "2026-06-01T00:00:00Z",
        "to_date": "2026-06-30T23:59:59Z",
    }
    assert client.calls[0]["transaction_filters"].category_names == [
        "Groceries"
    ]
    assert client.calls[0]["transaction_filters"].minimum_amount_cents == 5000


def test_get_transactions_exposes_all_filters_to_the_model() -> None:
    schema_type = cast(BaseTool, get_transactions).tool_call_schema
    assert not isinstance(schema_type, dict)
    schema = schema_type.model_json_schema()

    assert set(schema["properties"]) == {
        "category_ids",
        "category_names",
        "account_ids",
        "account_names",
        "merchant_search",
        "transaction_types",
        "minimum_amount_cents",
        "maximum_amount_cents",
        "account_type",
        "page",
        "page_size",
        "sort_by",
        "sort_order",
        "search",
        "from_date",
        "to_date",
    }
    assert "runtime" not in schema["properties"]
    assert "omit when not requested" in schema["properties"]["from_date"][
        "description"
    ]
    assert "quarter without a year" in schema["properties"]["from_date"][
        "description"
    ]


def test_get_transactions_rejects_invalid_amount_range_without_provider_call() -> None:
    client = FakeWWDataClient(_provider_response())
    runtime = FakeToolRuntime(
        state={"current_turn": {"filters": ResolvedFilters()}},
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    with pytest.raises(ToolException, match="filters are invalid"):
        _invoke(
            runtime,
            minimum_amount_cents=10000,
            maximum_amount_cents=5000,
        )
    assert client.calls == []


def test_get_transactions_rejects_invalid_pagination_without_provider_call() -> None:
    client = FakeWWDataClient(_provider_response())
    runtime = FakeToolRuntime(
        state={"current_turn": {}},
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    with pytest.raises(ToolException, match="filters are invalid"):
        _invoke(runtime, page=0)
    assert client.calls == []


def test_get_transactions_ignores_resolved_filters() -> None:
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

    result = _invoke(runtime)

    assert len(client.calls) == 1
    assert client.calls[0]["params"].model_dump() == {
        "page": 1,
        "page_size": 30,
        "sort_by": None,
        "sort_order": "desc",
        "search": None,
        "from_date": None,
        "to_date": None,
    }
    assert client.calls[0]["transaction_filters"].model_dump() == {
        "category_ids": None,
        "category_names": None,
        "account_ids": None,
        "account_names": None,
        "merchant_search": None,
        "transaction_types": None,
        "minimum_amount_cents": None,
        "maximum_amount_cents": None,
        "account_type": None,
    }
    assert "from_date" not in result["metadata"]["filters"]
    assert "to_date" not in result["metadata"]["filters"]


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


class FakeCategorySpendingWWDataClient:
    def __init__(
        self,
        response: list[CategorySpendingResponse] | Exception,
    ) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def get_spending_by_category(
        self,
        **kwargs: Any,
    ) -> list[CategorySpendingResponse]:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def _category_spending_response() -> list[CategorySpendingResponse]:
    return [
        CategorySpendingResponse.model_validate(
            {
                "category_id": "43581d15-1a1d-49ce-adc6-f0fe6184f18a",
                "category": "Groceries",
                "expense": -8423,
            }
        )
    ]


def test_spending_toolnode_injects_runtime_context() -> None:
    client = FakeCategorySpendingWWDataClient(_category_spending_response())
    graph = StateGraph(ToolState, context_schema=WingRuntimeContext)
    graph.add_node("tools", ToolNode([get_spending_by_category]))
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
                                "name": "get_spending_by_category",
                                "args": {
                                    "from_date": "2026-01-01",
                                    "to_date": "2026-01-31",
                                },
                                "id": "call-spending",
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
                    "ww_data_client": client,
                    "access_token": "secret-token",
                },
            ),
        )
    )

    tool_message = result["messages"][-1]
    assert isinstance(tool_message, ToolMessage)
    assert tool_message.status == "success"
    assert client.calls[0]["access_token"] == "secret-token"
    assert client.calls[0]["params"].model_dump(mode="json") == {
        "from_date": "2026-01-01",
        "to_date": "2026-01-31",
        "category_ids": None,
        "category_names": None,
    }
    model_schema_type = cast(BaseTool, get_spending_by_category).tool_call_schema
    assert not isinstance(model_schema_type, dict)
    model_schema = model_schema_type.model_json_schema()
    assert "runtime" not in model_schema["properties"]
    assert set(model_schema["required"]) == {"from_date", "to_date"}
    assert "quarter without a year" in model_schema["properties"]["from_date"][
        "description"
    ]


def test_get_spending_by_category_forwards_dates_and_returns_safe_payload() -> None:
    client = FakeCategorySpendingWWDataClient(_category_spending_response())
    runtime = FakeToolRuntime(
        state={"current_turn": {}},
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    result = _invoke_spending_by_category(
        runtime,
        from_date=date(2026, 6, 1),
        to_date=date(2026, 6, 30),
    )

    params = client.calls[0]["params"]
    assert params.model_dump() == {
        "from_date": date(2026, 6, 1),
        "to_date": date(2026, 6, 30),
        "category_ids": None,
        "category_names": None,
    }
    assert client.calls[0]["access_token"] == "secret-token"
    assert result == {
        "result_type": "spending_by_category",
        "data": {
            "categories": [
                {
                    "category_id": "43581d15-1a1d-49ce-adc6-f0fe6184f18a",
                    "category": "Groceries",
                    "expense": -8423,
                }
            ]
        },
        "metadata": {
            "filters": {
                "from_date": "2026-06-01",
                "to_date": "2026-06-30",
            },
            "source": "wealth-wing-data",
        },
        "ui": "spending_by_category",
    }
    assert "secret-token" not in str(result)


def test_get_spending_by_category_requires_dates() -> None:
    client = FakeCategorySpendingWWDataClient([])
    runtime = FakeToolRuntime(
        state={"current_turn": {"filters": ResolvedFilters()}},
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    with pytest.raises(TypeError):
        _invoke_spending_by_category(runtime)
    assert client.calls == []


def test_get_spending_by_category_rejects_invalid_filters_without_provider_call() -> None:
    client = FakeCategorySpendingWWDataClient(_category_spending_response())
    runtime = FakeToolRuntime(
        state={"current_turn": {}},
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    with pytest.raises(ToolException, match="filters are invalid"):
        _invoke_spending_by_category(
            runtime,
            from_date="invalid",
            to_date=date(2026, 6, 30),
        )
    assert client.calls == []


@pytest.mark.parametrize(
    "context",
    [{}, {"ww_data_client": FakeCategorySpendingWWDataClient([])}],
)
def test_get_spending_by_category_requires_runtime_dependencies(
    context: dict[str, Any],
) -> None:
    runtime = FakeToolRuntime(
        state={"current_turn": {"filters": ResolvedFilters()}},
        context=context,
    )

    with pytest.raises(ToolException):
        _invoke_spending_by_category(
            runtime,
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )


@pytest.mark.parametrize(
    ("provider_error", "message"),
    [
        (WWDataAuthorizationError(), "authorization failed"),
        (WWDataUnavailableError(), "service is unavailable"),
        (WWDataResponseError(), "could not be retrieved"),
    ],
)
def test_get_spending_by_category_maps_provider_errors(
    provider_error: Exception,
    message: str,
) -> None:
    runtime = FakeToolRuntime(
        state={"current_turn": {"filters": ResolvedFilters()}},
        context={
            "ww_data_client": FakeCategorySpendingWWDataClient(provider_error),
            "access_token": "secret-token",
        },
    )

    with pytest.raises(ToolException, match=message):
        _invoke_spending_by_category(
            runtime,
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )


class FakeCashFlowWWDataClient:
    def __init__(self, response: CashFlowHistoryResponse | Exception) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def get_cash_flow_history(self, **kwargs: Any) -> CashFlowHistoryResponse:
        self.calls.append(kwargs)
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def test_get_cash_flow_history_returns_stable_payload_and_forwards_inputs() -> None:
    client = FakeCashFlowWWDataClient(_cash_flow_response())
    runtime = FakeToolRuntime(
        state={"current_turn": {}},
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    result = _invoke_cash_flow(
        runtime,
        from_date=date(2026, 6, 1),
        to_date=date(2026, 6, 30),
        granularity="week",
        category_ids=["43581d15-1a1d-49ce-adc6-f0fe6184f18a"],
        account_ids=["f219bb47-8f12-455e-b575-e384ac524999"],
    )

    request = client.calls[0]["request"]
    assert request.model_dump() == {
        "from_date": date(2026, 6, 1),
        "to_date": date(2026, 6, 30),
        "category_ids": [UUID("43581d15-1a1d-49ce-adc6-f0fe6184f18a")],
        "account_ids": [UUID("f219bb47-8f12-455e-b575-e384ac524999")],
        "project_ids": None,
        "granularity": "week",
    }
    assert client.calls[0]["access_token"] == "secret-token"
    assert result["data"] == {
        "timezone": "America/New_York",
        "from_date": "2026-06-01",
        "to_date": "2026-06-30",
        "granularity": "month",
        "periods": [
            {
                "period_start": "2026-06-01T00:00:00-04:00",
                "period_end": "2026-06-30T23:59:59.999999-04:00",
                "income": 520000,
                "expense": -184500,
                "refunds": 2500,
                "net": 338000,
                "transaction_count": 73,
            }
        ],
    }
    assert result["metadata"] == {
        "filters": {
            "from_date": "2026-06-01",
            "to_date": "2026-06-30",
            "category_ids": ["43581d15-1a1d-49ce-adc6-f0fe6184f18a"],
            "account_ids": ["f219bb47-8f12-455e-b575-e384ac524999"],
            "granularity": "week",
        },
        "source": "wealth-wing-data",
    }
    assert "secret-token" not in str(result)


def test_get_cash_flow_history_rejects_invalid_date_range() -> None:
    client = FakeCashFlowWWDataClient(_cash_flow_response())
    runtime = FakeToolRuntime(
        state={"current_turn": {}},
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    with pytest.raises(ToolException, match="filters are invalid"):
        _invoke_cash_flow(
            runtime,
            from_date=date(2026, 6, 30),
            to_date=date(2026, 6, 1),
        )
    assert client.calls == []


def test_get_cash_flow_history_exposes_current_year_date_guidance() -> None:
    schema_type = cast(BaseTool, get_cash_flow_history).tool_call_schema
    assert not isinstance(schema_type, dict)
    schema = schema_type.model_json_schema()

    assert "runtime" not in schema["properties"]
    assert set(schema["required"]) == {"from_date", "to_date"}
    assert "quarter without a year" in schema["properties"]["from_date"][
        "description"
    ]


def test_get_cash_flow_history_rejects_missing_dates() -> None:
    client = FakeCashFlowWWDataClient(_cash_flow_response())
    runtime = FakeToolRuntime(
        state={"current_turn": {}},
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    with pytest.raises(TypeError):
        _invoke_cash_flow(runtime)
    assert client.calls == []


@pytest.mark.parametrize(
    ("provider_error", "message"),
    [
        (WWDataAuthorizationError(), "authorization failed"),
        (WWDataUnavailableError(), "service is unavailable"),
        (WWDataResponseError(), "could not be retrieved"),
    ],
)
def test_get_cash_flow_history_maps_provider_errors(
    provider_error: Exception,
    message: str,
) -> None:
    runtime = FakeToolRuntime(
        state={"current_turn": {}},
        context={
            "ww_data_client": FakeCashFlowWWDataClient(provider_error),
            "access_token": "secret-token",
        },
    )

    with pytest.raises(ToolException, match=message):
        _invoke_cash_flow(
            runtime,
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )


@pytest.mark.parametrize(
    "context",
    [{}, {"ww_data_client": FakeCashFlowWWDataClient(_cash_flow_response())}],
)
def test_get_cash_flow_history_requires_runtime_dependencies(
    context: dict[str, Any],
) -> None:
    runtime = FakeToolRuntime(
        state={"current_turn": {}},
        context=context,
    )

    with pytest.raises(ToolException):
        _invoke_cash_flow(
            runtime,
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
        )
