from __future__ import annotations

import sys
from pathlib import Path
from typing import Annotated, Any
from datetime import datetime, timezone
from langchain_core.tools import BaseTool, tool
from langgraph.prebuilt import InjectedState
from pydantic import BaseModel, Field
from src.utils.format import format_cents

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[3]))

from src.agents.wing.state import (
    ProfileId,
    ResolvedFilters,
    ToolResultPayload,
    WingGraphState,
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


# Use for charts and category-level explanations
@tool
def get_spending_by_category(
    state: Annotated[WingGraphState, InjectedState()],
    text: str,
) -> ToolResultPayload:
    """Return expense totals grouped by category for the resolved date range."""
    #“Where did I spend money last month?”
    #“Show my spending by category.”
    #“What were my biggest expenses in June?”
    return _tool_result(
        result_type="spending_by_category",
        data={
            "total_spent": format_cents(184500),
            "categories": [
                {
                    "category_id": "uuid",
                    "category_slug": "groceries",
                    "category_name": "Groceries",
                    "total_cents": 45200,
                    "transaction_count": 18,
                    "percent_of_total": 24.5,
                }
            ],
        },
        metadata={
            "from_date": "2026-06-01",
            "to_date": "2026-06-30",
            "transaction_types": ["expense"], #default to expense
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
def get_transactions(
    state: Annotated[WingGraphState, InjectedState()],
    text: str,
) -> ToolResultPayload:
    """Return a paginated list of transactions matching the resolved filters."""
    filters = state.get("current_turn", {}).get("filters", {})
    search = _search_from_filters(filters)
    category_values = _filter_values_from_filters(filters, "category")
   

    return _tool_result(
        result_type="transaction_list",
        data={
    "transactions": [
      {
        "id": "uuid",
        "date": "2026-06-14",
        "title": "ShopRite",
        "amount": format_cents(-8423),
        "type": "expense",
        "category": {
          "id": "uuid",
          "slug": "groceries",
          "name": "Groceries"
        },
        "account": {
          "id": "uuid",
          "name": "Chase Checking",
          "last_four": "6791"
        }
      }
    ],
    "next_cursor": "opaque-cursor",
    "has_more": True
  },
        metadata={"filters": _serialize_tool_metadata(filters)},
        ui="transactions_ui",
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
