from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from langchain_core.messages import BaseMessage, HumanMessage

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
    agent = WingAgent(settings=settings)

    state = await agent.ainvoke(
        {
            "messages": [HumanMessage(content=payload.message)],
            "additional_prompt": payload.additional_prompt,
        }
    )

    return WingAgentResponse(
        messages=[_serialize_message(message) for message in state.get("messages", [])],
        additional_prompt=state.get("additional_prompt"),
        resolved_system_prompt=state.get("resolved_system_prompt", ""),
        enabled_tools=state.get("enabled_tools", ()),
        metadata=state.get("metadata", {}),
    )


def _serialize_message(message: BaseMessage) -> WingAgentMessage:
    content = message.content

    return WingAgentMessage(
        role=_message_role(message),
        content=content if isinstance(content, str) else str(content),
    )


def _message_role(message: BaseMessage) -> Any:
    role = getattr(message, "type", "unknown")
    return role if role in {"ai", "human", "system", "tool"} else "unknown"
