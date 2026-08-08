from __future__ import annotations

from datetime import date
from uuid import UUID

from langgraph.prebuilt import ToolRuntime
from pydantic import BaseModel, ConfigDict, Field

from src.agents.wing.state import WingGraphState, WingRuntimeContext
from src.providers.ww_data_schemas import (
    CashFlowHistoryRequest,
    TransactionsAllRequest,
)


class GetTransactionsInput(TransactionsAllRequest):
    """Model-visible transaction filters plus graph-injected runtime context."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    runtime: ToolRuntime[WingRuntimeContext, WingGraphState]


class GetCashFlowHistoryInput(CashFlowHistoryRequest):
    """Model-visible cash-flow filters plus graph-injected runtime context."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    runtime: ToolRuntime[WingRuntimeContext, WingGraphState]


class GetSpendingByCategoryInput(BaseModel):
    """Model-visible category filters plus graph-injected runtime context."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    from_date: date = Field(
        description="Inclusive start date for the spending range (YYYY-MM-DD).",
    )
    to_date: date = Field(
        description="Inclusive end date for the spending range (YYYY-MM-DD).",
    )
    category_ids: list[UUID] | None = Field(
        default=None,
        description=(
            "Category UUIDs explicitly provided or resolved from trusted data; "
            "never infer UUIDs from category names."
        ),
    )
    category_names: list[str] | None = Field(
        default=None,
        description="Category names explicitly requested by the user.",
    )
    runtime: ToolRuntime[WingRuntimeContext, WingGraphState]
