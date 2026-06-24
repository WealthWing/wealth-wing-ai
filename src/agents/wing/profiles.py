from __future__ import annotations

from typing import TypedDict

from langchain_core.tools import BaseTool

from src.agents.wing.state import ProfileId
from src.agents.wing.tools import echo_context


class WingAgentProfile(TypedDict):
    instructions: str
    tools: tuple[BaseTool, ...]


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
            echo_context,
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
