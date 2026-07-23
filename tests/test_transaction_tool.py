from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

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


def _invoke(runtime: FakeToolRuntime, **kwargs: Any) -> dict[str, Any]:
    assert get_transactions.coroutine is not None
    return asyncio.run(get_transactions.coroutine(runtime=runtime, **kwargs))


def _invoke_cash_flow(
    runtime: FakeToolRuntime,
    **kwargs: Any,
) -> dict[str, Any]:
    assert get_cash_flow_history.coroutine is not None
    return asyncio.run(
        get_cash_flow_history.coroutine(
            text="show cash flow",
            runtime=runtime,
            **kwargs,
        )
    )


def _invoke_spending_by_category(runtime: FakeToolRuntime) -> dict[str, Any]:
    assert get_spending_by_category.coroutine is not None
    return asyncio.run(
        get_spending_by_category.coroutine(
            text="show spending by category",
            runtime=runtime,
        )
    )


def _invoke_transaction_summary(runtime: FakeToolRuntime) -> dict[str, Any]:
    assert get_transactions_summary.coroutine is not None
    return asyncio.run(
        get_transactions_summary.coroutine(
            text="summarize my transactions",
            runtime=runtime,
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
    filters = ResolvedFilters(
        params=StandardParams(
            from_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
            to_date=datetime(2026, 6, 30, tzinfo=timezone.utc),
        ),
        date_source="explicit",
    )
    runtime = FakeToolRuntime(
        state={"current_turn": {"filters": filters}},
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    result = _invoke_transaction_summary(runtime)

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
            "filters": filters.model_dump(mode="json"),
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
        def now(cls, tz: timezone | None = None) -> FrozenDateTime:
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
        _invoke_transaction_summary(runtime)
    assert client.calls == []


def test_get_transactions_summary_rejects_unsupported_filters() -> None:
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

    with pytest.raises(ToolException, match="not supported"):
        _invoke_transaction_summary(runtime)
    assert client.calls == []


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

    result = _invoke(
        runtime,
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
    assert client.calls[0]["transaction_filters"].category_names == [
        "Groceries"
    ]
    assert client.calls[0]["transaction_filters"].minimum_amount_cents == 5000


def test_get_transactions_exposes_only_endpoint_filters_to_the_model() -> None:
    schema = get_transactions.tool_call_schema.model_json_schema()

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
    }


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


def test_get_spending_by_category_forwards_dates_and_returns_safe_payload() -> None:
    client = FakeCategorySpendingWWDataClient(_category_spending_response())
    runtime = FakeToolRuntime(
        state={
            "current_turn": {
                "filters": ResolvedFilters(
                    params=StandardParams(
                        from_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
                        to_date=datetime(2026, 6, 30, tzinfo=timezone.utc),
                    ),
                    date_source="explicit",
                )
            }
        },
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    result = _invoke_spending_by_category(runtime)

    params = client.calls[0]["params"]
    assert params.model_dump() == {
        "from_date": datetime(2026, 6, 1, tzinfo=timezone.utc),
        "to_date": datetime(2026, 6, 30, tzinfo=timezone.utc),
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
                "from_date": "2026-06-01T00:00:00Z",
                "to_date": "2026-06-30T00:00:00Z",
            },
            "source": "wealth-wing-data",
        },
        "ui": "spending_by_category",
    }
    assert "secret-token" not in str(result)


def test_get_spending_by_category_forwards_no_dates() -> None:
    client = FakeCategorySpendingWWDataClient([])
    runtime = FakeToolRuntime(
        state={"current_turn": {"filters": ResolvedFilters()}},
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    result = _invoke_spending_by_category(runtime)

    assert client.calls[0]["params"].model_dump(exclude_none=True) == {}
    assert result["data"] == {"categories": []}


def test_get_spending_by_category_rejects_invalid_filters_without_provider_call() -> None:
    client = FakeCategorySpendingWWDataClient(_category_spending_response())
    runtime = FakeToolRuntime(
        state={"current_turn": {"filters": {"params": {"from_date": "invalid"}}}},
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    with pytest.raises(ToolException, match="filters are invalid"):
        _invoke_spending_by_category(runtime)
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
        _invoke_spending_by_category(runtime)


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
        _invoke_spending_by_category(runtime)


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
        state={
            "current_turn": {
                "filters": ResolvedFilters(
                    params=StandardParams(
                        from_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
                        to_date=datetime(2026, 6, 30, tzinfo=timezone.utc),
                    ),
                    date_source="explicit",
                )
            }
        },
        context={"ww_data_client": client, "access_token": "secret-token"},
    )

    result = _invoke_cash_flow(
        runtime,
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
    assert result["metadata"]["source"] == "wealth-wing-data"
    assert "secret-token" not in str(result)


def test_get_cash_flow_history_rejects_partial_date_range() -> None:
    client = FakeCashFlowWWDataClient(_cash_flow_response())
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
        state={"current_turn": {"filters": ResolvedFilters()}},
        context={
            "ww_data_client": FakeCashFlowWWDataClient(provider_error),
            "access_token": "secret-token",
        },
    )

    with pytest.raises(ToolException, match=message):
        _invoke_cash_flow(runtime)


@pytest.mark.parametrize(
    "context",
    [{}, {"ww_data_client": FakeCashFlowWWDataClient(_cash_flow_response())}],
)
def test_get_cash_flow_history_requires_runtime_dependencies(
    context: dict[str, Any],
) -> None:
    runtime = FakeToolRuntime(
        state={"current_turn": {"filters": ResolvedFilters()}},
        context=context,
    )

    with pytest.raises(ToolException):
        _invoke_cash_flow(runtime)
