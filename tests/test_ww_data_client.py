from __future__ import annotations

import asyncio
import json
from datetime import date, datetime, timezone

import httpx
import pytest
from pydantic import ValidationError

from src.providers.ww_data_client import (
    WWDataAuthorizationError,
    WWDataClient,
    WWDataResponseError,
    WWDataUnavailableError,
)
from src.providers.ww_data_schemas import (
    AccountTypeEnum,
    CashFlowHistoryRequest,
    CategorySpendingParams,
    TransactionSummaryRequest,
    TransactionsAllRequest,
    TransactionsQueryParams,
)


TRANSACTION_ID = "47c45f67-93a0-4cb2-a2ef-01d241b16a6c"
CATEGORY_ID = "43581d15-1a1d-49ce-adc6-f0fe6184f18a"
USER_ID = "87f9df12-5851-4937-9e5e-d357fee7d436"
ACCOUNT_ID = "f219bb47-8f12-455e-b575-e384ac524999"
PROJECT_ID = "a2d095d9-f36f-440c-8d60-7e6f83ff7308"


def _response_payload() -> dict[str, object]:
    return {
        "transactions": [
            {
                "uuid": TRANSACTION_ID,
                "user_id": USER_ID,
                "category_id": CATEGORY_ID,
                "account_id": None,
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
                "account_name": None,
            }
        ],
        "has_more": True,
        "total_pages": 3,
        "total_count": 41,
    }


def test_get_transactions_forwards_auth_and_supported_params() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=_response_payload())

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test/")
            result = await client.get_transactions(
                access_token="secret-token",
                params=TransactionsQueryParams(
                    page=2,
                    page_size=20,
                    sort_by="date",
                    sort_order="asc",
                    search="ShopRite",
                    from_date=datetime(2026, 6, 1, tzinfo=timezone.utc),
                    to_date=datetime(2026, 6, 30, 23, 59, tzinfo=timezone.utc),
                ),
                transaction_filters=TransactionsAllRequest(
                    category_ids=[CATEGORY_ID],
                    category_names=["Groceries", "Dining"],
                    account_ids=[ACCOUNT_ID],
                    account_names=["Chase Checking"],
                    merchant_search="ShopRite",
                    transaction_types=["expense", "refund"],
                    minimum_amount_cents=5000,
                    maximum_amount_cents=10000,
                    account_type=AccountTypeEnum.CHECKING,
                ),
            )

        assert result.total_count == 41
        assert result.transactions[0].title == "ShopRite"

    asyncio.run(run())

    request = captured["request"]
    assert isinstance(request, httpx.Request)
    assert str(request.url.copy_with(query=None)) == (
        "https://data.example.test/transaction/all"
    )
    assert request.headers["Authorization"] == "Bearer secret-token"
    assert {
        key: value
        for key, value in request.url.params.items()
        if key not in {
            "category_ids",
            "category_names",
            "account_ids",
            "account_names",
            "transaction_types",
        }
    } == {
        "page": "2",
        "page_size": "20",
        "sort_by": "date",
        "sort_order": "asc",
        "search": "ShopRite",
        "from_date": "2026-06-01T00:00:00Z",
        "to_date": "2026-06-30T23:59:00Z",
        "merchant_search": "ShopRite",
        "minimum_amount_cents": "5000",
        "maximum_amount_cents": "10000",
        "account_type": "CHECKING",
    }
    assert request.url.params.get_list("category_ids") == [CATEGORY_ID]
    assert request.url.params.get_list("category_names") == [
        "Groceries",
        "Dining",
    ]
    assert request.url.params.get_list("account_ids") == [ACCOUNT_ID]
    assert request.url.params.get_list("account_names") == ["Chase Checking"]
    assert request.url.params.get_list("transaction_types") == [
        "expense",
        "refund",
    ]


def test_transactions_all_request_rejects_invalid_amount_range() -> None:
    with pytest.raises(
        ValidationError,
        match="minimum_amount_cents cannot exceed maximum_amount_cents",
    ):
        TransactionsAllRequest(
            minimum_amount_cents=10000,
            maximum_amount_cents=5000,
        )


@pytest.mark.parametrize(
    ("status_code", "exception_type"),
    [(401, WWDataAuthorizationError), (403, WWDataAuthorizationError), (500, WWDataResponseError)],
)
def test_get_transactions_maps_http_errors(
    status_code: int,
    exception_type: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request)

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test")
            with pytest.raises(exception_type):
                await client.get_transactions(
                    access_token="secret-token",
                    params=TransactionsQueryParams(),
                )

    asyncio.run(run())


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"transactions": [{"title": "incomplete"}]}),
    ],
)
def test_get_transactions_rejects_invalid_responses(response: httpx.Response) -> None:
    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: response)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test")
            with pytest.raises(WWDataResponseError):
                await client.get_transactions(
                    access_token="secret-token",
                    params=TransactionsQueryParams(),
                )

    asyncio.run(run())


def test_get_transactions_maps_network_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test")
            with pytest.raises(WWDataUnavailableError):
                await client.get_transactions(
                    access_token="secret-token",
                    params=TransactionsQueryParams(),
                )

    asyncio.run(run())


def _category_spending_payload() -> list[dict[str, object]]:
    return [
        {
            "category_id": CATEGORY_ID,
            "category": "Groceries",
            "expense": -8423,
        }
    ]


def test_get_spending_by_category_forwards_auth_and_json_body() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=_category_spending_payload())

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test/")
            result = await client.get_spending_by_category(
                access_token="secret-token",
                params=CategorySpendingParams(
                    from_date=datetime(2026, 6, 1),
                    to_date=datetime(2026, 6, 30, 23, 59, tzinfo=timezone.utc),
                ),
            )

        assert result[0].category == "Groceries"
        assert result[0].expense == -8423

    asyncio.run(run())

    request = captured["request"]
    assert isinstance(request, httpx.Request)
    assert request.method == "POST"
    assert str(request.url) == "https://data.example.test/spending_by_category"
    assert request.headers["Authorization"] == "Bearer secret-token"
    assert json.loads(request.content) == {
        "from_date": "2026-06-01T00:00:00Z",
        "to_date": "2026-06-30T23:59:00Z",
    }


def test_get_spending_by_category_omits_empty_date_bounds() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=[])

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test")
            result = await client.get_spending_by_category(
                access_token="secret-token",
                params=CategorySpendingParams(),
            )

        assert result == []

    asyncio.run(run())

    request = captured["request"]
    assert isinstance(request, httpx.Request)
    assert json.loads(request.content) == {}


@pytest.mark.parametrize(
    ("status_code", "exception_type"),
    [
        (401, WWDataAuthorizationError),
        (403, WWDataAuthorizationError),
        (500, WWDataResponseError),
    ],
)
def test_get_spending_by_category_maps_http_errors(
    status_code: int,
    exception_type: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request)

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test")
            with pytest.raises(exception_type):
                await client.get_spending_by_category(
                    access_token="secret-token",
                    params=CategorySpendingParams(),
                )

    asyncio.run(run())


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(
            200,
            json=[{"category_id": CATEGORY_ID, "category": "Groceries"}],
        ),
    ],
)
def test_get_spending_by_category_rejects_invalid_responses(
    response: httpx.Response,
) -> None:
    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: response)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test")
            with pytest.raises(WWDataResponseError):
                await client.get_spending_by_category(
                    access_token="secret-token",
                    params=CategorySpendingParams(),
                )

    asyncio.run(run())


def test_get_spending_by_category_maps_network_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test")
            with pytest.raises(WWDataUnavailableError):
                await client.get_spending_by_category(
                    access_token="secret-token",
                    params=CategorySpendingParams(),
                )

    asyncio.run(run())


def _cash_flow_response_payload() -> dict[str, object]:
    return {
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


def test_get_cash_flow_history_forwards_auth_and_query_parameters() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=_cash_flow_response_payload())

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test/")
            result = await client.get_cash_flow_history(
                access_token="secret-token",
                request=CashFlowHistoryRequest(
                    from_date=date(2026, 6, 1),
                    to_date=date(2026, 6, 30),
                    category_ids=[CATEGORY_ID],
                    account_ids=[ACCOUNT_ID],
                    project_ids=[PROJECT_ID],
                    granularity="month",
                ),
            )

        assert result.timezone == "America/New_York"
        assert result.periods[0].net == 338000

    asyncio.run(run())

    request = captured["request"]
    assert isinstance(request, httpx.Request)
    assert request.method == "GET"
    assert str(request.url.copy_with(query=None)) == (
        "https://data.example.test/cash-flow-history"
    )
    assert request.headers["Authorization"] == "Bearer secret-token"
    assert list(request.url.params.multi_items()) == [
        ("from_date", "2026-06-01"),
        ("to_date", "2026-06-30"),
        ("category_ids", CATEGORY_ID),
        ("account_ids", ACCOUNT_ID),
        ("project_ids", PROJECT_ID),
        ("granularity", "month"),
    ]


@pytest.mark.parametrize(
    ("status_code", "exception_type"),
    [(401, WWDataAuthorizationError), (403, WWDataAuthorizationError), (500, WWDataResponseError)],
)
def test_get_cash_flow_history_maps_http_errors(
    status_code: int,
    exception_type: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request)

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test")
            with pytest.raises(exception_type):
                await client.get_cash_flow_history(
                    access_token="secret-token",
                    request=CashFlowHistoryRequest(
                        from_date=date(2026, 6, 1),
                        to_date=date(2026, 6, 30),
                    ),
                )

    asyncio.run(run())


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json={"timezone": "UTC", "periods": []}),
    ],
)
def test_get_cash_flow_history_rejects_invalid_responses(
    response: httpx.Response,
) -> None:
    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: response)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test")
            with pytest.raises(WWDataResponseError):
                await client.get_cash_flow_history(
                    access_token="secret-token",
                    request=CashFlowHistoryRequest(
                        from_date=date(2026, 6, 1),
                        to_date=date(2026, 6, 30),
                    ),
                )

    asyncio.run(run())


def test_get_cash_flow_history_maps_network_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test")
            with pytest.raises(WWDataUnavailableError):
                await client.get_cash_flow_history(
                    access_token="secret-token",
                    request=CashFlowHistoryRequest(
                        from_date=date(2026, 6, 1),
                        to_date=date(2026, 6, 30),
                    ),
                )

    asyncio.run(run())


def _transaction_summary_response_payload() -> dict[str, object]:
    return {
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
        "included_account_types": ["SAVINGS", "CHECKING"],
    }


def test_transaction_summary_request_defaults_deduplicates_and_validates() -> None:
    request = TransactionSummaryRequest(
        from_date=date(2026, 6, 1),
        to_date=date(2026, 6, 30),
    )
    assert request.account_types == [
        AccountTypeEnum.CHECKING,
        AccountTypeEnum.CREDIT_CARD,
    ]

    deduplicated = TransactionSummaryRequest(
        from_date=date(2026, 6, 1),
        to_date=date(2026, 6, 30),
        account_types=[
            AccountTypeEnum.SAVINGS,
            AccountTypeEnum.CHECKING,
            AccountTypeEnum.SAVINGS,
        ],
    )
    assert deduplicated.account_types == [
        AccountTypeEnum.SAVINGS,
        AccountTypeEnum.CHECKING,
    ]

    with pytest.raises(ValueError, match="from_date cannot be after to_date"):
        TransactionSummaryRequest(
            from_date=date(2026, 7, 1),
            to_date=date(2026, 6, 30),
        )

    with pytest.raises(ValueError):
        TransactionSummaryRequest(
            from_date=date(2026, 6, 1),
            to_date=date(2026, 6, 30),
            account_types=[],
        )


def test_get_transaction_summary_forwards_auth_and_query_parameters() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        return httpx.Response(200, json=_transaction_summary_response_payload())

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test/")
            result = await client.get_transaction_summary(
                access_token="secret-token",
                request=TransactionSummaryRequest(
                    from_date=date(2026, 6, 1),
                    to_date=date(2026, 6, 30),
                    account_types=[
                        AccountTypeEnum.SAVINGS,
                        AccountTypeEnum.CHECKING,
                        AccountTypeEnum.SAVINGS,
                    ],
                ),
            )

        assert result.gross_expense == 184500
        assert result.average_expense == 2713.24
        assert result.from_date == date(2026, 6, 1)
        assert result.included_account_types == [
            AccountTypeEnum.SAVINGS,
            AccountTypeEnum.CHECKING,
        ]

    asyncio.run(run())

    request = captured["request"]
    assert isinstance(request, httpx.Request)
    assert request.method == "GET"
    assert str(request.url.copy_with(query=None)) == (
        "https://data.example.test/transaction/summary"
    )
    assert request.headers["Authorization"] == "Bearer secret-token"
    assert list(request.url.params.multi_items()) == [
        ("from_date", "2026-06-01"),
        ("to_date", "2026-06-30"),
        ("account_types", "SAVINGS"),
        ("account_types", "CHECKING"),
    ]


def test_get_transaction_summary_uses_default_account_types() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["request"] = request
        payload = _transaction_summary_response_payload()
        payload["included_account_types"] = ["CHECKING", "CREDIT_CARD"]
        return httpx.Response(200, json=payload)

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test")
            await client.get_transaction_summary(
                access_token="secret-token",
                request=TransactionSummaryRequest(
                    from_date=date(2026, 6, 1),
                    to_date=date(2026, 6, 30),
                ),
            )

    asyncio.run(run())

    request = captured["request"]
    assert isinstance(request, httpx.Request)
    assert request.url.params.get_list("account_types") == [
        "CHECKING",
        "CREDIT_CARD",
    ]


@pytest.mark.parametrize(
    ("status_code", "exception_type"),
    [
        (400, WWDataResponseError),
        (401, WWDataAuthorizationError),
        (403, WWDataAuthorizationError),
        (503, WWDataResponseError),
    ],
)
def test_get_transaction_summary_maps_http_errors(
    status_code: int,
    exception_type: type[Exception],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, request=request)

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test")
            with pytest.raises(exception_type):
                await client.get_transaction_summary(
                    access_token="secret-token",
                    request=TransactionSummaryRequest(
                        from_date=date(2026, 6, 1),
                        to_date=date(2026, 6, 30),
                    ),
                )

    asyncio.run(run())


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(
            200,
            json={
                "from_date": "2026-06-01",
                "to_date": "2026-06-30",
                "included_account_types": ["CHECKING"],
            },
        ),
    ],
)
def test_get_transaction_summary_rejects_invalid_responses(
    response: httpx.Response,
) -> None:
    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: response)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test")
            with pytest.raises(WWDataResponseError):
                await client.get_transaction_summary(
                    access_token="secret-token",
                    request=TransactionSummaryRequest(
                        from_date=date(2026, 6, 1),
                        to_date=date(2026, 6, 30),
                    ),
                )

    asyncio.run(run())


def test_get_transaction_summary_maps_network_failures() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    async def run() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(handler)
        ) as http_client:
            client = WWDataClient(http_client, "https://data.example.test")
            with pytest.raises(WWDataUnavailableError):
                await client.get_transaction_summary(
                    access_token="secret-token",
                    request=TransactionSummaryRequest(
                        from_date=date(2026, 6, 1),
                        to_date=date(2026, 6, 30),
                    ),
                )

    asyncio.run(run())
