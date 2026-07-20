from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any, Literal
from datetime import date, datetime, timedelta, timezone
from uuid import UUID
from langchain_core.tools import BaseTool, ToolException, tool
from langgraph.prebuilt import InjectedState, ToolRuntime
from pydantic import BaseModel, Field, ValidationError
from src.providers.ww_data_client import (
    WWDataAuthorizationError,
    WWDataClientError,
    WWDataUnavailableError,
)
from src.providers.ww_data_schemas import (
    CashFlowHistoryRequest,
    CategorySpendingParams,
    TransactionResponse,
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

transactions_by_category = [
    {
        "date": "2026-05-01",
        "description": "Payroll Deposit",
        "amount": 4200.0,
        "category": "Income",
        "type": "income",
    },
    {
        "date": "2026-05-02",
        "description": "Whole Foods Market",
        "amount": 86.42,
        "category": "Groceries",
        "type": "expense",
    },
    {
        "date": "2026-05-03",
        "description": "Shell Gas Station",
        "amount": 52.18,
        "category": "Transportation",
        "type": "expense",
    },
    {
        "date": "2026-05-04",
        "description": "Netflix",
        "amount": 15.49,
        "category": "Subscriptions",
        "type": "expense",
    },
    {
        "date": "2026-05-05",
        "description": "Starbucks",
        "amount": 7.85,
        "category": "Dining",
        "type": "expense",
    },
    {
        "date": "2026-05-06",
        "description": "Con Edison",
        "amount": 124.67,
        "category": "Utilities",
        "type": "expense",
    },
    {
        "date": "2026-05-07",
        "description": "Amazon",
        "amount": 64.99,
        "category": "Shopping",
        "type": "expense",
    },
    {
        "date": "2026-05-08",
        "description": "Chipotle",
        "amount": 14.75,
        "category": "Dining",
        "type": "expense",
    },
    {
        "date": "2026-05-10",
        "description": "Rent Payment",
        "amount": 2100.0,
        "category": "Housing",
        "type": "expense",
    },
    {
        "date": "2026-05-12",
        "description": "Uber",
        "amount": 28.36,
        "category": "Transportation",
        "type": "expense",
    },
    {
        "date": "2026-05-15",
        "description": "Freelance Payment",
        "amount": 750.0,
        "category": "Income",
        "type": "income",
    },
    {
        "date": "2026-05-16",
        "description": "Target",
        "amount": 92.31,
        "category": "Shopping",
        "type": "expense",
    },
    {
        "date": "2026-05-18",
        "description": "Verizon Wireless",
        "amount": 89.99,
        "category": "Utilities",
        "type": "expense",
    },
    {
        "date": "2026-05-20",
        "description": "Planet Fitness",
        "amount": 24.99,
        "category": "Health",
        "type": "expense",
    },
    {
        "date": "2026-05-22",
        "description": "Trader Joe's",
        "amount": 74.56,
        "category": "Groceries",
        "type": "expense",
    },
    {
        "date": "2026-05-25",
        "description": "DoorDash",
        "amount": 38.42,
        "category": "Dining",
        "type": "expense",
    },
    {
        "date": "2026-05-25",
        "description": "PSE&G",
        "amount": 120.42,
        "category": "Utilities",
        "type": "expense",
    },
    {
        "date": "2026-06-25",
        "description": "PSE&G",
        "amount": 320.42,
        "category": "Utilities",
        "type": "expense",
    },
    {
        "date": "2026-07-25",
        "description": "PSE&G",
        "amount": 300.42,
        "category": "Utilities",
        "type": "expense",
    },
    {
        "date": "2026-08-25",
        "description": "PSE&G",
        "amount": 140.42,
        "category": "Utilities",
        "type": "expense",
    },
    {
        "date": "2026-09-25",
        "description": "PSE&G",
        "amount": 120.42,
        "category": "Utilities",
        "type": "expense",
    },
]

transactions_summary = {
    "totals": {
        "income": 5394696,
        "expense": -2641689,
        "net": 2753007,
        "average_monthly_spent": -220141.0,
    },
    "months": [
        {
            "month": "2025-07-01T00:00:00",
            "income": 449558,
            "expense": -205575,
            "net": 243983,
        },
        {
            "month": "2025-08-01T00:00:00",
            "income": 449558,
            "expense": -224098,
            "net": 225460,
        },
        {
            "month": "2025-09-01T00:00:00",
            "income": 449558,
            "expense": -226281,
            "net": 223277,
        },
        {
            "month": "2025-10-01T00:00:00",
            "income": 449558,
            "expense": -241291,
            "net": 208267,
        },
        {
            "month": "2025-11-01T00:00:00",
            "income": 449558,
            "expense": -220578,
            "net": 228980,
        },
        {
            "month": "2025-12-01T00:00:00",
            "income": 449558,
            "expense": -212078,
            "net": 237480,
        },
        {
            "month": "2026-01-01T00:00:00",
            "income": 449558,
            "expense": -207410,
            "net": 242148,
        },
        {
            "month": "2026-02-01T00:00:00",
            "income": 449558,
            "expense": -233410,
            "net": 216148,
        },
        {
            "month": "2026-03-01T00:00:00",
            "income": 449558,
            "expense": -220107,
            "net": 229451,
        },
        {
            "month": "2026-04-01T00:00:00",
            "income": 449558,
            "expense": -205536,
            "net": 244022,
        },
        {
            "month": "2026-05-01T00:00:00",
            "income": 449558,
            "expense": -221184,
            "net": 228374,
        },
        {
            "month": "2026-06-01T00:00:00",
            "income": 449558,
            "expense": -224141,
            "net": 225417,
        },
    ],
}


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
def get_transactions_summary(
    state: Annotated[WingGraphState, InjectedState()], text: str
) -> ToolResultPayload:
    """Return a transaction summary result for the requested text."""

    filters = state.get("current_turn", {}).get("filters", {})
    
    #Use cases:

    #“How much did I spend last month?”
    #“Give me a summary of June.”
    #“What was my net cash flow?”
    #“Did I spend more than I earned?”


    return _tool_result(
        result_type="transaction_summary",
        data={
    "income_cents": format_cents(520000),
    "expense_cents": format_cents(184500),
    "net_cents": format_cents(335500),
    "transaction_count": 73,
    "average_monthly_expense_cents": format_cents(184500)
  },
        metadata=filters.model_dump(mode="json") if isinstance(filters, ResolvedFilters) else {},
        ui="transactions_summary_ui",
    )
    
@tool
async def get_transactions(
    text: str,
    runtime: ToolRuntime[WingRuntimeContext, WingGraphState],
) -> ToolResultPayload:
    """Return a paginated list of transactions matching the resolved filters."""
    del text
    filters = runtime.state.get("current_turn", {}).get("filters", {})
    try:
        resolved_filters = _coerce_resolved_filters(filters)
    except (TypeError, ValidationError) as exc:
        raise ToolException("Transaction request filters are invalid.") from exc

    if resolved_filters.params.filter_by:
        raise ToolException(
            "Filtered transaction lists are not supported by the data service yet."
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
            "filters": _serialize_tool_metadata(resolved_filters),
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


@tool
def get_transactions_by_category(
    state: Annotated[WingGraphState, InjectedState()],
) -> ToolResultPayload:
    """Return transaction totals grouped by category."""
    filters = state.get("current_turn", {}).get("filters", {})
    search = _search_from_filters(filters)
    category_values = _filter_values_from_filters(filters, "category")
    filtered_transactions = [
        transaction
        for transaction in transactions_by_category
        if _matches_filter_values(transaction, "category", category_values)
        and _matches_search(transaction, search)
    ]

    totals_by_category = {}
    for transaction in filtered_transactions:
        category = transaction["category"]
        if category not in totals_by_category:
            totals_by_category[category] = {
                "category": category,
                "total_amount": 0.0,
                "transactions": [],
            }
        totals_by_category[category]["total_amount"] += transaction["amount"]
        totals_by_category[category]["transactions"].append(transaction)

    categories = [
        TransactionsByCategory(
            category=cat["category"],
            total_amount=cat["total_amount"],
            transactions=cat["transactions"],
        ).model_dump()
        for cat in totals_by_category.values()
    ]

    return _tool_result(
        result_type="transactions_by_category",
        data=categories,
        metadata={"filters": _serialize_tool_metadata(filters)},
        ui="transactions_by_category_ui",
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


def _search_from_filters(filters: Any) -> str | None:
    if isinstance(filters, ResolvedFilters):
        return filters.params.search

    if isinstance(filters, dict):
        params = filters.get("params", {})
        if isinstance(params, dict):
            search = params.get("search")
            return search if isinstance(search, str) and search else None

    return None


def _matches_search(transaction: dict[str, Any], search: str | None) -> bool:
    if not search:
        return True

    needle = search.casefold()
    return any(
        needle in str(transaction.get(field, "")).casefold()
        for field in ("description", "category", "type")
    )


def _filter_values_from_filters(filters: Any, field_name: str) -> list[str]:
    if isinstance(filters, ResolvedFilters):
        filter_by = filters.params.filter_by
        return [
            value
            for filter_input in filter_by
            if filter_input.field_name == field_name
            for value in filter_input.values
        ]

    if isinstance(filters, dict):
        params = filters.get("params", {})
        if not isinstance(params, dict):
            return []

        filter_by = params.get("filter_by", [])
        if not isinstance(filter_by, list):
            return []

        values: list[str] = []
        for filter_input in filter_by:
            if not isinstance(filter_input, dict):
                continue
            if filter_input.get("field_name") != field_name:
                continue
            raw_values = filter_input.get("values", [])
            if isinstance(raw_values, list):
                values.extend(value for value in raw_values if isinstance(value, str))
        return values

    return []


def _matches_filter_values(
    transaction: dict[str, Any],
    field_name: str,
    values: list[str],
) -> bool:
    if not values:
        return True

    raw_value = transaction.get(field_name)
    if raw_value is None:
        return False

    value = str(raw_value).casefold()
    return value in {item.casefold() for item in values}
