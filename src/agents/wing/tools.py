from __future__ import annotations

import sys
from pathlib import Path

from langchain_core.tools import BaseTool, tool
from openai import BaseModel
from pydantic import Field

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[3]))

from src.agents.wing.state import ProfileId, WingGraphState

transactions_by_category = [
     {
    "date": "2026-05-01",
    "description": "Payroll Deposit",
    "amount": 4200.0,
    "category": "Income",
    "type": "income"
  },
  {
    "date": "2026-05-02",
    "description": "Whole Foods Market",
    "amount": 86.42,
    "category": "Groceries",
    "type": "expense"
  },
  {
    "date": "2026-05-03",
    "description": "Shell Gas Station",
    "amount": 52.18,
    "category": "Transportation",
    "type": "expense"
  },
  {
    "date": "2026-05-04",
    "description": "Netflix",
    "amount": 15.49,
    "category": "Subscriptions",
    "type": "expense"
  },
  {
    "date": "2026-05-05",
    "description": "Starbucks",
    "amount": 7.85,
    "category": "Dining",
    "type": "expense"
  },
  {
    "date": "2026-05-06",
    "description": "Con Edison",
    "amount": 124.67,
    "category": "Utilities",
    "type": "expense"
  },
  {
    "date": "2026-05-07",
    "description": "Amazon",
    "amount": 64.99,
    "category": "Shopping",
    "type": "expense"
  },
  {
    "date": "2026-05-08",
    "description": "Chipotle",
    "amount": 14.75,
    "category": "Dining",
    "type": "expense"
  },
  {
    "date": "2026-05-10",
    "description": "Rent Payment",
    "amount": 2100.0,
    "category": "Housing",
    "type": "expense"
  },
  {
    "date": "2026-05-12",
    "description": "Uber",
    "amount": 28.36,
    "category": "Transportation",
    "type": "expense"
  },
  {
    "date": "2026-05-15",
    "description": "Freelance Payment",
    "amount": 750.0,
    "category": "Income",
    "type": "income"
  },
  {
    "date": "2026-05-16",
    "description": "Target",
    "amount": 92.31,
    "category": "Shopping",
    "type": "expense"
  },
  {
    "date": "2026-05-18",
    "description": "Verizon Wireless",
    "amount": 89.99,
    "category": "Utilities",
    "type": "expense"
  },
  {
    "date": "2026-05-20",
    "description": "Planet Fitness",
    "amount": 24.99,
    "category": "Health",
    "type": "expense"
  },
  {
    "date": "2026-05-22",
    "description": "Trader Joe's",
    "amount": 74.56,
    "category": "Groceries",
    "type": "expense"
  },
  {
    "date": "2026-05-25",
    "description": "DoorDash",
    "amount": 38.42,
    "category": "Dining",
    "type": "expense"
  },
    {
    "date": "2026-05-25",
    "description": "PSE&G",
    "amount": 120.42,
    "category": "Utilities",
    "type": "expense"
  },
    {
    "date": "2026-06-25",
      "description": "PSE&G",
    "amount": 320.42,
    "category": "Utilities",
    "type": "expense"
  },
    {
    "date": "2026-07-25",
    "description": "PSE&G",
    "amount": 300.42,
    "category": "Utilities",
    "type": "expense"
  },
    {
    "date": "2026-08-25",
    "description": "PSE&G",
    "amount": 140.42,
    "category": "Utilities",
    "type": "expense"
  },
    {
    "date": "2026-09-25",
    "description": "PSE&G",
    "amount": 120.42,
    "category": "Utilities",
    "type": "expense"
  }
]

transactions = {
    "totals": {
        "income": 5394696,
        "expense": -2641689,
        "net": 2753007,
        "average_monthly_spent": -220141.0
    },
    "months": [
        {
            "month": "2025-07-01T00:00:00",
            "income": 449558,
            "expense": -205575,
            "net": 243983
        },
        {
            "month": "2025-08-01T00:00:00",
            "income": 449558,
            "expense": -224098,
            "net": 225460
        },
        {
            "month": "2025-09-01T00:00:00",
            "income": 449558,
            "expense": -226281,
            "net": 223277
        },
        {
            "month": "2025-10-01T00:00:00",
            "income": 449558,
            "expense": -241291,
            "net": 208267
        },
        {
            "month": "2025-11-01T00:00:00",
            "income": 449558,
            "expense": -220578,
            "net": 228980
        },
        {
            "month": "2025-12-01T00:00:00",
            "income": 449558,
            "expense": -212078,
            "net": 237480
        },
        {
            "month": "2026-01-01T00:00:00",
            "income": 449558,
            "expense": -207410,
            "net": 242148
        },
        {
            "month": "2026-02-01T00:00:00",
            "income": 449558,
            "expense": -233410,
            "net": 216148
        },
        {
            "month": "2026-03-01T00:00:00",
            "income": 449558,
            "expense": -220107,
            "net": 229451
        },
        {
            "month": "2026-04-01T00:00:00",
            "income": 449558,
            "expense": -205536,
            "net": 244022
        },
        {
            "month": "2026-05-01T00:00:00",
            "income": 449558,
            "expense": -221184,
            "net": 228374
        },
        {
            "month": "2026-06-01T00:00:00",
            "income": 449558,
            "expense": -224141,
            "net": 225417
        }
    ]
}



class TransactionsByCategory(BaseModel):
    category: str = Field(..., description="The category of the transactions.")
    total_amount: float = Field(..., description="The total amount for the category.")
    transactions: list[dict] = Field(..., description="The list of transactions for the category.")


@tool
def echo_context(text: str) -> str:
    """Return the provided text unchanged."""
    return text

@tool
def get_transactions_summary(text: str) -> dict:
    """Return the provided text unchanged."""
    return transactions

@tool
def get_transactions_by_category(state: WingGraphState) -> list[TransactionsByCategory]:
    """Return the provided text unchanged."""
    filters = state.get("current_turn", {}).get("filters", {})

    totals_by_category = {}
    for transaction in transactions_by_category:
        category = transaction["category"]
        if category not in totals_by_category:
            totals_by_category[category] = {
                "category": category,
                "total_amount": 0.0,
                "transactions": [],
            }
        totals_by_category[category]["total_amount"] += transaction["amount"]
        totals_by_category[category]["transactions"].append(transaction)

    return [TransactionsByCategory(category=cat["category"], total_amount=cat["total_amount"], transactions=cat["transactions"]) for cat in totals_by_category.values()]


def get_tools(profile: ProfileId) -> tuple[BaseTool, ...]:
    from src.agents.wing.profiles import get_profile

    return get_profile(profile)["tools"]


