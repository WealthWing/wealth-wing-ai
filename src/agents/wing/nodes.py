from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime

from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.profiles import PROFILES
from src.agents.wing.state import (
    CurrentTurn,
    ResolvedFilters,
    WingGraphState,
    WingRuntimeContext,
)
from src.config import Settings


@dataclass(frozen=True)
class WingAgentNodes:
    settings: Settings
    configuration: WingAgentConfiguration
    tools_by_name: dict[str, Any]
    llm: ChatOpenAI
    llm_with_tools: ChatOpenAI

    def load_profile(
        self,
        state: WingGraphState,
        runtime: Runtime[WingRuntimeContext],
    ) -> WingGraphState:
        """Validate the profile selected for this run."""
        profile = runtime.context.get("agent_profile")

        if profile is None:
            return self._turn_error(state, "agent_profile is required")

        if profile not in PROFILES:
            return self._turn_error(state, f"Invalid agent_profile: {profile}")

        return {}

    async def _call_llm(
        self,
        state: WingGraphState,
        runtime: Runtime[WingRuntimeContext],
    ) -> WingGraphState:
        """Ask the LLM for the next response or tool call."""
        if state.get("current_turn", {}).get("error"):
            return {}

        messages = state.get("messages", [])
        system_prompt = runtime.context.get("resolved_system_prompt")

        if system_prompt:
            messages = [SystemMessage(content=system_prompt), *messages]

        response = await _ainvoke_model(self.llm_with_tools, messages)
        return {"messages": [response]}

    def _has_tool_calls(self, state: WingGraphState) -> bool:
        messages = state.get("messages", [])
        if not messages:
            return False

        last_message = messages[-1]

        if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
            return False

        return bool(last_message.tool_calls)

    async def resolve_filters(
        self,
        state: WingGraphState,
        runtime: Runtime[WingRuntimeContext],
    ) -> WingGraphState:
        """Resolve request filters for the current turn."""
        current_turn: CurrentTurn = state.get("current_turn", {})
        user_input = current_turn.get("user_input", "")
        intent = current_turn.get("intent", {}).get("intent")
        timezone_name = runtime.context.get("timezone", "UTC")

        try:
            timezone = ZoneInfo(timezone_name)
        except Exception:
            timezone = ZoneInfo("UTC")

        now = datetime.now(timezone)
        structured_llm = self.llm.with_structured_output(ResolvedFilters)
        raw_filters: object = await _ainvoke_model(
            structured_llm,
            [
                SystemMessage(
                    content=f"""
You extract filters from a Wealth Wing user request.

Current datetime: {now.isoformat()}

Rules:
- Extract only filters the user explicitly asks for.
- Convert relative dates such as "last month", "this month", "last 30 days",
  "in May", or "this year" into actual datetime values.
- Do not invent a default date range.
- If the user does not mention a time period, leave from_date and to_date as null.
- Default page=1, page_size=20, and sort_order="desc" unless explicitly requested.
- Return only the structured output.
                    """.strip()
                ),
                HumanMessage(content=user_input),
            ],
        )
        extracted_filters = _coerce_resolved_filters(raw_filters)

        params = extracted_filters.params
        date_source = (
            "explicit" if params.from_date or params.to_date else "not_applicable"
        )

        if not params.from_date and not params.to_date:
            if intent in {"summarize_spending", "compare_spending"}:
                current_month_start = now.replace(
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )
                previous_month_end = current_month_start - timedelta(microseconds=1)
                previous_month_start = previous_month_end.replace(
                    day=1,
                    hour=0,
                    minute=0,
                    second=0,
                    microsecond=0,
                )

                params.from_date = previous_month_start
                params.to_date = previous_month_end
                date_source = "default_last_completed_month"

            elif intent in {"list_transactions", "find_transactions"}:
                params.from_date = now - timedelta(days=30)
                params.to_date = now
                date_source = "default_last_30_days"

        resolved_filters = ResolvedFilters(
            params=params,
            date_source=date_source,
        )

        next_current_turn: CurrentTurn = {
            **current_turn,
            "filters": resolved_filters,
        }
        return {"current_turn": next_current_turn}

    def _turn_error(self, state: WingGraphState, error: str) -> WingGraphState:
        next_current_turn: CurrentTurn = {
            **state.get("current_turn", {}),
            "error": error,
        }
        return {"current_turn": next_current_turn}


def _coerce_resolved_filters(value: object) -> ResolvedFilters:
    if isinstance(value, ResolvedFilters):
        return value

    if isinstance(value, dict):
        return ResolvedFilters.model_validate(value)

    raise TypeError(f"Expected ResolvedFilters output, got {type(value).__name__}")


async def _ainvoke_model(model: Any, messages: Any) -> Any:
    ainvoke = getattr(model, "ainvoke", None)
    if ainvoke is not None:
        return await ainvoke(messages)

    return await asyncio.to_thread(model.invoke, messages)
