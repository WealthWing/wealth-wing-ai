from __future__ import annotations

import asyncio
import ast
import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI
from langgraph.runtime import Runtime
from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.profiles import PROFILES
from src.agents.wing.state import (
    CurrentTurn,
    FilterByInputs,
    ResolvedFilters,
    ToolResultPayload,
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
- Category/type/account filters should be extracted into filter_by. Example:
  "spending for dining and income" should set filter_by=[{{"field_name":"category","values":["Dining","Income"]}}].
- Search is only for free-text merchant or description matching. Example:
  "Find transactions with 'Starbucks' in the description" should set search="Starbucks".
- Return only the structured output.
                    """.strip()
                ),
                HumanMessage(content=user_input),
            ],
        )
        extracted_filters = _coerce_resolved_filters(raw_filters)

        params = extracted_filters.params
        existing_category_values = _filter_values(params.filter_by, "category")
        if not existing_category_values:
            inferred_categories = _infer_category_filter_values(user_input)
            if inferred_categories:
                params.filter_by.append(
                    FilterByInputs(
                        field_name="category",
                        values=inferred_categories,
                    )
                )

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
    
    def collect_results(self, state: WingGraphState) -> dict:
        """
        Reads only the ToolMessages produced by the most recent ToolNode run,
        normalizes them, and saves them under current_turn.tool_results.

        Does not call tools.
        Does not decide UI.
        Does not ask the LLM anything.
        """

        current_turn = state.get("current_turn", {})
        messages = state.get("messages", [])

        # ToolNode appends one or more ToolMessages at the end of messages.
        recent_tool_messages: list[ToolMessage] = []

        for message in reversed(messages):
            if isinstance(message, ToolMessage):
                recent_tool_messages.append(message)
            else:
                break

        recent_tool_messages.reverse()

        if not recent_tool_messages:
            return {
                "current_turn": {
                    **current_turn,
                    "tool_results": current_turn.get("tool_results", []),
                }
            }

        # Find the AIMessage that requested these tool calls.
        latest_tool_call_message: AIMessage | None = next(
            (
                message
                for message in reversed(messages)
                if isinstance(message, AIMessage) and message.tool_calls
            ),
            None,
        )

        calls_by_id = {
            tool_call["id"]: tool_call
            for tool_call in (latest_tool_call_message.tool_calls or [])
        } if latest_tool_call_message else {}

        # Preserve earlier results if the LLM requested several rounds of tools.
        results_by_id = {
            result["result_id"]: result
            for result in current_turn.get("tool_results", [])
        }

        tool_errors = list(current_turn.get("tool_errors", []))

        for tool_message in recent_tool_messages:
            tool_call = calls_by_id.get(tool_message.tool_call_id, {})
            tool_name = tool_call.get(
                "name",
                getattr(tool_message, "name", "unknown_tool"),
            )

            # ToolNode may return an error ToolMessage rather than raising.
            if getattr(tool_message, "status", None) == "error":
                tool_errors.append(
                    {
                        "tool_call_id": tool_message.tool_call_id,
                        "tool_name": tool_name,
                        "message": str(tool_message.content),
                    }
                )
                continue

            try:
                payload = _coerce_tool_result_payload(tool_message.content)
            except (
                json.JSONDecodeError,
                KeyError,
                SyntaxError,
                TypeError,
                ValueError,
            ) as error:
                tool_errors.append(
                    {
                        "tool_call_id": tool_message.tool_call_id,
                        "tool_name": tool_name,
                        "message": f"Invalid tool result format: {error}",
                    }
                )
                continue

            # tool_call_id is already unique for this agent run.
            results_by_id[tool_message.tool_call_id] = {  # pyright: ignore[reportArgumentType]
                "result_id": tool_message.tool_call_id,
                "result_type": payload["result_type"],
                "source_tool": tool_name,
                "data": payload["data"],
                "metadata": payload.get("metadata", {}),
                "ui": payload.get("ui"),
            }

        return {
            "current_turn": {
                **current_turn,
                "tool_results": list(results_by_id.values()),
                "tool_errors": tool_errors,
            }
        }
        
    async def final_response(self, state: WingGraphState):
        """Finalize the current turn and prepare for the next one."""
        current_turn = state.get("current_turn", {})
        

        return {
            "current_turn": json.loads(json.dumps(current_turn)),
        }

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


def _coerce_tool_result_payload(content: Any) -> ToolResultPayload:
    if isinstance(content, dict):
        payload = content
    elif isinstance(content, str):
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            payload = ast.literal_eval(content)
    else:
        raise TypeError(f"Expected dict or JSON string, got {type(content).__name__}")

    if not isinstance(payload, dict):
        raise TypeError(f"Expected object payload, got {type(payload).__name__}")

    result_type = payload.get("result_type")
    if not isinstance(result_type, str) or not result_type:
        raise ValueError("result_type is required")

    if "data" not in payload:
        raise KeyError("data")

    metadata = payload.get("metadata", {})
    if not isinstance(metadata, dict):
        raise TypeError("metadata must be an object")

    return {
        "result_type": result_type,
        "data": payload["data"],
        "metadata": metadata,
        "ui": payload.get("ui"),
    }


_FILTER_STOP_PHRASES = (
    "this month",
    "last month",
    "this year",
    "last year",
    "last week",
    "this week",
    "today",
    "yesterday",
)

_FILTER_STOP_WORDS = {
    "a",
    "an",
    "and",
    "for",
    "how",
    "is",
    "me",
    "my",
    "of",
    "please",
    "show",
    "spending",
    "the",
    "transactions",
}

_KNOWN_CATEGORY_VALUES = {
    "dining",
    "groceries",
    "health",
    "housing",
    "income",
    "shopping",
    "subscriptions",
    "transportation",
    "utilities",
}


def _filter_values(filters: list[FilterByInputs], field_name: str) -> list[str]:
    return [
        value
        for filter_by in filters
        if filter_by.field_name == field_name
        for value in filter_by.values
    ]


def _infer_category_filter_values(user_input: str) -> list[str]:
    normalized_input = user_input.strip()
    if not normalized_input:
        return []

    lowered = normalized_input.lower()
    values = [
        _restore_filter_value_casing(term)
        for term in sorted(_KNOWN_CATEGORY_VALUES, key=len, reverse=True)
        if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", lowered)
    ]
    if values:
        return values

    for pattern in (
        r"\b(?:for|on|at|from|with|about)\s+(.+?)(?:\?|$)",
        r"\bcategory\s+(.+?)(?:\?|$)",
    ):
        match = re.search(pattern, lowered)
        if not match:
            continue

        candidates = _clean_filter_candidates(match.group(1))
        if candidates:
            return candidates

    return []


def _clean_filter_candidates(candidate: str) -> list[str]:
    cleaned = candidate.strip(" .?!'\"")
    for phrase in _FILTER_STOP_PHRASES:
        cleaned = re.sub(rf"\b{re.escape(phrase)}\b", "", cleaned)

    words = [
        word
        for word in re.split(r"[\s,]+", cleaned.strip())
        if word and word not in _FILTER_STOP_WORDS
    ]
    known_words = [word for word in words if word in _KNOWN_CATEGORY_VALUES]

    return [_restore_filter_value_casing(word) for word in known_words]


def _restore_filter_value_casing(value: str) -> str:
    return value.title()


async def _ainvoke_model(model: Any, messages: Any) -> Any:
    ainvoke = getattr(model, "ainvoke", None)
    if ainvoke is not None:
        return await ainvoke(messages)

    return await asyncio.to_thread(model.invoke, messages)
