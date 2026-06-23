from __future__ import annotations

from datetime import date
from typing import Any

import httpx


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
        access_token: str | None,
        category: str | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "page": 1,
            "page_size": limit,
        }

        if start_date is not None:
            params["from_date"] = start_date.isoformat()

        if end_date is not None:
            params["to_date"] = end_date.isoformat()

        headers: dict[str, str] = {}
        if access_token is not None:
            headers["Authorization"] = f"Bearer {access_token}"

        try:
            response = await self._http_client.get(
                f"{self._base_url}/transaction/all",
                params=params,
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
            return response.json()
        except ValueError as exc:
            raise WWDataResponseError("ww-data returned invalid JSON") from exc
