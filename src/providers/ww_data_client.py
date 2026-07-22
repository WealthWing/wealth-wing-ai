from __future__ import annotations

import httpx
from pydantic import TypeAdapter, ValidationError

from src.providers.ww_data_schemas import (
    CashFlowHistoryRequest,
    CashFlowHistoryResponse,
    CategorySpendingParams,
    CategorySpendingResponse,
    TransactionSummaryRequest,
    TransactionSummaryResponse,
    TransactionsAllResponse,
    TransactionsQueryParams,
)


class WWDataClientError(Exception):
    pass


class WWDataUnavailableError(WWDataClientError):
    pass


class WWDataAuthorizationError(WWDataClientError):
    pass


class WWDataResponseError(WWDataClientError):
    pass


class WWDataClient:
    def __init__(
        self,
        http_client: httpx.AsyncClient,
        base_url: str,
    ) -> None:
        self._http_client = http_client
        self._base_url = base_url.rstrip("/")

    async def get_transactions(
        self,
        *,
        access_token: str,
        params: TransactionsQueryParams,
    ) -> TransactionsAllResponse:
        query_params = params.model_dump(mode="json", exclude_none=True)
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            response = await self._http_client.get(
                f"{self._base_url}/transaction/all",
                params=query_params,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise WWDataAuthorizationError(
                    "ww-data authorization failed"
                ) from exc

            raise WWDataResponseError("ww-data returned an error response") from exc
        except (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.NetworkError,
            httpx.RequestError,
        ) as exc:
            raise WWDataUnavailableError("ww-data is unavailable") from exc

        try:
            return TransactionsAllResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise WWDataResponseError("ww-data returned invalid JSON") from exc

    async def get_spending_by_category(
        self,
        *,
        access_token: str,
        params: CategorySpendingParams,
    ) -> list[CategorySpendingResponse]:
        payload = params.model_dump(mode="json", exclude_none=True)
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            response = await self._http_client.post(
                f"{self._base_url}/spending_by_category",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise WWDataAuthorizationError(
                    "ww-data authorization failed"
                ) from exc

            raise WWDataResponseError("ww-data returned an error response") from exc
        except (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.NetworkError,
            httpx.RequestError,
        ) as exc:
            raise WWDataUnavailableError("ww-data is unavailable") from exc

        try:
            return TypeAdapter(list[CategorySpendingResponse]).validate_python(
                response.json()
            )
        except (ValueError, ValidationError) as exc:
            raise WWDataResponseError("ww-data returned invalid JSON") from exc

    async def get_cash_flow_history(
        self,
        *,
        access_token: str,
        request: CashFlowHistoryRequest,
    ) -> CashFlowHistoryResponse:
        query_params = request.model_dump(mode="json", exclude_none=True)
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            response = await self._http_client.get(
                f"{self._base_url}/transaction/cash-flow-history",
                params=query_params,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise WWDataAuthorizationError(
                    "ww-data authorization failed"
                ) from exc

            raise WWDataResponseError("ww-data returned an error response") from exc
        except (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.NetworkError,
            httpx.RequestError,
        ) as exc:
            raise WWDataUnavailableError("ww-data is unavailable") from exc

        try:
            return CashFlowHistoryResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise WWDataResponseError("ww-data returned invalid JSON") from exc

    async def get_transaction_summary(
        self,
        *,
        access_token: str,
        request: TransactionSummaryRequest,
    ) -> TransactionSummaryResponse:
        """Return an organization-scoped transaction summary for a date range."""
        query_params = request.model_dump(mode="json")
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            response = await self._http_client.get(
                f"{self._base_url}/transaction/summary",
                params=query_params,
                headers=headers,
            )
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                raise WWDataAuthorizationError(
                    "ww-data authorization failed"
                ) from exc

            raise WWDataResponseError("ww-data returned an error response") from exc
        except (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.NetworkError,
            httpx.RequestError,
        ) as exc:
            raise WWDataUnavailableError("ww-data is unavailable") from exc

        try:
            return TransactionSummaryResponse.model_validate(response.json())
        except (ValueError, ValidationError) as exc:
            raise WWDataResponseError("ww-data returned invalid JSON") from exc
