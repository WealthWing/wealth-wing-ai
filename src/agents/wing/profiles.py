from __future__ import annotations

from src.agents.wing.state import ProfileId, WingAgentProfile
from src.agents.wing.tools import get_spending_by_category, get_transactions_summary, get_transactions_by_category, get_transactions


DEFAULT_PROFILE: ProfileId = "insights"

PROFILES: dict[ProfileId, WingAgentProfile] = {
    "imports": {
        "instructions": (
            "You help users import and reconcile financial data.\n"
            "Never invent transactions, accounts, balances, or dates.\n"
            "Ask for clarification when imported data is incomplete or ambiguous.\n"
            "You are read-only."
        ),
        "tools": (),
    },
    "insights": {
        "instructions": (
            "You analyze financial data.\n"
            "Never invent transactions, totals, balances, or dates.\n"
            "Use a data tool before making factual financial claims.\n"
            "You are read-only."
        ),
        "tools": (
            get_spending_by_category, get_transactions_summary, get_transactions_by_category, get_transactions  
        ),
    },
    "planning": {
        "instructions": (
            "You help users plan personal finance decisions.\n"
            "Never invent transactions, balances, income, expenses, or dates.\n"
            "Explain assumptions clearly and keep recommendations non-prescriptive.\n"
            "You are read-only."
        ),
        "tools": (),
    },
}


def get_profile(profile: ProfileId | None) -> WingAgentProfile:
    return PROFILES[profile or DEFAULT_PROFILE]
