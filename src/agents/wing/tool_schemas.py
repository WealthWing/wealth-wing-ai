from __future__ import annotations

from langgraph.prebuilt import ToolRuntime
from pydantic import ConfigDict

from src.agents.wing.state import WingGraphState, WingRuntimeContext
from src.providers.ww_data_schemas import TransactionsAllRequest


class GetTransactionsInput(TransactionsAllRequest):
    """Model-visible transaction filters plus graph-injected runtime context."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    runtime: ToolRuntime[WingRuntimeContext, WingGraphState]
