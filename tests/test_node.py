from __future__ import annotations

import asyncio
from datetime import datetime
from typing import cast

from langchain_openai import ChatOpenAI

from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.nodes import WingAgentNodes
from src.agents.wing.state import ResolvedFilters, StandardParams, WingRuntimeContext
from src.config import Settings


class FakeStructuredLLM:
    def __init__(self, response: ResolvedFilters | dict[str, object]) -> None:
        self.response = response

    def invoke(self, messages: object) -> ResolvedFilters | dict[str, object]:
        return self.response


class FakeLLM:
    def __init__(self, response: ResolvedFilters | dict[str, object]) -> None:
        self.response = response

    def with_structured_output(self, schema: object) -> FakeStructuredLLM:
        return FakeStructuredLLM(self.response)


class FakeRuntime:
    context: WingRuntimeContext = {"timezone": "America/New_York"}


def make_settings(**overrides: object) -> Settings:
    settings_values = {
        "ALLOWED_HOSTS": "testserver",
        "COGNITO_JWKS_URL": "",
        "COGNITO_USER_POOL_ID": "",
        "AWS_REGION": "",
        "COGNITO_ISSUER": "",
        "COGNITO_CLIENT_ID": "",
        "TOGETHER_API_KEY": "test-key",
        "WEALTH_WING_DATA_HEALTH_URL": None,
    }
    settings_values.update(overrides)
    return Settings(**settings_values)


def make_nodes(response: ResolvedFilters | dict[str, object]) -> WingAgentNodes:
    settings = make_settings()
    llm = cast(ChatOpenAI, FakeLLM(response))

    return WingAgentNodes(
        settings=settings,
        configuration=WingAgentConfiguration.from_settings(settings),
        tools_by_name={},
        llm=llm,
        llm_with_tools=llm,
    )


def test_resolve_filters_defaults_spending_to_last_completed_month() -> None:
    nodes = make_nodes(ResolvedFilters())

    result = asyncio.run(
        nodes.resolve_filters(
            {
                "current_turn": {
                    "turn_id": "turn-1",
                    "user_input": "summarize my spending",
                    "intent": {
                        "intent": "summarize_spending",
                        "confidence": 1.0,
                        "needs_clarification": False,
                        "clarification_question": None,
                    },
                }
            },
            FakeRuntime(),
        )
    )

    filters = result["current_turn"]["filters"]

    assert filters.date_source == "default_last_completed_month"
    assert filters.params.from_date is not None
    assert filters.params.to_date is not None
    assert filters.params.from_date.month == 6
    assert filters.params.to_date.month == 6


def test_resolve_filters_preserves_explicit_dates_from_llm_dict() -> None:
    nodes = make_nodes(
        {
            "params": {
                "from_date": "2026-05-01T00:00:00",
                "to_date": "2026-05-31T23:59:59",
                "page": 2,
            },
            "date_source": "explicit",
        }
    )

    result = asyncio.run(
        nodes.resolve_filters(
            {
                "current_turn": {
                    "turn_id": "turn-1",
                    "user_input": "show May spending page 2",
                    "intent": {
                        "intent": "summarize_spending",
                        "confidence": 1.0,
                        "needs_clarification": False,
                        "clarification_question": None,
                    },
                }
            },
            FakeRuntime(),
        )
    )

    filters = result["current_turn"]["filters"]

    assert filters.date_source == "explicit"
    assert filters.params.from_date == datetime(2026, 5, 1, 0, 0, 0)
    assert filters.params.to_date == datetime(2026, 5, 31, 23, 59, 59)
    assert filters.params.page == 2
