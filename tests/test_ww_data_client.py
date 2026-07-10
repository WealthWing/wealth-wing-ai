from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import httpx
import pytest

from src.providers.ww_data_client import (
    WWDataAuthorizationError,
    WWDataClient,
    WWDataResponseError,
    WWDataUnavailableError,
)
from src.providers.ww_data_schemas import TransactionsQueryParams


TRANSACTION_ID = "47c45f67-93a0-4cb2-a2ef-01d241b16a6c"
CATEGORY_ID = "43581d15-1a1d-49ce-adc6-f0fe6184f18a"
USER_ID = "87f9df12-5851-4937-9e5e-d357fee7d436"


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
    assert dict(request.url.params) == {
        "page": "2",
        "page_size": "20",
        "sort_by": "date",
        "sort_order": "asc",
        "search": "ShopRite",
        "from_date": "2026-06-01T00:00:00Z",
        "to_date": "2026-06-30T23:59:00Z",
    }


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
