from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[3]))

from langchain_core.messages import AnyMessage, BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel

from src.schemas.wing import WingAgentRequest

from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.graph import build_graph
from src.agents.wing.profiles import get_profile
from src.agents.wing.prompts import get_system_prompt
from src.agents.wing.state import (
    CurrentTurn,
    ProfileId,
    WingAgentState,
    WingRuntimeContext,
)
from src.agents.wing.tools import get_tools
from src.config import Settings, get_settings


class WingAgent:
    def __init__(
        self,
        settings: Settings,
        configuration: WingAgentConfiguration | None = None,
        request: WingAgentRequest | None = None,
    ) -> None:
        self.settings = settings
        self.configuration = configuration or WingAgentConfiguration.from_settings(
            settings
        )
        self.request = request
        self.last_runtime_context: WingRuntimeContext = {}

    def invoke(self, message: str | WingAgentRequest | WingAgentState) -> WingAgentState:
        return asyncio.run(self.ainvoke(message))

    async def ainvoke(
        self,
        message: str | WingAgentRequest | WingAgentState,
    ) -> WingAgentState:
        state = self._build_initial_state(message)
        runtime_context = self._build_runtime_context(message)
        self.last_runtime_context = runtime_context
        tools = get_tools(runtime_context.get("agent_profile", "imports"))
        tools_by_name = {tool.name: tool for tool in tools}
        llm = self._build_llm()
        graph = build_graph(
            settings=self.settings,
            configuration=self.configuration,
            tools_by_name=tools_by_name,
            tools=tools,
            llm=llm,
            llm_with_tools=self.bind_llm_tools(llm, tools),
        )

        return await graph.ainvoke(
            state,
            context=runtime_context,
            config={"recursion_limit": self.configuration.recursion_limit},
        )

    def _build_initial_state(
        self,
        message: str | WingAgentRequest | WingAgentState,
    ) -> WingAgentState:
        new_turn_id = str(uuid4())
        if isinstance(message, dict):
            messages = _messages_from_state(message)
            current_turn = _current_turn_from_state(message)
            user_input = current_turn.get("user_input") or _last_human_content(messages)
            next_turn: CurrentTurn = {
                **current_turn,
                "turn_id": current_turn.get("turn_id", new_turn_id),
                "user_input": user_input,
            }
            return {
                "current_turn_id": next_turn["turn_id"],
                "messages": messages,
                "current_turn": next_turn,
            }

        content = message.message if isinstance(message, WingAgentRequest) else message

        return {
            "current_turn_id": new_turn_id,
            "messages": [HumanMessage(content=content)],
            "current_turn": {
                "turn_id": new_turn_id,
                "user_input": content,
            },
        }

    def _build_runtime_context(
        self,
        message: str | WingAgentRequest | WingAgentState,
    ) -> WingRuntimeContext:
        request = message if isinstance(message, WingAgentRequest) else self.request
        profile = _profile_from_message(message, request)
        profile_definition = get_profile(profile)
        additional_prompt = _additional_prompt_from_message(message, request)
        resolved_system_prompt = _resolve_system_prompt(
            configuration=self.configuration,
            profile_instructions=profile_definition["instructions"],
            additional_prompt=additional_prompt,
        )
        tools = profile_definition["tools"]
        user_id = _optional_string(message, request, "user_id")
        organization_id = _optional_string(message, request, "organization_id")

        context: WingRuntimeContext = {
            "agent_profile": profile,
            "additional_prompt": additional_prompt,
            "resolved_system_prompt": resolved_system_prompt,
            "enabled_tools": tuple(tool.name for tool in tools),
            "metadata": dict(self.configuration.metadata),
        }

        if user_id:
            context["user_id"] = user_id
        if organization_id:
            context["organization_id"] = organization_id

        return context

    def build_llm_with_tools(self, tools: tuple[Any, ...]) -> Any:
        """Build a chat model, optionally bound to the tools for a profile."""
        llm = self._build_llm()
        return self.bind_llm_tools(llm, tools)

    def bind_llm_tools(self, llm: Any, tools: tuple[Any, ...]) -> Any:
        """Return the base model when no tools are needed, otherwise bind tools."""
        if not tools:
            return llm

        return llm.bind_tools(list(tools))

    def _build_llm(self) -> ChatOpenAI:
        return ChatOpenAI(
            model=self.configuration.default_model,
            api_key=self.settings.together_api_key,
            base_url=self.settings.together_api_base,
            temperature=self.configuration.temperature,
            max_completion_tokens=self.configuration.max_tokens,
            timeout=self.configuration.timeout_seconds,
            max_retries=self.configuration.max_retries,
        )


def _serialize_message(message: BaseMessage) -> dict[str, str]:
    content = message.content

    return {
        "role": getattr(message, "type", "unknown"),
        "content": content if isinstance(content, str) else str(content),
    }


def _serialize_for_json(value: Any) -> Any:
    if isinstance(value, BaseMessage):
        return _serialize_message(value)

    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")

    if isinstance(value, dict):
        return {key: _serialize_for_json(item) for key, item in value.items()}

    if isinstance(value, (list, tuple)):
        return [_serialize_for_json(item) for item in value]

    return value


def _messages_from_state(state: WingAgentState) -> list[AnyMessage]:
    messages = state.get("messages", [])
    return list(messages)


def _current_turn_from_state(state: WingAgentState) -> CurrentTurn:
    current_turn = state.get("current_turn")
    if current_turn is None:
        return {}

    return current_turn


def _profile_from_message(
    message: str | WingAgentRequest | WingAgentState,
    request: WingAgentRequest | None,
) -> ProfileId:
    if isinstance(message, WingAgentRequest):
        return message.agent_profile

    if isinstance(message, dict):
        profile = message.get("agent_profile")
        if profile in {"imports", "insights", "planning"}:
            return profile

    if request:
        return request.agent_profile

    return "imports"


def _additional_prompt_from_message(
    message: str | WingAgentRequest | WingAgentState,
    request: WingAgentRequest | None,
) -> str | None:
    if isinstance(message, WingAgentRequest):
        return message.additional_prompt

    if isinstance(message, dict):
        return message.get("additional_prompt")

    return request.additional_prompt if request else None


def _optional_string(
    message: str | WingAgentRequest | WingAgentState,
    request: WingAgentRequest | None,
    field_name: str,
) -> str:
    if isinstance(message, dict):
        value = message.get(field_name)
        return value if isinstance(value, str) else ""

    value = getattr(request, field_name, "") if request else ""
    return value if isinstance(value, str) else ""


def _resolve_system_prompt(
    configuration: WingAgentConfiguration,
    profile_instructions: str,
    additional_prompt: str | None,
) -> str:
    prompt_parts = [
        get_system_prompt(configuration).strip(),
        profile_instructions.strip(),
    ]

    if additional_prompt:
        prompt_parts.append(additional_prompt.strip())

    return "\n\n".join(part for part in prompt_parts if part)


def _last_human_content(messages: Sequence[BaseMessage]) -> str:
    for message in reversed(messages):
        if getattr(message, "type", None) == "human":
            content = message.content
            return content if isinstance(content, str) else str(content)

    return ""


async def _run_manual_call() -> None:
    parser = argparse.ArgumentParser(description="Run a manual Wing agent call.")
    parser.add_argument(
        "message",
        nargs="?",
        default="What was my net cash flow?",
    )
    parser.add_argument(
        "--profile",
        choices=("imports", "insights", "planning"),
        default="insights",
    )
    parser.add_argument("--additional-prompt", default=None)
    args = parser.parse_args()

    agent = WingAgent(settings=get_settings())
    state = await agent.ainvoke(
        WingAgentRequest(
            message=args.message,
            additional_prompt=args.additional_prompt,
            agent_profile=args.profile,
        )
    )

    print(
        json.dumps(
            {
                #"messages": [
                #    _serialize_message(message)
                #    for message in state.get("messages", [])
                #],
                #"profile": agent.last_runtime_context.get("agent_profile"),
                #"resolved_system_prompt": agent.last_runtime_context.get(
                #    "resolved_system_prompt"
                #),
                "current_turn": _serialize_for_json(state.get("current_turn", {})),
                "enabled_tools": agent.last_runtime_context.get("enabled_tools", ()),
                #"metadata": agent.last_runtime_context.get("metadata", {}),
                #"current_turn": state.get("current_turn", {}),
            },
            indent=2,
        )
    )


def main() -> int:
    try:
        asyncio.run(_run_manual_call())
    except KeyboardInterrupt:
        print("Manual Wing agent call interrupted.", file=sys.stderr)
        return 130

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
