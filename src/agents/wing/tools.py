from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Literal
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from langchain_core.tools import BaseTool, ToolException, tool
from langgraph.prebuilt import ToolRuntime
from pydantic import BaseModel, Field, ValidationError
from src.providers.ww_data_client import (
    WWDataAuthorizationError,
    WWDataClientError,
    WWDataUnavailableError,
)
from src.providers.ww_data_schemas import (
    AccountTypeEnum,
    CashFlowHistoryRequest,
    CategorySpendingParams,
    TransactionResponse,
    TransactionSummaryRequest,
    TransactionsAllRequest,
    TransactionsQueryParams,
)
from src.utils.format import format_cents

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[3]))

from src.agents.wing.state import (
    ProfileId,
    ResolvedFilters,
    ToolResultPayload,
    WingGraphState,
    WingRuntimeContext,
)
from src.agents.wing.tool_schemas import GetTransactionsInput





class TransactionsByCategory(BaseModel):
    category: str = Field(..., description="The category of the transactions.")
    total_amount: float = Field(..., description="The total amount for the category.")
    transactions: list[dict] = Field(
        ..., description="The list of transactions for the category."
    )


@tool
async def get_spending_by_category(
    text: str,
    runtime: ToolRuntime[WingRuntimeContext, WingGraphState],
) -> ToolResultPayload:
    """Return expense totals grouped by category for the resolved date range."""
    del text
    filters = runtime.state.get("current_turn", {}).get("filters", {})
    try:
        resolved_filters = _coerce_resolved_filters(filters)
        params = CategorySpendingParams(
            from_date=resolved_filters.params.from_date,
            to_date=resolved_filters.params.to_date,
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise ToolException("Spending request filters are invalid.") from exc

    ww_data_client = runtime.context.get("ww_data_client")
    access_token = runtime.context.get("access_token")
    if ww_data_client is None:
        raise ToolException("Spending data service is not configured.")
    if not access_token:
        raise ToolException("Spending data authorization is unavailable.")

    try:
        categories = await ww_data_client.get_spending_by_category(
            access_token=access_token,
            params=params,
        )
    except WWDataAuthorizationError as exc:
        raise ToolException("Spending data authorization failed.") from exc
    except WWDataUnavailableError as exc:
        raise ToolException("Spending data service is unavailable.") from exc
    except WWDataClientError as exc:
        raise ToolException("Spending data could not be retrieved.") from exc

    return _tool_result(
        result_type="spending_by_category",
        data={
            "categories": [
                {
                    "category_id": str(category.category_id),
                    "category": category.category,
                    "expense": category.expense,
                }
                for category in categories
            ],
        },
        metadata={
            "filters": params.model_dump(mode="json", exclude_none=True),
            "source": "wealth-wing-data",
        },
        ui="spending_by_category",
    )


@tool
async def get_transactions_summary(
    text: str,
    runtime: ToolRuntime[WingRuntimeContext, WingGraphState],
) -> ToolResultPayload:
    """Return a transaction summary for the resolved date range."""
    del text
    filters = runtime.state.get("current_turn", {}).get("filters", {})
    try:
        resolved_filters = _coerce_resolved_filters(filters)
        if resolved_filters.params.filter_by or resolved_filters.params.search:
            raise ToolException(
                "Filtered transaction summaries are not supported by the data "
                "service yet."
            )
        from_date, to_date = _cash_flow_date_range(resolved_filters)
        query = TransactionSummaryRequest(
            from_date=from_date,
            to_date=to_date,
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise ToolException("Transaction summary request filters are invalid.") from exc

    ww_data_client = runtime.context.get("ww_data_client")
    access_token = runtime.context.get("access_token")

    if ww_data_client is None:
        raise ToolException("Transaction data service is not configured.")
    if not access_token:
        raise ToolException("Transaction data authorization is unavailable.")

    try:
        summary_response = await ww_data_client.get_transaction_summary(
            access_token=access_token,
            request=query,
        )
    except WWDataAuthorizationError as exc:
        raise ToolException("Transaction data authorization failed.") from exc
    except WWDataUnavailableError as exc:
        raise ToolException("Transaction data service is unavailable.") from exc
    except WWDataClientError as exc:
        raise ToolException("Transaction data could not be retrieved.") from exc

    return _tool_result(
        result_type="transaction_summary",
        data=summary_response.model_dump(mode="json"),
        metadata={
            "filters": _serialize_tool_metadata(resolved_filters),
            "source": "wealth-wing-data",
        },
        ui="transactions_summary_ui",
    )


@tool(args_schema=GetTransactionsInput)
async def get_transactions(
    runtime: ToolRuntime[WingRuntimeContext, WingGraphState],
    category_ids: list[UUID] | None = None,
    category_names: list[str] | None = None,
    account_ids: list[UUID] | None = None,
    account_names: list[str] | None = None,
    merchant_search: str | None = None,
    transaction_types: list[str] | None = None,
    minimum_amount_cents: int | None = None,
    maximum_amount_cents: int | None = None,
    account_type: AccountTypeEnum | None = None,
) -> ToolResultPayload:
    """Return transactions matching shared query and endpoint-specific filters.

    Supply only filters explicitly requested by the user. Category and account
    names belong in the name fields. UUID fields may only contain identifiers
    explicitly provided by the user or obtained from trusted application data.
    Amount bounds are non-negative magnitudes expressed in cents.
    """
    filters = runtime.state.get("current_turn", {}).get("filters", {})
    try:
        resolved_filters = _coerce_resolved_filters(filters)
        transaction_filters = TransactionsAllRequest(
            category_ids=category_ids,
            category_names=category_names,
            account_ids=account_ids,
            account_names=account_names,
            merchant_search=merchant_search,
            transaction_types=transaction_types,
            minimum_amount_cents=minimum_amount_cents,
            maximum_amount_cents=maximum_amount_cents,
            account_type=account_type,
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise ToolException("Transaction request filters are invalid.") from exc

    if resolved_filters.params.filter_by:
        raise ToolException(
            "Legacy global transaction filters are not supported; use the "
            "transaction tool filters."
        )

    ww_data_client = runtime.context.get("ww_data_client")
    access_token = runtime.context.get("access_token")
    if ww_data_client is None:
        raise ToolException("Transaction data service is not configured.")
    if not access_token:
        raise ToolException("Transaction data authorization is unavailable.")

    params = resolved_filters.params
    query = TransactionsQueryParams(
        page=params.page,
        page_size=params.page_size,
        sort_by=params.sort_by,
        sort_order=params.sort_order,
        search=params.search,
        from_date=params.from_date,
        to_date=params.to_date,
    )

    try:
        response = await ww_data_client.get_transactions(
            access_token=access_token,
            params=query,
            transaction_filters=transaction_filters,
        )
    except WWDataAuthorizationError as exc:
        raise ToolException("Transaction data authorization failed.") from exc
    except WWDataUnavailableError as exc:
        raise ToolException("Transaction data service is unavailable.") from exc
    except WWDataClientError as exc:
        raise ToolException("Transaction data could not be retrieved.") from exc

    return _tool_result(
        result_type="transaction_list",
        data={
            "transactions": [
                _serialize_transaction(transaction)
                for transaction in response.transactions
            ],
            "page": params.page,
            "page_size": params.page_size,
            "total_count": response.total_count,
            "total_pages": response.total_pages,
            "has_more": response.has_more,
        },
        metadata={
            "filters": {
                **_serialize_tool_metadata(resolved_filters),
                "transaction_filters": transaction_filters.model_dump(
                    mode="json",
                    exclude_none=True,
                ),
            },
            "source": "wealth-wing-data",
        },
        ui="transactions_ui",
    )


@tool
async def get_cash_flow_history(
    text: str,
    runtime: ToolRuntime[WingRuntimeContext, WingGraphState],
    granularity: Literal["day", "week", "month"] = "month",
    category_ids: list[UUID] | None = None,
    account_ids: list[UUID] | None = None,
    project_ids: list[UUID] | None = None,
) -> ToolResultPayload:
    """Return income, expenses, refunds, and net cash flow for a date range.

    Use granularity day, week, or month. UUID filters may only be supplied when
    they are known; do not infer IDs from category, account, or project names.
    """
    del text
    filters = runtime.state.get("current_turn", {}).get("filters", {})
    try:
        resolved_filters = _coerce_resolved_filters(filters)
        from_date, to_date = _cash_flow_date_range(resolved_filters)
        request = CashFlowHistoryRequest(
            from_date=from_date,
            to_date=to_date,
            category_ids=category_ids,
            account_ids=account_ids,
            project_ids=project_ids,
            granularity=granularity,
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise ToolException("Cash-flow request filters are invalid.") from exc

    ww_data_client = runtime.context.get("ww_data_client")
    access_token = runtime.context.get("access_token")
    if ww_data_client is None:
        raise ToolException("Cash-flow data service is not configured.")
    if not access_token:
        raise ToolException("Cash-flow data authorization is unavailable.")

    try:
        response = await ww_data_client.get_cash_flow_history(
            access_token=access_token,
            request=request,
        )
    except WWDataAuthorizationError as exc:
        raise ToolException("Cash-flow data authorization failed.") from exc
    except WWDataUnavailableError as exc:
        raise ToolException("Cash-flow data service is unavailable.") from exc
    except WWDataClientError as exc:
        raise ToolException("Cash-flow data could not be retrieved.") from exc

    return _tool_result(
        result_type="cash_flow_history",
        data={
            "timezone": response.timezone,
            "from_date": response.from_date.isoformat(),
            "to_date": response.to_date.isoformat(),
            "granularity": response.granularity,
            "periods": [
                {
                    "period_start": period.period_start.isoformat(),
                    "period_end": period.period_end.isoformat(),
                    "income": period.income,
                    "expense": period.expense,
                    "refunds": period.refunds,
                    "net": period.net,
                    "transaction_count": period.transaction_count,
                }
                for period in response.periods
            ],
        },
        metadata={
            "filters": _serialize_tool_metadata(resolved_filters),
            "source": "wealth-wing-data",
        },
        ui="cash_flow_history",
    )


def get_tools(profile: ProfileId) -> tuple[BaseTool, ...]:
    from src.agents.wing.profiles import get_profile

    return get_profile(profile)["tools"]


def _tool_result(
    *,
    result_type: str,
    data: Any,
    metadata: dict[str, Any] | None = None,
    ui: str | None = None,
) -> ToolResultPayload:
    return {
        "result_type": result_type,
        "data": data,
        "metadata": metadata or {},
        "ui": ui,
    }


def _serialize_tool_metadata(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")

    if isinstance(value, dict):
        return {key: _serialize_tool_metadata(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [_serialize_tool_metadata(item) for item in value]

    return value


def _coerce_resolved_filters(value: Any) -> ResolvedFilters:
    if isinstance(value, ResolvedFilters):
        return value
    if isinstance(value, dict):
        return ResolvedFilters.model_validate(value)
    return ResolvedFilters()


def _cash_flow_date_range(filters: ResolvedFilters) -> tuple[date, date]:
    from_datetime = filters.params.from_date
    to_datetime = filters.params.to_date
    if from_datetime is not None and to_datetime is not None:
        return from_datetime.date(), to_datetime.date()

    if from_datetime is not None or to_datetime is not None:
        raise ValueError("cash-flow queries require both from_date and to_date")

    today = datetime.now(timezone.utc).date()
    current_month_start = today.replace(day=1)
    previous_month_end = current_month_start - timedelta(days=1)
    return previous_month_end.replace(day=1), previous_month_end


def _serialize_transaction(transaction: TransactionResponse) -> dict[str, Any]:
    account = None
    if transaction.account_id is not None or transaction.account_name is not None:
        account = {
            "id": str(transaction.account_id) if transaction.account_id else None,
            "name": transaction.account_name,
        }

    return {
        "id": str(transaction.uuid),
        "date": transaction.date.isoformat() if transaction.date else None,
        "title": transaction.title,
        "description": transaction.description,
        "amount_cents": transaction.amount,
        "amount": format_cents(transaction.amount, transaction.currency or "USD"),
        "currency": transaction.currency,
        "type": transaction.type,
        "category": {
            "id": str(transaction.category_id),
            "name": transaction.category,
        },
        "account": account,
    }


#def _search_from_filters(filters: Any) -> str | None:
#    if isinstance(filters, ResolvedFilters):
#        return filters.params.search
#
#    if isinstance(filters, dict):
#        params = filters.get("params", {})
#        if isinstance(params, dict):
#            search = params.get("search")
#            return search if isinstance(search, str) and search else None
#
#    return None
