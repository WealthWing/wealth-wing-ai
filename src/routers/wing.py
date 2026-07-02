from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from langchain_core.messages import AIMessage, BaseMessage

from src.agents.wing.agent import WingAgent
from src.config import get_settings
from src.schemas.wing import WingAgentMessage, WingAgentRequest, WingAgentResponse

router = APIRouter()


@router.post("/invoke", response_model=WingAgentResponse)
async def invoke_wing_agent(
    payload: WingAgentRequest,
    request: Request,
) -> WingAgentResponse:
    settings = getattr(request.app.state, "settings", None) or get_settings()
    agent = WingAgent(settings=settings, request=payload)

    state = await agent.ainvoke(payload.message)
    runtime_context = agent.last_runtime_context

    return WingAgentResponse(
        messages=[
            _serialize_message(message)
            for message in _response_messages(state.get("messages", []))
        ],
        additional_prompt=runtime_context.get("additional_prompt"),
        agent_profile=runtime_context.get("agent_profile"),
        resolved_system_prompt=runtime_context.get("resolved_system_prompt", ""),
        enabled_tools=runtime_context.get("enabled_tools", ()),
        metadata=runtime_context.get("metadata", {}),
    )


def _serialize_message(message: BaseMessage) -> WingAgentMessage:
    content = message.content
    serialized_content = content if isinstance(content, str) else str(content)

    return WingAgentMessage(
        role=_message_role(message),
        content=_clean_assistant_content(message, serialized_content),
    )


def _response_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    return [
        message
        for message in messages
        if getattr(message, "type", "unknown") in {"human", "ai"}
        and not _is_tool_call_message(message)
    ]


def _message_role(message: BaseMessage) -> Any:
    role = getattr(message, "type", "unknown")
    return role if role in {"ai", "human", "system", "tool"} else "unknown"


def _is_tool_call_message(message: BaseMessage) -> bool:
    return isinstance(message, AIMessage) and bool(message.tool_calls)


def _clean_assistant_content(message: BaseMessage, content: str) -> str:
    if isinstance(message, AIMessage) and content.startswith("final"):
        return content.removeprefix("final").lstrip()

    return content
