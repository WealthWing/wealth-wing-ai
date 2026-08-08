from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Literal
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from langchain_core.tools import BaseTool, ToolException
from langchain_core.tools import tool  # pyright: ignore[reportUnknownVariableType]
from langgraph.prebuilt import ToolRuntime
from pydantic import ValidationError
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
    ToolResultPayload,
    WingGraphState,
    WingRuntimeContext,
)
from src.agents.wing.tool_schemas import (
    GetCashFlowHistoryInput,
    GetSpendingByCategoryInput,
    GetTransactionsInput,
    GetTransactionsSummaryInput,
)


@tool(args_schema=GetSpendingByCategoryInput)
async def get_spending_by_category(
    runtime: ToolRuntime[WingRuntimeContext, WingGraphState],
    from_date: date,
    to_date: date,
    category_ids: list[UUID] | None = None,
    category_names: list[str] | None = None,
) -> ToolResultPayload:
    """Use this tool for spending breakdowns or comparisons by category.

    Returns aggregate expense totals per category for the requested date range.
    Optionally filter by explicit category names or trusted category UUIDs.

    Do not use this tool to retrieve individual transactions, transaction summaries,
    income, refunds, or net cash flow. Never infer category UUIDs from names.
    """

    ww_data_client = runtime.context.get("ww_data_client")
    access_token = runtime.context.get("access_token")
    if ww_data_client is None:
        raise ToolException("Spending data service is not configured.")
    if not access_token:
        raise ToolException("Spending data authorization is unavailable.")

    try:
        params = CategorySpendingParams(
            from_date=from_date,
            to_date=to_date,
            category_ids=category_ids,
            category_names=category_names,
        )
    except ValidationError as exc:
        raise ToolException("Spending request filters are invalid.") from exc

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


@tool(args_schema=GetTransactionsSummaryInput)
async def get_transactions_summary(
    runtime: ToolRuntime[WingRuntimeContext, WingGraphState],
    from_date: date | None = None,
    to_date: date | None = None,
    account_types: list[AccountTypeEnum] | None = None,
) -> ToolResultPayload:
    """Return a transaction summary for the model-supplied filters.

    Convert explicitly requested periods into concrete dates before calling.
    Omit both dates to summarize the last completed month. Supply account types
    only when the user explicitly requests them.
    """
    try:
        resolved_from_date, resolved_to_date = _transaction_summary_date_range(
            from_date,
            to_date,
        )
        if account_types is None:
            query = TransactionSummaryRequest(
                from_date=resolved_from_date,
                to_date=resolved_to_date,
            )
        else:
            query = TransactionSummaryRequest(
                from_date=resolved_from_date,
                to_date=resolved_to_date,
                account_types=account_types,
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
            "filters": query.model_dump(mode="json"),
            "source": "wealth-wing-data",
        },
        ui="transactions_summary_ui",
    )


@tool(args_schema=GetTransactionsInput)
async def get_transactions(
    runtime: ToolRuntime[WingRuntimeContext, WingGraphState],
    page: int = 1,
    page_size: int = 30,
    sort_by: Literal["amount", "date", "title"] | None = None,
    sort_order: Literal["asc", "desc"] = "desc",
    search: str | None = None,
    from_date: datetime | None = None,
    to_date: datetime | None = None,
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
    """Return transactions matching the model-supplied filters.

    Supply only filters explicitly requested by the user. Category and account
    names belong in the name fields. UUID fields may only contain identifiers
    explicitly provided by the user or obtained from trusted application data.
    Convert relative dates into concrete datetimes before calling; omit dates
    when the user did not request a period. Amount bounds are non-negative
    magnitudes expressed in cents.
    """
    try:
        query = TransactionsQueryParams(
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_order=sort_order,
            search=search,
            from_date=from_date,
            to_date=to_date,
        )
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

    ww_data_client = runtime.context.get("ww_data_client")
    access_token = runtime.context.get("access_token")
    if ww_data_client is None:
        raise ToolException("Transaction data service is not configured.")
    if not access_token:
        raise ToolException("Transaction data authorization is unavailable.")

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
            "page": query.page,
            "page_size": query.page_size,
            "total_count": response.total_count,
            "total_pages": response.total_pages,
            "has_more": response.has_more,
        },
        metadata={
            "filters": {
                **query.model_dump(mode="json", exclude_none=True),
                **transaction_filters.model_dump(mode="json", exclude_none=True),
            },
            "source": "wealth-wing-data",
        },
        ui="transactions_ui",
    )


@tool(args_schema=GetCashFlowHistoryInput)
async def get_cash_flow_history(
    runtime: ToolRuntime[WingRuntimeContext, WingGraphState],
    from_date: date,
    to_date: date,
    category_ids: list[UUID] | None = None,
    account_ids: list[UUID] | None = None,
    project_ids: list[UUID] | None = None,
    granularity: Literal["day", "week", "month"] = "month",
) -> ToolResultPayload:
    """Return income, expenses, refunds, and net cash flow for a date range.

    Always supply concrete from_date and to_date as ISO dates. Convert relative
    phrases such as "last month" before calling. Use granularity day, week, or
    month. UUID filters may only be supplied when they are known; do not infer
    IDs from category, account, or project names.
    """
    try:
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
            "filters": request.model_dump(mode="json", exclude_none=True),
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


def _transaction_summary_date_range(
    from_date: date | None,
    to_date: date | None,
) -> tuple[date, date]:
    if from_date is not None and to_date is not None:
        return from_date, to_date

    if from_date is not None or to_date is not None:
        raise ValueError("transaction summaries require both from_date and to_date")

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
