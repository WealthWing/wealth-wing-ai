from __future__ import annotations

from dataclasses import dataclass

from src.agents.wing.configuration import WingAgentConfiguration
from src.agents.wing.prompts import get_system_prompt
from src.agents.wing.state import WingAgentState
from src.agents.wing.tools import get_tools
from src.config import Settings


@dataclass(frozen=True)
class WingAgentNodes:
    settings: Settings
    configuration: WingAgentConfiguration

    def prepare_context(self, state: WingAgentState) -> WingAgentState:
        tools = get_tools(self.configuration)

        return {
            "resolved_system_prompt": get_system_prompt(self.configuration),
            "enabled_tools": tuple(tool.name for tool in tools),
            "metadata": dict(self.configuration.metadata),
        }
