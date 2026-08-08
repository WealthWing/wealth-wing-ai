from __future__ import annotations

from datetime import date
from uuid import UUID

from langgraph.prebuilt import ToolRuntime
from pydantic import BaseModel, ConfigDict, Field

from src.agents.wing.state import WingGraphState, WingRuntimeContext
from src.providers.ww_data_schemas import (
    AccountTypeEnum,
    CashFlowHistoryRequest,
    TransactionsAllRequest,
    TransactionsQueryParams,
)


class GetTransactionsInput(TransactionsQueryParams, TransactionsAllRequest):
    """All model-visible transaction filters plus injected runtime context."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    runtime: ToolRuntime[WingRuntimeContext, WingGraphState]


class GetTransactionsSummaryInput(BaseModel):
    """Model-visible transaction-summary filters plus injected runtime context."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    from_date: date | None = Field(
        default=None,
        description=(
            "Inclusive start date for an explicitly requested summary period. "
            "Resolve relative or yearless periods from the authoritative current "
            "date in the system prompt; a quarter without a year belongs to the "
            "current calendar year. Omit both dates to summarize the last "
            "completed month."
        ),
    )
    to_date: date | None = Field(
        default=None,
        description=(
            "Inclusive end date for an explicitly requested summary period. "
            "Resolve relative or yearless periods from the authoritative current "
            "date in the system prompt; a quarter without a year belongs to the "
            "current calendar year. Omit both dates to summarize the last "
            "completed month."
        ),
    )
    account_types: list[AccountTypeEnum] | None = Field(
        default=None,
        min_length=1,
        description=(
            "Account types explicitly requested by the user. Omit to use checking "
            "and credit-card accounts."
        ),
    )
    runtime: ToolRuntime[WingRuntimeContext, WingGraphState]


class GetCashFlowHistoryInput(CashFlowHistoryRequest):
    """Model-visible cash-flow filters plus graph-injected runtime context."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    runtime: ToolRuntime[WingRuntimeContext, WingGraphState]


class GetSpendingByCategoryInput(BaseModel):
    """Model-visible category filters plus graph-injected runtime context."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    from_date: date = Field(
        description=(
            "Inclusive start date for the spending range (YYYY-MM-DD). Resolve "
            "relative or yearless periods from the authoritative current date in "
            "the system prompt; a quarter without a year belongs to the current "
            "calendar year."
        ),
    )
    to_date: date = Field(
        description=(
            "Inclusive end date for the spending range (YYYY-MM-DD). Resolve "
            "relative or yearless periods from the authoritative current date in "
            "the system prompt; a quarter without a year belongs to the current "
            "calendar year."
        ),
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
