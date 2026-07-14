from __future__ import annotations
import logging
from typing import Annotated, Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Request
from langgraph.checkpoint.base import BaseCheckpointSaver

from src.agents.wing.agent import WingAgent
from src.agents.wing.state import CurrentTurn, ResolvedFilters
from src.config import Settings
from src.dependencies import (
    get_app_settings,
    get_wing_checkpointer,
    get_ww_data_client,
)
from src.providers.ww_data_client import WWDataClient
from src.schemas.wing import (
    WingAgentError,
    WingAgentRequest,
    WingAgentResponse,
    WingAgentResult,
)
logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/invoke", response_model=WingAgentResponse)
async def invoke_wing_agent(
    payload: WingAgentRequest,
    request: Request,
    settings: Annotated[Settings, Depends(get_app_settings)],
    ww_data_client: Annotated[WWDataClient | None, Depends(get_ww_data_client)],
    checkpointer: Annotated[
        BaseCheckpointSaver[Any],
        Depends(get_wing_checkpointer),
    ],
) -> WingAgentResponse:
    thread_id = payload.thread_id or uuid4()
    agent = WingAgent(
        settings=settings,
        request=payload,
        ww_data_client=ww_data_client,
        access_token=getattr(request.state, "access_token", None),
        request_id=getattr(request.state, "request_id", None),
        checkpointer=checkpointer,
        thread_id=_checkpoint_thread_id(request, thread_id, payload.agent_profile),
    )

    state = await agent.ainvoke(payload.message)
    current_turn = state.get("current_turn", {})
    response = _response_from_current_turn(current_turn, thread_id)
    logger.info(
        "wing_agent_invoked",
        extra={
            "request_id": getattr(request.state, "request_id", None),
            "turn_id": response.turn_id,
            "result_count": len(response.results),
            "has_error": response.error is not None,
        },
    )
    return response


def _response_from_current_turn(
    current_turn: CurrentTurn,
    thread_id: UUID,
) -> WingAgentResponse:
    turn_id = current_turn.get("turn_id")
    if not isinstance(turn_id, str) or not turn_id:
        turn_id = "unknown"

    error = _public_error(current_turn)
    answer = current_turn.get("final_answer")
    if not isinstance(answer, str) or not answer:
        answer = error.message if error else "I could not complete that request."

    return WingAgentResponse(
        thread_id=thread_id,
        turn_id=turn_id,
        answer=answer,
        results=[
            serialized
            for result in current_turn.get("tool_results", [])
            if (serialized := _serialize_result(result)) is not None
        ],
        applied_filters=_serialize_filters(current_turn.get("filters")),
        error=error,
    )


def _checkpoint_thread_id(
    request: Request,
    thread_id: UUID,
    agent_profile: str,
) -> str:
    user_id = getattr(request.state, "user_uuid", "unauthenticated")
    return f"{user_id}:{agent_profile}:{thread_id}"


def _public_error(current_turn: CurrentTurn) -> WingAgentError | None:
    if current_turn.get("error"):
        return WingAgentError(
            code="agent_error",
            message="I could not complete that request.",
        )

    if current_turn.get("tool_errors"):
        return WingAgentError(
            code="data_unavailable",
            message="The requested financial data could not be retrieved.",
        )

    return None


def _serialize_filters(filters: Any) -> dict[str, Any] | None:
    try:
        return ResolvedFilters.model_validate(filters).model_dump(mode="json")
    except (TypeError, ValueError):
        return None


def _serialize_result(result: Any) -> WingAgentResult | None:
    if not isinstance(result, dict):
        return None

    result_type = result.get("result_type")
    result_id = result.get("result_id")
    data = result.get("data")
    if not isinstance(result_id, str) or result_type not in {
        "spending_by_category",
        "transaction_summary",
        "transaction_list",
        "transactions_by_category",
    }:
        return None

    public_data = _public_result_data(result_type, data)
    if public_data is None:
        return None

    ui = result.get("ui")
    return WingAgentResult(
        id=result_id,
        type=result_type,
        data=public_data,
        ui=ui if isinstance(ui, str) else None,
    )


def _public_result_data(
    result_type: str,
    data: Any,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    if result_type == "spending_by_category" and isinstance(data, dict):
        return {
            "total_spent": data.get("total_spent"),
            "categories": [
                _select_fields(
                    category,
                    "category_slug",
                    "category_name",
                    "total_cents",
                    "transaction_count",
                    "percent_of_total",
                )
                for category in data.get("categories", [])
                if isinstance(category, dict)
            ],
        }

    if result_type == "transaction_summary" and isinstance(data, dict):
        return _select_fields(
            data,
            "income_cents",
            "expense_cents",
            "net_cents",
            "transaction_count",
            "average_monthly_expense_cents",
        )

    if result_type == "transaction_list" and isinstance(data, dict):
        return {
            "transactions": [
                _public_transaction(transaction)
                for transaction in data.get("transactions", [])
                if isinstance(transaction, dict)
            ],
            **_select_fields(
                data,
                "page",
                "page_size",
                "total_count",
                "total_pages",
                "has_more",
            ),
        }

    if result_type == "transactions_by_category" and isinstance(data, list):
        return [
            {
                **_select_fields(category, "category", "total_amount"),
                "transactions": [
                    _select_fields(
                        transaction,
                        "date",
                        "description",
                        "amount",
                        "category",
                        "type",
                    )
                    for transaction in category.get("transactions", [])
                    if isinstance(transaction, dict)
                ],
            }
            for category in data
            if isinstance(category, dict)
        ]

    return None


def _public_transaction(transaction: dict[str, Any]) -> dict[str, Any]:
    public_transaction = _select_fields(
        transaction,
        "id",
        "date",
        "title",
        "description",
        "amount_cents",
        "amount",
        "currency",
        "type",
    )
    for field_name in ("category", "account"):
        value = transaction.get(field_name)
        if isinstance(value, dict):
            public_transaction[field_name] = _select_fields(value, "id", "name")
    return public_transaction


def _select_fields(value: dict[str, Any], *field_names: str) -> dict[str, Any]:
    return {
        field_name: value[field_name]
        for field_name in field_names
        if field_name in value
    }
